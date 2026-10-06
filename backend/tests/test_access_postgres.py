"""PostgreSQL owns the grant-revocation/row-lock contract; SQLite cannot prove it."""

import asyncio
import os
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Jurisdiction, Organization, User
from app.models.access import AccessGrant, ResourceAccess
from app.models.application import Application
from app.services.access import (
    effective_permissions,
    initialize_access,
    protect_child,
    require_access,
)


@pytest.mark.skipif(not os.getenv("CAP_TEST_POSTGRES_URL"), reason="Isolated PostgreSQL required")
async def test_waiting_content_write_rechecks_revoked_grant_after_lock_acquisition():
    url = make_url(os.environ["CAP_TEST_POSTGRES_URL"])
    assert url.host == "127.0.0.1" and (url.port, url.database) == (25489, "cap_e2e")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    fixture_org_id = None
    fixture_jurisdiction_id = None
    pending = None
    try:
        async with sessions() as db:
            key = uuid.uuid4().hex[:10]
            org = Organization(code=key, name="Disposable access test")
            jurisdiction = Jurisdiction(code=key, name="Disposable jurisdiction")
            db.add_all([org, jurisdiction])
            await db.flush()
            owner, editor, admin = [
                User(
                    email=f"{key}-{role}@example.test",
                    full_name=role,
                    password_hash="unused",
                    role=role,
                    organization_id=org.id,
                    active=True,
                )
                for role in ("manager", "contributor", "admin")
            ]
            db.add_all([owner, editor, admin])
            await db.flush()
            parent, child = [
                Application(
                    name=name,
                    scope="licence",
                    jurisdiction_id=jurisdiction.id,
                    organization_id=org.id,
                    created_by=owner.id,
                )
                for name in ("Secret", "Inherited")
            ]
            db.add_all([parent, child])
            await db.flush()
            policy = await initialize_access(db, "application", parent.id, owner)
            await initialize_access(db, "application", child.id, owner, "organisation")
            await protect_child(db, "application", parent.id, "application", child.id, owner)
            for permission in ("view", "edit"):
                db.add(
                    AccessGrant(
                        policy_id=policy.id,
                        subject_type="user",
                        subject_id=editor.id,
                        permission=permission,
                    )
                )
            await db.commit()
            fixture_org_id, fixture_jurisdiction_id = org.id, jurisdiction.id
            assert await effective_permissions(db, "application", parent.id, admin) == []
            assert await effective_permissions(db, "application", child.id, admin) == []
            assert set(await effective_permissions(db, "application", child.id, editor)) == {
                "summary",
                "view",
                "edit",
            }
        started = asyncio.Event()
        backend_pid = None

        async def edit_after_wait():
            nonlocal backend_pid
            async with sessions() as db:
                backend_pid = await db.scalar(text("select pg_backend_pid()"))
                started.set()
                try:
                    current = await require_access(db, "application", parent.id, editor, "edit")
                    current.description = "Must not be written after access was revoked"
                    await db.commit()
                    return "written"
                except HTTPException as error:
                    await db.rollback()
                    return error.status_code

        async with sessions() as revoking:
            # Same lock acquired by the real access-management endpoint.
            await require_access(revoking, "application", parent.id, owner, "manage_access")
            await revoking.execute(
                delete(AccessGrant).where(
                    AccessGrant.policy_id == policy.id, AccessGrant.subject_id == editor.id
                )
            )
            pending = asyncio.create_task(edit_after_wait())
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
                    pytest.fail("Content write did not wait on the access-management transaction")
            assert not pending.done()
            await revoking.commit()
        assert await asyncio.wait_for(pending, 10) == 404
        async with sessions() as db:
            stored = await db.get(Application, parent.id)
            assert stored.description is None
            assert await effective_permissions(db, "application", child.id, editor) == []
    finally:
        if pending and not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        try:
            async with sessions() as db:
                if fixture_org_id:
                    policies = select(ResourceAccess.id).where(
                        ResourceAccess.organization_id == fixture_org_id
                    )
                    await db.execute(delete(AccessGrant).where(AccessGrant.policy_id.in_(policies)))
                    # Descendant-first for the self-referencing policy foreign key.
                    await db.execute(
                        delete(ResourceAccess).where(
                            ResourceAccess.organization_id == fixture_org_id,
                            ResourceAccess.parent_id.is_not(None),
                        )
                    )
                    await db.execute(
                        delete(ResourceAccess).where(
                            ResourceAccess.organization_id == fixture_org_id
                        )
                    )
                    await db.execute(
                        delete(Application).where(Application.organization_id == fixture_org_id)
                    )
                    await db.execute(delete(User).where(User.organization_id == fixture_org_id))
                    await db.execute(delete(Organization).where(Organization.id == fixture_org_id))
                    await db.execute(
                        delete(Jurisdiction).where(Jurisdiction.id == fixture_jurisdiction_id)
                    )
                    await db.commit()
        finally:
            await engine.dispose()
