"""A concurrent preparation edit cannot slip through application approval.

Requires the explicitly selected disposable PostgreSQL database, migrated to head.
SQLite API tests intentionally make no claim about this lock ordering contract.
"""

import asyncio
import json
import os
import uuid
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Jurisdiction, Organization, User
from app.models.application import Application, ApplicationComponent, ApplicationSnapshot
from app.models.preparation import PreparationCase, PreparationResponse, PreparationTemplate
from app.schemas.application import WorkflowAction
from app.services.applications import transition
from app.services.preparation import field_for, save_response


@pytest.mark.skipif(not os.getenv("CAP_TEST_POSTGRES_URL"), reason="Isolated PostgreSQL required")
async def test_approval_waits_for_form_edit_and_rejects_unreviewed_content():
    url = make_url(os.environ["CAP_TEST_POSTGRES_URL"])
    assert url.host == "127.0.0.1" and (url.port, url.database) == (25489, "cap_e2e")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    fixtures = []
    pending = None
    try:
        async with sessions() as db:
            key = uuid.uuid4().hex[:10]
            org = Organization(code=key, name="Disposable application lock test")
            jurisdiction = Jurisdiction(code=key, name="Disposable jurisdiction")
            db.add_all([org, jurisdiction])
            await db.flush()
            user = User(
                email=f"{key}@example.test",
                full_name="Fixture",
                role="admin",
                password_hash="unused",
                organization_id=org.id,
            )
            db.add(user)
            await db.flush()
            fields = json.dumps([{"key": "answer", "label": "Answer", "type": "text"}])
            template = PreparationTemplate(
                organization_id=org.id,
                name="Annex",
                kind="questionnaire",
                fields_json=fields,
                created_by=user.id,
            )
            db.add(template)
            await db.flush()
            case = PreparationCase(
                organization_id=org.id,
                template_id=template.id,
                template_name=template.name,
                template_revision=1,
                fields_json=fields,
                kind="questionnaire",
                jurisdiction_id=jurisdiction.id,
                name="Annex A",
                created_by=user.id,
            )
            application = Application(
                organization_id=org.id,
                jurisdiction_id=jurisdiction.id,
                name="Annex pack",
                scope="annex_only",
                created_by=user.id,
            )
            db.add_all([case, application])
            await db.flush()
            response = PreparationResponse(
                case_id=case.id,
                field_key="answer",
                value_json='"Reviewed"',
                accepted_by=user.id,
                accepted_at=datetime.now(UTC),
            )
            component = ApplicationComponent(
                application_id=application.id, name="Annex A", kind="annex", case_id=case.id
            )
            db.add_all([response, component])
            await db.flush()
            await transition(
                db, application, "request-review", WorkflowAction(expected_revision=1), user
            )
            fixtures = [
                (ApplicationComponent, component.id),
                (Application, application.id),
                (PreparationResponse, response.id),
                (PreparationCase, case.id),
                (PreparationTemplate, template.id),
                (User, user.id),
                (Jurisdiction, jurisdiction.id),
                (Organization, org.id),
            ]
            await db.commit()
        started = asyncio.Event()
        backend_pid = None

        async def approve():
            nonlocal backend_pid
            async with sessions() as db:
                current = await db.get(Application, application.id)
                backend_pid = await db.scalar(text("select pg_backend_pid()"))
                started.set()
                try:
                    await transition(
                        db, current, "approve", WorkflowAction(expected_revision=2), user
                    )
                    await db.commit()
                    return "approved"
                except HTTPException as error:
                    await db.rollback()
                    return error.status_code

        async with sessions() as editing:
            current = await editing.get(PreparationCase, case.id)
            await save_response(
                editing,
                current,
                field_for(current, "answer"),
                1,
                value="Unreviewed concurrent edit",
                reason=None,
                evidence=[],
            )
            pending = asyncio.create_task(approve())
            await asyncio.wait_for(started.wait(), 5)
            # Observe an actual PostgreSQL lock wait, rather than assuming task timing.
            async with sessions() as observer:
                for _ in range(100):
                    waiting = await observer.scalar(
                        text("select wait_event_type from pg_stat_activity where pid = :pid"),
                        {"pid": backend_pid},
                    )
                    if waiting == "Lock":
                        break
                    await observer.commit()
                    await asyncio.sleep(0.05)
                else:
                    pytest.fail("Approval did not wait for the form transaction")
            assert not pending.done()
            await editing.commit()
        assert await asyncio.wait_for(pending, 10) == 422
        async with sessions() as db:
            stored = await db.get(Application, application.id)
            assert stored.status == "in_review" and stored.revision == 2
            assert (
                await db.scalars(
                    select(ApplicationSnapshot).where(
                        ApplicationSnapshot.application_id == stored.id
                    )
                )
            ).all() == []
    finally:
        if pending and not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        try:
            async with sessions() as db:
                if fixtures:
                    await db.execute(
                        delete(ApplicationSnapshot).where(
                            ApplicationSnapshot.application_id == application.id
                        )
                    )
                for model, key in fixtures:
                    await db.execute(delete(model).where(model.id == key))
                await db.commit()
        finally:
            await engine.dispose()
