"""Optional PostgreSQL check; run only against the dedicated disposable database."""

import asyncio
import os
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.reviews import _get_review_cycle_for_user
from app.models import Jurisdiction, ReviewCycle, User
from app.models.organization import Organization


@pytest.mark.skipif(not os.getenv("CAP_TEST_POSTGRES_URL"), reason="Isolated PostgreSQL required")
async def test_waiting_writer_rechecks_closed_review_after_lock():
    url = make_url(os.environ["CAP_TEST_POSTGRES_URL"])
    assert url.host == "127.0.0.1" and (url.port, url.database) == (25489, "cap_e2e")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    waiting = None
    try:
        async with sessions() as setup:
            suffix = uuid.uuid4().hex[:10]
            org = Organization(code=suffix, name="Disposable concurrency fixture")
            jurisdiction = Jurisdiction(code=suffix, name="Test", regulator_name="Test")
            setup.add_all([org, jurisdiction])
            await setup.flush()
            owner = User(
                email=f"{suffix}@example.test",
                full_name="Test",
                role="admin",
                password_hash="not-a-login",
                organization_id=org.id,
            )
            setup.add(owner)
            await setup.flush()
            cycle = ReviewCycle(
                name="Disposable lock test",
                organization_id=org.id,
                jurisdiction_id=jurisdiction.id,
                created_by=owner.id,
            )
            setup.add(cycle)
            await setup.commit()

        async with sessions() as closer, sessions() as writer, sessions() as observer:
            # Deliberately retain the old active object in the writer's identity map.
            stale = await writer.get(ReviewCycle, cycle.id)
            assert stale.status == "active"
            locked = await _get_review_cycle_for_user(closer, owner, cycle.id, writable=True)
            writer_pid = await writer.scalar(text("select pg_backend_pid()"))
            waiting = asyncio.create_task(
                _get_review_cycle_for_user(writer, owner, cycle.id, writable=True)
            )
            try:
                deadline = asyncio.get_running_loop().time() + 10
                while True:
                    state = await observer.scalar(
                        text("select wait_event_type from pg_stat_activity where pid = :pid"),
                        {"pid": writer_pid},
                    )
                    await observer.rollback()  # Refresh PostgreSQL's activity snapshot.
                    if state == "Lock":
                        break
                    assert not waiting.done(), "Writer bypassed the review lock"
                    assert (
                        asyncio.get_running_loop().time() < deadline
                    ), "Writer never took the lock"
                    await asyncio.sleep(0.02)
                locked.status = "closed"
                await closer.commit()
                with pytest.raises(HTTPException) as rejected:
                    await asyncio.wait_for(waiting, 10)
                assert rejected.value.status_code == 409
                assert stale.status == "closed"
                await writer.rollback()
                assert (await observer.get(ReviewCycle, cycle.id)).status == "closed"
            finally:
                # Finish the task before closing its connection, including on assertion failure.
                if not waiting.done():
                    waiting.cancel()
                    await asyncio.gather(waiting, return_exceptions=True)
    finally:
        if waiting and not waiting.done():
            waiting.cancel()
            await asyncio.gather(waiting, return_exceptions=True)
        await engine.dispose()


@pytest.mark.skipif(not os.getenv("CAP_TEST_POSTGRES_URL"), reason="Isolated PostgreSQL required")
async def test_concurrent_audit_writers_keep_one_hash_chain():
    from sqlalchemy import select
    from app.models.audit import AuditLog
    from app.services.audit import log_action
    url = make_url(os.environ["CAP_TEST_POSTGRES_URL"])
    assert url.host == "127.0.0.1" and (url.port, url.database) == (25489, "cap_e2e")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as db:
            org = Organization(code=uuid.uuid4().hex[:10], name="Audit concurrency fixture")
            db.add(org)
            await db.flush()
            user = User(email=f"{uuid.uuid4()}@example.test", full_name="Audit fixture", role="admin", password_hash="not-a-login", organization_id=org.id)
            db.add(user)
            await db.commit()
        async def append(index):
            async with sessions() as db:
                await log_action(db, user, "test", "audit_fixture", str(index))
                await db.commit()
        await asyncio.gather(*(append(i) for i in range(8)))
        async with sessions() as db:
            rows = (await db.execute(select(AuditLog).where(AuditLog.organization_id == org.id).order_by(AuditLog.timestamp, AuditLog.id))).scalars().all()
            assert len(rows) == 8
            assert rows[0].prev_hash is None
            assert all(current.prev_hash == previous.event_hash for previous, current in zip(rows, rows[1:]))
    finally:
        await engine.dispose()


@pytest.mark.skipif(not os.getenv("CAP_TEST_POSTGRES_URL"), reason="Isolated PostgreSQL required")
@pytest.mark.parametrize("kind", ["package", "change"])
async def test_handover_writers_refresh_status_after_waiting_for_lock(kind):
    from app.api.program import _get_submission_package_for_user
    from app.api.change_management import _get_change_entry_for_user
    from app.models.program import CertificationProject, SubmissionPackage
    from app.models.change_management import ComponentRegister, ChangeEntry
    url = make_url(os.environ["CAP_TEST_POSTGRES_URL"])
    assert url.host == "127.0.0.1" and (url.port, url.database) == (25489, "cap_e2e")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    pending = None
    try:
        async with sessions() as db:
            key = uuid.uuid4().hex[:10]
            org = Organization(code=key, name="Disposable handover lock test")
            jurisdiction = Jurisdiction(code=key, name="Lock fixture", regulator_name="Test")
            db.add_all([org, jurisdiction]); await db.flush()
            owner = User(email=f"{key}@example.test", full_name="Fixture", role="admin", password_hash="not-a-login", organization_id=org.id)
            db.add(owner); await db.flush()
            if kind == "package":
                parent = CertificationProject(name="Lock fixture", organization_id=org.id, jurisdiction_id=jurisdiction.id, created_by=owner.id)
                db.add(parent); await db.flush()
                item = SubmissionPackage(project_id=parent.id, version="v1", status="draft", created_by=owner.id)
            else:
                parent = ComponentRegister(name="Lock fixture", organization_id=org.id, jurisdiction_id=jurisdiction.id, created_by=owner.id)
                db.add(parent); await db.flush()
                item = ChangeEntry(register_id=parent.id, title="Lock fixture", status="draft", proposed_by=owner.id)
            db.add(item); await db.commit()
        async def load(session):
            if kind == "package":
                return await _get_submission_package_for_user(session, owner, item.id, lock=True)
            return (await _get_change_entry_for_user(session, owner, item.id, lock=True))[0]
        async with sessions() as first, sessions() as second, sessions() as observer:
            stale = await second.get(type(item), item.id)
            locked = await load(first)
            pid = await second.scalar(text("select pg_backend_pid()"))
            pending = asyncio.create_task(load(second))
            deadline = asyncio.get_running_loop().time() + 10
            while True:
                state = await observer.scalar(text("select wait_event_type from pg_stat_activity where pid = :pid"), {"pid": pid})
                await observer.rollback()
                if state == "Lock":
                    break
                assert not pending.done(), "Concurrent writer bypassed the lock"
                assert asyncio.get_running_loop().time() < deadline
                await asyncio.sleep(0.02)
            final_status = "locked" if kind == "package" else "verified"
            locked.status = final_status
            await first.commit()
            refreshed = await asyncio.wait_for(pending, 10)
            assert refreshed.status == stale.status == final_status
            await second.rollback()
    finally:
        if pending and not pending.done():
            pending.cancel(); await asyncio.gather(pending, return_exceptions=True)
        await engine.dispose()


@pytest.mark.skipif(not os.getenv("CAP_TEST_POSTGRES_URL"), reason="Isolated PostgreSQL required")
async def test_concurrent_project_baseline_updates_reject_stale_expected_versions():
    from sqlalchemy import delete, select

    from app.api.program import update_project_baseline
    from app.models.audit import AuditLog
    from app.models.document import Document
    from app.models.program import (
        CertificationProject,
        CertificationProjectRequirementBaseline,
        RequirementSetVersion,
    )
    from app.schemas.program import CertificationProjectBaselineUpdateRequest
    from app.services.access import require_access

    url = make_url(os.environ["CAP_TEST_POSTGRES_URL"])
    assert url.host == "127.0.0.1" and (url.port, url.database) == (25489, "cap_e2e")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    cleanup = []
    pending = None
    try:
        async with sessions() as db:
            key = uuid.uuid4().hex[:10]
            org = Organization(code=key, name="Disposable baseline concurrency fixture")
            jurisdiction = Jurisdiction(code=key, name="Baseline lock fixture")
            db.add_all([org, jurisdiction])
            await db.flush()
            owner = User(
                email=f"{key}@example.test", full_name="Baseline fixture", role="admin",
                password_hash="not-a-login", organization_id=org.id,
            )
            db.add(owner)
            await db.flush()
            document = Document(
                organization_id=org.id, jurisdiction_id=jurisdiction.id,
                name="Versioned requirements", document_type="scp", status="approved",
                uploaded_by=owner.id,
            )
            db.add(document)
            await db.flush()
            old_version, new_version = [
                RequirementSetVersion(
                    organization_id=org.id, document_id=document.id, version_number=number,
                    status="approved", is_current=number == 2, created_by=owner.id,
                )
                for number in (1, 2)
            ]
            project = CertificationProject(
                organization_id=org.id, jurisdiction_id=jurisdiction.id,
                source_document_id=document.id, name="Concurrent baseline", created_by=owner.id,
            )
            db.add_all([old_version, new_version, project])
            await db.flush()
            db.add(CertificationProjectRequirementBaseline(
                project_id=project.id, document_id=document.id,
                requirement_set_version_id=old_version.id,
            ))
            cleanup = [
                delete(AuditLog).where(AuditLog.organization_id == org.id),
                delete(CertificationProjectRequirementBaseline).where(
                    CertificationProjectRequirementBaseline.project_id == project.id
                ),
                delete(CertificationProject).where(CertificationProject.id == project.id),
                delete(RequirementSetVersion).where(RequirementSetVersion.document_id == document.id),
                delete(Document).where(Document.id == document.id),
                delete(User).where(User.id == owner.id),
                delete(Jurisdiction).where(Jurisdiction.id == jurisdiction.id),
                delete(Organization).where(Organization.id == org.id),
            ]
            await db.commit()

        body = CertificationProjectBaselineUpdateRequest(
            requirement_set_ids=[document.id],
            target_version_ids={document.id: new_version.id},
            expected_baseline_version_ids={document.id: old_version.id},
        )
        async with sessions() as first, sessions() as second, sessions() as observer:
            # Hold the same lock the endpoint takes, so the second request overlaps
            # the first transaction rather than merely arriving after its commit.
            await require_access(first, CertificationProject, project.id, owner, "edit")
            second_pid = await second.scalar(text("select pg_backend_pid()"))
            pending = asyncio.create_task(update_project_baseline(
                project.id, body, db=second, current_user=owner,
            ))
            try:
                deadline = asyncio.get_running_loop().time() + 10
                while True:
                    state = await observer.scalar(
                        text("select wait_event_type from pg_stat_activity where pid = :pid"),
                        {"pid": second_pid},
                    )
                    await observer.rollback()  # Refresh PostgreSQL's activity snapshot.
                    if state == "Lock":
                        break
                    assert not pending.done(), "Baseline writer bypassed the project lock"
                    assert asyncio.get_running_loop().time() < deadline, "Writer never waited"
                    await asyncio.sleep(0.02)

                saved = await asyncio.wait_for(update_project_baseline(
                    project.id, body, db=first, current_user=owner,
                ), 10)
                assert saved.project.baseline_versions[0].requirement_set_version_id == new_version.id
                with pytest.raises(HTTPException) as rejected:
                    await asyncio.wait_for(pending, 10)
                assert rejected.value.status_code == 409
                assert "project baseline changed" in rejected.value.detail
                await second.rollback()

                stored = (await observer.scalars(
                    select(CertificationProjectRequirementBaseline).where(
                        CertificationProjectRequirementBaseline.project_id == project.id
                    )
                )).all()
                assert len(stored) == 1
                assert stored[0].requirement_set_version_id == new_version.id
                events = (await observer.scalars(select(AuditLog).where(
                    AuditLog.organization_id == org.id,
                    AuditLog.entity_type == "certification_project_baseline",
                ))).all()
                assert len(events) == 1, "Rejected baseline update must not emit an audit event"
            finally:
                if not pending.done():
                    pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
    finally:
        try:
            async with sessions() as db:
                for statement in cleanup:
                    await db.execute(statement)
                await db.commit()
        finally:
            await engine.dispose()
