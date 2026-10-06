import json
import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from redis.asyncio import Redis

from app.config import settings

log = logging.getLogger(__name__)
_CHANNEL_PREFIX = "extraction_events"


def _channel(run_id: str) -> str:
    return f"{_CHANNEL_PREFIX}:{run_id}"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def publish_event(run_id: str, event: dict) -> None:
    payload = dict(event)
    payload.setdefault("timestamp", _now_iso())
    payload.setdefault("level", "info")
    try:
        async with Redis.from_url(settings.redis_url, decode_responses=True,
                                  socket_connect_timeout=1, socket_timeout=1) as redis:
            await redis.publish(_channel(run_id), json.dumps(payload))
    except Exception:
        log.warning("Extraction progress event unavailable for run %s", run_id, exc_info=True)


async def stream_events(run_id: str) -> AsyncGenerator[str, None]:
    async with (
        Redis.from_url(settings.redis_url, decode_responses=True,
                       socket_connect_timeout=1, socket_timeout=1) as redis,
        redis.pubsub() as pubsub,
    ):
        await pubsub.subscribe(_channel(run_id))
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message.get("type") == "message":
                yield message.get("data", "")
            else:
                yield ""
