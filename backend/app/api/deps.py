import uuid
import secrets
from typing import Optional

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User, RevokedSession
from app.services.auth import decode_token
from app.services.operator_authority import is_installation_operator

security = HTTPBearer(auto_error=False)
SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


async def _get_user_from_token(token: str, db: AsyncSession, token_type: str = "access") -> User:
    payload = decode_token(token)
    if payload is None or payload.get("type") != token_type:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    try:
        user_id = uuid.UUID(payload["sub"])
        session_id = str(uuid.UUID(payload["jti"]))
    except (KeyError, ValueError, TypeError, AttributeError):
        raise HTTPException(401, "Session expired. Sign in again.")
    result = await db.execute(select(User).where(User.id == user_id, User.active.is_(True)))
    user = result.scalar_one_or_none()
    if (
        user is None
        or payload.get("ver") != user.auth_version
        or await db.get(RevokedSession, session_id)
    ):
        raise HTTPException(401, "Session expired. Sign in again.")

    return user


def _validate_csrf(request: Request, csrf_cookie: Optional[str]) -> None:
    if request.method.upper() in SAFE_METHODS:
        return

    csrf_header = request.headers.get("x-csrf-token")
    if not csrf_cookie or not csrf_header:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token required")
    if not secrets.compare_digest(csrf_cookie, csrf_header):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    access_token: Optional[str] = Cookie(None),
    csrf_token: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is not None:
        return await _get_user_from_token(credentials.credentials, db)

    if access_token:
        _validate_csrf(request, csrf_token)
        return await _get_user_from_token(access_token, db)

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


def require_role(*roles: str):
    async def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user

    return checker


async def get_current_organization_id(
    user: User = Depends(get_current_user),
) -> Optional[str]:
    return str(user.organization_id) if user.organization_id else None


async def require_installation_operator(user: User = Depends(get_current_user)) -> User:
    if not is_installation_operator(user):
        raise HTTPException(
            403, "System-admin access is required for this operation."
        )
    return user
