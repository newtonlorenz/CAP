from __future__ import annotations

import uuid

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.program import RequirementSetVersion
from app.models.requirement import Requirement


async def get_current_approved_version_for_document(
    db: AsyncSession,
    document_id: uuid.UUID,
) -> RequirementSetVersion | None:
    """Select the approved version for a document already scoped by its caller."""
    preferred_result = await db.execute(
        select(RequirementSetVersion)
        .where(
            and_(
                RequirementSetVersion.document_id == document_id,
                RequirementSetVersion.status == "approved",
                RequirementSetVersion.is_current.is_(True),
            )
        )
        .limit(1)
    )
    preferred = preferred_result.scalar_one_or_none()
    if preferred is not None:
        return preferred

    fallback_result = await db.execute(
        select(RequirementSetVersion)
        .where(
            and_(
                RequirementSetVersion.document_id == document_id,
                RequirementSetVersion.status == "approved",
            )
        )
        .order_by(RequirementSetVersion.version_number.desc())
        .limit(1)
    )
    return fallback_result.scalar_one_or_none()


async def load_requirements_for_versions(
    db: AsyncSession,
    jurisdiction_id: uuid.UUID,
    version_ids: list[uuid.UUID],
    *,
    organization_id: uuid.UUID | None,
) -> list[Requirement]:
    if not version_ids:
        return []

    query = select(Requirement).where(
        and_(
            Requirement.jurisdiction_id == jurisdiction_id,
            Requirement.active.is_(True),
            Requirement.requirement_set_version_id.in_(version_ids),
        )
    )
    if organization_id is None:
        query = query.where(Requirement.organization_id.is_(None))
    else:
        query = query.where(Requirement.organization_id == organization_id)
    query = query.order_by(Requirement.document_id.asc(), Requirement.sort_order.asc())

    requirements_result = await db.execute(query)
    return requirements_result.scalars().all()


def default_review_state_for_requirement(
    requirement: Requirement,
    *,
    not_applicable_state: tuple[str, str | None],
) -> tuple[str, str | None]:
    """Return the caller-selected review state for not-applicable requirements.

    Program submission cycles pass ``("confirmed", rationale)``; review cycles
    retain their distinct ``("pending", None)`` policy.
    """
    if requirement.requirement_type == "informational":
        return "confirmed", "Informational requirement - no action required"
    if requirement.requirement_type == "not_applicable":
        return not_applicable_state
    return "pending", None
