"""Real row-lock waits must recheck evidence assignments after another writer commits."""

import asyncio
import os
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.program import create_evidence_validation, update_evidence_item
from app.models import Jurisdiction, Organization, User
from app.models.audit import AuditLog
from app.models.program import EvidenceItem, EvidenceValidation
from app.models.requirement import Requirement
from app.schemas.program import EvidenceItemUpdate, EvidenceValidationCreate
from app.services.access_audit import audit_access_clause


@pytest.mark.skipif(
    not os.getenv("CAP_TEST_POSTGRES_URL"),
    reason="Disposable evidence PostgreSQL required",
)
@pytest.mark.parametrize("operation", ["edit", "approve", "validate"])
async def test_waiting_evidence_write_rechecks_revoked_participant_assignment(operation):
    url = make_url(os.environ["CAP_TEST_POSTGRES_URL"])
    assert url.host == "127.0.0.1" and (url.port, url.database) == (25489, "cap_e2e")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    pending = None
    fixture_org_id = None
    fixture_jurisdiction_id = None
    try:
        async with sessions() as db:
            key = uuid.uuid4().hex[:10]
            org = Organization(code=key, name="Disposable evidence test")
            jurisdiction = Jurisdiction(code=key, name="Disposable jurisdiction")
            db.add_all([org, jurisdiction])
            await db.flush()
            creator, editor = [
                User(
                    email=f"{key}-{role}@example.test",
                    full_name=role,
                    password_hash="unused",
                    role=role,
                    organization_id=org.id,
                    active=True,
                )
                for role in ("manager", "contributor" if operation == "edit" else "approver")
            ]
            db.add_all([creator, editor])
            await db.flush()
            requirement = Requirement(
                organization_id=org.id,
                jurisdiction_id=jurisdiction.id,
                reference_id=key,
                text="Keep proof",
                requirement_type="mandatory",
                sort_order=1,
            )
            db.add(requirement)
            await db.flush()
            item = EvidenceItem(
                organization_id=org.id,
                requirement_id=requirement.id,
                evidence_type="note",
                title="Secret proof",
                body="Original",
                created_by=creator.id,
                owner_id=editor.id if operation == "edit" else creator.id,
                reviewer_id=editor.id if operation != "edit" else None,
                review_status="approved",
                approved_by=creator.id,
            )
            db.add(item)
            await db.flush()
            db.add(
                AuditLog(
                    organization_id=org.id,
                    user_id=creator.id,
                    user_name=creator.full_name,
                    action="create",
                    entity_type="evidence_item",
                    entity_id=str(item.id),
                )
            )
            await db.commit()
            fixture_org_id, fixture_jurisdiction_id = org.id, jurisdiction.id
            assert list(
                (
                    await db.scalars(
                        select(AuditLog.id).where(
                            AuditLog.entity_id == str(item.id), audit_access_clause(editor)
                        )
                    )
                ).all()
            )
        started = asyncio.Event()
        backend_pid = None

        async def waiting_editor():
            nonlocal backend_pid
            async with sessions() as db:
                backend_pid = await db.scalar(text("select pg_backend_pid()"))
                started.set()
                try:
                    if operation == "validate":
                        await create_evidence_validation(
                            EvidenceValidationCreate(
                                evidence_item_id=item.id,
                                validation_status="pass",
                                comment="Unauthorised validation",
                            ),
                            db,
                            editor,
                        )
                    else:
                        changes = (
                            {"body": "Unauthorised replacement"}
                            if operation == "edit"
                            else {"review_status": "rejected"}
                        )
                        await update_evidence_item(
                            item.id, EvidenceItemUpdate(**changes), db, editor
                        )
                    return "written"
                except HTTPException as error:
                    await db.rollback()
                    return error.status_code

        async with sessions() as revoking:
            await revoking.scalar(
                select(EvidenceItem.id).where(EvidenceItem.id == item.id).with_for_update()
            )
            await revoking.execute(
                update(EvidenceItem)
                .where(EvidenceItem.id == item.id)
                .values(**{"owner_id" if operation == "edit" else "reviewer_id": creator.id})
            )
            pending = asyncio.create_task(waiting_editor())
            await asyncio.wait_for(started.wait(), 5)
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
                    pytest.fail("Evidence write did not wait on the reassignment transaction")
            assert not pending.done()
            await revoking.commit()
        assert await asyncio.wait_for(pending, 10) == 404
        async with sessions() as db:
            stored = await db.get(EvidenceItem, item.id)
            assert stored.body == "Original" and stored.review_status == "approved"
            assert stored.owner_id == creator.id and stored.approved_by == creator.id
            assert not list(
                await db.scalars(
                    select(EvidenceValidation.id).where(
                        EvidenceValidation.evidence_item_id == item.id
                    )
                )
            )
            assert not list(
                (
                    await db.scalars(
                        select(AuditLog.id).where(
                            AuditLog.entity_id == str(item.id), audit_access_clause(editor)
                        )
                    )
                ).all()
            )
    finally:
        if pending and not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        try:
            async with sessions() as db:
                if fixture_org_id:
                    evidence_ids = select(EvidenceItem.id).where(
                        EvidenceItem.organization_id == fixture_org_id
                    )
                    await db.execute(
                        delete(EvidenceValidation).where(
                            EvidenceValidation.evidence_item_id.in_(evidence_ids)
                        )
                    )
                    await db.execute(
                        delete(AuditLog).where(AuditLog.organization_id == fixture_org_id)
                    )
                    await db.execute(
                        delete(EvidenceItem).where(EvidenceItem.organization_id == fixture_org_id)
                    )
                    await db.execute(
                        delete(Requirement).where(Requirement.organization_id == fixture_org_id)
                    )
                    await db.execute(delete(User).where(User.organization_id == fixture_org_id))
                    await db.execute(delete(Organization).where(Organization.id == fixture_org_id))
                    await db.execute(
                        delete(Jurisdiction).where(Jurisdiction.id == fixture_jurisdiction_id)
                    )
                    await db.commit()
        finally:
            await engine.dispose()
