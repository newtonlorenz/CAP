"""Shared, atomic login limits; identities are keyed hashes, never stored plaintext."""

import hashlib
import hmac
import time
from fastapi import HTTPException
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from app.config import settings
from app.models.user import LoginThrottle


async def check_login_limit(db, email, client_ip):
    window = int(time.time()) // 600
    insert = sqlite_insert if db.bind.dialect.name == "sqlite" else pg_insert
    exceeded = False
    account_key = None
    for identity, limit in (
        ("account:" + email.strip().casefold(), 8),
        ("ip:" + (client_ip or "unknown"), 60),
    ):
        key = hmac.new(
            settings.secret_key.encode(), f"{window}:{identity}".encode(), hashlib.sha256
        ).hexdigest()
        if identity.startswith("account:"):
            account_key = key
        stmt = insert(LoginThrottle).values(key=key, attempts=1, window=window)
        stmt = stmt.on_conflict_do_update(
            index_elements=[LoginThrottle.key], set_={"attempts": LoginThrottle.attempts + 1}
        ).returning(LoginThrottle.attempts)
        exceeded |= (await db.execute(stmt)).scalar_one() > limit
    await db.execute(delete(LoginThrottle).where(LoginThrottle.window < window - 6))
    await db.commit()
    if exceeded:
        raise HTTPException(
            429,
            "Too many sign-in attempts. Please try again in ten minutes.",
            headers={"Retry-After": "600"},
        )
    return account_key
