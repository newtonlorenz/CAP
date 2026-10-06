import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.user import User


async def log_action(
    db: AsyncSession,
    user: User,
    action: str,
    entity_type: str,
    entity_id: str,
    old_value: Optional[dict] = None,
    new_value: Optional[dict] = None,
):
    if db.bind.dialect.name == "postgresql":
        # Transaction-scoped per-organisation lock prevents concurrent events from
        # forking the hash chain. The caller's commit releases the lock.
        key = int.from_bytes(
            hashlib.sha256(str(user.organization_id).encode()).digest()[:8], "big", signed=True
        )
        await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
    previous_hash_query = (
        select(AuditLog.event_hash)
        .where(AuditLog.organization_id == user.organization_id)
        .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
        .limit(1)
    )
    previous_hash_result = await db.execute(previous_hash_query)
    previous_hash = previous_hash_result.scalar_one_or_none()

    payload = {
        "organization_id": str(user.organization_id) if user.organization_id else None,
        "user_id": str(user.id),
        "user_name": user.full_name,
        "action": action,
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "old_value": old_value,
        "new_value": new_value,
    }
    canonical_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    event_hash = hashlib.sha256(
        f"{previous_hash or ''}|{canonical_payload}".encode("utf-8")
    ).hexdigest()

    entry = AuditLog(
        organization_id=user.organization_id,
        user_id=user.id,
        user_name=user.full_name,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        old_value=json.dumps(old_value) if old_value else None,
        new_value=json.dumps(new_value) if new_value else None,
        prev_hash=previous_hash,
        event_hash=event_hash,
        # Set an application timestamp to avoid same-second ordering ambiguity from DB defaults.
        timestamp=datetime.now(timezone.utc),
    )
    db.add(entry)
    await db.flush()
