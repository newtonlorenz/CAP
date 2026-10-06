from __future__ import annotations

from sqlalchemy import and_

ACTIONABLE_REQUIREMENT_TYPES = ("mandatory", "recommended")
COMPLETED_REVIEW_STATUSES = ("confirmed", "updated")


def is_review_progress_eligible(
    requirement_type: str | None, requirement_status: str | None
) -> bool:
    return (
        requirement_type in ACTIONABLE_REQUIREMENT_TYPES and requirement_status != "not_applicable"
    )


def review_progress_eligible_condition(requirement_type_expr, requirement_status_expr):
    return and_(
        requirement_type_expr.in_(ACTIONABLE_REQUIREMENT_TYPES),
        requirement_status_expr != "not_applicable",
    )
