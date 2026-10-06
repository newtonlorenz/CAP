import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.program import (
    CertificationProjectRequirementBaseline,
    MaintenanceEvent,
    MaintenancePlan,
    RequirementSetVersion,
    ReviewCycleRequirementBaseline,
)
from app.models.requirement import Requirement
from app.models.review import ReviewCycle, ReviewItem
from app.models.user import User
from app.services.access import access_clause


_STAGE_TEXT_TO_DAYS: list[tuple[str, int]] = [
    ("daily", 1),
    ("weekly", 7),
    ("biweekly", 14),
    ("fortnight", 14),
    ("monthly", 30),
    ("quarter", 90),
    ("semi", 182),
    ("annual", 365),
    ("yearly", 365),
]


def frequency_to_days(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    lowered = value.strip().lower()
    if not lowered:
        return None

    if lowered.isdigit():
        days = int(lowered)
        return days if days > 0 else None

    for token, days in _STAGE_TEXT_TO_DAYS:
        if token in lowered:
            return days

    return None


def _coerce_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _plan_name(document: Document) -> str:
    base = (document.name or document.filename or "requirement-set").strip()
    return f"Maintenance plan: {base}"


def _org_filter(query, model, current_user: User):
    query = query.where(access_clause(model, current_user, "view"))
    org_id = current_user.organization_id
    if org_id is None:
        return query.where(model.organization_id.is_(None))
    return query.where(model.organization_id == org_id)


async def ensure_maintenance_plan_for_document(
    db: AsyncSession,
    document: Document,
    *,
    created_by: Optional[uuid.UUID],
    only_missing: bool = True,
) -> Optional[MaintenancePlan]:
    cadence_days = frequency_to_days(document.testing_frequency)
    if cadence_days is None:
        return None

    document.cadence_interval_days = cadence_days

    existing = None
    if only_missing:
        existing_result = await db.execute(
            select(MaintenancePlan).where(
                and_(
                    MaintenancePlan.document_id == document.id,
                    MaintenancePlan.certification_project_id.is_(None),
                    MaintenancePlan.status != "archived",
                    MaintenancePlan.organization_id == document.organization_id,
                )
            )
        )
        existing = existing_result.scalars().first()

    if existing is not None:
        if document.maintenance_plan_id is None:
            document.maintenance_plan_id = existing.id
        return existing

    now = datetime.now(timezone.utc)
    plan = MaintenancePlan(
        organization_id=document.organization_id,
        jurisdiction_id=document.jurisdiction_id,
        document_id=document.id,
        name=_plan_name(document),
        cadence_days=cadence_days,
        reminder_days=7,
        escalation_days=3,
        next_run_at=now + timedelta(days=cadence_days),
        status="active",
        auto_generated=True,
        owner_id=document.uploaded_by,
        created_by=created_by,
    )
    db.add(plan)
    await db.flush()

    document.maintenance_plan_id = plan.id
    return plan


async def generate_maintenance_plans(
    db: AsyncSession,
    *,
    current_user: User,
    jurisdiction_id: Optional[uuid.UUID] = None,
    only_missing: bool = True,
) -> dict[str, int]:
    query = _org_filter(
        select(Document).where(Document.archived_at.is_(None)),
        Document,
        current_user,
    )
    if jurisdiction_id is not None:
        query = query.where(Document.jurisdiction_id == jurisdiction_id)
    result = await db.execute(query)
    documents = result.scalars().all()

    generated = 0
    reused = 0
    skipped = 0

    for document in documents:
        before_plan_id = document.maintenance_plan_id
        plan = await ensure_maintenance_plan_for_document(
            db,
            document,
            created_by=current_user.id,
            only_missing=only_missing,
        )
        if plan is None:
            skipped += 1
            continue
        if before_plan_id is None and document.maintenance_plan_id is not None:
            generated += 1
        else:
            reused += 1

    return {
        "total_documents": len(documents),
        "generated": generated,
        "reused": reused,
        "skipped": skipped,
    }


async def generate_due_review_cycles(
    db: AsyncSession,
    *,
    current_user: User,
    now: Optional[datetime] = None,
    certification_project_id: Optional[uuid.UUID] = None,
) -> dict[str, int]:
    run_at = _coerce_utc(now or datetime.now(timezone.utc))

    due_result = await db.execute(
        _org_filter(
            select(MaintenancePlan).where(
                and_(
                    MaintenancePlan.status == "active",
                    access_clause(MaintenancePlan, current_user, "edit"),
                    (MaintenancePlan.certification_project_id == certification_project_id)
                    if certification_project_id else True,
                    MaintenancePlan.next_run_at.is_not(None),
                    MaintenancePlan.next_run_at <= run_at,
                )
            ),
            MaintenancePlan,
            current_user,
        )
    )
    plans = due_result.scalars().all()

    generated_cycles = 0
    generated_items = 0

    for plan in plans:
        baseline_pairs: list[tuple[uuid.UUID, uuid.UUID]] = []
        if plan.certification_project_id is not None:
            baseline_query = select(
                CertificationProjectRequirementBaseline.document_id,
                CertificationProjectRequirementBaseline.requirement_set_version_id,
            ).join(RequirementSetVersion, RequirementSetVersion.id == CertificationProjectRequirementBaseline.requirement_set_version_id).where(
                CertificationProjectRequirementBaseline.project_id == plan.certification_project_id,
                RequirementSetVersion.status == "approved",
                RequirementSetVersion.organization_id == current_user.organization_id,
            )
            if plan.document_id:
                baseline_query = baseline_query.where(CertificationProjectRequirementBaseline.document_id == plan.document_id)
            baseline_pairs = list((await db.execute(baseline_query)).all())
        elif plan.document_id is not None:
            document_result = await db.execute(
                _org_filter(
                    select(Document).where(
                        and_(
                            Document.id == plan.document_id,
                            Document.jurisdiction_id == plan.jurisdiction_id,
                            Document.status == "approved",
                        )
                    ),
                    Document,
                    current_user,
                )
            )
            document = document_result.scalar_one_or_none()
            if document is not None:
                version_result = await db.execute(
                    select(RequirementSetVersion)
                    .where(
                        and_(
                            RequirementSetVersion.document_id == document.id,
                            RequirementSetVersion.status == "approved",
                            RequirementSetVersion.is_current.is_(True),
                            RequirementSetVersion.organization_id == current_user.organization_id,
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
                                RequirementSetVersion.document_id == document.id,
                                RequirementSetVersion.status == "approved",
                                RequirementSetVersion.organization_id
                                == current_user.organization_id,
                            )
                        )
                        .order_by(RequirementSetVersion.version_number.desc())
                        .limit(1)
                    )
                    version = fallback_result.scalar_one_or_none()
                if version is not None:
                    baseline_pairs.append((document.id, version.id))
        else:
            documents_result = await db.execute(
                _org_filter(
                    select(Document).where(
                        and_(
                            Document.jurisdiction_id == plan.jurisdiction_id,
                            Document.status == "approved",
                        )
                    ),
                    Document,
                    current_user,
                )
            )
            documents = documents_result.scalars().all()
            for document in documents:
                version_result = await db.execute(
                    select(RequirementSetVersion)
                    .where(
                        and_(
                            RequirementSetVersion.document_id == document.id,
                            RequirementSetVersion.status == "approved",
                            RequirementSetVersion.is_current.is_(True),
                            RequirementSetVersion.organization_id == current_user.organization_id,
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
                                RequirementSetVersion.document_id == document.id,
                                RequirementSetVersion.status == "approved",
                                RequirementSetVersion.organization_id
                                == current_user.organization_id,
                            )
                        )
                        .order_by(RequirementSetVersion.version_number.desc())
                        .limit(1)
                    )
                    version = fallback_result.scalar_one_or_none()
                if version is not None:
                    baseline_pairs.append((document.id, version.id))

        if not baseline_pairs:
            continue

        predecessor_id = await db.scalar(select(MaintenanceEvent.review_cycle_id).where(
            MaintenanceEvent.maintenance_plan_id == plan.id,
            MaintenanceEvent.review_cycle_id.is_not(None),
        ).order_by(MaintenanceEvent.created_at.desc(), MaintenanceEvent.id.desc()).limit(1))
        cycle_name = f"Auto cycle: {plan.name} ({run_at.date().isoformat()})"
        cycle = ReviewCycle(
            organization_id=plan.organization_id,
            certification_project_id=plan.certification_project_id,
            predecessor_cycle_id=predecessor_id,
            jurisdiction_id=plan.jurisdiction_id,
            cycle_type="maintenance",
            name=cycle_name,
            description="Auto-generated from maintenance plan cadence.",
            scope="documents",
            scope_filter=json.dumps([str(document_id) for document_id, _ in baseline_pairs]),
            deadline=run_at + timedelta(days=max(1, plan.reminder_days)),
            status="active",
            created_by=current_user.id,
        )
        db.add(cycle)
        await db.flush()

        for document_id, version_id in baseline_pairs:
            db.add(
                ReviewCycleRequirementBaseline(
                    review_cycle_id=cycle.id,
                    document_id=document_id,
                    requirement_set_version_id=version_id,
                )
            )

        baseline_version_ids = [version_id for _, version_id in baseline_pairs]
        req_query = _org_filter(
            select(Requirement).where(
                and_(
                    Requirement.active.is_(True),
                    Requirement.jurisdiction_id == plan.jurisdiction_id,
                    Requirement.requirement_set_version_id.in_(baseline_version_ids),
                )
            ),
            Requirement,
            current_user,
        )

        req_result = await db.execute(req_query)
        requirements = req_result.scalars().all()

        for req in requirements:
            non_actionable = req.requirement_type in {"informational", "not_applicable"}
            db.add(
                ReviewItem(
                    review_cycle_id=cycle.id,
                    requirement_id=req.id,
                    assessment_status="not_started",
                    review_status="confirmed" if non_actionable else "pending",
                    review_comment=(
                        "Informational requirement - no action required"
                        if req.requirement_type == "informational"
                        else (
                            "Not applicable requirement - no action required"
                            if req.requirement_type == "not_applicable"
                            else None
                        )
                    ),
                )
            )
            generated_items += 1

        db.add(
            MaintenanceEvent(
                maintenance_plan_id=plan.id,
                review_cycle_id=cycle.id,
                event_type="generated",
                created_at=run_at,
                due_at=cycle.deadline,
                status="completed",
            )
        )

        plan.last_run_at = run_at
        plan.next_run_at = run_at + timedelta(days=max(1, plan.cadence_days))

        generated_cycles += 1

    return {
        "due_plans": len(plans),
        "generated_cycles": generated_cycles,
        "generated_items": generated_items,
    }
