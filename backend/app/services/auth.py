import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from jwt import InvalidTokenError
from starlette.concurrency import run_in_threadpool

from app.config import settings


def hash_password(password: str) -> str:
    if len(password.encode()) > 72:
        raise ValueError("Password exceeds bcrypt's 72-byte limit")
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    if len(plain.encode()) > 72:
        return False
    return bcrypt.checkpw(plain.encode(), hashed.encode())


async def hash_password_async(password: str) -> str:
    return await run_in_threadpool(hash_password, password)


async def verify_password_async(plain: str, hashed: str) -> bool:
    return await run_in_threadpool(verify_password, plain, hashed)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode["exp"] = expire
    to_encode["type"] = "access"
    to_encode.setdefault("jti", str(uuid.uuid4()))
    to_encode.setdefault("ver", 0)
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def create_refresh_token(data: dict) -> str:
    payload = {**data, "type": "refresh"}
    payload.setdefault("jti", str(uuid.uuid4()))
    payload.setdefault("ver", 0)
    payload["exp"] = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except InvalidTokenError:
        return None
