from __future__ import annotations

import json
import logging
import mimetypes
import os
import re
import smtplib
import uuid
import shutil
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.api.tenant import apply_org_scope, get_active_user_in_org_or_404, get_org_owned_or_404
from app.config import settings
from app.database import get_db
from app.models.document import Document
from app.models.jurisdiction import Jurisdiction
from app.models.program import (
    BaselineMigration,
    CertificationProject,
    CertificationProjectRequirementBaseline,
    MaintenanceEvent,
    RequirementSetVersion,
    ReviewCycleRequirementBaseline,
    SubmissionPackage,
)
from app.models.requirement import Requirement, RequirementStatus
from app.models.review import (
    ReviewCycle,
    ReviewItem,
    ReviewItemComment,
    ReviewItemEvidenceFile,
    Snapshot,
)
from app.models.user import User
from app.schemas.review import (
    RequirementSummary,
    ReviewCycleBaselineMigrationChangedDecision,
    ReviewCycleBaselineMigrationDeltaItem,
    ReviewCycleBaselineMigrationExecuteRequest,
    ReviewCycleBaselineMigrationExecuteResponse,
    ReviewCycleListResponse,
    ReviewCycleBaselineMigrationPreviewResponse,
    ReviewCycleCreate,
    ReviewCycleResponse,
    ReviewCycleWithItemsResponse,
    ReviewCycleReminderRequest,
    ReviewCycleJiraSyncRequest,
    ReviewCycleJiraSyncResponse,
    ReviewCycleBaselineVersion,
    ReviewItemAssign,
    ReviewItemBulkMutationFailure,
    ReviewItemBulkMutationRequest,
    ReviewItemBulkMutationResponse,
    ReviewItemCommentCreate,
    ReviewItemCommentResponse,
    ReviewItemCommentUpdate,
    ReviewItemEvidenceFileResponse,
    ReviewItemJiraUpdate,
    ReviewItemResponse,
    ReviewItemUpdate,
    ReviewItemWithRequirementResponse,
    SnapshotCreate,
    SnapshotDetailResponse,
    SnapshotResponse,
)
from app.services.review_assurance import assessment_rows, readiness, freeze_review, evidence_download_path
from app.services.review_assessment import legacy_assessment_status, update_assessment
from app.services.requirement_baselines import (
    default_review_state_for_requirement as _shared_default_review_state_for_requirement,
    get_current_approved_version_for_document as _get_current_approved_version_for_document,
    load_requirements_for_versions as _load_requirements_for_versions,
)
from app.services.audit import log_action
from app.services.access import access_clause, get_policy, require_access
from app.services.email import EmailConfigError, send_email
from app.services.installation_settings import resolve_installation_settings
from app.services.file_utils import save_upload_file
from app.services.jira import (
    apply_item_jira_key,
    get_jira_integration,
    sync_review_cycle_jira_items,
)
from app.services.review_migration import (
    ReviewMigrationCloneError,
    cleanup_cloned_files,
    clone_review_cycle_items_for_migration,
)
from app.services.review_progress import (
    COMPLETED_REVIEW_STATUSES,
    is_review_progress_eligible,
)


def _default_review_state_for_requirement(requirement: Requirement) -> tuple[str, Optional[str]]:
    return _shared_default_review_state_for_requirement(
        requirement, not_applicable_state=("pending", None)
    )

router = APIRouter(prefix="/api/v1", tags=["reviews"])
logger = logging.getLogger(__name__)

EDIT_WINDOW = timedelta(minutes=15)
ALLOWED_EVIDENCE_EXTENSIONS = {
    ".pdf",
    ".txt",
    ".csv",
    ".md",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".png",
    ".jpg",
    ".jpeg",
}


async def _get_review_cycle_for_user(
    db: AsyncSession,
    current_user: User,
    cycle_id: uuid.UUID,
    *,
    writable: bool = False,
    action: str = "view",
) -> ReviewCycle:
    cycle = await get_org_owned_or_404(
        db,
        ReviewCycle,
        cycle_id,
        current_user,
        detail="Review cycle not found",
    )
    if cycle.certification_project_id:
        requested = "edit" if writable else action
        # Preserve historical reviewer capabilities only for an unprotected legacy project.
        if requested == "edit" and current_user.role in {"assigned_reviewer", "approver"}:
            policy = await get_policy(db, "certification_project", cycle.certification_project_id)
            if policy is None or (policy.visibility == "organisation" and policy.parent_id is None):
                requested = "view"
        await require_access(db, CertificationProject, cycle.certification_project_id, current_user, requested)
    if writable:
        # Serialise changes with closure on PostgreSQL; re-read after taking the lock.
        result = await db.execute(
            select(ReviewCycle)
            .where(ReviewCycle.id == cycle.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        cycle = result.scalar_one()
        if cycle.status != "active":
            raise HTTPException(
                status_code=409,
                detail="This review is read-only. Start a new review to record further work.",
            )
    return cycle


async def _project_is_confidential(db, project_id):
    policy = await get_policy(db, "certification_project", project_id)
    return policy is not None and (policy.visibility != "organisation" or policy.parent_id is not None)


async def _can_receive_cycle_notification(db, cycle, recipient):
    if not cycle.certification_project_id:
        return True
    return bool(await db.scalar(select(CertificationProject.id).where(
        CertificationProject.id == cycle.certification_project_id,
        access_clause(CertificationProject, recipient, "view"),
    )))


async def _get_snapshot_for_user(
    db: AsyncSession,
    current_user: User,
    snapshot_id: uuid.UUID,
) -> Snapshot:
    return await get_org_owned_or_404(
        db,
        Snapshot,
        snapshot_id,
        current_user,
        detail="Snapshot not found",
    )


async def _get_review_item_for_cycle(
    db: AsyncSession,
    current_user: User,
    cycle_id: uuid.UUID,
    item_id: uuid.UUID,
) -> tuple[ReviewCycle, ReviewItem]:
    cycle = await _get_review_cycle_for_user(db, current_user, cycle_id, writable=True)
    result = await db.execute(
        select(ReviewItem).where(
            ReviewItem.id == item_id,
            ReviewItem.review_cycle_id == cycle.id,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Review item not found")
    return cycle, item


def _is_image_evidence_filename(filename: str) -> bool:
    return os.path.splitext(filename)[1].lower() in {".png", ".jpg", ".jpeg"}


def _parse_document_ids(scope_filter: Optional[str]) -> Optional[list[uuid.UUID]]:
    if not scope_filter:
        return None
    try:
        raw = json.loads(scope_filter)
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, list):
        return None
    document_ids: list[uuid.UUID] = []
    for item in raw:
        try:
            document_ids.append(uuid.UUID(str(item)))
        except ValueError:
            continue
    return document_ids or None


def _latest_requirement_set_version_subquery():
    return (
        select(
            RequirementSetVersion.document_id.label("document_id"),
            RequirementSetVersion.id.label("latest_version_id"),
            RequirementSetVersion.version_number.label("latest_version_number"),
            func.row_number()
            .over(
                partition_by=RequirementSetVersion.document_id,
                order_by=(
                    RequirementSetVersion.is_current.desc(),
                    RequirementSetVersion.version_number.desc(),
                    RequirementSetVersion.created_at.desc(),
                    RequirementSetVersion.id.desc(),
                ),
            )
            .label("rn"),
        )
        .where(RequirementSetVersion.status == "approved")
        .subquery()
    )


async def _load_cycle_baseline_versions(
    db: AsyncSession,
    cycle_id: uuid.UUID,
) -> list[ReviewCycleBaselineVersion]:
    latest_version_subq = _latest_requirement_set_version_subquery()
    baseline_result = await db.execute(
        select(
            ReviewCycleRequirementBaseline.document_id,
            ReviewCycleRequirementBaseline.requirement_set_version_id,
            RequirementSetVersion.version_number,
            Document.name,
            Document.filename,
            latest_version_subq.c.latest_version_id,
            latest_version_subq.c.latest_version_number,
        )
        .join(
            RequirementSetVersion,
            RequirementSetVersion.id == ReviewCycleRequirementBaseline.requirement_set_version_id,
        )
        .outerjoin(Document, Document.id == ReviewCycleRequirementBaseline.document_id)
        .outerjoin(
            latest_version_subq,
            and_(
                latest_version_subq.c.document_id == ReviewCycleRequirementBaseline.document_id,
                latest_version_subq.c.rn == 1,
            ),
        )
        .where(ReviewCycleRequirementBaseline.review_cycle_id == cycle_id)
        .order_by(Document.name.asc(), Document.filename.asc())
    )
    return [
        ReviewCycleBaselineVersion(
            document_id=document_id,
            requirement_set_version_id=version_id,
            version_number=version_number,
            set_name=set_name or filename,
            is_latest=(latest_version_id is None or latest_version_id == version_id),
            latest_requirement_set_version_id=latest_version_id,
            latest_version_number=latest_version_number,
        )
        for (
            document_id,
            version_id,
            version_number,
            set_name,
            filename,
            latest_version_id,
            latest_version_number,
        ) in baseline_result.all()
    ]


async def _cycle_response(db: AsyncSession, cycle: ReviewCycle) -> ReviewCycleResponse:
    data = ReviewCycleResponse.model_validate(cycle).model_dump()
    if cycle.scope == "documents":
        data["document_ids"] = _parse_document_ids(cycle.scope_filter)
    data["baseline_versions"] = [
        item.model_dump() for item in await _load_cycle_baseline_versions(db, cycle.id)
    ]
    return ReviewCycleResponse(**data)


async def _build_cycle_item_lookup(
    db: AsyncSession,
    cycle_id: uuid.UUID,
) -> dict[tuple[Optional[uuid.UUID], str], tuple[ReviewItem, Requirement]]:
    rows_result = await db.execute(
        select(ReviewItem, Requirement)
        .join(Requirement, Requirement.id == ReviewItem.requirement_id)
        .where(ReviewItem.review_cycle_id == cycle_id)
    )
    lookup: dict[tuple[Optional[uuid.UUID], str], tuple[ReviewItem, Requirement]] = {}
    for item, requirement in rows_result.all():
        lookup[(requirement.document_id, requirement.reference_id)] = (item, requirement)
    return lookup


async def _build_latest_cycle_migration_preview(
    db: AsyncSession,
    cycle: ReviewCycle,
):
    if cycle.change_entry_id:
        raise HTTPException(409, "Change assessments preserve their selected impact scope. Update change impacts and start a new assessment for a different version.")
    if cycle.certification_project_id and cycle.cycle_type == "maintenance":
        raise HTTPException(
            status_code=409,
            detail="Project maintenance assessments preserve the project's pinned baseline. Update the project baseline and run the maintenance plan to start a new assessment.",
        )
    current_baselines = await _load_cycle_baseline_versions(db, cycle.id)
    if not current_baselines:
        raise HTTPException(
            status_code=409,
            detail="Review cycle baseline is empty. Locked requirement-set versions are required before migration.",
        )

    target_baselines: list[tuple[uuid.UUID, RequirementSetVersion, Optional[str]]] = []
    for baseline in current_baselines:
        latest_version = await _get_current_approved_version_for_document(db, baseline.document_id)
        if latest_version is None:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"No approved baseline version found for requirement set "
                    f"'{baseline.set_name or baseline.document_id}'."
                ),
            )
        target_baselines.append((baseline.document_id, latest_version, baseline.set_name))

    current_version_ids = [baseline.requirement_set_version_id for baseline in current_baselines]
    target_version_ids = [version.id for _, version, _ in target_baselines]
    if current_version_ids == target_version_ids:
        raise HTTPException(
            status_code=409,
            detail="Review cycle already uses the latest approved requirement-set versions.",
        )

    target_requirements = await _load_requirements_for_versions(
        db,
        cycle.jurisdiction_id,
        target_version_ids,
        organization_id=cycle.organization_id,
    )
    target_lookup = {
        (requirement.document_id, requirement.reference_id): requirement
        for requirement in target_requirements
    }
    set_name_by_document_id = {
        document_id: set_name for document_id, _, set_name in target_baselines
    }

    from_lookup = await _build_cycle_item_lookup(db, cycle.id)
    from_requirement_by_id = {
        requirement.id: (item, requirement) for item, requirement in from_lookup.values()
    }

    matched: list[ReviewCycleBaselineMigrationDeltaItem] = []
    changed: list[ReviewCycleBaselineMigrationDeltaItem] = []
    added: list[ReviewCycleBaselineMigrationDeltaItem] = []
    removed: list[ReviewCycleBaselineMigrationDeltaItem] = []
    matched_old_requirement_ids: set[uuid.UUID] = set()

    for key, requirement in target_lookup.items():
        previous = from_lookup.get(key)
        if previous is None and requirement.source_requirement_id is not None:
            previous = from_requirement_by_id.get(requirement.source_requirement_id)

        if previous is None:
            added.append(
                ReviewCycleBaselineMigrationDeltaItem(
                    document_id=requirement.document_id,
                    set_name=set_name_by_document_id.get(requirement.document_id),
                    reference_id=requirement.reference_id,
                    new_requirement_id=requirement.id,
                    new_text=requirement.text,
                )
            )
            continue

        _, old_requirement = previous
        matched_old_requirement_ids.add(old_requirement.id)
        delta_item = ReviewCycleBaselineMigrationDeltaItem(
            document_id=requirement.document_id,
            set_name=set_name_by_document_id.get(requirement.document_id),
            reference_id=requirement.reference_id,
            old_requirement_id=old_requirement.id,
            new_requirement_id=requirement.id,
            old_text=old_requirement.text,
            new_text=requirement.text,
        )
        if (
            old_requirement.text == requirement.text
            and old_requirement.requirement_type == requirement.requirement_type
        ):
            matched.append(delta_item)
        else:
            changed.append(delta_item)

    current_baseline_by_document_id = {
        baseline.document_id: baseline for baseline in current_baselines
    }
    for key, previous in from_lookup.items():
        _, old_requirement = previous
        if old_requirement.id in matched_old_requirement_ids or key in target_lookup:
            continue
        removed.append(
            ReviewCycleBaselineMigrationDeltaItem(
                document_id=old_requirement.document_id,
                set_name=(
                    current_baseline_by_document_id.get(old_requirement.document_id).set_name
                    if old_requirement.document_id in current_baseline_by_document_id
                    else None
                ),
                reference_id=old_requirement.reference_id,
                old_requirement_id=old_requirement.id,
                old_text=old_requirement.text,
            )
        )

    return {
        "current_baselines": current_baselines,
        "target_baselines": target_baselines,
        "target_version_ids": target_version_ids,
        "target_requirements": target_requirements,
        "from_lookup": from_lookup,
        "from_requirement_by_id": from_requirement_by_id,
        "matched": matched,
        "changed": changed,
        "added": added,
        "removed": removed,
    }


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _can_edit_comment(comment: ReviewItemComment, user: User, now: datetime) -> bool:
    if comment.author_id is None or comment.author_id != user.id:
        return False
    created_at = _ensure_aware(comment.created_at)
    return created_at + EDIT_WINDOW >= now


def _comment_response(
    comment: ReviewItemComment,
    author_name: str,
    can_edit: bool,
) -> ReviewItemCommentResponse:
    return ReviewItemCommentResponse(
        id=comment.id,
        review_item_id=comment.review_item_id,
        author_id=comment.author_id,
        author_name=author_name,
        body=comment.body,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
        can_edit=can_edit,
    )


def _smtp_ready(config) -> bool:
    return config.email_available


def _normalize_handle(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


async def _resolve_mentioned_users(
    db: AsyncSession,
    current_user: User,
    text: str,
    *,
    previous_text: str = "",
) -> list[User]:
    result = await db.execute(
        apply_org_scope(select(User).where(User.active.is_(True)), User, current_user)
    )
    users = result.scalars().all()
    aliases: dict[str, set[uuid.UUID]] = {}
    for user in users:
        email = user.email.casefold()
        local_part = email.split("@", 1)[0]
        for alias in (
            email, local_part, user.full_name,
            _normalize_handle(local_part), _normalize_handle(user.full_name),
        ):
            alias = " ".join(alias.split()).casefold()
            if alias:
                aliases.setdefault(alias, set()).add(user.id)
    if not aliases:
        return []

    # Match known identities, not arbitrary words after @. Longest names win so
    # tagging @Jane Smith does not also notify a different person named Jane.
    alternatives = "|".join(
        re.escape(alias).replace(r"\ ", r"[ \t]+")
        for alias in sorted(aliases, key=len, reverse=True)
    )
    pattern = re.compile(
        rf"(?<![\w@./+\-])@({alternatives})(?![\w@\-]|\.[\w])",
        re.IGNORECASE,
    )

    def mentioned_ids(body: str) -> set[uuid.UUID]:
        ids: set[uuid.UUID] = set()
        for match in pattern.finditer(body):
            alias = " ".join(match.group(1).split()).casefold()
            ids.update(aliases.get(alias, set()))
        return ids

    new_ids = mentioned_ids(text) - mentioned_ids(previous_text) - {current_user.id}
    return [user for user in users if user.id in new_ids]


def _build_mention_email(
    cycle: ReviewCycle,
    commenter: User,
    comment_body: str,
    item_id: uuid.UUID,
) -> tuple[str, str]:
    subject = f"You were mentioned in review cycle: {cycle.name}"
    lines = [
        "Hello,",
        "",
        f'{commenter.full_name} mentioned you in review cycle "{cycle.name}".',
        "",
        "Comment:",
        comment_body,
    ]
    if settings.frontend_base_url:
        lines.append("")
        lines.append(
            f"Open review item: {settings.frontend_base_url.rstrip('/')}/review-cycles/{cycle.id}"
            f"?mode=focus&item={item_id}"
        )
    return subject, "\n".join(lines)


async def _queue_comment_mention_emails(
    db: AsyncSession,
    background_tasks: BackgroundTasks,
    cycle: ReviewCycle,
    item: ReviewItem,
    commenter: User,
    body: str,
    *,
    previous_body: str = "",
) -> None:
    if "@" not in body:
        return
    runtime_settings = await resolve_installation_settings(db)
    if not _smtp_ready(runtime_settings):
        return
    mentioned_users = await _resolve_mentioned_users(
        db, commenter, body, previous_text=previous_body,
    )
    for user in mentioned_users:
        if not user.review_mentions:
            continue
        if not await _can_receive_cycle_notification(db, cycle, user):
            continue
        subject, email_body = _build_mention_email(cycle, commenter, body, item.id)
        background_tasks.add_task(
            send_email, [user.email], subject, email_body,
            config=runtime_settings, raise_on_error=False,
        )


def _short_text(value: Optional[str], limit: int = 140) -> str:
    if not value:
        return ""
    cleaned = " ".join(value.split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: max(0, limit - 3)]}..."


def _restored_cycle_status(cycle: ReviewCycle) -> str:
    if cycle.closed_at is not None or cycle.closed_by is not None or cycle.snapshot_id is not None:
        return "closed"
    return "active"


@router.post("/review-cycles", response_model=ReviewCycleResponse, status_code=201)
async def create_review_cycle(
    body: ReviewCycleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    if body.certification_project_id:
        await require_access(db, CertificationProject, body.certification_project_id, current_user, "edit")
    allowed_cycle_types = {"operational", "submission", "maintenance"}
    if body.cycle_type not in allowed_cycle_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported cycle_type. Allowed values: {', '.join(sorted(allowed_cycle_types))}",
        )
    if body.cycle_type == "submission" and body.certification_project_id is None:
        raise HTTPException(
            status_code=400,
            detail="certification_project_id is required for submission cycles",
        )

    if (
        body.scope == "documents"
        and not body.document_ids
        and body.certification_project_id is None
    ):
        raise HTTPException(
            status_code=400,
            detail="document_ids is required when scope is 'documents'",
        )

    jurisdiction_result = await db.execute(
        select(Jurisdiction).where(
            Jurisdiction.id == body.jurisdiction_id, Jurisdiction.active.is_(True)
        )
    )
    jurisdiction = jurisdiction_result.scalar_one_or_none()
    if jurisdiction is None:
        raise HTTPException(status_code=400, detail="Invalid or inactive jurisdiction_id")

    project: Optional[CertificationProject] = None
    baseline_pairs: list[tuple[uuid.UUID, uuid.UUID]] = []

    if body.certification_project_id is not None:
        project_query = apply_org_scope(
            select(CertificationProject).where(
                CertificationProject.id == body.certification_project_id
            ),
            CertificationProject,
            current_user,
        )
        project_result = await db.execute(project_query)
        project = project_result.scalar_one_or_none()
        if project is None:
            raise HTTPException(status_code=404, detail="Certification project not found")
        if project.jurisdiction_id != body.jurisdiction_id:
            raise HTTPException(
                status_code=400,
                detail="Project jurisdiction does not match review cycle jurisdiction",
            )
        if body.cycle_type == "submission":
            existing_submission_cycle = await db.execute(
                apply_org_scope(select(ReviewCycle), ReviewCycle, current_user).where(
                    and_(
                        ReviewCycle.certification_project_id == body.certification_project_id,
                        ReviewCycle.cycle_type == "submission",
                        ReviewCycle.status != "archived",
                    )
                )
            )
            if existing_submission_cycle.scalar_one_or_none() is not None:
                raise HTTPException(
                    status_code=409,
                    detail="A submission review cycle already exists for this project",
                )
        baseline_result = await db.execute(
            select(
                CertificationProjectRequirementBaseline.document_id,
                CertificationProjectRequirementBaseline.requirement_set_version_id,
            ).where(CertificationProjectRequirementBaseline.project_id == project.id)
        )
        baseline_pairs = baseline_result.all()
        if not baseline_pairs:
            raise HTTPException(
                status_code=409,
                detail="Project baseline is empty. Select requirement sets before creating a review cycle.",
            )

    if body.certification_project_id is None and body.scope == "documents" and body.document_ids:
        docs_result = await db.execute(
            apply_org_scope(
                select(Document).where(Document.id.in_(body.document_ids)),
                Document,
                current_user,
            )
        )
        docs = docs_result.scalars().all()
        if len(docs) != len(body.document_ids):
            raise HTTPException(status_code=400, detail="One or more documents not found")
        not_approved = [d.id for d in docs if d.status != "approved"]
        if not_approved:
            raise HTTPException(
                status_code=400,
                detail="All selected requirement sets must be approved",
            )
        doc_jurisdictions = {d.jurisdiction_id for d in docs}
        if len(doc_jurisdictions) != 1:
            raise HTTPException(
                status_code=400,
                detail="All selected documents must belong to the same jurisdiction",
            )
        if next(iter(doc_jurisdictions)) != body.jurisdiction_id:
            raise HTTPException(
                status_code=400,
                detail="Selected documents do not match jurisdiction_id",
            )
        for doc in docs:
            version_result = await db.execute(
                select(RequirementSetVersion)
                .where(
                    and_(
                        RequirementSetVersion.document_id == doc.id,
                        RequirementSetVersion.status == "approved",
                        RequirementSetVersion.is_current.is_(True),
                    )
                )
                .limit(1)
            )
            version = version_result.scalar_one_or_none()
            if version is None:
                fallback_result = await db.execute(
                    select(RequirementSetVersion)
                    .where(
                        and_(
                            RequirementSetVersion.document_id == doc.id,
                            RequirementSetVersion.status == "approved",
                        )
                    )
                    .order_by(RequirementSetVersion.version_number.desc())
                    .limit(1)
                )
                version = fallback_result.scalar_one_or_none()
            if version is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"No approved baseline version found for requirement set '{doc.name or doc.filename}'",
                )
            baseline_pairs.append((doc.id, version.id))
    elif body.certification_project_id is None and body.scope == "all":
        docs_result = await db.execute(
            apply_org_scope(select(Document), Document, current_user).where(
                and_(
                    Document.jurisdiction_id == body.jurisdiction_id,
                    Document.status == "approved",
                )
            )
        )
        docs = docs_result.scalars().all()
        for doc in docs:
            version_result = await db.execute(
                select(RequirementSetVersion)
                .where(
                    and_(
                        RequirementSetVersion.document_id == doc.id,
                        RequirementSetVersion.status == "approved",
                        RequirementSetVersion.is_current.is_(True),
                    )
                )
                .limit(1)
            )
            version = version_result.scalar_one_or_none()
            if version is None:
                fallback_result = await db.execute(
                    select(RequirementSetVersion)
                    .where(
                        and_(
                            RequirementSetVersion.document_id == doc.id,
                            RequirementSetVersion.status == "approved",
                        )
                    )
                    .order_by(RequirementSetVersion.version_number.desc())
                    .limit(1)
                )
                version = fallback_result.scalar_one_or_none()
            if version is not None:
                baseline_pairs.append((doc.id, version.id))

    if not baseline_pairs:
        if body.scope == "documents":
            raise HTTPException(
                status_code=400,
                detail="No approved baseline versions found for the selected requirement sets",
            )
        raise HTTPException(
            status_code=400,
            detail="No approved requirement set baselines found for this jurisdiction",
        )

    scope_document_ids = [document_id for document_id, _ in baseline_pairs]
    cycle = ReviewCycle(
        organization_id=current_user.organization_id,
        certification_project_id=body.certification_project_id,
        cycle_type=body.cycle_type,
        name=body.name,
        jurisdiction_id=body.jurisdiction_id,
        description=body.description,
        scope="documents" if scope_document_ids else body.scope,
        scope_filter=(
            json.dumps([str(doc_id) for doc_id in scope_document_ids])
            if scope_document_ids
            else body.scope_filter
        ),
        deadline=body.deadline,
        created_by=current_user.id,
    )
    db.add(cycle)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        if body.cycle_type == "submission" and body.certification_project_id is not None:
            raise HTTPException(
                status_code=409,
                detail="A submission review cycle already exists for this project",
            ) from exc
        raise HTTPException(
            status_code=409,
            detail="Review cycle could not be created due to a conflicting record",
        ) from exc

    default_assigned_reviewer_id = body.default_assigned_reviewer_id
    default_responsible_user_id = body.default_responsible_user_id
    if default_assigned_reviewer_id is not None:
        await get_active_user_in_org_or_404(
            db,
            default_assigned_reviewer_id,
            current_user,
            detail="Default assigned reviewer not found or inactive",
        )
    if default_responsible_user_id is not None:
        await get_active_user_in_org_or_404(
            db,
            default_responsible_user_id,
            current_user,
            detail="Default responsible user not found or inactive",
        )

    for document_id, version_id in baseline_pairs:
        db.add(
            ReviewCycleRequirementBaseline(
                review_cycle_id=cycle.id,
                document_id=document_id,
                requirement_set_version_id=version_id,
            )
        )

    baseline_version_ids = [version_id for _, version_id in baseline_pairs]
    requirements_result = await db.execute(
        apply_org_scope(select(Requirement), Requirement, current_user)
        .where(
            and_(
                Requirement.active.is_(True),
                Requirement.jurisdiction_id == body.jurisdiction_id,
                Requirement.requirement_set_version_id.in_(baseline_version_ids),
            )
        )
        .order_by(Requirement.document_id.asc(), Requirement.sort_order.asc())
    )
    requirements = requirements_result.scalars().all()

    for req in requirements:
        review_status, review_comment = _default_review_state_for_requirement(req)
        item_id = uuid.uuid4()
        item = ReviewItem(
            id=item_id,
            review_cycle_id=cycle.id,
            requirement_id=req.id,
            review_status=review_status,
            assessment_status="not_applicable" if req.requirement_type == "not_applicable" else "not_started",
            review_comment=review_comment,
            assigned_reviewer_id=default_assigned_reviewer_id,
            responsible_user_id=default_responsible_user_id,
        )
        db.add(item)
        if review_comment:
            db.add(
                ReviewItemComment(
                    review_item_id=item_id,
                    author_id=None,
                    body=review_comment,
                )
            )

    await log_action(
        db,
        current_user,
        "create",
        "review_cycle",
        str(cycle.id),
        new_value={
            "name": cycle.name,
            "cycle_type": cycle.cycle_type,
            "certification_project_id": (
                str(cycle.certification_project_id) if cycle.certification_project_id else None
            ),
            "requirements_count": len(requirements),
        },
    )
    await db.commit()
    await db.refresh(cycle)
    return await _cycle_response(db, cycle)


@router.get("/review-cycles", response_model=ReviewCycleListResponse)
async def list_review_cycles(
    skip: int = 0,
    limit: int = 20,
    status: Optional[str] = None,
    jurisdiction_id: Optional[uuid.UUID] = None,
    certification_project_id: Optional[uuid.UUID] = None,
    change_entry_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReviewCycleListResponse:
    query = apply_org_scope(select(ReviewCycle), ReviewCycle, current_user)
    count_query = apply_org_scope(select(func.count(ReviewCycle.id)), ReviewCycle, current_user)

    if status:
        query = query.where(ReviewCycle.status == status)
        count_query = count_query.where(ReviewCycle.status == status)

    if jurisdiction_id:
        query = query.where(ReviewCycle.jurisdiction_id == jurisdiction_id)
        count_query = count_query.where(ReviewCycle.jurisdiction_id == jurisdiction_id)

    if certification_project_id:
        query = query.where(ReviewCycle.certification_project_id == certification_project_id)
        count_query = count_query.where(
            ReviewCycle.certification_project_id == certification_project_id
        )

    if change_entry_id:
        query = query.where(ReviewCycle.change_entry_id == change_entry_id)
        count_query = count_query.where(ReviewCycle.change_entry_id == change_entry_id)

    total_result = await db.execute(count_query)
    total = int(total_result.scalar() or 0)

    query = query.order_by(ReviewCycle.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    cycles = result.scalars().all()

    items: list[ReviewCycleResponse] = []
    for cycle in cycles:
        items.append(await _cycle_response(db, cycle))
    return ReviewCycleListResponse(items=items, total=total)


@router.get("/review-cycles/{cycle_id}", response_model=ReviewCycleWithItemsResponse)
async def get_review_cycle(
    cycle_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cycle = await _get_review_cycle_for_user(db, current_user, cycle_id)

    snapshot_warning = None
    try:
        rows = await assessment_rows(db, cycle)
    except HTTPException as exc:
        if exc.status_code != 409 or "legacy closed review" not in str(exc.detail):
            raise
        snapshot_warning = str(exc.detail)
        rows = await assessment_rows(db, cycle, use_snapshot=False)
    if current_user.role == "assigned_reviewer":
        rows = [row for row in rows if row.item.assigned_reviewer_id == current_user.id]
    progress_rows = [
        row
        for row in rows
        if is_review_progress_eligible(row.requirement.requirement_type, row.status)
    ]
    author_ids = {
        comment.author_id for row in rows for comment in row.comments if comment.author_id
    }
    authors = (
        {
            u.id: u.full_name
            for u in (
                await db.execute(
                    select(User).where(
                        User.id.in_(author_ids),
                        User.organization_id == current_user.organization_id,
                    )
                )
            ).scalars()
        }
        if author_ids
        else {}
    )
    response_items = []
    for row in rows:
        item_data = ReviewItemResponse.model_validate(row.item).model_dump()
        item_data["requirement"] = RequirementSummary.model_validate(row.requirement)
        item_data["requirement_current_status"] = row.status
        item_data["reviewer_name"] = (row.reviewer.full_name or row.reviewer.email) if row.reviewer else None
        changed_at = row.item.evidence_changed_at
        reviewed_at = row.item.reviewed_at
        item_data["evidence_changed_since_review"] = bool(
            changed_at and reviewed_at and changed_at > reviewed_at
            and row.item.review_status in {"confirmed", "updated"}
        )
        item_data["comments"] = [
            _comment_response(
                c,
                authors.get(c.author_id, "System"),
                cycle.status == "active"
                and _can_edit_comment(c, current_user, datetime.now(timezone.utc)),
            )
            for c in row.comments
        ]
        item_data["evidence_files"] = [
            ReviewItemEvidenceFileResponse.model_validate(f) for f in row.files
        ]
        response_items.append(ReviewItemWithRequirementResponse(**item_data))
    integration = await get_jira_integration(db, current_user.organization_id)
    return ReviewCycleWithItemsResponse(
        **(await _cycle_response(db, cycle)).model_dump(),
        jira_integration_configured=bool(integration and integration.enabled),
        items=response_items,
        readiness={**readiness(rows), "snapshot_warning": snapshot_warning},
        progress={
            "total": len(progress_rows),
            "completed": sum(
                r.item.review_status in COMPLETED_REVIEW_STATUSES for r in progress_rows
            ),
            "pending": sum(
                r.item.review_status not in COMPLETED_REVIEW_STATUSES for r in progress_rows
            ),
        },
    )


@router.post(
    "/review-cycles/{cycle_id}/baseline-migrations/preview",
    response_model=ReviewCycleBaselineMigrationPreviewResponse,
)
async def preview_review_cycle_latest_baseline_migration(
    cycle_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    cycle = await _get_review_cycle_for_user(db, current_user, cycle_id, action="edit")
    if cycle.status != "active":
        raise HTTPException(
            status_code=409,
            detail="Only active review cycles can be migrated to the latest requirements.",
        )

    preview = await _build_latest_cycle_migration_preview(db, cycle)
    return ReviewCycleBaselineMigrationPreviewResponse(
        source_cycle_id=cycle.id,
        target_version_ids=preview["target_version_ids"],
        matched=preview["matched"],
        changed=preview["changed"],
        added=preview["added"],
        removed=preview["removed"],
    )


@router.post(
    "/review-cycles/{cycle_id}/baseline-migrations/execute",
    response_model=ReviewCycleBaselineMigrationExecuteResponse,
)
async def execute_review_cycle_latest_baseline_migration(
    cycle_id: uuid.UUID,
    body: ReviewCycleBaselineMigrationExecuteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    if not body.target_version_ids:
        raise HTTPException(
            status_code=400,
            detail="target_version_ids is required. Generate a migration preview before executing.",
        )

    cycle = await _get_review_cycle_for_user(db, current_user, cycle_id, writable=True)
    if cycle.status != "active":
        raise HTTPException(
            status_code=409,
            detail="Only active review cycles can be migrated to the latest requirements.",
        )

    preview = await _build_latest_cycle_migration_preview(db, cycle)
    current_target_ids = preview["target_version_ids"]
    if set(body.target_version_ids) != set(current_target_ids) or len(
        body.target_version_ids
    ) != len(current_target_ids):
        raise HTTPException(
            status_code=409,
            detail="Latest requirement versions changed after preview. Generate a new migration preview before executing.",
        )

    changed_decision_by_requirement_id: dict[
        uuid.UUID, ReviewCycleBaselineMigrationChangedDecision
    ] = {decision.new_requirement_id: decision for decision in body.changed_decisions}
    cloned_file_paths: list[str] = []
    try:
        # Release the active submission-cycle slot before inserting its successor.
        cycle.status = "archived"
        await db.flush()
        successor_cycle = ReviewCycle(
            organization_id=cycle.organization_id,
            certification_project_id=cycle.certification_project_id,
            predecessor_cycle_id=cycle.id,
            change_entry_id=cycle.change_entry_id,
            cycle_type=cycle.cycle_type,
            name=f"{cycle.name} (migrated)"[:255],
            jurisdiction_id=cycle.jurisdiction_id,
            description=cycle.description,
            scope="documents",
            scope_filter=json.dumps(
                [str(document_id) for document_id, _, _ in preview["target_baselines"]]
            ),
            deadline=cycle.deadline,
            status="active",
            created_by=current_user.id,
        )
        db.add(successor_cycle)
        await db.flush()

        for document_id, version, _ in preview["target_baselines"]:
            db.add(
                ReviewCycleRequirementBaseline(
                    review_cycle_id=successor_cycle.id,
                    document_id=document_id,
                    requirement_set_version_id=version.id,
                )
            )

        migration_result = await clone_review_cycle_items_for_migration(
            db=db,
            successor_cycle_id=successor_cycle.id,
            target_requirements=preview["target_requirements"],
            previous_lookup=preview["from_lookup"],
            previous_lookup_by_source_id=preview["from_requirement_by_id"],
            should_carry_forward=lambda requirement, _previous_item, previous_requirement: (
                (
                    previous_requirement.text == requirement.text
                    and previous_requirement.requirement_type == requirement.requirement_type
                )
                or (
                    changed_decision_by_requirement_id.get(requirement.id) is not None
                    and changed_decision_by_requirement_id[requirement.id].action == "carry_forward"
                )
            ),
            default_review_state_for_requirement=_default_review_state_for_requirement,
            current_user_id=current_user.id,
        )
        cloned_file_paths = migration_result.cloned_file_paths
        migrated_items = migration_result.migrated_items

        await log_action(
            db,
            current_user,
            "migrate",
            "review_cycle_baseline",
            str(successor_cycle.id),
            new_value={
                "from_cycle_id": str(cycle.id),
                "to_cycle_id": str(successor_cycle.id),
                "target_version_ids": [str(version_id) for version_id in current_target_ids],
                "migrated_items": migrated_items,
            },
        )
        await db.commit()
    except ReviewMigrationCloneError as exc:
        await db.rollback()
        cleanup_cloned_files(cloned_file_paths)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception:
        await db.rollback()
        cleanup_cloned_files(cloned_file_paths)
        raise

    return ReviewCycleBaselineMigrationExecuteResponse(
        created=True,
        from_cycle_id=cycle.id,
        to_cycle_id=successor_cycle.id,
        migrated_items=migrated_items,
    )


@router.post("/review-cycles/{cycle_id}/archive", response_model=ReviewCycleResponse)
async def archive_review_cycle(
    cycle_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    cycle = await _get_review_cycle_for_user(db, current_user, cycle_id, action="edit")
    if cycle.status == "archived":
        raise HTTPException(status_code=400, detail="Review cycle is already archived")

    old_status = cycle.status
    cycle.status = "archived"

    await log_action(
        db,
        current_user,
        "archive",
        "review_cycle",
        str(cycle.id),
        old_value={"status": old_status},
        new_value={"status": "archived"},
    )
    await db.commit()
    await db.refresh(cycle)
    return await _cycle_response(db, cycle)


@router.post("/review-cycles/{cycle_id}/restore", response_model=ReviewCycleResponse)
async def restore_review_cycle(
    cycle_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    cycle = await _get_review_cycle_for_user(db, current_user, cycle_id, action="edit")
    if cycle.status != "archived":
        raise HTTPException(status_code=400, detail="Review cycle is not archived")

    restored_status = _restored_cycle_status(cycle)

    if cycle.cycle_type == "submission" and cycle.certification_project_id is not None:
        conflicting_submission_result = await db.execute(
            select(ReviewCycle.id)
            .where(
                and_(
                    ReviewCycle.certification_project_id == cycle.certification_project_id,
                    ReviewCycle.cycle_type == "submission",
                    ReviewCycle.status != "archived",
                    ReviewCycle.id != cycle.id,
                )
            )
            .limit(1)
        )
        if conflicting_submission_result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=409,
                detail="A submission review cycle already exists for this project",
            )

    cycle.status = restored_status

    await log_action(
        db,
        current_user,
        "restore",
        "review_cycle",
        str(cycle.id),
        old_value={"status": "archived"},
        new_value={"status": restored_status},
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if cycle.cycle_type == "submission" and cycle.certification_project_id is not None:
            raise HTTPException(
                status_code=409,
                detail="A submission review cycle already exists for this project",
            ) from exc
        raise HTTPException(
            status_code=409,
            detail="Review cycle could not be restored due to a conflicting record",
        ) from exc
    await db.refresh(cycle)
    return await _cycle_response(db, cycle)


@router.delete("/review-cycles/{cycle_id}", status_code=204)
async def delete_review_cycle(
    cycle_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    cycle = await _get_review_cycle_for_user(db, current_user, cycle_id, action="edit")

    result = await db.execute(select(ReviewCycle).where(ReviewCycle.id == cycle.id)
                              .with_for_update().execution_options(populate_existing=True))
    cycle = result.scalar_one()
    if cycle.closed_at or cycle.snapshot_id or cycle.status == "closed":
        raise HTTPException(409, "Completed reviews must be retained. Archive this review instead.")

    item_ids_result = await db.execute(
        select(ReviewItem.id).where(ReviewItem.review_cycle_id == cycle_id)
    )
    item_ids = item_ids_result.scalars().all()

    if item_ids:
        files_result = await db.execute(
            select(ReviewItemEvidenceFile).where(
                ReviewItemEvidenceFile.review_item_id.in_(item_ids)
            )
        )
        evidence_files = files_result.scalars().all()
        for evidence_file in evidence_files:
            if os.path.exists(evidence_file.file_path):
                try:
                    os.remove(evidence_file.file_path)
                except OSError:
                    logger.warning(
                        "Failed to remove review evidence file during cycle delete: %s",
                        evidence_file.file_path,
                        exc_info=True,
                    )

        await db.execute(
            delete(ReviewItemComment).where(ReviewItemComment.review_item_id.in_(item_ids))
        )
        await db.execute(
            delete(ReviewItemEvidenceFile).where(
                ReviewItemEvidenceFile.review_item_id.in_(item_ids)
            )
        )

    await db.execute(delete(ReviewItem).where(ReviewItem.review_cycle_id == cycle_id))
    await db.execute(
        delete(ReviewCycleRequirementBaseline).where(
            ReviewCycleRequirementBaseline.review_cycle_id == cycle_id
        )
    )
    await db.execute(
        update(ReviewCycle)
        .where(ReviewCycle.predecessor_cycle_id == cycle_id)
        .values(predecessor_cycle_id=None)
    )
    await db.execute(
        update(SubmissionPackage)
        .where(SubmissionPackage.review_cycle_id == cycle_id)
        .values(review_cycle_id=None)
    )
    await db.execute(
        update(BaselineMigration)
        .where(BaselineMigration.from_cycle_id == cycle_id)
        .values(from_cycle_id=None)
    )
    await db.execute(
        update(BaselineMigration)
        .where(BaselineMigration.to_cycle_id == cycle_id)
        .values(to_cycle_id=None)
    )
    await db.execute(
        update(MaintenanceEvent)
        .where(MaintenanceEvent.review_cycle_id == cycle_id)
        .values(review_cycle_id=None)
    )

    old_value = {
        "name": cycle.name,
        "status": cycle.status,
        "items_deleted": len(item_ids),
    }
    await log_action(
        db,
        current_user,
        "delete",
        "review_cycle",
        str(cycle.id),
        old_value=old_value,
    )
    await db.delete(cycle)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        logger.exception("Failed to delete review cycle %s due to linked records", cycle_id)
        raise HTTPException(
            status_code=409,
            detail="Review cycle cannot be deleted because it is still referenced by related records",
        ) from exc


@router.put("/review-cycles/{cycle_id}/items/{item_id}", response_model=ReviewItemResponse)
async def update_review_item(
    cycle_id: uuid.UUID,
    item_id: uuid.UUID,
    body: ReviewItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cycle, item = await _get_review_item_for_cycle(db, current_user, cycle_id, item_id)
    if current_user.role == "assigned_reviewer" and item.assigned_reviewer_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only update review items assigned to you",
        )

    if body.requirement_status == "not_applicable" and current_user.role not in [
        "manager", "approver", "admin"
    ]:
        raise HTTPException(
            status_code=403,
            detail="Only approvers, managers, or admins can mark requirements as not applicable",
        )
    assessment_changes = {}
    if body.requirement_status is not None:
        assessment_changes["status"] = body.requirement_status
    if "review_evidence" in body.model_fields_set:
        assessment_changes["evidence"] = body.review_evidence
    if assessment_changes:
        try:
            update_assessment(
                item,
                legacy_status=await legacy_assessment_status(db, item),
                **assessment_changes,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    old_status = item.review_status
    if body.review_status is not None:
        item.review_status = body.review_status
        item.reviewer_id = current_user.id
        item.reviewed_at = datetime.now(timezone.utc)
    if body.requirement_status is not None and not (
        cycle.certification_project_id
        and await _project_is_confidential(db, cycle.certification_project_id)
    ):
        current_result = await db.execute(
            select(RequirementStatus)
            .where(RequirementStatus.requirement_id == item.requirement_id)
            .order_by(RequirementStatus.changed_at.desc(), RequirementStatus.id.desc())
            .limit(1)
        )
        current_status = current_result.scalar_one_or_none()

        new_status = RequirementStatus(
            requirement_id=item.requirement_id,
            status=body.requirement_status,
            assigned_to=current_status.assigned_to if current_status else None,
            comment=(body.review_evidence or "").strip(),
            changed_by=current_user.id,
            changed_at=datetime.now(timezone.utc),
        )
        db.add(new_status)

        await log_action(
            db,
            current_user,
            "status_change",
            "requirement",
            str(item.requirement_id),
            old_value={"status": current_status.status if current_status else None},
            new_value={"status": body.requirement_status, "evidence": body.review_evidence},
        )

    await log_action(
        db,
        current_user,
        "update",
        "review_item",
        str(item.id),
        old_value={"review_status": old_status},
        new_value={
            "review_status": item.review_status,
            "evidence": item.review_evidence,
        },
    )
    await db.commit()
    await db.refresh(item)
    return item


@router.put(
    "/review-cycles/{cycle_id}/items/{item_id}/jira",
    response_model=ReviewItemResponse,
)
async def update_review_item_jira(
    cycle_id: uuid.UUID,
    item_id: uuid.UUID,
    body: ReviewItemJiraUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "assigned_reviewer":
        raise HTTPException(
            status_code=403,
            detail="Assigned reviewers can only update review status and comments",
        )
    if current_user.role not in {"admin", "manager", "contributor"}:
        raise HTTPException(status_code=403, detail="Insufficient role")

    _, item = await _get_review_item_for_cycle(db, current_user, cycle_id, item_id)

    integration = await get_jira_integration(db, current_user.organization_id)
    old_value = {"jira_issue_key": item.jira_issue_key}
    try:
        normalized_key = apply_item_jira_key(
            item,
            issue_key=body.jira_issue_key,
            project_key=integration.project_key if integration else None,
            base_url=integration.base_url if integration and integration.enabled else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await log_action(
        db,
        current_user,
        "update_jira",
        "review_item",
        str(item.id),
        old_value=old_value,
        new_value={"jira_issue_key": normalized_key},
    )
    await db.commit()
    await db.refresh(item)
    return item


@router.post(
    "/review-cycles/{cycle_id}/jira-sync",
    response_model=ReviewCycleJiraSyncResponse,
)
async def sync_review_cycle_jira(
    cycle_id: uuid.UUID,
    body: ReviewCycleJiraSyncRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cycle = await _get_review_cycle_for_user(db, current_user, cycle_id, writable=True)
    if cycle.certification_project_id:
        # Even an import sends the linked issue identifiers to the external service.
        await require_access(
            db, CertificationProject, cycle.certification_project_id, current_user, "export"
        )

    summary = await sync_review_cycle_jira_items(
        db,
        cycle_id,
        force=bool(body.force),
        assigned_reviewer_id=current_user.id if current_user.role == "assigned_reviewer" else None,
    )

    await log_action(
        db,
        current_user,
        "sync_jira",
        "review_cycle",
        str(cycle.id),
        new_value={"force": bool(body.force), **summary.to_dict()},
    )
    await db.commit()
    return ReviewCycleJiraSyncResponse(**summary.to_dict())


@router.patch(
    "/review-cycles/{cycle_id}/items/bulk",
    response_model=ReviewItemBulkMutationResponse,
)
async def bulk_mutate_review_items(
    cycle_id: uuid.UUID,
    body: ReviewItemBulkMutationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cycle = await _get_review_cycle_for_user(db, current_user, cycle_id, writable=True)
    fields_set = body.model_fields_set - {"item_ids"}
    if not fields_set:
        raise HTTPException(status_code=400, detail="At least one bulk mutation field is required")

    if "assigned_reviewer_id" in fields_set and current_user.role not in {"admin", "manager"}:
        raise HTTPException(
            status_code=403, detail="Only managers or admins can bulk assign reviewers"
        )
    if "responsible_user_id" in fields_set and current_user.role not in {
        "admin",
        "manager",
        "assigned_reviewer",
    }:
        raise HTTPException(status_code=403, detail="Insufficient role to bulk assign owners")
    if (
        "assigned_reviewer_id" not in fields_set
        and "responsible_user_id" not in fields_set
        and current_user.role
        not in {"admin", "manager", "approver", "contributor", "assigned_reviewer"}
    ):
        raise HTTPException(status_code=403, detail="Insufficient role")

    if "assigned_reviewer_id" in fields_set and body.assigned_reviewer_id is not None:
        await get_active_user_in_org_or_404(
            db,
            body.assigned_reviewer_id,
            current_user,
            detail="Assigned reviewer not found or inactive",
        )
    if "responsible_user_id" in fields_set and body.responsible_user_id is not None:
        await get_active_user_in_org_or_404(
            db,
            body.responsible_user_id,
            current_user,
            detail="Responsible user not found or inactive",
        )

    item_ids = list(dict.fromkeys(body.item_ids))
    items_result = await db.execute(
        select(ReviewItem).where(
            ReviewItem.review_cycle_id == cycle.id,
            ReviewItem.id.in_(item_ids),
        )
    )
    items_by_id = {item.id: item for item in items_result.scalars().all()}
    failures: list[ReviewItemBulkMutationFailure] = []
    updated_item_ids: list[uuid.UUID] = []
    now = datetime.now(timezone.utc)

    for item_id in item_ids:
        item = items_by_id.get(item_id)
        if item is None:
            failures.append(
                ReviewItemBulkMutationFailure(item_id=item_id, detail="Review item not found")
            )
            continue
        if (
            current_user.role == "assigned_reviewer"
            and item.assigned_reviewer_id != current_user.id
        ):
            failures.append(
                ReviewItemBulkMutationFailure(
                    item_id=item_id,
                    detail="You can only bulk update review items assigned to you",
                )
            )
            continue

        if "review_evidence" in fields_set:
            try:
                update_assessment(
                    item,
                    evidence=body.review_evidence,
                    legacy_status=await legacy_assessment_status(db, item),
                )
            except ValueError as exc:
                failures.append(ReviewItemBulkMutationFailure(item_id=item_id, detail=str(exc)))
                continue

        if "review_status" in fields_set and body.review_status is not None:
            item.review_status = body.review_status
            item.reviewer_id = current_user.id
            item.reviewed_at = now
        if "assigned_reviewer_id" in fields_set:
            item.assigned_reviewer_id = body.assigned_reviewer_id
        if "responsible_user_id" in fields_set:
            item.responsible_user_id = body.responsible_user_id

        updated_item_ids.append(item.id)

    await log_action(
        db,
        current_user,
        "bulk_update",
        "review_item",
        str(cycle.id),
        new_value={
            "updated_count": len(updated_item_ids),
            "failed_count": len(failures),
            "fields": sorted(fields_set),
            "item_ids": [str(item_id) for item_id in updated_item_ids],
        },
    )
    await db.commit()
    return ReviewItemBulkMutationResponse(
        updated_count=len(updated_item_ids),
        failed_count=len(failures),
        updated_item_ids=updated_item_ids,
        failures=failures,
    )


@router.put(
    "/review-cycles/{cycle_id}/items/{item_id}/assign",
    response_model=ReviewItemResponse,
)
async def assign_review_item(
    cycle_id: uuid.UUID,
    item_id: uuid.UUID,
    body: ReviewItemAssign,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _, item = await _get_review_item_for_cycle(db, current_user, cycle_id, item_id)

    if current_user.role not in {"admin", "manager", "assigned_reviewer"}:
        raise HTTPException(status_code=403, detail="Insufficient role")

    fields_set = body.model_fields_set
    if current_user.role == "assigned_reviewer":
        if item.assigned_reviewer_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="You can only update responsibility for your assigned items",
            )
        if "assigned_reviewer_id" in fields_set:
            raise HTTPException(
                status_code=403,
                detail="Assigned reviewers cannot change assigned reviewer",
            )

    assigned_reviewer_id = (
        body.assigned_reviewer_id if "assigned_reviewer_id" in fields_set else None
    )
    responsible_user_id = body.responsible_user_id if "responsible_user_id" in fields_set else None

    if "assigned_reviewer_id" in fields_set and assigned_reviewer_id is not None:
        await get_active_user_in_org_or_404(
            db,
            assigned_reviewer_id,
            current_user,
            detail="Assigned reviewer not found or inactive",
        )

    if "responsible_user_id" in fields_set and responsible_user_id is not None:
        await get_active_user_in_org_or_404(
            db,
            responsible_user_id,
            current_user,
            detail="Responsible user not found or inactive",
        )

    old_value = {
        "assigned_reviewer_id": (
            str(item.assigned_reviewer_id) if item.assigned_reviewer_id else None
        ),
        "responsible_user_id": str(item.responsible_user_id) if item.responsible_user_id else None,
    }
    new_value: dict[str, str | None] = {}
    if "assigned_reviewer_id" in fields_set:
        item.assigned_reviewer_id = assigned_reviewer_id
        new_value["assigned_reviewer_id"] = (
            str(assigned_reviewer_id) if assigned_reviewer_id else None
        )
    if "responsible_user_id" in fields_set:
        item.responsible_user_id = responsible_user_id
        new_value["responsible_user_id"] = str(responsible_user_id) if responsible_user_id else None

    await log_action(
        db,
        current_user,
        "assign",
        "review_item",
        str(item.id),
        old_value=old_value,
        new_value=new_value,
    )
    await db.commit()
    await db.refresh(item)
    return item


@router.post("/review-cycles/{cycle_id}/remind-assigned", response_model=dict)
async def remind_assigned_reviewers(
    cycle_id: uuid.UUID,
    body: ReviewCycleReminderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    if not body.review_statuses:
        raise HTTPException(status_code=400, detail="review_statuses cannot be empty")

    cycle = await _get_review_cycle_for_user(db, current_user, cycle_id, writable=True)
    runtime_settings = await resolve_installation_settings(db)
    if not runtime_settings.email_available:
        raise HTTPException(503, "Email delivery is disabled or not configured for this installation.")


    items_result = await db.execute(
        select(ReviewItem, Requirement, Document)
        .join(Requirement, Requirement.id == ReviewItem.requirement_id)
        .outerjoin(Document, Document.id == Requirement.document_id)
        .where(
            ReviewItem.review_cycle_id == cycle_id,
            ReviewItem.review_status.in_(body.review_statuses),
            or_(
                ReviewItem.assigned_reviewer_id.is_not(None),
                ReviewItem.responsible_user_id.is_not(None),
            ),
        )
        .order_by(Document.id, Requirement.sort_order)
    )
    rows = items_result.all()

    user_ids: set[uuid.UUID] = set()
    for item, _, _ in rows:
        if item.assigned_reviewer_id:
            user_ids.add(item.assigned_reviewer_id)
        if item.responsible_user_id:
            user_ids.add(item.responsible_user_id)

    users_by_id: dict[uuid.UUID, User] = {}
    if user_ids:
        user_result = await db.execute(
            apply_org_scope(select(User), User, current_user).where(
                User.id.in_(user_ids),
                User.active.is_(True),
            )
        )
        users_by_id = {u.id: u for u in user_result.scalars().all()}

    items_by_reviewer: dict[uuid.UUID, dict] = {}
    for item, requirement, document in rows:
        recipient_ids = []
        if item.assigned_reviewer_id:
            recipient_ids.append(item.assigned_reviewer_id)
        if item.responsible_user_id and item.responsible_user_id not in recipient_ids:
            recipient_ids.append(item.responsible_user_id)

        for recipient_id in recipient_ids:
            reviewer = users_by_id.get(recipient_id)
            if (
                reviewer is None
                or not reviewer.review_reminders
                or not await _can_receive_cycle_notification(db, cycle, reviewer)
            ):
                continue
            entry = items_by_reviewer.setdefault(reviewer.id, {"reviewer": reviewer, "items": []})
            entry["items"].append((item, requirement, document))

    reviewers_emailed = 0
    items_included = 0
    failures: list[dict[str, str]] = []
    deadline = cycle.deadline.isoformat() if cycle.deadline else "No deadline"
    statuses_label = ", ".join(body.review_statuses)

    for entry in items_by_reviewer.values():
        reviewer = entry["reviewer"]
        items = entry["items"]
        if not items:
            continue
        items_included += len(items)
        subject = f"Review Cycle Reminder: {cycle.name}"
        lines = [
            f"Hello {reviewer.full_name},",
            "",
            f'This is a reminder for review cycle "{cycle.name}".',
            f"Deadline: {deadline}",
            f"Statuses included: {statuses_label}",
            "",
            "Items:",
        ]
        for item, requirement, document in items:
            doc_name = (document.name or document.filename) if document else "Unknown Document"
            summary = _short_text(requirement.title or requirement.text)
            lines.append(
                f"- [{doc_name}] {requirement.reference_id} - {summary} (status: {item.review_status})"
            )
        if settings.frontend_base_url:
            lines.append("")
            lines.append(
                f"Review cycle: {settings.frontend_base_url.rstrip('/')}/review-cycles/{cycle.id}"
            )
        body_text = "\n".join(lines)
        try:
            await run_in_threadpool(
                send_email,
                [reviewer.email],
                subject,
                body_text,
                config=runtime_settings,
            )
            reviewers_emailed += 1
        except EmailConfigError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except smtplib.SMTPResponseException as exc:
            failures.append(
                {"email": reviewer.email, "error": f"SMTP server rejected the message (code {exc.smtp_code})."}
            )
        except Exception:
            failures.append({"email": reviewer.email, "error": "Email delivery failed. Ask a system admin to test Email settings."})

    await log_action(
        db,
        current_user,
        "notify",
        "review_cycle",
        str(cycle.id),
        new_value={
            "reviewers_emailed": reviewers_emailed,
            "items_included": items_included,
            "review_statuses": body.review_statuses,
        },
    )
    await db.commit()

    if failures:
        # Surface failures to the caller so the UI doesn't say "sent" when it's not.
        raise HTTPException(
            status_code=502,
            detail={
                "message": "One or more reminder emails failed to send.",
                "failures": failures,
                "reviewers_emailed": reviewers_emailed,
                "items_included": items_included,
            },
        )

    return {"reviewers_emailed": reviewers_emailed, "items_included": items_included}


@router.post(
    "/review-cycles/{cycle_id}/items/{item_id}/comments",
    response_model=ReviewItemCommentResponse,
    status_code=201,
)
async def create_review_item_comment(
    cycle_id: uuid.UUID,
    item_id: uuid.UUID,
    body: ReviewItemCommentCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _create_review_item_comment(
        cycle_id, item_id, body, background_tasks, db, current_user, []
    )


@router.post(
    "/review-cycles/{cycle_id}/items/{item_id}/comments/attachments",
    response_model=ReviewItemCommentResponse,
    status_code=201,
)
async def create_review_item_comment_with_attachments(
    cycle_id: uuid.UUID,
    item_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    body: str = Form(...),
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _create_review_item_comment(
        cycle_id,
        item_id,
        ReviewItemCommentCreate(body=body),
        background_tasks,
        db,
        current_user,
        files,
    )


async def _create_review_item_comment(
    cycle_id: uuid.UUID,
    item_id: uuid.UUID,
    body: ReviewItemCommentCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession,
    current_user: User,
    files: list[UploadFile],
):
    cycle, item = await _get_review_item_for_cycle(db, current_user, cycle_id, item_id)

    body_text = body.body.strip()
    if not body_text:
        raise HTTPException(status_code=400, detail="Comment body cannot be empty")

    if (
        files
        and current_user.role == "assigned_reviewer"
        and item.assigned_reviewer_id != current_user.id
    ):
        raise HTTPException(403, "You can only upload files for review items assigned to you")
    if len(files) > 10:
        raise HTTPException(400, "Attach at most 10 files per comment")
    allowed = {".jpg", ".jpeg", ".png", ".pdf", ".docx", ".txt", ".md"}
    for file in files:
        if not file.filename or os.path.splitext(file.filename)[1].lower() not in allowed:
            raise HTTPException(400, "Supported attachments: JPG, PNG, PDF, DOCX, TXT and MD")

    comment_id = uuid.uuid4()
    comment = ReviewItemComment(
        id=comment_id,
        review_item_id=item.id,
        author_id=current_user.id,
        body=body_text,
    )
    db.add(comment)
    item.review_comment = body_text

    paths: list[str] = []
    try:
        # Flush the comment first so attachment foreign keys are valid.
        await db.flush()
        for file in files:
            filename = file.filename or "attachment"
            safe_filename = "".join(c for c in filename if c.isalnum() or c in "._- ")
            path = os.path.join(
                settings.upload_dir, "review-item-evidence", f"{uuid.uuid4()}_{safe_filename}"
            )
            paths.append(path)
            size = await save_upload_file(file, path, settings.max_evidence_upload_mb * 1024 * 1024)
            if size == 0:
                raise HTTPException(400, "Attachment cannot be empty")
            attachment = ReviewItemEvidenceFile(
                id=uuid.uuid4(),
                review_item_id=item.id,
                comment_id=comment_id,
                filename=filename,
                file_path=path,
                uploaded_by=current_user.id,
            )
            db.add(attachment)
            await log_action(
                db,
                current_user,
                "create",
                "review_item_evidence_file",
                str(attachment.id),
                new_value={
                    "review_item_id": str(item.id),
                    "comment_id": str(comment_id),
                    "filename": filename,
                },
            )
        if files:
            item.evidence_changed_at = datetime.now(timezone.utc)
        await _queue_comment_mention_emails(
            db,
            background_tasks,
            cycle,
            item,
            current_user,
            body_text,
        )

        await log_action(
            db,
            current_user,
            "create",
            "review_item_comment",
            str(comment_id),
            new_value={"review_item_id": str(item.id)},
        )
        await db.commit()

    except Exception:
        await db.rollback()
        for path in paths:
            if os.path.exists(path):
                os.remove(path)
        raise

    await db.refresh(comment)
    now = datetime.now(timezone.utc)
    return _comment_response(
        comment, current_user.full_name, _can_edit_comment(comment, current_user, now)
    )

@router.put(
    "/review-cycles/{cycle_id}/items/{item_id}/comments/{comment_id}",
    response_model=ReviewItemCommentResponse,
)
async def update_review_item_comment(
    cycle_id: uuid.UUID,
    item_id: uuid.UUID,
    comment_id: uuid.UUID,
    body: ReviewItemCommentUpdate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cycle = await _get_review_cycle_for_user(db, current_user, cycle_id, writable=True)
    result = await db.execute(
        select(ReviewItemComment, ReviewItem)
        .join(ReviewItem, ReviewItem.id == ReviewItemComment.review_item_id)
        .where(
            ReviewItem.id == item_id,
            ReviewItem.review_cycle_id == cycle_id,
            ReviewItemComment.id == comment_id,
        )
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Comment not found")

    comment, item = row

    if current_user.role == "assigned_reviewer" and item.assigned_reviewer_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only edit comments on review items assigned to you",
        )

    if comment.author_id is None or comment.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the author can edit this comment")

    now = datetime.now(timezone.utc)
    if not _can_edit_comment(comment, current_user, now):
        raise HTTPException(status_code=403, detail="Comment can no longer be edited")

    body_text = body.body.strip()
    if not body_text:
        raise HTTPException(status_code=400, detail="Comment body cannot be empty")

    previous_body = comment.body
    comment.body = body_text
    comment.updated_at = now
    item.review_comment = body_text

    await _queue_comment_mention_emails(
        db, background_tasks, cycle, item, current_user, body_text,
        previous_body=previous_body,
    )

    await log_action(
        db,
        current_user,
        "update",
        "review_item_comment",
        str(comment.id),
        old_value=None,
        new_value={"review_item_id": str(item.id)},
    )
    await db.commit()
    await db.refresh(comment)

    return _comment_response(
        comment, current_user.full_name, _can_edit_comment(comment, current_user, now)
    )


@router.post(
    "/review-cycles/{cycle_id}/items/{item_id}/files",
    response_model=ReviewItemEvidenceFileResponse,
    status_code=201,
)
async def upload_review_item_file(
    cycle_id: uuid.UUID,
    item_id: uuid.UUID,
    file: UploadFile = File(...),
    description: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _, item = await _get_review_item_for_cycle(db, current_user, cycle_id, item_id)
    if current_user.role == "assigned_reviewer" and item.assigned_reviewer_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only upload files for review items assigned to you",
        )

    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")
    extension = os.path.splitext(file.filename)[1].lower()
    if extension not in ALLOWED_EVIDENCE_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EVIDENCE_EXTENSIONS))
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed extensions: {allowed}",
        )

    safe_filename = "".join(c for c in file.filename if c.isalnum() or c in "._- ")
    if not safe_filename:
        safe_filename = f"evidence{extension}"
    unique_filename = f"{uuid.uuid4()}_{safe_filename}"
    evidence_dir = os.path.join(settings.upload_dir, "review-item-evidence")
    os.makedirs(evidence_dir, exist_ok=True)
    file_path = os.path.join(evidence_dir, unique_filename)

    max_bytes = settings.max_evidence_upload_mb * 1024 * 1024
    await save_upload_file(file, file_path, max_bytes)

    evidence_file = ReviewItemEvidenceFile(
        id=uuid.uuid4(),
        review_item_id=item.id,
        filename=file.filename,
        file_path=file_path,
        description=description,
        uploaded_by=current_user.id,
    )
    db.add(evidence_file)
    item.evidence_changed_at = datetime.now(timezone.utc)

    await log_action(
        db,
        current_user,
        "create",
        "review_item_evidence_file",
        str(evidence_file.id),
        new_value={"review_item_id": str(item.id), "filename": file.filename},
    )
    await db.commit()
    await db.refresh(evidence_file)
    return evidence_file


@router.delete(
    "/review-cycles/{cycle_id}/items/{item_id}/files/{file_id}",
    status_code=204,
)
async def delete_review_item_file(
    cycle_id: uuid.UUID,
    item_id: uuid.UUID,
    file_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_review_cycle_for_user(db, current_user, cycle_id, writable=True)
    result = await db.execute(
        select(ReviewItemEvidenceFile, ReviewItem)
        .join(ReviewItem, ReviewItem.id == ReviewItemEvidenceFile.review_item_id)
        .where(
            ReviewItemEvidenceFile.id == file_id,
            ReviewItemEvidenceFile.review_item_id == item_id,
            ReviewItem.review_cycle_id == cycle_id,
        )
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Evidence file not found")
    evidence_file, item = row

    if current_user.role == "assigned_reviewer" and item.assigned_reviewer_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only delete files for review items assigned to you",
        )

    try:
        update_assessment(
            item,
            legacy_status=await legacy_assessment_status(db, item),
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    if os.path.exists(evidence_file.file_path):
        os.remove(evidence_file.file_path)
    item.evidence_changed_at = datetime.now(timezone.utc)

    await log_action(
        db,
        current_user,
        "delete",
        "review_item_evidence_file",
        str(evidence_file.id),
        old_value={"review_item_id": str(item.id), "filename": evidence_file.filename},
    )
    await db.delete(evidence_file)
    await db.commit()


@router.get(
    "/review-cycles/{cycle_id}/items/{item_id}/files/{file_id}/preview",
)
async def preview_review_item_file(
    cycle_id: uuid.UUID,
    item_id: uuid.UUID,
    file_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cycle = await _get_review_cycle_for_user(db, current_user, cycle_id)
    result = await db.execute(
        select(ReviewItemEvidenceFile, ReviewItem)
        .join(ReviewItem, ReviewItem.id == ReviewItemEvidenceFile.review_item_id)
        .where(
            ReviewItemEvidenceFile.id == file_id,
            ReviewItemEvidenceFile.review_item_id == item_id,
            ReviewItem.review_cycle_id == cycle_id,
        )
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Evidence file not found")
    evidence_file, item = row

    if current_user.role == "assigned_reviewer" and item.assigned_reviewer_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only preview files for review items assigned to you",
        )

    if not _is_image_evidence_filename(evidence_file.filename):
        raise HTTPException(status_code=400, detail="Evidence file is not previewable")

    path = await evidence_download_path(db, cycle, evidence_file)

    media_type, _ = mimetypes.guess_type(evidence_file.filename)
    return FileResponse(
        path,
        media_type=media_type or "image/png",
    )


@router.get(
    "/review-cycles/{cycle_id}/items/{item_id}/files/{file_id}/download",
)
async def download_review_item_file(
    cycle_id: uuid.UUID,
    item_id: uuid.UUID,
    file_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cycle = await _get_review_cycle_for_user(db, current_user, cycle_id, action="export")
    result = await db.execute(
        select(ReviewItemEvidenceFile, ReviewItem)
        .join(ReviewItem, ReviewItem.id == ReviewItemEvidenceFile.review_item_id)
        .where(
            ReviewItemEvidenceFile.id == file_id,
            ReviewItemEvidenceFile.review_item_id == item_id,
            ReviewItem.review_cycle_id == cycle_id,
        )
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Evidence file not found")
    evidence_file, item = row

    if current_user.role == "assigned_reviewer" and item.assigned_reviewer_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only download files for review items assigned to you",
        )

    path = await evidence_download_path(db, cycle, evidence_file)

    return FileResponse(
        path,
        filename=evidence_file.filename,
        media_type="application/octet-stream",
    )


@router.post("/review-cycles/{cycle_id}/close", response_model=ReviewCycleResponse)
async def close_review_cycle(
    cycle_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    cycle = await _get_review_cycle_for_user(db, current_user, cycle_id, writable=True)

    if cycle.status != "active":
        raise HTTPException(status_code=400, detail="Review cycle is not active")

    rows = await assessment_rows(db, cycle)
    checks = readiness(rows)
    if not checks["can_close"]:
        raise HTTPException(
            409, {"message": "Resolve readiness blockers before completing this review.", **checks}
        )
    snapshot, snapshot_folder = await freeze_review(db, cycle, current_user, rows)

    cycle.status = "closed"
    cycle.closed_at = datetime.now(timezone.utc)
    cycle.closed_by = current_user.id
    cycle.snapshot_id = snapshot.id

    await log_action(
        db,
        current_user,
        "close",
        "review_cycle",
        str(cycle.id),
        new_value={"status": "closed", "snapshot_id": str(snapshot.id)},
    )
    try:
        await db.commit()
    except BaseException:
        shutil.rmtree(snapshot_folder, ignore_errors=True)
        raise
    await db.refresh(cycle)
    return await _cycle_response(db, cycle)


async def _create_snapshot(
    db: AsyncSession,
    user: User,
    name: str,
    description: Optional[str] = None,
    snapshot_type: str = "manual",
    requirement_ids: Optional[list[uuid.UUID]] = None,
) -> Snapshot:
    from app.services.requirement_scope import current_requirement_condition
    # Gather all requirements with their current status
    requirements_query = (
        apply_org_scope(select(Requirement), Requirement, user)
        .outerjoin(Document, Document.id == Requirement.document_id)
        .where(
            Requirement.active.is_(True),
            or_(Requirement.document_id.is_(None), Document.status == "approved"),
        )
    )
    if requirement_ids is not None:
        if requirement_ids:
            requirements_query = requirements_query.where(Requirement.id.in_(requirement_ids))
        else:
            requirements_query = requirements_query.where(Requirement.id.is_(None))
    else:
        requirements_query = requirements_query.where(current_requirement_condition())

    reqs_result = await db.execute(requirements_query)
    requirements = reqs_result.scalars().all()

    snapshot_data = []
    evidenced_count = 0

    for req in requirements:
        # Get latest status
        status_result = await db.execute(
            select(RequirementStatus)
            .where(RequirementStatus.requirement_id == req.id)
            .order_by(RequirementStatus.changed_at.desc(), RequirementStatus.id.desc())
            .limit(1)
        )
        latest_status = status_result.scalar_one_or_none()

        req_data = {
            "id": str(req.id),
            "reference_id": req.reference_id,
            "text": req.text,
            "requirement_type": req.requirement_type,
            "status": latest_status.status if latest_status else None,
            "assigned_to": (
                str(latest_status.assigned_to)
                if latest_status and latest_status.assigned_to
                else None
            ),
        }
        snapshot_data.append(req_data)

        if latest_status and latest_status.status == "evidenced":
            evidenced_count += 1

    snapshot = Snapshot(
        organization_id=user.organization_id,
        name=name,
        description=description,
        snapshot_type=snapshot_type,
        data_json=json.dumps(snapshot_data),
        total_requirements=len(requirements),
        evidenced_requirements=evidenced_count,
        created_by=user.id,
    )
    db.add(snapshot)
    await db.flush()
    return snapshot


@router.post("/snapshots", response_model=SnapshotResponse, status_code=201)
async def create_snapshot(
    body: SnapshotCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    snapshot = await _create_snapshot(db, current_user, body.name, body.description, "manual")
    await log_action(
        db,
        current_user,
        "create",
        "snapshot",
        str(snapshot.id),
        new_value={"name": snapshot.name, "total": snapshot.total_requirements},
    )
    await db.commit()
    await db.refresh(snapshot)
    return snapshot


@router.get("/snapshots", response_model=dict)
async def list_snapshots(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    total_result = await db.execute(
        apply_org_scope(select(func.count(Snapshot.id)), Snapshot, current_user)
    )
    total = total_result.scalar()

    result = await db.execute(
        apply_org_scope(select(Snapshot), Snapshot, current_user)
        .order_by(Snapshot.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    snapshots = result.scalars().all()

    return {"items": [SnapshotResponse.model_validate(s) for s in snapshots], "total": total}


@router.get("/snapshots/{snapshot_id}", response_model=SnapshotDetailResponse)
async def get_snapshot(
    snapshot_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _get_snapshot_for_user(db, current_user, snapshot_id)
