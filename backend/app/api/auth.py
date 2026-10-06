import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import _get_user_from_token, _validate_csrf, get_current_user
from app.config import settings
from app.database import get_db
from app.models.user import LoginThrottle, RevokedSession, User
from app.schemas.user import (
    AccountUpdate,
    LoginRequest,
    NotificationSettings,
    PasswordChange,
    TokenResponse,
    UserResponse,
)
from app.services.audit import log_action
from app.services.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password_async,
    verify_password_async,
)
from app.services.login_throttle import check_login_limit
from app.services.operator_authority import has_operator_designation, is_installation_operator

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"
CSRF_COOKIE = "csrf_token"


def _set_session_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    secure = settings.is_production
    csrf_token = secrets.token_urlsafe(32)
    response.set_cookie(
        key=ACCESS_COOKIE,
        value=access_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=refresh_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        path="/",
    )
    response.set_cookie(
        key=CSRF_COOKIE,
        value=csrf_token,
        httponly=False,
        secure=secure,
        samesite="lax",
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        path="/",
    )


def _clear_session_cookies(response: Response) -> None:
    secure = settings.is_production
    for cookie_name in (ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE):
        response.delete_cookie(
            key=cookie_name,
            path="/",
            secure=secure,
            samesite="lax",
        )


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    if len(body.email) > 254:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    throttle_key = await check_login_limit(
        db, body.email, request.client.host if request.client else None
    )
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user is None or not await verify_password_async(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not user.active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account disabled")

    await db.execute(delete(LoginThrottle).where(LoginThrottle.key == throttle_key))
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    await log_action(
        db,
        user,
        "login",
        "auth",
        str(user.id),
        new_value={"ip_address": client_ip, "user_agent": user_agent},
    )
    await db.commit()

    token_data = {
        "sub": str(user.id),
        "role": user.role,
        "ver": user.auth_version,
        "jti": secrets.token_hex(16),
    }
    # The access and refresh tokens share a revocable session identity.
    import uuid

    token_data["jti"] = str(uuid.UUID(token_data["jti"]))
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)
    _set_session_cookies(response, access_token, refresh_token)
    return TokenResponse()


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    _validate_csrf(request, request.cookies.get(CSRF_COOKIE))
    token = request.cookies.get(REFRESH_COOKIE, "")
    user = await _get_user_from_token(token, db, "refresh")
    payload = decode_token(token)
    # Keep the original absolute refresh expiry and session identity. Concurrent tabs
    # can renew safely; logout and account changes revoke the entire session.
    access = create_access_token(
        {"sub": str(user.id), "ver": user.auth_version, "jti": payload["jti"]}
    )
    _set_session_cookies(response, access, token)
    return TokenResponse()


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    bearer = request.headers.get("authorization", "")
    cookie_tokens = [
        token
        for token in (request.cookies.get(REFRESH_COOKIE), request.cookies.get(ACCESS_COOKIE))
        if token
    ]
    if cookie_tokens:
        _validate_csrf(request, request.cookies.get(CSRF_COOKIE))
    tokens = cookie_tokens or ([bearer[7:]] if bearer.lower().startswith("bearer ") else [])
    for token in tokens:
        payload = decode_token(token)
        if payload:
            try:
                user = await _get_user_from_token(token, db, payload.get("type"))
            except HTTPException:
                user = None
            if user:
                # Serialize logout per account so concurrent tabs cannot insert twice.
                await db.execute(select(User).where(User.id == user.id).with_for_update())
                if not await db.get(RevokedSession, payload["jti"]):
                    db.add(
                        RevokedSession(
                            id=payload["jti"],
                            user_id=user.id,
                            expires_at=datetime.now(timezone.utc)
                            + timedelta(days=settings.refresh_token_expire_days),
                        )
                    )
                await db.execute(
                    delete(RevokedSession).where(
                        RevokedSession.expires_at < datetime.now(timezone.utc)
                    )
                )
                await db.commit()
                break
    _clear_session_cookies(response)
    response.status_code = 204
    return response


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Convenience endpoint for session-based auth checks.

    Some browser privacy/adblock extensions block requests to paths like `/users/me`.
    Keeping this under `/auth/me` gives the frontend a stable alternative.
    """
    result = UserResponse.model_validate(current_user)
    result.installation_operator = is_installation_operator(current_user)
    result.system_admin_designated = has_operator_designation(current_user)
    return result


@router.patch("/me", response_model=UserResponse)
async def update_account(
    body: AccountUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    old_value = {"full_name": current_user.full_name}
    current_user.full_name = body.full_name
    await log_action(
        db, current_user, "update", "user", str(current_user.id),
        old_value, {"full_name": current_user.full_name},
    )
    await db.commit()
    await db.refresh(current_user)
    return await get_current_user_info(current_user)


@router.post("/change-password", status_code=204)
async def change_password(
    body: PasswordChange,
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Serialise credential changes and reload after the lock so a concurrent
    # request cannot verify against a password which has already been replaced.
    result = await db.execute(
        select(User).where(User.id == current_user.id).with_for_update()
        .execution_options(populate_existing=True)
    )
    user = result.scalar_one()
    if not await verify_password_async(body.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    user.password_hash = await hash_password_async(body.new_password)
    user.auth_version += 1
    await log_action(
        db, user, "update", "user", str(user.id),
        new_value={"password_changed": True},
    )
    await db.commit()
    token_data = {"sub": str(user.id), "ver": user.auth_version, "jti": str(uuid.uuid4())}
    _set_session_cookies(
        response, create_access_token(token_data), create_refresh_token(token_data),
    )
    response.status_code = 204
    return response


@router.get("/notification-settings", response_model=NotificationSettings)
async def get_notification_settings(current_user: User = Depends(get_current_user)):
    return NotificationSettings.model_validate(current_user)


@router.patch("/notification-settings", response_model=NotificationSettings)
async def update_notification_settings(
    body: NotificationSettings,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    old_value = NotificationSettings.model_validate(current_user).model_dump()
    current_user.review_mentions = body.review_mentions
    current_user.review_reminders = body.review_reminders
    await log_action(
        db, current_user, "update", "user", str(current_user.id),
        old_value, body.model_dump(),
    )
    await db.commit()
    return NotificationSettings.model_validate(current_user)
