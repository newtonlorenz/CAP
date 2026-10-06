"""Shared source-version scope for current compliance views and exports."""

from sqlalchemy import and_, or_, select

from app.models.program import RequirementSetVersion
from app.models.requirement import Requirement


def current_requirement_condition():
    """Use the current version, or legacy rows when no current version exists.

    Review-specific queries intentionally do not use this condition: their locked
    requirement membership can refer to a historical baseline.
    """
    current_version_exists = (
        select(RequirementSetVersion.id)
        .where(
            RequirementSetVersion.document_id == Requirement.document_id,
            RequirementSetVersion.is_current.is_(True),
        )
        .correlate(Requirement)
        .exists()
    )
    belongs_to_current_version = (
        select(RequirementSetVersion.id)
        .where(
            RequirementSetVersion.id == Requirement.requirement_set_version_id,
            RequirementSetVersion.document_id == Requirement.document_id,
            RequirementSetVersion.is_current.is_(True),
        )
        .correlate(Requirement)
        .exists()
    )
    return or_(
        belongs_to_current_version,
        and_(Requirement.requirement_set_version_id.is_(None), ~current_version_exists),
    )
