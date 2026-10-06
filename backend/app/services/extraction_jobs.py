"""Durable extraction dispatch and single-worker ownership."""

import asyncio
import logging
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, or_, select, text

from app.config import settings
from app.models.document import Document
from app.models.extraction import ExtractionRun

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 4
DISPATCH_INTERVAL = timedelta(seconds=60)
PUBLISH_FAILURE_INTERVAL = timedelta(seconds=15)
_sqlite_locks: dict[uuid.UUID, threading.Lock] = {}
_sqlite_locks_guard = threading.Lock()


def utcnow() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


async def dispatch_run(db, run_id: uuid.UUID, *, now: datetime | None = None) -> bool:
    """Publish a due run. Repeated or ambiguous publishes are safe at the worker."""
    now = now or utcnow()
    # Lock document first, matching trigger/cancel and worker commit ordering.
    run_doc = await db.scalar(select(ExtractionRun.document_id).where(ExtractionRun.id == run_id))
    if run_doc is None:
        return False
    doc = await db.scalar(
        select(Document).where(Document.id == run_doc).with_for_update()
        .execution_options(populate_existing=True)
    )
    run = await db.scalar(
        select(ExtractionRun).where(ExtractionRun.id == run_id).with_for_update()
        .execution_options(populate_existing=True)
    )
    if doc is None or run is None or doc.current_extraction_id != run.id:
        await db.rollback()
        return False
    if run.status not in {"pending", "running"}:
        await db.rollback()
        return False
    if run.dispatch_after and _as_utc(run.dispatch_after) > now:
        await db.rollback()
        return False
    if run.status == "running":
        last = run.last_progress_at or run.started_at or run.created_at
        if last and now - _as_utc(last) < timedelta(seconds=settings.extraction_stuck_timeout_seconds):
            await db.rollback()
            return False
    # Commit the claim to the next dispatch slot before touching the broker.
    # A crash here is recovered by the next slot; a lost acknowledgement also
    # becomes a duplicate delivery, which the worker ownership lock rejects.
    run.dispatch_after = now + DISPATCH_INTERVAL
    await db.commit()
    from app.tasks.extraction import extract_requirements_task

    try:
        await asyncio.to_thread(extract_requirements_task.delay, str(doc.id), str(run.id))
    except Exception:
        log.exception("Extraction dispatch failed for run %s; reconciliation will retry", run_id)
        # Shorten the retry slot only if the run has not changed meanwhile.
        current_doc = await db.scalar(
            select(Document).where(Document.id == run_doc).with_for_update()
            .execution_options(populate_existing=True)
        )
        current = await db.scalar(
            select(ExtractionRun).where(ExtractionRun.id == run_id).with_for_update()
            .execution_options(populate_existing=True)
        )
        if (current_doc and current_doc.current_extraction_id == run_id
                and current and current.status in {"pending", "running"}):
            current.dispatch_after = now + PUBLISH_FAILURE_INTERVAL
            await db.commit()
        else:
            await db.rollback()
        return False
    return True


async def reconcile_jobs(session_factory, *, now: datetime | None = None, limit: int = 100) -> int:
    now = now or utcnow()
    async with session_factory() as db:
        stale_before = now - timedelta(seconds=settings.extraction_stuck_timeout_seconds)
        ids = (
            await db.scalars(
                select(ExtractionRun.id)
                .join(Document, Document.id == ExtractionRun.document_id)
                .where(Document.current_extraction_id == ExtractionRun.id)
                .where(or_(
                    ExtractionRun.status == "pending",
                    and_(ExtractionRun.status == "running",
                         func.coalesce(ExtractionRun.last_progress_at, ExtractionRun.started_at,
                                       ExtractionRun.created_at) <= stale_before),
                ))
                .where((ExtractionRun.dispatch_after.is_(None)) | (ExtractionRun.dispatch_after <= now))
                # First publish rows with no prior slot, then oldest due slot.
                # This prevents a fixed batch of repeatedly failing jobs from
                # keeping later jobs behind the per-pass limit.
                .order_by(ExtractionRun.dispatch_after.is_not(None),
                          ExtractionRun.dispatch_after, ExtractionRun.created_at)
                .limit(limit)
            )
        ).all()
        await db.rollback()
    dispatched = 0
    for run_id in ids:
        async with session_factory() as db:
            if await dispatch_run(db, run_id, now=now):
                dispatched += 1
    return dispatched


@asynccontextmanager
async def run_lock(session_factory, run_id: uuid.UUID):
    """Hold a PostgreSQL session lock across all task commits."""
    engine = session_factory.kw["bind"]
    if engine.dialect.name == "postgresql":
        connection = await engine.connect()
        key = run_id.int & ((1 << 63) - 1)
        acquired = False
        try:
            acquired = bool(await connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}))
            pid = await connection.scalar(text("SELECT pg_backend_pid()")) if acquired else None
            await connection.commit()
            yield (connection, pid, key) if acquired else None
        finally:
            if acquired:
                try:
                    await connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
                    await connection.commit()
                except Exception:
                    log.exception("Could not release extraction lock %s", run_id)
            await connection.close()
    else:
        with _sqlite_locks_guard:
            lock = _sqlite_locks.setdefault(run_id, threading.Lock())
        acquired = lock.acquire(blocking=False)
        try:
            yield lock if acquired else None
        finally:
            if acquired:
                lock.release()


async def check_lock(lock) -> None:
    # A lost advisory-lock connection must stop its old worker before it writes.
    if isinstance(lock, tuple):
        connection, pid, key = lock
        held = await connection.scalar(text("""
            SELECT pg_backend_pid() = :pid AND EXISTS (
                SELECT 1 FROM pg_locks
                WHERE pid = pg_backend_pid() AND locktype = 'advisory' AND granted
                  AND classid::bigint = :high AND objid::bigint = :low AND objsubid = 1
            )
        """), {"pid": pid, "high": key >> 32, "low": key & 0xffffffff})
        await connection.commit()
        if not held:
            raise RuntimeError("Extraction advisory lock was lost")
