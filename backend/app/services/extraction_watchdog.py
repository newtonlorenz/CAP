import asyncio
import logging

from app.database import async_session
from app.services.extraction_jobs import reconcile_jobs
from app.services.quality_jobs import reconcile_quality_jobs

log = logging.getLogger(__name__)


def _get_session_factory():
    return async_session


async def run_extraction_watchdog(poll_interval_seconds: int = 60) -> None:
    session_factory = _get_session_factory()
    try:
        while True:
            try:
                await reconcile_jobs(session_factory)
                await reconcile_quality_jobs(session_factory)
            except Exception:
                log.exception("Extraction reconciliation failed; will try again")
            await asyncio.sleep(poll_interval_seconds)
    finally:
        if session_factory is not async_session and "bind" in getattr(session_factory, "kw", {}):
            await session_factory.kw["bind"].dispose()
