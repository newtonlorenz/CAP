"""Exercise revision fencing against the dedicated disposable PostgreSQL target."""

import asyncio
import json
import os
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Jurisdiction, Organization, User
from app.models.preparation import PreparationCase, PreparationResponse, PreparationTemplate
from app.services.preparation import field_for, save_response


@pytest.mark.skipif(not os.getenv("CAP_TEST_POSTGRES_URL"), reason="Isolated PostgreSQL required")
async def test_only_one_concurrent_case_edit_commits():
    url = make_url(os.environ["CAP_TEST_POSTGRES_URL"])
    assert url.host == "127.0.0.1" and (url.port, url.database) == (25489, "cap_e2e")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    fixtures = []
    try:
        async with sessions() as db:
            key = uuid.uuid4().hex[:10]
            org = Organization(code=key, name="Preparation concurrency fixture")
            jurisdiction = Jurisdiction(code=key, name="Disposable jurisdiction")
            db.add_all([org, jurisdiction])
            await db.flush()
            user = User(
                email=f"{key}@example.test",
                full_name="Fixture",
                role="admin",
                password_hash="not-a-login",
                organization_id=org.id,
            )
            db.add(user)
            await db.flush()
            fields = json.dumps([{"key": "name", "label": "Name", "type": "text"}])
            template = PreparationTemplate(
                organization_id=org.id,
                name="Concurrent form",
                kind="questionnaire",
                fields_json=fields,
                created_by=user.id,
            )
            db.add(template)
            await db.flush()
            case = PreparationCase(
                organization_id=org.id,
                name="Concurrent case",
                kind="questionnaire",
                fields_json=fields,
                template_id=template.id,
                template_name=template.name,
                template_revision=1,
                jurisdiction_id=jurisdiction.id,
                created_by=user.id,
            )
            db.add(case)
            await db.flush()
            fixtures = [
                (PreparationCase, case.id),
                (PreparationTemplate, template.id),
                (User, user.id),
                (Jurisdiction, jurisdiction.id),
                (Organization, org.id),
            ]
            await db.commit()
        ready = asyncio.Event()
        loaded = 0

        async def edit(value):
            nonlocal loaded
            async with sessions() as db:
                current = await db.get(PreparationCase, case.id)
                assert current.revision == 1
                loaded += 1
                if loaded == 2:
                    ready.set()
                await asyncio.wait_for(ready.wait(), 10)
                try:
                    await save_response(
                        db,
                        current,
                        field_for(current, "name"),
                        1,
                        value=value,
                        reason=None,
                        evidence=[],
                    )
                    await db.commit()
                    return "saved"
                except HTTPException as error:
                    await db.rollback()
                    assert error.status_code == 409
                    return "conflict"

        results = await asyncio.wait_for(
            asyncio.gather(edit("First draft"), edit("Second draft")), 15
        )
        assert sorted(results) == ["conflict", "saved"]
        async with sessions() as db:
            stored = await db.get(PreparationCase, case.id)
            assert stored.revision == 2
            responses = list(
                (
                    await db.scalars(
                        select(PreparationResponse).where(PreparationResponse.case_id == case.id)
                    )
                ).all()
            )
            assert len(responses) == 1
            assert json.loads(responses[0].value_json) in {"First draft", "Second draft"}
            assert responses[0].accepted_at is None
    finally:
        try:
            # Do not change the default jurisdiction or counts in later browser tests.
            async with sessions() as db:
                for model, item_id in fixtures:
                    await db.execute(delete(model).where(model.id == item_id))
                await db.commit()
        finally:
            await engine.dispose()
