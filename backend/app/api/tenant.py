import uuid
from typing import TypeVar

from fastapi import HTTPException
from sqlalchemy import Select, and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

T = TypeVar("T")


def org_clause(model, current_user: User, action: str = "view"):
    from app.services.access import access_clause
    return and_(_tenant_clause(model, current_user), access_clause(model, current_user, action))


def _tenant_clause(model, current_user: User):
    org_id = current_user.organization_id
    if org_id is None:
        return model.organization_id.is_(None)
    return model.organization_id == org_id


def apply_org_scope(query: Select, model, current_user: User, action: str = "view") -> Select:
    return query.where(org_clause(model, current_user, action))


async def get_org_owned_or_404(
    db: AsyncSession,
    model: type[T],
    entity_id: uuid.UUID,
    current_user: User,
    *,
    id_attr: str = "id",
    detail: str = "Not found",
) -> T:
    result = await db.execute(
        apply_org_scope(
            select(model).where(getattr(model, id_attr) == entity_id),
            model,
            current_user,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=detail)
    return row


async def get_active_user_in_org_or_404(
    db: AsyncSession,
    user_id: uuid.UUID | None,
    current_user: User,
    *,
    roles: set[str] | None = None,
    detail: str = "User not found",
    status_code: int = 404,
) -> User | None:
    if user_id is None:
        return None

    predicates = [
        User.id == user_id,
        User.active.is_(True),
        org_clause(User, current_user),
    ]
    if roles:
        predicates.append(User.role.in_(roles))

    result = await db.execute(select(User).where(and_(*predicates)))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status_code, detail=detail)
    return user
