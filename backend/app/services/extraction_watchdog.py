import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.services.extraction_jobs import reconcile_jobs
from app.services.quality_jobs import reconcile_quality_jobs

log = logging.getLogger(__name__)


def _get_session_factory():
    engine = create_async_engine(settings.database_url)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


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
        await session_factory.kw["bind"].dispose()
