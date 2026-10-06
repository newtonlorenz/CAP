"""Apply review assessment edits against the resulting evidence state."""

import html
import re
from datetime import datetime, timezone

from sqlalchemy import select

from app.models.requirement import RequirementStatus

_UNCHANGED = object()


def plain_text(value):
    return html.unescape(re.sub(r"<[^>]*>", " ", value or "")).replace("\u00a0", " ").strip()


def current_rationale(item, legacy_comment=""):
    """Explicit assessments use the current text, never a superseded rationale."""
    if item.assessment_status is not None:
        return item.review_evidence or ""
    return item.review_evidence if plain_text(item.review_evidence) else (legacy_comment or "")


async def legacy_assessment_status(db, item):
    if item.assessment_status is not None:
        return None
    return await db.scalar(
        select(RequirementStatus.status)
        .where(RequirementStatus.requirement_id == item.requirement_id)
        .order_by(RequirementStatus.changed_at.desc(), RequirementStatus.id.desc())
        .limit(1)
    )


def update_assessment(
    item, *, status=_UNCHANGED, evidence=_UNCHANGED, legacy_status=None
):
    """Validate the proposed assessment before changing the item.

    Call with no status/evidence change when a legacy assessment needs to capture its status.
    """
    resulting_status = (
        (item.assessment_status or legacy_status) if status is _UNCHANGED else status
    )
    resulting_evidence = item.review_evidence if evidence is _UNCHANGED else evidence
    has_text = bool(plain_text(resulting_evidence))
    if resulting_status == "not_applicable" and not has_text:
        raise ValueError("Explain why this requirement does not apply in the evidence / rationale field.")
    if evidence is not _UNCHANGED:
        if (item.review_evidence or "") != (evidence or ""):
            item.evidence_changed_at = datetime.now(timezone.utc)
        item.review_evidence = evidence
    if status is not _UNCHANGED:
        item.assessment_status = status
    elif item.assessment_status is None and legacy_status is not None:
        item.assessment_status = legacy_status
    if evidence is not _UNCHANGED or status is not _UNCHANGED or legacy_status is not None:
        item.assessment_rationale = resulting_evidence
