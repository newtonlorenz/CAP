"""Coordination only: reviewer assignment never changes the resource access policy."""

import json
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import exists, or_, select

from app.api.tenant import org_clause
from app.models.application import Application, ApplicationComponent
from app.models.audit import AuditLog
from app.models.preparation import (
    PreparationCase,
    PreparationReviewFeedback,
    PreparationResponse,
    PreparationResponseEvidence,
)
from app.models.user import User
from app.services.access import effective_permissions


async def eligible_reviewer(db, case, user_id):
    if user_id is None:
        return None
    candidate = await db.get(User, user_id)
    if (
        candidate is None
        or not candidate.active
        or candidate.role not in {"manager", "admin"}
        or candidate.organization_id != case.organization_id
    ):
        return None
    permissions = await effective_permissions(db, "preparation_case", case.id, candidate)
    if not {"view", "approve"}.issubset(permissions):
        return None
    evidence_ids = (
        await db.scalars(
            select(PreparationResponseEvidence.evidence_id)
            .join(
                PreparationResponse,
                PreparationResponse.id == PreparationResponseEvidence.response_id,
            )
            .where(PreparationResponse.case_id == case.id)
            .distinct()
        )
    ).all()
    for evidence_id in evidence_ids:
        if "view" not in await effective_permissions(
            db, "preparation_evidence", evidence_id, candidate
        ):
            return None
    sources = (
        await db.scalars(
            select(PreparationResponse.reused_from_case_id)
            .where(
                PreparationResponse.case_id == case.id,
                PreparationResponse.reused_from_case_id.is_not(None),
            )
            .distinct()
        )
    ).all()
    for source_id in sources:
        if "view" not in await effective_permissions(db, "preparation_case", source_id, candidate):
            return None
    return candidate


async def validate_reviewer(db, case, reviewer_id):
    if reviewer_id is not None and await eligible_reviewer(db, case, reviewer_id) is None:
        raise HTTPException(
            422, "Review owner must be an active manager with access to approve this form"
        )


async def review_owner(db, case, user=None):
    # Current programme and pack owner fields are general ownership, not a configured
    # review responsibility. Do not silently reinterpret those assignments.
    if case.reviewer_id:
        candidate = await eligible_reviewer(db, case, case.reviewer_id)
        return (candidate, "case") if candidate else (None, None)
    return None, None


def included_case_clause(user):
    """Hide explicitly excluded pack content; independent forms remain available.

    Only visible pack relationships may influence a viewer's queue membership.
    """
    linked = (
        select(ApplicationComponent.id)
        .join(Application, Application.id == ApplicationComponent.application_id)
        .where(ApplicationComponent.case_id == PreparationCase.id, org_clause(Application, user))
    )
    return or_(
        ~exists(linked),
        exists(
            linked.where(ApplicationComponent.included.is_(True), Application.status != "completed")
        ),
    )


async def feedback_for(db, responses):
    if not responses:
        return {}
    records = (
        await db.execute(
            select(PreparationReviewFeedback, User.full_name)
            .outerjoin(User, User.id == PreparationReviewFeedback.created_by)
            .where(PreparationReviewFeedback.response_id.in_([item.id for item in responses]))
            .order_by(PreparationReviewFeedback.created_at, PreparationReviewFeedback.id)
        )
    ).all()
    result = {}
    for item, name in records:
        result.setdefault(item.response_id, []).append(
            dict(
                id=item.id,
                comment=item.comment,
                created_by=item.created_by,
                created_by_name=name,
                created_at=item.created_at,
                returned_revision=item.returned_revision,
                resolved_at=item.resolved_at,
                resolved_by=item.resolved_by,
            )
        )
    return result


async def answer_changes(db, case, user):
    events = (
        await db.scalars(
            select(AuditLog).where(
                org_clause(AuditLog, user),
                AuditLog.entity_type == "preparation_response",
                AuditLog.entity_id.like(f"{case.id}:%"),
                AuditLog.action.in_(["update", "reuse"]),
            )
        )
    ).all()
    latest = {}
    for event in events:
        before = json.loads(event.old_value) if event.old_value else None
        after = json.loads(event.new_value) if event.new_value else None
        if not after or "response" not in after:
            continue
        field_key = after["response"]["field_key"]
        revision = after.get("revision", 0)
        if field_key in latest and revision <= latest[field_key][0]:
            continue
        kind = (
            "new_answer"
            if before is None
            else (
                "evidence_changed"
                if sorted(before.get("evidence_ids", []))
                != sorted(after["response"].get("evidence_ids", []))
                else "answer_updated"
            )
        )
        latest[field_key] = revision, kind
    return {field: value[1] for field, value in latest.items()}


async def visible_case_projection(db, case, user):
    from app.services.preparation import build_case_response

    try:
        return await build_case_response(db, case, user=user)
    except HTTPException as error:
        # A separately protected original/reuse source can make the full form
        # inaccessible even when the outer case itself is visible.
        if error.status_code in {403, 404}:
            return None
        raise


async def review_queue_items(db, user, jurisdiction_id=None, case_id=None, include_excluded=False):
    # Build through the existing response projection: inaccessible evidence/reuse sources suppress
    # answers here too, so neither counts nor feedback disclose a hidden response.
    query = select(PreparationCase).where(
        org_clause(PreparationCase, user),
        PreparationCase.status == "active",
        exists(
            select(PreparationResponse.id).where(
                PreparationResponse.case_id == PreparationCase.id,
                PreparationResponse.accepted_at.is_(None),
            )
        ),
    )
    if jurisdiction_id:
        query = query.where(PreparationCase.jurisdiction_id == jurisdiction_id)
    if case_id:
        query = query.where(PreparationCase.id == case_id)
    if not include_excluded:
        query = query.where(included_case_clause(user))
    cases = (
        await db.scalars(
            query.order_by(PreparationCase.due_date.asc().nullslast(), PreparationCase.id)
        )
    ).all()
    result = []
    for case in cases:
        projection = await visible_case_projection(db, case, user)
        if projection is None:
            continue
        changes = await answer_changes(db, case, user)
        owner = await db.get(User, case.owner_id) if case.owner_id else None
        can_approve = (
            user.role in {"manager", "admin"} and "approve" in projection.access["permissions"]
        )
        fields = {field.key: field for field in projection.fields}
        for response in projection.responses:
            if response.accepted_at or response.field_key not in fields:
                continue
            if (
                response.value is None
                and not response.not_applicable_reason
                and not response.evidence_ids
            ):
                continue
            field = fields[response.field_key]
            result.append(
                dict(
                    case_id=case.id,
                    case_name=case.name,
                    jurisdiction_id=case.jurisdiction_id,
                    field_key=field.key,
                    question=field.label,
                    section=field.section,
                    guidance=field.help_text,
                    revision=case.revision,
                    review_status=response.review_status,
                    change_kind=changes.get(field.key),
                    reviewer_id=projection.reviewer_id,
                    reviewer_name=projection.reviewer_name,
                    owner_id=case.owner_id,
                    owner_name=owner.full_name if owner else None,
                    due_date=case.due_date,
                    last_saved_at=response.last_saved_at,
                    last_saved_by=response.last_saved_by,
                    open_feedback_count=sum(item.resolved_at is None for item in response.feedback),
                    can_approve=can_approve,
                )
            )
    return result


def filter_review_items(
    items,
    *,
    reviewer_id=None,
    status="pending_review",
    unassigned=False,
    overdue=False,
    changed_evidence=False,
    q=None,
):
    today = datetime.now(UTC).date()
    return [
        item
        for item in items
        if (not reviewer_id or item["reviewer_id"] == reviewer_id)
        and (status == "all" or item["review_status"] == status)
        and (not changed_evidence or item["change_kind"] == "evidence_changed")
        and (not unassigned or item["reviewer_id"] is None)
        and (not overdue or item["due_date"] is not None and item["due_date"] < today)
        and (
            not q
            or q.casefold()
            in f'{item["case_name"]} {item["question"]} {item["section"]}'.casefold()
        )
    ]
