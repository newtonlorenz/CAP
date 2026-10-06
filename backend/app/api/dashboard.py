from __future__ import annotations

import json
import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, case, exists, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from app.api.deps import get_current_user
from app.api.tenant import org_clause
from app.database import get_db
from app.models.application import Application
from app.models.audit import AuditLog
from app.models.change_management import ChangeEntry, ComponentRegister
from app.models.document import Document
from app.models.evidence import EvidenceFile, EvidenceLink, EvidenceNote
from app.models.extraction import ExtractionRun
from app.models.preparation import PreparationCase
from app.models.program import CertificationProject
from app.models.requirement import Requirement, RequirementStatus
from app.models.review import ReviewCycle, ReviewItem, ReviewItemComment, Snapshot
from app.models.user import User
from app.schemas.dashboard import (
    ActiveReviewCycleItem,
    AssignedRequirementItem,
    AssignedRequirements,
    AssignedReviewItem,
    AssignedReviewItems,
    AuditActivityItem,
    Breakdowns,
    ComplianceMetric,
    DashboardResponse,
    DataQuality,
    DataQualityRequirementItem,
    DocumentBreakdownItem,
    DocumentQueueItem,
    DocumentStatusCount,
    DocumentTypeBreakdownItem,
    EvidenceCounts,
    ExtractionFailureItem,
    ExtractionFailuresRecent,
    Kpis,
    MyWork,
    Queues,
    RequirementTypeBreakdownItem,
    ReviewCycleProgress,
    ReviewCycles,
    SnapshotItem,
    StatusBreakdownItem,
)
from app.services.access_audit import audit_access_clause
from app.services.dashboard_work import application_work
from app.services.requirement_scope import current_requirement_condition
from app.services.review_assurance import AssessmentRow, assessment_gap_reasons
from app.services.review_progress import (
    ACTIONABLE_REQUIREMENT_TYPES,
    COMPLETED_REVIEW_STATUSES,
    review_progress_eligible_condition,
)

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
async def get_dashboard(
    jurisdiction_id: uuid.UUID | None = Query(None, description="Optional jurisdiction filter"),
    work_scope: Literal["all", "unresolved"] = Query("all"),
    work_page: int = Query(1, ge=1),
    work_page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    now = datetime.now(UTC)

    latest_status = select(
        RequirementStatus.requirement_id.label("requirement_id"),
        RequirementStatus.status.label("status"),
        RequirementStatus.assigned_to.label("assigned_to"),
        RequirementStatus.changed_at.label("changed_at"),
        RequirementStatus.comment.label("comment"),
        func.row_number()
        .over(
            partition_by=RequirementStatus.requirement_id,
            order_by=(RequirementStatus.changed_at.desc(), RequirementStatus.id.desc()),
        )
        .label("rn"),
    ).subquery()

    join_latest = and_(latest_status.c.requirement_id == Requirement.id, latest_status.c.rn == 1)
    status_expr = func.coalesce(latest_status.c.status, literal("not_started"))
    assigned_to_expr = latest_status.c.assigned_to
    review_progress_predicate = review_progress_eligible_condition(
        Requirement.requirement_type, func.coalesce(ReviewItem.assessment_status, status_expr)
    )

    requirement_filters = [
        Requirement.active.is_(True),
        org_clause(Requirement, current_user),
        current_requirement_condition(),
    ]
    if jurisdiction_id is not None:
        requirement_filters.append(Requirement.jurisdiction_id == jurisdiction_id)

    review_cycle_filters = [org_clause(ReviewCycle, current_user)]
    document_filters = [org_clause(Document, current_user)]
    if jurisdiction_id is not None:
        review_cycle_filters.append(ReviewCycle.jurisdiction_id == jurisdiction_id)
        document_filters.append(Document.jurisdiction_id == jurisdiction_id)

    # Exclude draft/unapproved requirement sets from compliance metrics by default.
    #
    # Requirements can be "manual" (no document) OR sourced from an approved document set.
    # Some older fixtures/records may reference a non-existent document; treat those as eligible.
    eligible_requirement_source = and_(
        or_(
            Requirement.document_id.is_(None),
            Document.id.is_(None),
            Document.status == "approved",
        ),
        review_progress_eligible_condition(Requirement.requirement_type, status_expr),
    )

    # KPI metrics
    metrics_result = await db.execute(
        select(
            func.count(Requirement.id).label("total"),
            func.sum(case((status_expr == "evidenced", 1), else_=0)).label("evidenced"),
            func.sum(case((Requirement.requirement_type == "mandatory", 1), else_=0)).label(
                "mandatory_total"
            ),
            func.sum(
                case(
                    (
                        and_(
                            Requirement.requirement_type == "mandatory", status_expr == "evidenced"
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("mandatory_evidenced"),
            func.sum(case((status_expr.in_(["in_progress", "blocked"]), 1), else_=0)).label(
                "at_risk"
            ),
        )
        .select_from(Requirement)
        .outerjoin(Document, Document.id == Requirement.document_id)
        .outerjoin(latest_status, join_latest)
        .where(*requirement_filters, eligible_requirement_source)
    )
    metrics = metrics_result.first()
    total = int(metrics.total or 0)
    evidenced = int(metrics.evidenced or 0)
    mandatory_total = int(metrics.mandatory_total or 0)
    mandatory_evidenced = int(metrics.mandatory_evidenced or 0)
    at_risk_count = int(metrics.at_risk or 0)

    overall_metric = ComplianceMetric(
        total=total,
        evidenced=evidenced,
        percentage=round((evidenced / total * 100) if total > 0 else 0.0, 1),
    )
    mandatory_metric = ComplianceMetric(
        total=mandatory_total,
        evidenced=mandatory_evidenced,
        percentage=round(
            (mandatory_evidenced / mandatory_total * 100) if mandatory_total > 0 else 0.0, 1
        ),
    )

    # Status breakdown (global)
    status_rows = await db.execute(
        select(status_expr.label("status"), func.count(Requirement.id).label("total"))
        .select_from(Requirement)
        .outerjoin(Document, Document.id == Requirement.document_id)
        .outerjoin(latest_status, join_latest)
        .where(*requirement_filters, eligible_requirement_source)
        .group_by(status_expr)
        .order_by(func.count(Requirement.id).desc())
    )
    by_status = []
    for status, count in status_rows.all():
        count_i = int(count)
        by_status.append(
            StatusBreakdownItem(
                status=str(status),
                total=count_i,
                percentage_of_total=round((count_i / total * 100) if total > 0 else 0.0, 1),
            )
        )

    # Breakdowns: by document, by document type, by requirement type
    doc_name_expr = case(
        (Requirement.document_id.is_(None), literal("Unassigned")),
        else_=func.coalesce(Document.name, Document.filename, literal("Unknown")),
    )
    doc_type_expr = case(
        (Requirement.document_id.is_(None), literal("unassigned")),
        else_=func.coalesce(Document.document_type, literal("unknown")),
    )

    doc_rows = await db.execute(
        select(
            Requirement.document_id.label("document_id"),
            doc_name_expr.label("name"),
            doc_type_expr.label("document_type"),
            func.count(Requirement.id).label("total"),
            func.sum(case((status_expr == "evidenced", 1), else_=0)).label("evidenced"),
        )
        .select_from(Requirement)
        .outerjoin(Document, Document.id == Requirement.document_id)
        .outerjoin(latest_status, join_latest)
        .where(*requirement_filters, eligible_requirement_source)
        .group_by(Requirement.document_id, doc_name_expr, doc_type_expr)
        .order_by(func.count(Requirement.id).desc())
    )
    by_document: list[DocumentBreakdownItem] = []
    for document_id, name, document_type, count, evid in doc_rows.all():
        count_i = int(count)
        evid_i = int(evid or 0)
        doc_id_str = str(document_id) if document_id is not None else "unassigned"
        by_document.append(
            DocumentBreakdownItem(
                document_id=doc_id_str,
                name=str(name),
                document_type=str(document_type),
                total=count_i,
                evidenced=evid_i,
                percentage=round((evid_i / count_i * 100) if count_i > 0 else 0.0, 1),
            )
        )

    doc_type_rows = await db.execute(
        select(
            doc_type_expr.label("document_type"),
            func.count(Requirement.id).label("total"),
            func.sum(case((status_expr == "evidenced", 1), else_=0)).label("evidenced"),
        )
        .select_from(Requirement)
        .outerjoin(Document, Document.id == Requirement.document_id)
        .outerjoin(latest_status, join_latest)
        .where(*requirement_filters, eligible_requirement_source)
        .group_by(doc_type_expr)
        .order_by(func.count(Requirement.id).desc())
    )
    by_document_type: list[DocumentTypeBreakdownItem] = []
    for document_type, count, evid in doc_type_rows.all():
        count_i = int(count)
        evid_i = int(evid or 0)
        by_document_type.append(
            DocumentTypeBreakdownItem(
                document_type=str(document_type),
                total=count_i,
                evidenced=evid_i,
                percentage=round((evid_i / count_i * 100) if count_i > 0 else 0.0, 1),
            )
        )

    req_type_rows = await db.execute(
        select(
            Requirement.requirement_type.label("requirement_type"),
            func.count(Requirement.id).label("total"),
            func.sum(case((status_expr == "evidenced", 1), else_=0)).label("evidenced"),
        )
        .select_from(Requirement)
        .outerjoin(Document, Document.id == Requirement.document_id)
        .outerjoin(latest_status, join_latest)
        .where(*requirement_filters, eligible_requirement_source)
        .group_by(Requirement.requirement_type)
        .order_by(func.count(Requirement.id).desc())
    )
    by_requirement_type: list[RequirementTypeBreakdownItem] = []
    for requirement_type, count, evid in req_type_rows.all():
        count_i = int(count)
        evid_i = int(evid or 0)
        by_requirement_type.append(
            RequirementTypeBreakdownItem(
                requirement_type=str(requirement_type),
                total=count_i,
                evidenced=evid_i,
                percentage=round((evid_i / count_i * 100) if count_i > 0 else 0.0, 1),
            )
        )

    breakdowns = Breakdowns(
        by_document=by_document,
        by_document_type=by_document_type,
        by_requirement_type=by_requirement_type,
    )

    # Apply the personal queue scope before counting or paging.
    work_offset = (work_page - 1) * work_page_size
    my_req_filters = [assigned_to_expr == current_user.id]
    if work_scope == "unresolved":
        my_req_filters.append(status_expr != "evidenced")

    # My work: assigned requirements
    my_req_total_result = await db.execute(
        select(func.count(Requirement.id))
        .select_from(Requirement)
        .outerjoin(Document, Document.id == Requirement.document_id)
        .outerjoin(latest_status, join_latest)
        .where(
            *requirement_filters,
            eligible_requirement_source,
            *my_req_filters,
        )
    )
    my_req_total = int(my_req_total_result.scalar() or 0)

    my_req_status_rows = await db.execute(
        select(status_expr.label("status"), func.count(Requirement.id).label("total"))
        .select_from(Requirement)
        .outerjoin(Document, Document.id == Requirement.document_id)
        .outerjoin(latest_status, join_latest)
        .where(
            *requirement_filters,
            eligible_requirement_source,
            *my_req_filters,
        )
        .group_by(status_expr)
        .order_by(func.count(Requirement.id).desc())
    )
    my_req_by_status: list[StatusBreakdownItem] = []
    for status, count in my_req_status_rows.all():
        count_i = int(count)
        my_req_by_status.append(
            StatusBreakdownItem(
                status=str(status),
                total=count_i,
                percentage_of_total=round(
                    (count_i / my_req_total * 100) if my_req_total > 0 else 0.0, 1
                ),
            )
        )

    my_req_items_rows = await db.execute(
        select(
            Requirement.id,
            Requirement.reference_id,
            Requirement.title,
            doc_name_expr.label("document_name"),
            status_expr.label("status"),
            assigned_to_expr.label("assigned_to"),
            latest_status.c.changed_at.label("changed_at"),
        )
        .select_from(Requirement)
        .outerjoin(Document, Document.id == Requirement.document_id)
        .outerjoin(latest_status, join_latest)
        .where(
            *requirement_filters,
            eligible_requirement_source,
            *my_req_filters,
        )
        .order_by(
            case((status_expr == "blocked", 0), else_=1),
            latest_status.c.changed_at.asc().nullsfirst(),
            Requirement.reference_id.asc(),
            Requirement.id,
        )
        .offset(work_offset)
        .limit(work_page_size)
    )
    my_req_items: list[AssignedRequirementItem] = []
    for req_id, ref_id, title, doc_name, status, assigned_to, changed_at in my_req_items_rows.all():
        my_req_items.append(
            AssignedRequirementItem(
                requirement_id=str(req_id),
                reference_id=str(ref_id),
                title=title,
                document_name=str(doc_name),
                status=str(status),
                assigned_to=str(assigned_to) if assigned_to else None,
                last_changed_at=changed_at,
                action_reasons=(
                    ["Resolve the blocker"]
                    if status == "blocked"
                    else ["Complete the evidence"]
                    if status != "evidenced"
                    else []
                ),
            )
        )

    assigned_requirements = AssignedRequirements(
        total=my_req_total,
        by_status=my_req_by_status,
        items=my_req_items,
    )

    # My work: assigned review items (active cycles only)
    if current_user.role == "assigned_reviewer":
        my_review_predicate = ReviewItem.assigned_reviewer_id == current_user.id
    else:
        my_review_predicate = or_(
            ReviewItem.assigned_reviewer_id == current_user.id,
            ReviewItem.responsible_user_id == current_user.id,
        )

    my_review_items_rows = await db.execute(
        select(
            ReviewCycle,
            ReviewItem,
            Requirement,
            latest_status.c.comment,
            latest_status.c.status.label("legacy_status"),
            CertificationProject.id.label("project_id"),
            CertificationProject.name.label("project_name"),
            ChangeEntry.id.label("change_entry_id"),
            ChangeEntry.title.label("change_title"),
        )
        .options(
            load_only(ReviewCycle.id, ReviewCycle.name, ReviewCycle.deadline),
            load_only(
                ReviewItem.id,
                ReviewItem.assessment_status,
                ReviewItem.review_status,
                ReviewItem.review_evidence,
            ),
            load_only(
                Requirement.id,
                Requirement.reference_id,
                Requirement.title,
                Requirement.requirement_type,
            ),
        )
        .select_from(ReviewItem)
        .join(ReviewCycle, ReviewCycle.id == ReviewItem.review_cycle_id)
        .join(Requirement, Requirement.id == ReviewItem.requirement_id)
        .outerjoin(latest_status, join_latest)
        .outerjoin(
            CertificationProject,
            and_(
                CertificationProject.id == ReviewCycle.certification_project_id,
                org_clause(CertificationProject, current_user),
            ),
        )
        .outerjoin(
            ChangeEntry,
            and_(
                ChangeEntry.id == ReviewCycle.change_entry_id,
                exists(
                    select(ComponentRegister.id).where(
                        ComponentRegister.id == ChangeEntry.register_id,
                        org_clause(ComponentRegister, current_user),
                    )
                ),
            ),
        )
        .where(
            ReviewCycle.status == "active",
            my_review_predicate,
            *review_cycle_filters,
            org_clause(Requirement, current_user),
        )
        .order_by(
            case((ReviewCycle.deadline < now, 0), else_=1),
            case(
                (
                    or_(
                        ReviewItem.review_status == "escalated",
                        func.coalesce(ReviewItem.assessment_status, latest_status.c.status)
                        == "blocked",
                    ),
                    0,
                ),
                else_=1,
            ),
            ReviewCycle.deadline.asc().nullslast(),
            ReviewItem.created_at,
            ReviewItem.id,
        )
    )
    # Evaluate the shared readiness rule over all visible assignments, then page.
    # A confirmed decision can still need evidence or a non-applicability reason.
    my_review_items: list[AssignedReviewItem] = []
    for (
        cycle,
        item,
        requirement,
        legacy_comment,
        legacy_status,
        project_id,
        project_name,
        change_entry_id,
        change_title,
    ) in my_review_items_rows.all():
        reasons = assessment_gap_reasons(
            AssessmentRow(
                item=item,
                requirement=requirement,
                document=None,
                status=item.assessment_status
                if item.assessment_status is not None
                else legacy_status or "not_started",
                status_comment=legacy_comment or "",
            )
        )
        if work_scope == "unresolved" and not reasons:
            continue
        my_review_items.append(
            AssignedReviewItem(
                cycle_id=str(cycle.id),
                cycle_name=cycle.name,
                deadline=cycle.deadline,
                review_item_id=str(item.id),
                requirement_reference_id=requirement.reference_id,
                requirement_title=requirement.title,
                review_status=item.review_status,
                project_id=str(project_id) if project_id else None,
                project_name=project_name,
                change_entry_id=str(change_entry_id) if change_entry_id else None,
                change_title=change_title,
                action_reasons=reasons,
            )
        )
    my_review_total = len(my_review_items)
    my_review_by_status = [
        StatusBreakdownItem(
            status=status,
            total=count,
            percentage_of_total=round(count / my_review_total * 100, 1),
        )
        for status, count in Counter(item.review_status for item in my_review_items).items()
    ]
    assigned_review_items = AssignedReviewItems(
        total=my_review_total,
        by_status=my_review_by_status,
        items=my_review_items[work_offset : work_offset + work_page_size],
    )

    assigned_forms, authority_queries = await application_work(
        db, current_user, jurisdiction_id, offset=work_offset, limit=work_page_size
    )
    my_work = MyWork(
        assigned_requirements=assigned_requirements,
        assigned_review_items=assigned_review_items,
        assigned_forms=assigned_forms,
        authority_queries=authority_queries,
    )

    # Review cycles (active) + progress
    if current_user.role == "assigned_reviewer":
        my_pending_predicate = ReviewItem.assigned_reviewer_id == current_user.id
    else:
        my_pending_predicate = or_(
            ReviewItem.assigned_reviewer_id == current_user.id,
            ReviewItem.responsible_user_id == current_user.id,
        )

    active_cycles_rows = await db.execute(
        select(
            ReviewCycle.id,
            ReviewCycle.name,
            ReviewCycle.deadline,
            func.sum(
                case(
                    (review_progress_predicate, 1),
                    else_=0,
                )
            ).label("total"),
            func.sum(
                case(
                    (
                        and_(
                            review_progress_predicate,
                            ReviewItem.review_status.in_(COMPLETED_REVIEW_STATUSES),
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("completed"),
            func.sum(
                case(
                    (
                        and_(
                            review_progress_predicate,
                            ReviewItem.review_status == "pending",
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("pending"),
            func.sum(
                case(
                    (
                        and_(
                            review_progress_predicate,
                            ReviewItem.review_status == "pending",
                            my_pending_predicate,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("my_pending"),
        )
        .select_from(ReviewCycle)
        .outerjoin(ReviewItem, ReviewItem.review_cycle_id == ReviewCycle.id)
        .outerjoin(Requirement, Requirement.id == ReviewItem.requirement_id)
        .outerjoin(latest_status, join_latest)
        .where(ReviewCycle.status == "active", *review_cycle_filters)
        .group_by(ReviewCycle.id, ReviewCycle.name, ReviewCycle.deadline)
        .order_by(ReviewCycle.deadline.asc().nullslast(), ReviewCycle.created_at.desc())
    )
    active_cycles: list[ActiveReviewCycleItem] = []
    for (
        cycle_id,
        name,
        deadline,
        total_c,
        completed_c,
        pending_c,
        my_pending_c,
    ) in active_cycles_rows.all():
        total_i = int(total_c or 0)
        completed_i = int(completed_c or 0)
        pending_i = int(pending_c or 0)
        my_pending_i = int(my_pending_c or 0)
        due_in_days = None
        if deadline is not None:
            try:
                due_in_days = (deadline.date() - now.date()).days
            except Exception:
                due_in_days = None
        active_cycles.append(
            ActiveReviewCycleItem(
                id=str(cycle_id),
                name=str(name),
                deadline=deadline,
                progress=ReviewCycleProgress(
                    total=total_i, completed=completed_i, pending=pending_i
                ),
                due_in_days=due_in_days,
                my_pending_count=my_pending_i,
            )
        )

    review_cycles = ReviewCycles(active=active_cycles)

    # Organisation-wide manual snapshots are comparable; individual review scopes are not.
    snapshots_result = await db.execute(
        select(Snapshot)
        .where(org_clause(Snapshot, current_user), Snapshot.snapshot_type == "manual")
        .order_by(Snapshot.created_at.desc())
        .limit(20)
    )
    snapshots: list[SnapshotItem] = []
    for s in snapshots_result.scalars().all():
        snapshots.append(
            SnapshotItem(
                id=str(s.id),
                name=s.name,
                snapshot_type=s.snapshot_type,
                total_requirements=int(s.total_requirements),
                evidenced_requirements=int(s.evidenced_requirements),
                created_at=s.created_at,
            )
        )

    # Work changes only. Authentication remains available in the audit trail.
    activity_result = await db.execute(
        select(AuditLog)
        .where(
            org_clause(AuditLog, current_user),
            audit_access_clause(current_user),
            AuditLog.action.not_in(["login", "logout", "refresh", "login_failed", "token_refresh"]),
            AuditLog.entity_type.not_in(["session", "authentication"]),
        )
        .order_by(AuditLog.timestamp.desc())
        .limit(20)
    )

    def _summarize(a: AuditLog) -> str | None:
        # Best-effort; keep it short.
        new_value = None
        old_value = None
        try:
            new_value = json.loads(a.new_value) if a.new_value else None
        except Exception:
            new_value = None
        try:
            old_value = json.loads(a.old_value) if a.old_value else None
        except Exception:
            old_value = None

        if a.entity_type == "document":
            status = None
            if isinstance(new_value, dict):
                status = new_value.get("status")
            if a.action in {"approve", "reject", "archive"} and status:
                return f"Document {a.action}d (status: {status})"
            if a.action == "update" and status:
                prev = old_value.get("status") if isinstance(old_value, dict) else None
                if prev and prev != status:
                    return f"Status {prev} -> {status}"
                return f"Updated (status: {status})"
            return None

        if a.entity_type == "requirement" and a.action == "status_change":
            if isinstance(new_value, dict) and "status" in new_value:
                return f"Status -> {new_value.get('status')}"
            return None

        if a.entity_type == "review_item" and a.action == "update":
            if isinstance(new_value, dict) and "review_status" in new_value:
                return f"Review status -> {new_value.get('review_status')}"
            return None

        return None

    recent_activity: list[AuditActivityItem] = []
    for a in activity_result.scalars().all():
        title = None
        destination = None
        try:
            entity_uuid = uuid.UUID(a.entity_id)
        except (ValueError, TypeError):
            entity_uuid = None
        if entity_uuid and a.entity_type in {"review_item", "review_item_comment"}:
            query = (
                select(ReviewItem, Requirement, ReviewCycle)
                .join(Requirement, Requirement.id == ReviewItem.requirement_id)
                .join(ReviewCycle, ReviewCycle.id == ReviewItem.review_cycle_id)
                .where(
                    org_clause(ReviewCycle, current_user),
                    org_clause(Requirement, current_user),
                )
            )
            if a.entity_type == "review_item_comment":
                query = query.join(
                    ReviewItemComment, ReviewItemComment.review_item_id == ReviewItem.id
                ).where(ReviewItemComment.id == entity_uuid)
            else:
                query = query.where(ReviewItem.id == entity_uuid)
            record = (await db.execute(query)).first()
            if record:
                item, requirement, cycle = record
                title = f"{requirement.reference_id} · {requirement.title or cycle.name}"
                destination = f"/review-cycles/{cycle.id}?mode=focus&item={item.id}"
        elif entity_uuid and a.entity_type in {
            "requirement",
            "document",
            "requirement_set",
            "review_cycle",
            "review_package",
            "certification_project",
            "application",
            "preparation_case",
        }:
            model = {
                "requirement": Requirement,
                "document": Document,
                "requirement_set": Document,
                "review_cycle": ReviewCycle,
                "review_package": ReviewCycle,
                "certification_project": CertificationProject,
                "application": Application,
                "preparation_case": PreparationCase,
            }[a.entity_type]
            record = await db.scalar(
                select(model).where(model.id == entity_uuid, org_clause(model, current_user))
            )
            if record:
                title = (
                    f"{record.reference_id} · {record.title or 'Requirement'}"
                    if isinstance(record, Requirement)
                    else record.name or getattr(record, "filename", None)
                )
        recent_activity.append(
            AuditActivityItem(
                id=str(a.id),
                user_name=a.user_name,
                action=a.action,
                entity_type=a.entity_type,
                entity_id=a.entity_id,
                timestamp=a.timestamp,
                summary=_summarize(a),
                title=title,
                destination=destination,
            )
        )

    # Role-gated sections: queues + data quality
    queues = None
    data_quality = None

    if current_user.role in {"admin", "manager", "approver", "contributor"}:
        # Document status counts
        status_counts_rows = await db.execute(
            select(Document.status, func.count(Document.id))
            .select_from(Document)
            .where(Document.archived_at.is_(None), *document_filters)
            .group_by(Document.status)
            .order_by(func.count(Document.id).desc())
        )
        document_status_counts = [
            DocumentStatusCount(status=str(status), total=int(count))
            for status, count in status_counts_rows.all()
        ]

        # Document queues
        pending_approval_rows = await db.execute(
            select(Document)
            .where(
                Document.status == "pending_approval",
                Document.archived_at.is_(None),
                *document_filters,
            )
            .order_by(Document.created_at.desc())
            .limit(20)
        )
        documents_pending_approval: list[DocumentQueueItem] = []
        for d in pending_approval_rows.scalars().all():
            missing = []
            if not d.name or not d.name.strip():
                missing.append("name")
            if not d.testing_frequency or not d.testing_frequency.strip():
                missing.append("testing_frequency")
            documents_pending_approval.append(
                DocumentQueueItem(
                    id=str(d.id),
                    name=d.name,
                    filename=d.filename,
                    document_type=d.document_type,
                    status=d.status,
                    created_at=d.created_at,
                    missing_fields=missing,
                )
            )

        needing_submission_rows = await db.execute(
            select(Document)
            .where(
                Document.status.in_(["extracted", "reviewed", "changes_requested"]),
                Document.archived_at.is_(None),
                *document_filters,
            )
            .order_by(Document.created_at.desc())
            .limit(20)
        )
        documents_needing_submission = [
            DocumentQueueItem(
                id=str(d.id),
                name=d.name,
                filename=d.filename,
                document_type=d.document_type,
                status=d.status,
                created_at=d.created_at,
                missing_fields=[],
            )
            for d in needing_submission_rows.scalars().all()
        ]

        needing_extraction_rows = await db.execute(
            select(Document)
            .where(
                Document.status.in_(["uploaded", "extraction_failed", "extraction_cancelled"]),
                Document.archived_at.is_(None),
                *document_filters,
            )
            .order_by(Document.created_at.desc())
            .limit(20)
        )
        documents_needing_extraction = [
            DocumentQueueItem(
                id=str(d.id),
                name=d.name,
                filename=d.filename,
                document_type=d.document_type,
                status=d.status,
                created_at=d.created_at,
                missing_fields=[],
            )
            for d in needing_extraction_rows.scalars().all()
        ]

        # Extraction failures (last 30 days)
        since_30 = now - timedelta(days=30)
        since_7 = now - timedelta(days=7)
        failures_base = (
            select(ExtractionRun, Document)
            .join(Document, Document.id == ExtractionRun.document_id)
            .where(
                ExtractionRun.status.in_(["failed", "timed_out"]),
                ExtractionRun.created_at >= since_30,
                *document_filters,
            )
            .order_by(ExtractionRun.created_at.desc())
        )
        failures_rows = await db.execute(failures_base.limit(20))
        failure_items: list[ExtractionFailureItem] = []
        for run, doc in failures_rows.all():
            doc_name = doc.name or doc.filename or "Unknown"
            failure_items.append(
                ExtractionFailureItem(
                    run_id=str(run.id),
                    document_id=str(doc.id),
                    document_name=str(doc_name),
                    status=run.status,
                    error_message=run.error_message,
                    error_page=run.error_page,
                    created_at=run.created_at,
                    completed_at=run.completed_at,
                )
            )

        last_30_count_result = await db.execute(
            select(func.count(ExtractionRun.id))
            .select_from(ExtractionRun)
            .join(Document, Document.id == ExtractionRun.document_id)
            .where(
                ExtractionRun.status.in_(["failed", "timed_out"]),
                ExtractionRun.created_at >= since_30,
                *document_filters,
            )
        )
        last_7_count_result = await db.execute(
            select(func.count(ExtractionRun.id))
            .select_from(ExtractionRun)
            .join(Document, Document.id == ExtractionRun.document_id)
            .where(
                ExtractionRun.status.in_(["failed", "timed_out"]),
                ExtractionRun.created_at >= since_7,
                *document_filters,
            )
        )
        failures_recent = ExtractionFailuresRecent(
            last_7_days=int(last_7_count_result.scalar() or 0),
            last_30_days=int(last_30_count_result.scalar() or 0),
            items=failure_items,
        )

        queues = Queues(
            document_status_counts=document_status_counts,
            documents_pending_approval=documents_pending_approval,
            documents_needing_submission=documents_needing_submission,
            documents_needing_extraction=documents_needing_extraction,
            extraction_failures_recent=failures_recent,
        )

        # Data quality: evidence mismatches
        notes_subq = (
            select(
                EvidenceNote.requirement_id.label("requirement_id"),
                func.count(EvidenceNote.id).label("notes_count"),
            )
            .group_by(EvidenceNote.requirement_id)
            .subquery()
        )
        files_subq = (
            select(
                EvidenceFile.requirement_id.label("requirement_id"),
                func.count(EvidenceFile.id).label("files_count"),
            )
            .group_by(EvidenceFile.requirement_id)
            .subquery()
        )
        links_subq = (
            select(
                EvidenceLink.requirement_id.label("requirement_id"),
                func.count(EvidenceLink.id).label("links_count"),
            )
            .group_by(EvidenceLink.requirement_id)
            .subquery()
        )

        notes_count = func.coalesce(notes_subq.c.notes_count, 0)
        files_count = func.coalesce(files_subq.c.files_count, 0)
        links_count = func.coalesce(links_subq.c.links_count, 0)
        evidence_total = notes_count + files_count + links_count

        base_quality_query = (
            select(
                Requirement.id,
                Requirement.reference_id,
                Requirement.title,
                doc_name_expr.label("document_name"),
                status_expr.label("status"),
                notes_count.label("notes"),
                files_count.label("files"),
                links_count.label("links"),
            )
            .select_from(Requirement)
            .outerjoin(Document, Document.id == Requirement.document_id)
            .outerjoin(latest_status, join_latest)
            .outerjoin(notes_subq, notes_subq.c.requirement_id == Requirement.id)
            .outerjoin(files_subq, files_subq.c.requirement_id == Requirement.id)
            .outerjoin(links_subq, links_subq.c.requirement_id == Requirement.id)
            .where(*requirement_filters, eligible_requirement_source)
        )

        evidenced_without_evidence_rows = await db.execute(
            base_quality_query.where(status_expr == "evidenced", evidence_total == 0)
            .order_by(Requirement.reference_id.asc())
            .limit(20)
        )
        evidenced_without_evidence: list[DataQualityRequirementItem] = []
        for (
            req_id,
            ref_id,
            title,
            doc_name,
            status,
            notes,
            files,
            links,
        ) in evidenced_without_evidence_rows.all():
            evidenced_without_evidence.append(
                DataQualityRequirementItem(
                    requirement_id=str(req_id),
                    reference_id=str(ref_id),
                    title=title,
                    document_name=str(doc_name),
                    current_status=str(status),
                    evidence_counts=EvidenceCounts(
                        notes=int(notes or 0),
                        files=int(files or 0),
                        links=int(links or 0),
                    ),
                )
            )

        evidence_without_evidenced_status_rows = await db.execute(
            base_quality_query.where(evidence_total > 0, status_expr != "evidenced")
            .order_by(Requirement.reference_id.asc())
            .limit(20)
        )
        evidence_without_evidenced_status: list[DataQualityRequirementItem] = []
        for (
            req_id,
            ref_id,
            title,
            doc_name,
            status,
            notes,
            files,
            links,
        ) in evidence_without_evidenced_status_rows.all():
            evidence_without_evidenced_status.append(
                DataQualityRequirementItem(
                    requirement_id=str(req_id),
                    reference_id=str(ref_id),
                    title=title,
                    document_name=str(doc_name),
                    current_status=str(status),
                    evidence_counts=EvidenceCounts(
                        notes=int(notes or 0),
                        files=int(files or 0),
                        links=int(links or 0),
                    ),
                )
            )

        unassigned_count_result = await db.execute(
            select(func.count(Requirement.id))
            .select_from(Requirement)
            .outerjoin(Document, Document.id == Requirement.document_id)
            .outerjoin(latest_status, join_latest)
            .where(
                *requirement_filters,
                eligible_requirement_source,
                Requirement.requirement_type.in_(list(ACTIONABLE_REQUIREMENT_TYPES)),
                latest_status.c.assigned_to.is_(None),
            )
        )
        unlinked_count_result = await db.execute(
            select(func.count(Requirement.id)).where(
                *requirement_filters,
                Requirement.requirement_type.in_(list(ACTIONABLE_REQUIREMENT_TYPES)),
                Requirement.document_id.is_(None),
            )
        )

        data_quality = DataQuality(
            evidenced_without_evidence=evidenced_without_evidence,
            evidence_without_evidenced_status=evidence_without_evidenced_status,
            unassigned_requirements_count=int(unassigned_count_result.scalar() or 0),
            unlinked_requirements_count=int(unlinked_count_result.scalar() or 0),
        )

    response = DashboardResponse(
        generated_at=now,
        kpis=Kpis(
            overall=overall_metric,
            mandatory=mandatory_metric,
            at_risk_count=at_risk_count,
            by_status=by_status,
        ),
        breakdowns=breakdowns,
        my_work=my_work,
        review_cycles=review_cycles,
        snapshots=snapshots,
        recent_activity=recent_activity,
        queues=queues,
        data_quality=data_quality,
    )
    return response
