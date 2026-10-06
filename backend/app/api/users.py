import json
from typing import Optional, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.database import get_db
from app.models.audit import AuditLog
from app.models.user import User
from app.schemas.user import UserCreate, UserMentionResponse, UserResponse, UserUpdate
from app.services.audit import log_action
from app.services.auth import hash_password_async
from app.services.operator_authority import has_operator_designation, is_installation_operator
from app.services.access import has_confidential_access
from app.services.access_audit import audit_access_clause

router = APIRouter(prefix="/api/v1/users", tags=["users"])


def _parse_json(value: Optional[str]) -> Optional[Dict[str, Any]]:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {"raw": value}


def _serialize_audit_log(entry: AuditLog) -> dict:
    # Historical free-text payloads may refer to sources whose audience changed
    # since the event. Keep the event, never replay those payloads to a browser.
    sensitive = entry.entity_type in {"application", "preparation_response", "preparation_case"}
    return {
        "id": str(entry.id),
        "user_id": str(entry.user_id),
        "user_name": entry.user_name,
        "action": entry.action,
        "entity_type": entry.entity_type,
        "entity_id": entry.entity_id,
        "old_value": None if sensitive else _parse_json(entry.old_value),
        "new_value": None if sensitive else _parse_json(entry.new_value),
        "timestamp": entry.timestamp.isoformat(),
    }


def _scope_audit_log_query(query, organization_id: Optional[UUID]):
    if organization_id is None:
        return query.where(AuditLog.organization_id.is_(None))
    return query.where(AuditLog.organization_id == organization_id)


async def _get_user_or_404(
    db: AsyncSession,
    user_id: UUID,
    organization_id: Optional[UUID] = None,
) -> User:
    query = select(User).where(User.id == user_id)
    if organization_id is None:
        query = query.where(User.organization_id.is_(None))
    else:
        query = query.where(User.organization_id == organization_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _require_operator_account_authority(target: User, actor: User) -> None:
    if has_operator_designation(target) and not is_installation_operator(actor):
        raise HTTPException(
            status_code=403,
            detail="System-admin access is required for this operation.",
        )


def _user_response(user: User) -> UserResponse:
    result = UserResponse.model_validate(user)
    result.installation_operator = is_installation_operator(user)
    result.system_admin_designated = has_operator_designation(user)
    return result


def _check_password_length(password: str) -> None:
    if len(password.encode()) > 72:
        raise HTTPException(status_code=422, detail="Password exceeds 72 UTF-8 bytes")


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    _check_password_length(body.password)
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        organization_id=current_user.organization_id,
        email=body.email,
        password_hash=await hash_password_async(body.password),
        full_name=body.full_name,
        role=body.role,
        active=True,
    )
    db.add(user)
    await log_action(
        db,
        current_user,
        "create",
        "user",
        str(user.id),
        new_value={
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "active": user.active,
        },
    )
    await db.commit()
    await db.refresh(user)
    return _user_response(user)


@router.get("", response_model=dict)
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=1000),
    q: str = Query("", max_length=255),
    active: bool | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    base_query = select(User)
    if current_user.organization_id is None:
        base_query = base_query.where(User.organization_id.is_(None))
    else:
        base_query = base_query.where(User.organization_id == current_user.organization_id)

    if active is not None:
        base_query = base_query.where(User.active.is_(active))

    if q.strip():
        base_query = base_query.where(
            or_(
                User.full_name.icontains(q.strip(), autoescape=True),
                User.email.icontains(q.strip(), autoescape=True),
            )
        )

    scoped_users = base_query.subquery()
    total_result = await db.execute(select(func.count()).select_from(scoped_users))
    total = total_result.scalar()
    result = await db.execute(
        base_query.order_by(User.created_at.desc(), User.id).offset(skip).limit(limit)
    )
    users = result.scalars().all()
    return {"items": [_user_response(u) for u in users], "total": total}


@router.get("/mentions", response_model=dict)
async def list_mentionable_users(
    limit: int = 1000,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(User)
        .where(
            User.active.is_(True),
            (
                User.organization_id == current_user.organization_id
                if current_user.organization_id is not None
                else User.organization_id.is_(None)
            ),
        )
        .order_by(User.full_name)
        .limit(limit)
    )
    users = result.scalars().all()
    return {"items": [UserMentionResponse.model_validate(u) for u in users], "total": len(users)}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
):
    """Get the currently authenticated user's information."""
    return _user_response(current_user)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    return _user_response(await _get_user_or_404(db, user_id, current_user.organization_id))


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    body: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    user = await _get_user_or_404(db, user_id, current_user.organization_id)
    _require_operator_account_authority(user, current_user)
    # Account administration must not provide an impersonation route into
    # confidential resources. Infrastructure recovery remains a separate process.
    if (
        user.id != current_user.id
        and (body.password or (body.email is not None and body.email != user.email))
        and await has_confidential_access(db, user)
    ):
        raise HTTPException(
            403,
            "This account requires identity-verified credential recovery; "
            "an administrator cannot replace its password or sign-in address.",
        )
    if (
        user.id == current_user.id
        and is_installation_operator(current_user)
        and ((body.role is not None and body.role != "admin") or body.active is False)
    ):
        raise HTTPException(
            status_code=400,
            detail="A system admin cannot demote or deactivate their own account.",
        )

    old_value = {
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "active": user.active,
    }

    if body.email is not None and body.email != user.email:
        existing = await db.execute(select(User).where(User.email == body.email))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already registered")
        user.email = body.email
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.role is not None:
        user.role = body.role
    if body.active is not None:
        user.active = body.active
    if body.password:
        _check_password_length(body.password)
        user.password_hash = await hash_password_async(body.password)
    if body.password or body.email is not None or body.role is not None or body.active is not None:
        user.auth_version += 1

    new_value = {
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "active": user.active,
    }
    if body.password:
        new_value["password_reset"] = True

    await log_action(db, current_user, "update", "user", str(user.id), old_value, new_value)
    await db.commit()
    await db.refresh(user)
    return _user_response(user)


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    user = await _get_user_or_404(db, user_id, current_user.organization_id)
    _require_operator_account_authority(user, current_user)
    if not user.active:
        return Response(status_code=204)

    old_value = {
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "active": user.active,
    }
    user.active = False
    user.auth_version += 1
    new_value = {
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "active": user.active,
    }
    await log_action(db, current_user, "delete", "user", str(user.id), old_value, new_value)
    await db.commit()
    return Response(status_code=204)


@router.get("/{user_id}/logins", response_model=dict)
async def get_user_login_history(
    user_id: UUID,
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    await _get_user_or_404(db, user_id, current_user.organization_id)
    base_query = _scope_audit_log_query(
        select(AuditLog).where(
            AuditLog.action == "login",
            AuditLog.entity_type == "auth",
            AuditLog.entity_id == str(user_id),
        ),
        current_user.organization_id,
    )
    total_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = total_result.scalar() or 0
    result = await db.execute(
        base_query.order_by(AuditLog.timestamp.desc()).offset(skip).limit(limit)
    )
    items = []
    for entry in result.scalars().all():
        details = _parse_json(entry.new_value) or {}
        items.append(
            {
                "id": str(entry.id),
                "user_id": str(entry.user_id),
                "ip_address": details.get("ip_address"),
                "user_agent": details.get("user_agent"),
                "timestamp": entry.timestamp.isoformat(),
            }
        )
    return {"items": items, "total": total}


@router.get("/{user_id}/edits", response_model=dict)
async def get_user_edit_history(
    user_id: UUID,
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    await _get_user_or_404(db, user_id, current_user.organization_id)
    base_query = _scope_audit_log_query(
        select(AuditLog).where(
            AuditLog.entity_type == "user",
            AuditLog.entity_id == str(user_id),
        ),
        current_user.organization_id,
    )
    total_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = total_result.scalar() or 0
    result = await db.execute(
        base_query.order_by(AuditLog.timestamp.desc()).offset(skip).limit(limit)
    )
    return {
        "items": [_serialize_audit_log(entry) for entry in result.scalars().all()],
        "total": total,
    }


@router.get("/{user_id}/audit", response_model=dict)
async def get_user_audit_trail(
    user_id: UUID,
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    await _get_user_or_404(db, user_id, current_user.organization_id)
    base_query = _scope_audit_log_query(
        select(AuditLog).where(AuditLog.user_id == user_id),
        current_user.organization_id,
    ).where(audit_access_clause(current_user))
    total_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = total_result.scalar() or 0
    result = await db.execute(
        base_query.order_by(AuditLog.timestamp.desc()).offset(skip).limit(limit)
    )
    return {
        "items": [_serialize_audit_log(entry) for entry in result.scalars().all()],
        "total": total,
    }
