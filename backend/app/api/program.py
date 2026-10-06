import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_installation_operator, require_role
from app.api.tenant import apply_org_scope, get_active_user_in_org_or_404, get_org_owned_or_404
from app.database import get_db
from app.models.document import Document
from app.models.requirement import Requirement
from app.models.program import (
    BaselineMigration,
    CertificationProject,
    CertificationProjectRequirementBaseline,
    CertificationProjectMilestone,
    Control,
    ControlCrosswalk,
    EvidenceItem,
    EvidenceValidation,
    ExportManifest,
    IntegrationConnection,
    MaintenanceEvent,
    MaintenancePlan,
    Obligation,
    RequirementSetVersion,
    ReviewCycleRequirementBaseline,
    SubmissionPackage,
    SubmissionPackageArtifact,
)
from app.models.review import ReviewCycle, ReviewItem, ReviewItemComment, Snapshot
from app.models.user import User
from app.schemas.program import (
    BaselineMigrationExecuteResponse,
    BaselineMigrationPreviewRequest,
    BaselineMigrationPreviewResponse,
    CertificationProjectBaselineUpdateRequest,
    CertificationProjectBaselineUpdateResponse,
    CertificationProjectCreate,
    CertificationProjectFromDocumentResponse,
    CertificationProjectMilestoneCreate,
    CertificationProjectMilestoneResponse,
    CertificationProjectMilestoneUpdate,
    CertificationProjectSubmissionCycleResponse,
    CertificationProjectResponse,
    CertificationProjectUpdate,
    EngagementFields,
    ControlCreate,
    ControlCrosswalkCreate,
    ControlCrosswalkResponse,
    ControlResponse,
    EvidenceItemCreate,
    EvidenceItemResponse,
    EvidenceItemUpdate,
    EvidenceValidationCreate,
    EvidenceValidationResponse,
    ExportManifestCreate,
    ExportManifestResponse,
    IntegrationConnectionCreate,
    IntegrationConnectionResponse,
    IntegrationConnectionUpdate,
    MaintenanceEventResponse,
    MaintenancePlanCreate,
    MaintenancePlanGenerateRequest,
    MaintenancePlanResponse,
    MaintenancePlanUpdate,
    ObligationCreate,
    ObligationResponse,
    ProgramGateBlocker,
    ProgramStageCheck,
    ProgramStageReadiness,
    ProgramStageState,
    ProgramWorkspaceAction,
    ProgramWorkspaceProjectDeepLinks,
    ProgramWorkspaceProjectSummary,
    ProgramWorkspaceSummaryResponse,
    ProjectBaselineVersion,
    ProjectMigrationExecuteRequest,
    SubmissionChecklist,
    SubmissionChecklistCompletion,
    SubmissionPackageArtifactCreate,
    SubmissionPackageArtifactResponse,
    SubmissionPackageArtifactUpdate,
    SubmissionPackageCreate,
    SubmissionPackageGateCheckResponse,
    SubmissionPackageResponse,
    SubmissionPackageUpdate,
    SubmissionPackageReturnRequest,
)
from app.services.audit import log_action
from app.services.access import access_clause, initialize_access, require_access
from app.services.export_manifest import sign_manifest, verify_manifest
from app.services.maintenance import (
    ensure_maintenance_plan_for_document,
    generate_due_review_cycles,
    generate_maintenance_plans,
)
from app.services.requirement_baselines import (
    default_review_state_for_requirement,
    get_current_approved_version_for_document,
    load_requirements_for_versions,
)
from app.services.review_migration import (
    ReviewMigrationCloneError,
    ReviewMigrationDecisionError,
    cleanup_cloned_files,
    clone_review_cycle_items_for_migration,
    compare_baseline_requirements,
    resolve_project_changed_decisions,
    should_carry_forward_requirement,
)

router = APIRouter(prefix="/api/v1", tags=["program"])


PROJECT_STAGES = [
    "intake",
    "scoping",
    "gap_assessment",
    "remediation",
    "pre_audit",
    "submission",
    "follow_up",
]
PROJECT_STAGE_INDEX = {stage: index for index, stage in enumerate(PROJECT_STAGES)}
ACTION_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}
PROGRAM_NOT_APPLICABLE_REVIEW_STATE = (
    "confirmed",
    "Not applicable requirement - no action required",
)


def _format_stage_title(stage: str) -> str:
    return stage.replace("_", " ").title()


def _project_workspace_link(project_id: uuid.UUID, section: Optional[str] = None) -> str:
    path = f"/certification-projects?project={project_id}"
    return f"{path}&section={section}" if section else path


def _org_filter(query, model, current_user: User):
    return apply_org_scope(query, model, current_user)


def _seed_project_milestones(db: AsyncSession, project_id: uuid.UUID) -> None:
    for stage in PROJECT_STAGES:
        db.add(
            CertificationProjectMilestone(
                project_id=project_id,
                stage=stage,
                title=stage.replace("_", " ").title(),
                status="pending",
            )
        )


async def _load_project_baseline_versions(
    db: AsyncSession,
    project_id: uuid.UUID,
) -> tuple[list[ProjectBaselineVersion], list[uuid.UUID]]:
    baseline_result = await db.execute(
        select(
            CertificationProjectRequirementBaseline.document_id,
            CertificationProjectRequirementBaseline.requirement_set_version_id,
            RequirementSetVersion.version_number,
            Document.name,
            Document.filename,
        )
        .join(
            RequirementSetVersion,
            RequirementSetVersion.id
            == CertificationProjectRequirementBaseline.requirement_set_version_id,
        )
        .outerjoin(Document, Document.id == CertificationProjectRequirementBaseline.document_id)
        .where(CertificationProjectRequirementBaseline.project_id == project_id)
        .order_by(Document.name.asc(), Document.filename.asc())
    )
    baseline_versions: list[ProjectBaselineVersion] = []
    requirement_set_ids: list[uuid.UUID] = []
    for document_id, version_id, version_number, set_name, filename in baseline_result.all():
        baseline_versions.append(
            ProjectBaselineVersion(
                document_id=document_id,
                requirement_set_version_id=version_id,
                version_number=version_number,
                set_name=set_name or filename,
            )
        )
        requirement_set_ids.append(document_id)
    return baseline_versions, requirement_set_ids


async def _build_project_response(
    db: AsyncSession,
    project: CertificationProject,
) -> CertificationProjectResponse:
    baseline_versions, requirement_set_ids = await _load_project_baseline_versions(db, project.id)
    response = CertificationProjectResponse.model_validate(project).model_dump()
    response["baseline_versions"] = [item.model_dump() for item in baseline_versions]
    response["requirement_set_ids"] = requirement_set_ids
    return CertificationProjectResponse(**response)


async def _resolve_project_baseline_targets(
    db: AsyncSession,
    current_user: User,
    jurisdiction_id: uuid.UUID,
    requirement_set_ids: list[uuid.UUID],
) -> list[tuple[Document, RequirementSetVersion]]:
    if not requirement_set_ids:
        return []

    deduped_ids: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for document_id in requirement_set_ids:
        if document_id in seen:
            continue
        seen.add(document_id)
        deduped_ids.append(document_id)

    docs_result = await db.execute(
        _org_filter(
            select(Document).where(Document.id.in_(deduped_ids)),
            Document,
            current_user,
        )
    )
    docs_by_id = {doc.id: doc for doc in docs_result.scalars().all()}
    if len(docs_by_id) != len(deduped_ids):
        raise HTTPException(status_code=404, detail="One or more requirement sets were not found")

    targets: list[tuple[Document, RequirementSetVersion]] = []
    for document_id in deduped_ids:
        document = docs_by_id[document_id]
        if document.jurisdiction_id != jurisdiction_id:
            raise HTTPException(
                status_code=400,
                detail="All selected requirement sets must match the project jurisdiction",
            )
        if document.status != "approved":
            raise HTTPException(
                status_code=400,
                detail=f"Requirement set '{document.name or document.filename}' must be approved",
            )
        version = await get_current_approved_version_for_document(db, document.id)
        if version is None:
            raise HTTPException(
                status_code=400,
                detail=f"No approved baseline version found for requirement set '{document.name or document.filename}'",
            )
        targets.append((document, version))
    return targets


async def _replace_project_baselines(
    db: AsyncSession,
    project: CertificationProject,
    targets: list[tuple[Document, RequirementSetVersion]],
) -> None:
    await db.execute(
        delete(CertificationProjectRequirementBaseline).where(
            CertificationProjectRequirementBaseline.project_id == project.id
        )
    )
    for document, version in targets:
        db.add(
            CertificationProjectRequirementBaseline(
                project_id=project.id,
                document_id=document.id,
                requirement_set_version_id=version.id,
            )
        )


async def _create_review_items_from_requirements(
    db: AsyncSession,
    cycle_id: uuid.UUID,
    requirements: list[Requirement],
) -> int:
    created = 0
    for requirement in requirements:
        review_status, review_comment = default_review_state_for_requirement(
            requirement,
            not_applicable_state=PROGRAM_NOT_APPLICABLE_REVIEW_STATE,
        )

        item = ReviewItem(
            review_cycle_id=cycle_id,
            requirement_id=requirement.id,
            review_status=review_status,
            review_comment=review_comment,
            assessment_status=(
                "not_applicable" if requirement.requirement_type == "not_applicable"
                else "not_started"
            ),
        )
        db.add(item)
        await db.flush()
        created += 1
        if review_comment:
            db.add(
                ReviewItemComment(
                    review_item_id=item.id,
                    author_id=None,
                    body=review_comment,
                )
            )
    return created

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
        key = (requirement.document_id, requirement.reference_id)
        lookup[key] = (item, requirement)
    return lookup


async def _get_project_for_user(
    db: AsyncSession,
    current_user: User,
    project_id: uuid.UUID,
) -> CertificationProject:
    query = _org_filter(
        select(CertificationProject).where(CertificationProject.id == project_id, access_clause(CertificationProject, current_user, "view")),
        CertificationProject,
        current_user,
    )
    result = await db.execute(query)
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Certification project not found")
    return project


async def _get_submission_package_for_user(
    db: AsyncSession,
    current_user: User,
    package_id: uuid.UUID,
    *,
    lock: bool = False,
) -> SubmissionPackage:
    query = (
        select(SubmissionPackage)
        .join(CertificationProject, CertificationProject.id == SubmissionPackage.project_id)
        .where(SubmissionPackage.id == package_id)
    )
    query = _org_filter(query, CertificationProject, current_user)
    if lock:
        query = query.with_for_update(of=SubmissionPackage).execution_options(populate_existing=True)
    result = await db.execute(query)
    package = result.scalar_one_or_none()
    if package is None:
        raise HTTPException(status_code=404, detail="Submission package not found")
    return package


async def _require_package_access(db, current_user, package_id, action):
    package = await _get_submission_package_for_user(db, current_user, package_id)
    await require_access(db, CertificationProject, package.project_id, current_user, action)
    return package


def _parse_submission_checklist(checklist_json: Optional[str]) -> Optional[SubmissionChecklist]:
    if not checklist_json:
        return None
    try:
        payload = json.loads(checklist_json)
    except json.JSONDecodeError:
        return None
    try:
        return SubmissionChecklist.model_validate(payload)
    except ValueError:
        return None


def _submission_checklist_completion(
    checklist: Optional[SubmissionChecklist],
) -> SubmissionChecklistCompletion:
    if checklist is None:
        return SubmissionChecklistCompletion()

    required_total = 0
    required_completed = 0
    optional_total = 0
    optional_completed = 0
    blocking_items: list[str] = []

    for section in checklist.sections:
        for item in section.items:
            if item.required:
                required_total += 1
                if item.completed:
                    required_completed += 1
                else:
                    blocking_items.append(item.label)
            else:
                optional_total += 1
                if item.completed:
                    optional_completed += 1

    total_items = required_total + optional_total
    completed_items = required_completed + optional_completed
    completion_score = completed_items / total_items if total_items else 1.0
    return SubmissionChecklistCompletion(
        required_total=required_total,
        required_completed=required_completed,
        optional_total=optional_total,
        optional_completed=optional_completed,
        completion_score=round(completion_score, 4),
        ready=not blocking_items,
        blocking_items=blocking_items,
    )


def _checklist_json_from_payload(checklist: Optional[SubmissionChecklist]) -> Optional[str]:
    if checklist is None:
        return None
    return json.dumps(checklist.model_dump(mode="json"), sort_keys=True)


def _submission_package_response(package: SubmissionPackage) -> SubmissionPackageResponse:
    checklist = _parse_submission_checklist(package.checklist_json)
    data = SubmissionPackageResponse.model_validate(package).model_dump()
    data["checklist"] = checklist.model_dump() if checklist else None
    data["checklist_completion"] = _submission_checklist_completion(checklist).model_dump()
    return SubmissionPackageResponse(**data)


async def _get_project_submission_cycle(
    db: AsyncSession,
    project_id: uuid.UUID,
) -> Optional[ReviewCycle]:
    result = await db.execute(
        select(ReviewCycle).where(
            and_(
                ReviewCycle.certification_project_id == project_id,
                ReviewCycle.cycle_type == "submission",
                ReviewCycle.status != "archived",
            )
        )
    )
    return result.scalar_one_or_none()


async def _build_submission_package_gate_check(
    db: AsyncSession,
    package: SubmissionPackage,
    project: CertificationProject,
) -> SubmissionPackageGateCheckResponse:
    blocking_reasons: list[str] = []
    cycle: Optional[ReviewCycle] = None

    if package.review_cycle_id is not None:
        cycle_result = await db.execute(
            select(ReviewCycle).where(
                and_(
                    ReviewCycle.id == package.review_cycle_id,
                    ReviewCycle.certification_project_id == project.id,
                    ReviewCycle.cycle_type == "submission",
                )
            )
        )
        cycle = cycle_result.scalar_one_or_none()
        if cycle is None:
            blocking_reasons.append("Linked submission review cycle is not valid for this project.")
    else:
        blocking_reasons.append("Submission package is not linked to a submission review cycle.")

    review_cycle_closed = cycle is not None and cycle.status == "closed"
    if cycle is not None and not review_cycle_closed:
        blocking_reasons.append("Submission review cycle must be closed before package approval.")

    review_cycle_snapshot_id = cycle.snapshot_id if cycle is not None else None
    if cycle is not None and cycle.status == "closed" and cycle.snapshot_id is None:
        blocking_reasons.append("Closed submission review cycle is missing its snapshot.")

    if package.snapshot_id is None:
        blocking_reasons.append("Submission package is not bound to a snapshot.")
    elif (
        cycle is not None
        and cycle.snapshot_id is not None
        and package.snapshot_id != cycle.snapshot_id
    ):
        blocking_reasons.append(
            "Submission package snapshot does not match submission review cycle snapshot."
        )

    required_result = await db.execute(
        select(SubmissionPackageArtifact).where(
            and_(
                SubmissionPackageArtifact.submission_package_id == package.id,
                SubmissionPackageArtifact.required.is_(True),
            )
        )
    )
    required_artifacts = required_result.scalars().all()
    missing_required_artifacts = [
        artifact.name for artifact in required_artifacts
        if not artifact.included or not ((artifact.file_path or "").strip() or (artifact.link_url or "").strip())
    ]
    if missing_required_artifacts:
        blocking_reasons.append("Required artifacts need an included file reference or link: " + ", ".join(missing_required_artifacts))

    required_total = len(required_artifacts)
    required_included = required_total - len(missing_required_artifacts)
    checklist_completion = _submission_checklist_completion(
        _parse_submission_checklist(package.checklist_json)
    )
    if checklist_completion.blocking_items:
        blocking_reasons.append("Required checklist items are incomplete.")

    return SubmissionPackageGateCheckResponse(
        package_id=package.id,
        project_id=project.id,
        status=package.status,
        review_cycle_linked=cycle is not None,
        review_cycle_closed=review_cycle_closed,
        review_cycle_snapshot_id=review_cycle_snapshot_id,
        snapshot_bound=package.snapshot_id is not None,
        required_artifacts_total=required_total,
        required_artifacts_included=required_included,
        missing_required_artifacts=missing_required_artifacts,
        checklist_required_total=checklist_completion.required_total,
        checklist_required_completed=checklist_completion.required_completed,
        checklist_completion_score=checklist_completion.completion_score,
        checklist_blocking_items=checklist_completion.blocking_items,
        checks_passed=len(blocking_reasons) == 0,
        blocking_reasons=blocking_reasons,
    )


async def _get_latest_project_package(
    db: AsyncSession,
    project_id: uuid.UUID,
) -> Optional[SubmissionPackage]:
    result = await db.execute(
        select(SubmissionPackage)
        .where(SubmissionPackage.project_id == project_id)
        .order_by(SubmissionPackage.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _build_stage_transition_checks(
    db: AsyncSession,
    project: CertificationProject,
    stage: str,
) -> list[ProgramStageCheck]:
    project_link = _project_workspace_link(project.id, {
        "intake": "baseline", "scoping": "review", "gap_assessment": "review",
        "remediation": "review", "pre_audit": "packages", "submission": "packages",
    }.get(stage))

    if stage == "intake":
        baseline_count_result = await db.execute(
            select(func.count(CertificationProjectRequirementBaseline.document_id)).where(
                CertificationProjectRequirementBaseline.project_id == project.id
            )
        )
        baseline_count = int(baseline_count_result.scalar() or 0)
        passed = baseline_count > 0
        return [
            ProgramStageCheck(
                code="baseline_configured",
                label="Project baseline is configured",
                passed=passed,
                severity="error",
                reason=(
                    None
                    if passed
                    else "Select at least one approved requirement set before moving out of Intake."
                ),
                cta_label="Configure baseline",
                cta_path=project_link,
            )
        ]

    if stage == "scoping":
        cycle = await _get_project_submission_cycle(db, project.id)
        passed = cycle is not None
        return [
            ProgramStageCheck(
                code="submission_cycle_exists",
                label="Submission review cycle exists",
                passed=passed,
                severity="error",
                reason=(
                    None
                    if passed
                    else "Create a submission review cycle before progressing to Gap Assessment."
                ),
                cta_label="Open submission cycle setup",
                cta_path=project_link,
            )
        ]

    if stage == "gap_assessment":
        cycle = await _get_project_submission_cycle(db, project.id)
        if cycle is None:
            return [
                ProgramStageCheck(
                    code="submission_cycle_exists",
                    label="Submission review cycle exists",
                    passed=False,
                    severity="error",
                    reason="No submission review cycle is linked to this project.",
                    cta_label="Open submission cycle setup",
                    cta_path=project_link,
                )
            ]
        item_count_result = await db.execute(
            select(func.count(ReviewItem.id)).where(ReviewItem.review_cycle_id == cycle.id)
        )
        item_count = int(item_count_result.scalar() or 0)
        passed = item_count > 0
        return [
            ProgramStageCheck(
                code="review_items_seeded",
                label="Submission requirements are selected",
                passed=passed,
                severity="error",
                reason=(
                    None if passed else "The submission assessment has no requirements to assess."
                ),
                cta_label="Open submission cycle",
                cta_path=f"/review-cycles/{cycle.id}",
            )
        ]

    if stage == "remediation":
        cycle = await _get_project_submission_cycle(db, project.id)
        if cycle is None:
            return [
                ProgramStageCheck(
                    code="submission_cycle_exists",
                    label="Submission review cycle exists",
                    passed=False,
                    severity="error",
                    reason="No submission review cycle is linked to this project.",
                    cta_label="Open submission cycle setup",
                    cta_path=project_link,
                ),
                ProgramStageCheck(
                    code="submission_cycle_closed",
                    label="Submission review cycle is closed",
                    passed=False,
                    severity="error",
                    reason="Close the submission review cycle after completing remediation validation.",
                    cta_label="Open submission cycle setup",
                    cta_path=project_link,
                ),
            ]
        cycle_closed = cycle.status == "closed"
        has_snapshot = cycle.snapshot_id is not None
        return [
            ProgramStageCheck(
                code="submission_cycle_closed",
                label="Submission review cycle is closed",
                passed=cycle_closed,
                severity="error",
                reason=(
                    None
                    if cycle_closed
                    else "Close the submission review cycle before moving to Pre-audit."
                ),
                cta_label="Open submission cycle",
                cta_path=f"/review-cycles/{cycle.id}",
            ),
            ProgramStageCheck(
                code="submission_cycle_snapshot_bound",
                label="Closed submission cycle has a bound snapshot",
                passed=cycle_closed and has_snapshot,
                severity="error",
                reason=(
                    None
                    if cycle_closed and has_snapshot
                    else "Create and bind a snapshot to the closed submission cycle."
                ),
                cta_label="Open submission cycle",
                cta_path=f"/review-cycles/{cycle.id}",
            ),
        ]

    if stage == "pre_audit":
        package = await _get_latest_project_package(db, project.id)
        if package is None:
            return [
                ProgramStageCheck(
                    code="submission_package_exists",
                    label="Submission package exists and passes gate checks",
                    passed=False,
                    severity="error",
                    reason="No submission package exists for this project.",
                    cta_label="Open submission packages",
                    cta_path=project_link,
                )
            ]
        gate_check = await _build_submission_package_gate_check(db, package, project)
        blocking_reason = (
            "; ".join(gate_check.blocking_reasons[:2]) if gate_check.blocking_reasons else None
        )
        return [
            ProgramStageCheck(
                code="submission_package_gate_check",
                label="Submission package passes hard gate checks",
                passed=gate_check.checks_passed,
                severity="error",
                reason=(
                    None
                    if gate_check.checks_passed
                    else (blocking_reason or "Submission package gate checks are not satisfied.")
                ),
                cta_label="Open submission packages",
                cta_path=project_link,
            )
        ]

    if stage == "submission":
        locked_count_result = await db.execute(
            select(func.count(SubmissionPackage.id)).where(
                and_(
                    SubmissionPackage.project_id == project.id,
                    SubmissionPackage.status == "locked",
                )
            )
        )
        locked_count = int(locked_count_result.scalar() or 0)
        has_handoff_marker = (
            project.completed_at is not None
            or project.status == "completed"
            or project.stage == "follow_up"
        )
        return [
            ProgramStageCheck(
                code="submission_package_locked",
                label="Submission package is approved and locked",
                passed=locked_count > 0,
                severity="error",
                reason=(
                    None
                    if locked_count > 0
                    else "Lock the approved submission package before handing off to follow-up."
                ),
                cta_label="Open submission packages",
                cta_path=project_link,
            ),
            ProgramStageCheck(
                code="handoff_recorded",
                label="Project handoff has been recorded",
                passed=has_handoff_marker,
                severity="error",
                reason=(
                    None
                    if has_handoff_marker
                    else "Project completion handoff has not been recorded yet."
                ),
                cta_label="Open project",
                cta_path=project_link,
            ),
        ]

    if stage == "follow_up":
        return [
            ProgramStageCheck(
                code="follow_up_active",
                label="Project is operating in follow-up mode",
                passed=True,
                severity="warning",
                cta_label="Open project",
                cta_path=project_link,
            )
        ]

    return [
        ProgramStageCheck(
            code="unknown_stage",
            label="Unknown stage configuration",
            passed=False,
            severity="error",
            reason="This project is set to an unsupported stage value.",
            cta_label="Open project",
            cta_path=project_link,
        )
    ]


async def _build_project_stage_state_summary(
    db: AsyncSession,
    project: CertificationProject,
) -> tuple[list[ProgramStageState], ProgramStageReadiness, list[ProgramGateBlocker]]:
    checks_by_stage: dict[str, list[ProgramStageCheck]] = {}
    for stage in PROJECT_STAGES:
        checks_by_stage[stage] = await _build_stage_transition_checks(db, project, stage)

    current_stage = project.stage if project.stage in PROJECT_STAGE_INDEX else PROJECT_STAGES[0]
    current_index = PROJECT_STAGE_INDEX.get(current_stage, 0)
    current_checks = checks_by_stage.get(current_stage, [])
    current_blockers = [check for check in current_checks if not check.passed]
    current_ready = len(current_blockers) == 0

    stage_states: list[ProgramStageState] = []
    for index, stage in enumerate(PROJECT_STAGES):
        stage_checks = checks_by_stage.get(stage, [])
        ready_to_advance = all(check.passed for check in stage_checks)
        if index < current_index:
            state = "completed"
        elif index == current_index:
            state = "in_progress"
        elif index == current_index + 1:
            state = "ready" if current_ready else "blocked"
        else:
            state = "upcoming"
        stage_states.append(
            ProgramStageState(
                stage=stage,
                title=_format_stage_title(stage),
                order=index,
                state=state,
                ready_to_advance=ready_to_advance,
                checks=stage_checks,
            )
        )

    blockers = [
        ProgramGateBlocker(
            code=check.code,
            reason=check.reason or f"{check.label} is not satisfied.",
            cta_label=check.cta_label,
            cta_path=check.cta_path,
        )
        for check in current_blockers
    ]
    readiness = ProgramStageReadiness(ready=current_ready, blocker_count=len(blockers))
    return stage_states, readiness, blockers


async def _build_project_workspace_deep_links(
    db: AsyncSession,
    project: CertificationProject,
) -> ProgramWorkspaceProjectDeepLinks:
    cycle = await _get_project_submission_cycle(db, project.id)
    package = await _get_latest_project_package(db, project.id)
    return ProgramWorkspaceProjectDeepLinks(
        project=_project_workspace_link(project.id),
        review_cycle=f"/review-cycles/{cycle.id}" if cycle is not None else None,
        submission_package=_project_workspace_link(project.id, "packages") if package is not None else None,
    )


def _action_priority_for_stage(stage: str) -> str:
    if stage in {"remediation", "pre_audit", "submission"}:
        return "high"
    if stage in {"intake", "scoping", "gap_assessment"}:
        return "medium"
    return "low"


def _build_project_next_actions(
    project: CertificationProject,
    blockers: list[ProgramGateBlocker],
    readiness: ProgramStageReadiness,
    deep_links: ProgramWorkspaceProjectDeepLinks,
) -> list[ProgramWorkspaceAction]:
    actions: list[ProgramWorkspaceAction] = []
    role_scope = ["admin", "manager"]

    if blockers:
        priority = _action_priority_for_stage(project.stage)
        for blocker in blockers:
            actions.append(
                ProgramWorkspaceAction(
                    id=f"{project.id}:{project.stage}:{blocker.code}",
                    project_id=project.id,
                    stage=project.stage,
                    priority=priority,
                    title=f"{_format_stage_title(project.stage)} is blocked",
                    summary=blocker.reason,
                    cta_label=blocker.cta_label or "Open project",
                    cta_path=blocker.cta_path or deep_links.project,
                    role_scope=role_scope,
                )
            )
        return actions

    current_index = PROJECT_STAGE_INDEX.get(project.stage, 0)
    if readiness.ready and current_index < len(PROJECT_STAGES) - 1:
        next_stage = PROJECT_STAGES[current_index + 1]
        actions.append(
            ProgramWorkspaceAction(
                id=f"{project.id}:{project.stage}:advance",
                project_id=project.id,
                stage=project.stage,
                priority="low",
                title=f"Advance to {_format_stage_title(next_stage)}",
                summary=(
                    f"{_format_stage_title(project.stage)} checks are clear. "
                    "Update the project stage when ready."
                ),
                cta_label="Open project stage controls",
                cta_path=deep_links.project,
                role_scope=role_scope,
            )
        )
    return actions


def _action_sort_key(action: ProgramWorkspaceAction) -> tuple[int, str, str]:
    return (
        ACTION_PRIORITY_ORDER.get(action.priority, 99),
        action.stage,
        action.title,
    )


async def _resolve_submission_cycle_for_project(
    db: AsyncSession,
    project_id: uuid.UUID,
    review_cycle_id: Optional[uuid.UUID],
) -> Optional[ReviewCycle]:
    if review_cycle_id is None:
        return None
    result = await db.execute(
        select(ReviewCycle).where(
            and_(
                ReviewCycle.id == review_cycle_id,
                ReviewCycle.certification_project_id == project_id,
                ReviewCycle.cycle_type == "submission",
            )
        )
    )
    cycle = result.scalar_one_or_none()
    if cycle is None:
        raise HTTPException(status_code=400, detail="Invalid submission review cycle for project")
    return cycle


async def _resolve_snapshot_for_org(
    db: AsyncSession,
    current_user: User,
    snapshot_id: Optional[uuid.UUID],
) -> Optional[Snapshot]:
    if snapshot_id is None:
        return None
    query = _org_filter(
        select(Snapshot).where(Snapshot.id == snapshot_id),
        Snapshot,
        current_user,
    )
    result = await db.execute(query)
    snapshot = result.scalar_one_or_none()
    if snapshot is None:
        raise HTTPException(status_code=400, detail="Invalid snapshot_id")
    return snapshot


@router.get("/controls", response_model=dict)
async def list_controls(
    jurisdiction_id: Optional[uuid.UUID] = None,
    skip: int = 0,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    limit = min(max(limit, 1), 1000)
    count_query = select(Control)
    if jurisdiction_id:
        count_query = count_query.where(Control.jurisdiction_id == jurisdiction_id)

    all_rows = await db.execute(count_query.order_by(Control.code))
    items = all_rows.scalars().all()
    return {
        "items": [ControlResponse.model_validate(item) for item in items[skip : skip + limit]],
        "total": len(items),
    }


@router.post("/controls", response_model=ControlResponse, status_code=201)
async def create_control(
    body: ControlCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_installation_operator),
):
    duplicate = await db.execute(
        select(Control).where(
            and_(
                Control.jurisdiction_id == body.jurisdiction_id,
                Control.code == body.code.strip(),
            )
        )
    )
    if duplicate.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Control code already exists for jurisdiction")

    item = Control(
        jurisdiction_id=body.jurisdiction_id,
        code=body.code.strip(),
        title=body.title.strip(),
        description=body.description,
        test_method=body.test_method,
        evidence_expectations=body.evidence_expectations,
        cadence_days=body.cadence_days,
        status=body.status,
    )
    db.add(item)

    await log_action(
        db,
        current_user,
        "create",
        "control",
        str(item.id),
        new_value={
            "jurisdiction_id": str(item.jurisdiction_id),
            "code": item.code,
            "title": item.title,
        },
    )
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/obligations", response_model=dict)
async def list_obligations(
    jurisdiction_id: Optional[uuid.UUID] = None,
    skip: int = 0,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    limit = min(max(limit, 1), 1000)
    query = select(Obligation)
    if jurisdiction_id:
        query = query.where(Obligation.jurisdiction_id == jurisdiction_id)

    result = await db.execute(query.order_by(Obligation.code))
    rows = result.scalars().all()
    return {
        "items": [ObligationResponse.model_validate(item) for item in rows[skip : skip + limit]],
        "total": len(rows),
    }


@router.post("/obligations", response_model=ObligationResponse, status_code=201)
async def create_obligation(
    body: ObligationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_installation_operator),
):
    duplicate = await db.execute(
        select(Obligation).where(
            and_(
                Obligation.jurisdiction_id == body.jurisdiction_id,
                Obligation.code == body.code.strip(),
            )
        )
    )
    if duplicate.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409, detail="Obligation code already exists for jurisdiction"
        )

    item = Obligation(
        jurisdiction_id=body.jurisdiction_id,
        code=body.code.strip(),
        legal_reference=body.legal_reference,
        title=body.title.strip(),
        description=body.description,
        status=body.status,
    )
    db.add(item)

    await log_action(
        db,
        current_user,
        "create",
        "obligation",
        str(item.id),
        new_value={
            "jurisdiction_id": str(item.jurisdiction_id),
            "code": item.code,
            "title": item.title,
        },
    )
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/crosswalks", response_model=dict)
async def list_crosswalks(
    source_control_id: Optional[uuid.UUID] = None,
    target_obligation_id: Optional[uuid.UUID] = None,
    skip: int = 0,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    limit = min(max(limit, 1), 1000)
    query = select(ControlCrosswalk)
    if source_control_id is not None:
        query = query.where(ControlCrosswalk.source_control_id == source_control_id)
    if target_obligation_id is not None:
        query = query.where(ControlCrosswalk.target_obligation_id == target_obligation_id)

    result = await db.execute(query.order_by(ControlCrosswalk.created_at.desc()))
    rows = result.scalars().all()
    return {
        "items": [
            ControlCrosswalkResponse.model_validate(item) for item in rows[skip : skip + limit]
        ],
        "total": len(rows),
    }


@router.post("/crosswalks", response_model=ControlCrosswalkResponse, status_code=201)
async def create_crosswalk(
    body: ControlCrosswalkCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_installation_operator),
):
    duplicate = await db.execute(
        select(ControlCrosswalk).where(
            and_(
                ControlCrosswalk.source_control_id == body.source_control_id,
                ControlCrosswalk.target_obligation_id == body.target_obligation_id,
            )
        )
    )
    if duplicate.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Crosswalk already exists")

    item = ControlCrosswalk(
        source_control_id=body.source_control_id,
        target_obligation_id=body.target_obligation_id,
        mapping_strength=body.mapping_strength,
        notes=body.notes,
    )
    db.add(item)

    await log_action(
        db,
        current_user,
        "create",
        "control_crosswalk",
        str(item.id),
        new_value={
            "source_control_id": str(item.source_control_id),
            "target_obligation_id": str(item.target_obligation_id),
            "mapping_strength": item.mapping_strength,
        },
    )
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/certification-projects", response_model=dict)
async def list_certification_projects(
    jurisdiction_id: Optional[uuid.UUID] = None,
    stage: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    limit = min(max(limit, 1), 1000)
    query = _org_filter(select(CertificationProject), CertificationProject, current_user).where(
        access_clause(CertificationProject, current_user, "view")
    )
    if jurisdiction_id is not None:
        query = query.where(CertificationProject.jurisdiction_id == jurisdiction_id)
    if stage:
        query = query.where(CertificationProject.stage == stage)
    if status:
        query = query.where(CertificationProject.status == status)

    result = await db.execute(query.order_by(CertificationProject.created_at.desc()))
    rows = result.scalars().all()
    items: list[CertificationProjectResponse] = []
    for project in rows[skip : skip + limit]:
        items.append(await _build_project_response(db, project))
    return {
        "items": items,
        "total": len(rows),
    }


@router.get("/program-workspace/summary", response_model=ProgramWorkspaceSummaryResponse)
async def get_program_workspace_summary(
    jurisdiction_id: Optional[uuid.UUID] = Query(None),
    project_id: Optional[uuid.UUID] = Query(None),
    limit: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = _org_filter(select(CertificationProject), CertificationProject, current_user).where(
        access_clause(CertificationProject, current_user, "view")
    )
    if jurisdiction_id is not None:
        query = query.where(CertificationProject.jurisdiction_id == jurisdiction_id)
    if project_id is not None:
        query = query.where(CertificationProject.id == project_id)

    result = await db.execute(query.order_by(CertificationProject.created_at.desc()))
    projects = result.scalars().all()
    if project_id is not None and not projects:
        raise HTTPException(status_code=404, detail="Certification project not found")

    items: list[ProgramWorkspaceProjectSummary] = []
    next_actions: list[ProgramWorkspaceAction] = []
    for project in projects[:limit]:
        stage_states, readiness, blockers = await _build_project_stage_state_summary(db, project)
        deep_links = await _build_project_workspace_deep_links(db, project)
        items.append(
            ProgramWorkspaceProjectSummary(
                project_id=project.id,
                project_name=project.name,
                jurisdiction_id=project.jurisdiction_id,
                stage=project.stage,
                status=project.status,
                target_submission_date=project.target_submission_date,
                stage_states=stage_states,
                current_stage_readiness=readiness,
                blockers=blockers,
                deep_links=deep_links,
            )
        )
        next_actions.extend(_build_project_next_actions(project, blockers, readiness, deep_links))

    role_scoped_actions = [a for a in next_actions if current_user.role in a.role_scope]
    role_scoped_actions.sort(key=_action_sort_key)

    return ProgramWorkspaceSummaryResponse(
        generated_at=datetime.now(timezone.utc),
        jurisdiction_id=jurisdiction_id,
        items=items,
        next_actions=role_scoped_actions,
    )


@router.post(
    "/certification-projects", response_model=CertificationProjectResponse, status_code=201
)
async def create_certification_project(
    body: CertificationProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    requested_requirement_set_ids = list(body.requirement_set_ids)
    if (
        body.source_document_id is not None
        and body.source_document_id not in requested_requirement_set_ids
    ):
        requested_requirement_set_ids.insert(0, body.source_document_id)
    baseline_targets = await _resolve_project_baseline_targets(
        db,
        current_user,
        body.jurisdiction_id,
        requested_requirement_set_ids,
    )
    await get_active_user_in_org_or_404(
        db,
        body.owner_id,
        current_user,
        detail="Owner not found",
    )
    source_document_id = baseline_targets[0][0].id if baseline_targets else body.source_document_id

    project = CertificationProject(
        id=uuid.uuid4(),
        organization_id=current_user.organization_id,
        source_document_id=source_document_id,
        jurisdiction_id=body.jurisdiction_id,
        name=body.name.strip(),
        description=body.description,
        stage=body.stage,
        status=body.status,
        owner_id=body.owner_id,
        created_by=current_user.id,
        started_at=datetime.now(timezone.utc),
        target_submission_date=body.target_submission_date,
        **body.model_dump(include=set(EngagementFields.model_fields)),
    )
    db.add(project)

    await log_action(
        db,
        current_user,
        "create",
        "certification_project",
        str(project.id),
        new_value={
            "name": project.name,
            "stage": project.stage,
            "status": project.status,
            "jurisdiction_id": str(project.jurisdiction_id),
            "source_document_id": (
                str(project.source_document_id) if project.source_document_id else None
            ),
            "requirement_set_ids": [str(item[0].id) for item in baseline_targets],
            **{
                field: value.isoformat() if isinstance(value := getattr(project, field), datetime) else value
                for field in EngagementFields.model_fields
            },
        },
    )

    await db.flush()
    await initialize_access(db, "certification_project", project.id, current_user, "organisation")
    _seed_project_milestones(db, project.id)
    await _replace_project_baselines(db, project, baseline_targets)

    await db.commit()
    await db.refresh(project)
    return await _build_project_response(db, project)


@router.post(
    "/certification-projects/from-document/{document_id}",
    response_model=CertificationProjectFromDocumentResponse,
    status_code=201,
)
async def create_certification_project_from_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    source_query = _org_filter(
        select(Document).where(Document.id == document_id),
        Document,
        current_user,
    )
    source_result = await db.execute(source_query)
    source_document = source_result.scalar_one_or_none()
    if source_document is None:
        raise HTTPException(status_code=404, detail="Requirement set not found")
    if source_document.status != "approved":
        raise HTTPException(
            status_code=400,
            detail="Requirement set must be approved before creating a certification project baseline",
        )

    existing_query = _org_filter(
        select(CertificationProject)
        .where(CertificationProject.source_document_id == document_id)
        .order_by(CertificationProject.created_at.desc()),
        CertificationProject,
        current_user,
    )
    existing_result = await db.execute(existing_query)
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        existing_response = await _build_project_response(db, existing)
        return CertificationProjectFromDocumentResponse(
            created=False,
            project=existing_response,
        )

    source_name = source_document.name or source_document.filename or "Requirement Set"
    project_name = f"{source_name} Certification Project"[:255]
    project_description = f"Created from requirement set {source_name}."
    project = CertificationProject(
        organization_id=current_user.organization_id,
        source_document_id=source_document.id,
        jurisdiction_id=source_document.jurisdiction_id,
        name=project_name,
        description=project_description,
        stage="intake",
        status="active",
        created_by=current_user.id,
        started_at=datetime.now(timezone.utc),
    )
    db.add(project)
    await db.flush()
    await initialize_access(db, "certification_project", project.id, current_user, "organisation")
    _seed_project_milestones(db, project.id)
    source_version = await get_current_approved_version_for_document(db, source_document.id)
    if source_version is None:
        raise HTTPException(
            status_code=400,
            detail="No approved requirement set baseline version found for source requirement set",
        )
    await _replace_project_baselines(db, project, [(source_document, source_version)])

    await log_action(
        db,
        current_user,
        "create",
        "certification_project",
        str(project.id),
        new_value={
            "name": project.name,
            "stage": project.stage,
            "status": project.status,
            "jurisdiction_id": str(project.jurisdiction_id),
            "source_document_id": str(project.source_document_id),
        },
    )

    await db.commit()
    await db.refresh(project)
    project_response = await _build_project_response(db, project)
    return CertificationProjectFromDocumentResponse(
        created=True,
        project=project_response,
    )


@router.post(
    "/certification-projects/{project_id}/submission-cycle",
    response_model=CertificationProjectSubmissionCycleResponse,
)
async def ensure_project_submission_cycle(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    await require_access(db, CertificationProject, project_id, current_user, "edit")
    project = await _get_project_for_user(db, current_user, project_id)
    existing_cycle = await _get_project_submission_cycle(db, project.id)
    if existing_cycle is not None:
        return CertificationProjectSubmissionCycleResponse(
            created=False,
            review_cycle_id=existing_cycle.id,
        )

    baseline_result = await db.execute(
        select(
            CertificationProjectRequirementBaseline.document_id,
            CertificationProjectRequirementBaseline.requirement_set_version_id,
        ).where(CertificationProjectRequirementBaseline.project_id == project.id)
    )
    baseline_rows = baseline_result.all()
    if not baseline_rows:
        raise HTTPException(
            status_code=409,
            detail="Project baseline is empty. Select requirement sets before creating a submission cycle.",
        )
    baseline_document_ids = [document_id for document_id, _ in baseline_rows]
    baseline_version_ids = [version_id for _, version_id in baseline_rows]

    cycle = ReviewCycle(
        organization_id=current_user.organization_id,
        certification_project_id=project.id,
        cycle_type="submission",
        jurisdiction_id=project.jurisdiction_id,
        name=f"Submission assessment: {project.name}"[:255],
        description="Requirement assessment supporting the certification submission package.",
        scope="documents" if baseline_document_ids else "all",
        scope_filter=(
            json.dumps([str(doc_id) for doc_id in baseline_document_ids])
            if baseline_document_ids
            else None
        ),
        deadline=project.target_submission_date,
        status="active",
        created_by=current_user.id,
    )
    db.add(cycle)
    await db.flush()

    for document_id, version_id in baseline_rows:
        db.add(
            ReviewCycleRequirementBaseline(
                review_cycle_id=cycle.id,
                document_id=document_id,
                requirement_set_version_id=version_id,
            )
        )

    requirements = await load_requirements_for_versions(
        db,
        project.jurisdiction_id,
        baseline_version_ids,
        organization_id=current_user.organization_id,
    )
    review_items_created = await _create_review_items_from_requirements(db, cycle.id, requirements)

    await log_action(
        db,
        current_user,
        "create",
        "review_cycle",
        str(cycle.id),
        new_value={
            "name": cycle.name,
            "cycle_type": cycle.cycle_type,
            "status": cycle.status,
            "certification_project_id": str(project.id),
            "review_items_created": review_items_created,
        },
    )
    await db.commit()
    return CertificationProjectSubmissionCycleResponse(
        created=True,
        review_cycle_id=cycle.id,
        review_items_created=review_items_created,
        warning=None,
    )


@router.get("/certification-projects/{project_id}", response_model=CertificationProjectResponse)
async def get_certification_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = _org_filter(
        select(CertificationProject).where(CertificationProject.id == project_id, access_clause(CertificationProject, current_user, "view")),
        CertificationProject,
        current_user,
    )
    result = await db.execute(query)
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Certification project not found")
    return await _build_project_response(db, project)


@router.patch("/certification-projects/{project_id}", response_model=CertificationProjectResponse)
async def update_certification_project(
    project_id: uuid.UUID,
    body: CertificationProjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    await require_access(db, CertificationProject, project_id, current_user, "edit")
    query = _org_filter(
        select(CertificationProject).where(CertificationProject.id == project_id),
        CertificationProject,
        current_user,
    )
    result = await db.execute(query)
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Certification project not found")

    def engagement_audit_value() -> dict:
        return {
            field: value.isoformat() if isinstance(value := getattr(project, field), datetime) else value
            for field in EngagementFields.model_fields
        }

    old_value = {
        "name": project.name,
        "description": project.description,
        "stage": project.stage,
        "status": project.status,
        "owner_id": str(project.owner_id) if project.owner_id else None,
        "target_submission_date": (
            project.target_submission_date.isoformat() if project.target_submission_date else None
        ),
        **engagement_audit_value(),
    }
    requested_stage = body.stage
    stage_gate_check_payload: Optional[dict] = None
    await get_active_user_in_org_or_404(
        db,
        body.owner_id,
        current_user,
        detail="Owner not found",
    )
    if requested_stage is not None and requested_stage != project.stage:
        stage_checks = await _build_stage_transition_checks(db, project, project.stage)
        failed_checks = [check for check in stage_checks if not check.passed]
        stage_gate_check_payload = {
            "from_stage": project.stage,
            "to_stage": requested_stage,
            "passed": len(failed_checks) == 0,
            "mode": "warn_only",
            "blockers": [
                {
                    "code": check.code,
                    "reason": check.reason or f"{check.label} is not satisfied.",
                    "cta_path": check.cta_path,
                }
                for check in failed_checks
            ],
        }

    for field in [
        "name",
        "description",
        "stage",
        "status",
        "owner_id",
        "target_submission_date",
        "completed_at",
    ]:
        value = getattr(body, field)
        if value is not None:
            setattr(project, field, value)
    for field in EngagementFields.model_fields:
        if field in body.model_fields_set:
            setattr(project, field, getattr(body, field))

    if stage_gate_check_payload is not None:
        await log_action(
            db,
            current_user,
            "stage_gate_check",
            "certification_project_stage_gate",
            str(project.id),
            new_value=stage_gate_check_payload,
        )

    await log_action(
        db,
        current_user,
        "update",
        "certification_project",
        str(project.id),
        old_value=old_value,
        new_value={
            "name": project.name,
            "description": project.description,
            "stage": project.stage,
            "status": project.status,
            "owner_id": str(project.owner_id) if project.owner_id else None,
            "target_submission_date": (
                project.target_submission_date.isoformat()
                if project.target_submission_date
                else None
            ),
            **engagement_audit_value(),
        },
    )

    await db.commit()
    await db.refresh(project)
    return await _build_project_response(db, project)


@router.delete("/certification-projects/{project_id}", status_code=204)
async def delete_certification_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    await require_access(db, CertificationProject, project_id, current_user, "edit")
    project = await _get_project_for_user(db, current_user, project_id)

    from app.models.change_management import ChangeRequirementImpact
    linked_impacts = await db.scalar(select(ChangeRequirementImpact.id).where(
        ChangeRequirementImpact.certification_project_id == project.id,
    ).limit(1))
    linked_plans = await db.scalar(select(MaintenancePlan.id).where(
        MaintenancePlan.certification_project_id == project.id,
    ).limit(1))
    if linked_impacts or linked_plans:
        raise HTTPException(409, "Project is referenced by change impacts or maintenance plans; retain it for workflow provenance")

    package_count_result = await db.execute(
        select(func.count(SubmissionPackage.id)).where(SubmissionPackage.project_id == project.id)
    )
    package_count = int(package_count_result.scalar() or 0)
    if package_count > 0:
        raise HTTPException(
            status_code=409,
            detail=(
                "Certification project cannot be deleted while submission packages are linked. "
                "Delete linked submission packages first."
            ),
        )

    cycle_count_result = await db.execute(
        select(func.count(ReviewCycle.id)).where(ReviewCycle.certification_project_id == project.id)
    )
    cycle_count = int(cycle_count_result.scalar() or 0)
    if cycle_count > 0:
        raise HTTPException(
            status_code=409,
            detail=(
                "Certification project cannot be deleted while review cycles are linked. "
                "Archive or delete linked review cycles first."
            ),
        )

    await db.execute(
        delete(CertificationProjectRequirementBaseline).where(
            CertificationProjectRequirementBaseline.project_id == project.id
        )
    )
    await db.execute(
        delete(CertificationProjectMilestone).where(
            CertificationProjectMilestone.project_id == project.id
        )
    )
    await db.execute(delete(BaselineMigration).where(BaselineMigration.project_id == project.id))

    await log_action(
        db,
        current_user,
        "delete",
        "certification_project",
        str(project.id),
        old_value={
            "name": project.name,
            "stage": project.stage,
            "status": project.status,
        },
    )

    await db.delete(project)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Certification project cannot be deleted because it is still referenced by related records",
        )


@router.put(
    "/certification-projects/{project_id}/baseline",
    response_model=CertificationProjectBaselineUpdateResponse,
)
async def update_project_baseline(
    project_id: uuid.UUID,
    body: CertificationProjectBaselineUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    await require_access(db, CertificationProject, project_id, current_user, "edit")
    project = await _get_project_for_user(db, current_user, project_id)
    if not body.requirement_set_ids:
        raise HTTPException(
            status_code=400,
            detail="At least one approved requirement set must be selected for the project baseline",
        )

    # Serialize project-baseline writes before checking the displayed version snapshot.
    await db.execute(select(CertificationProject.id).where(
        CertificationProject.id == project.id
    ).with_for_update())
    existing_result = await db.execute(
        select(Document, RequirementSetVersion)
        .join(CertificationProjectRequirementBaseline,
              CertificationProjectRequirementBaseline.document_id == Document.id)
        .join(RequirementSetVersion,
              RequirementSetVersion.id == CertificationProjectRequirementBaseline.requirement_set_version_id)
        .where(CertificationProjectRequirementBaseline.project_id == project.id)
    )
    existing = {document.id: (document, version) for document, version in existing_result.all()}
    actual_versions = {document_id: version.id for document_id, (_, version) in existing.items()}
    if body.expected_baseline_version_ids is not None and body.expected_baseline_version_ids != actual_versions:
        raise HTTPException(409, "The project baseline changed. Reload the project before saving.")
    if set(body.target_version_ids) - set(body.requirement_set_ids):
        raise HTTPException(400, "Target versions must belong to selected requirement sets")
    changed_ids = [document_id for document_id in body.requirement_set_ids
                   if document_id not in existing or (
                       document_id in body.target_version_ids
                       and body.target_version_ids[document_id] != actual_versions[document_id])]
    resolved = await _resolve_project_baseline_targets(
        db, current_user, project.jurisdiction_id, changed_ids,
    )
    for document, version in resolved:
        expected = body.target_version_ids.get(document.id)
        if expected is not None and expected != version.id:
            raise HTTPException(409, "The approved requirement version changed. Reload and confirm the new version.")
    resolved_by_id = {document.id: (document, version) for document, version in resolved}
    targets = [resolved_by_id.get(document_id) or existing[document_id]
               for document_id in dict.fromkeys(body.requirement_set_ids)]
    await _replace_project_baselines(db, project, targets)
    if targets:
        project.source_document_id = targets[0][0].id

    await log_action(
        db,
        current_user,
        "update",
        "certification_project_baseline",
        str(project.id),
        new_value={
            "requirement_set_ids": [str(document.id) for document, _ in targets],
            "baseline_version_ids": {str(document.id): str(version.id) for document, version in targets},
        },
    )
    await db.commit()
    await db.refresh(project)

    active_cycles_result = await db.execute(
        select(func.count(ReviewCycle.id)).where(
            and_(
                ReviewCycle.certification_project_id == project.id,
                ReviewCycle.status.in_(["active", "closed"]),
            )
        )
    )
    active_cycles = int(active_cycles_result.scalar() or 0)
    warning = (
        f"{active_cycles} existing active/closed review cycle(s) keep their original baseline."
        if active_cycles > 0
        else None
    )
    return CertificationProjectBaselineUpdateResponse(
        project=await _build_project_response(db, project),
        warning=warning,
    )


@router.post(
    "/certification-projects/{project_id}/baseline-migrations/preview",
    response_model=BaselineMigrationPreviewResponse,
)
async def preview_project_baseline_migration(
    project_id: uuid.UUID,
    body: BaselineMigrationPreviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    await require_access(db, CertificationProject, project_id, current_user, "edit")
    project = await _get_project_for_user(db, current_user, project_id)

    target_document_ids = list(body.requirement_set_ids)
    if not target_document_ids:
        baseline_rows_result = await db.execute(
            select(CertificationProjectRequirementBaseline.document_id).where(
                CertificationProjectRequirementBaseline.project_id == project.id
            )
        )
        target_document_ids = [document_id for (document_id,) in baseline_rows_result.all()]
    if not target_document_ids:
        raise HTTPException(
            status_code=400,
            detail="Project baseline is empty. Select requirement sets before previewing migration.",
        )

    target_baselines = await _resolve_project_baseline_targets(
        db,
        current_user,
        project.jurisdiction_id,
        target_document_ids,
    )
    set_name_by_document_id = {
        document.id: document.name or document.filename
        for document, _ in target_baselines
    }
    target_version_ids = [version.id for _, version in target_baselines]
    target_requirements = await load_requirements_for_versions(
        db,
        project.jurisdiction_id,
        target_version_ids,
        organization_id=current_user.organization_id,
    )
    from_cycle: Optional[ReviewCycle] = None
    if body.from_cycle_id is not None:
        from_cycle_result = await db.execute(
            select(ReviewCycle).where(
                and_(
                    ReviewCycle.id == body.from_cycle_id,
                    ReviewCycle.certification_project_id == project.id,
                    ReviewCycle.status == "active",
                )
            )
        )
        from_cycle = from_cycle_result.scalar_one_or_none()
        if from_cycle is None:
            raise HTTPException(status_code=404, detail="Active predecessor cycle not found")
        if from_cycle.change_entry_id or from_cycle.cycle_type != "submission":
            raise HTTPException(
                status_code=409,
                detail="Project baseline migration requires a submission assessment. Change and maintenance assessments retain their original scope.",
            )
    else:
        from_cycle_result = await db.execute(
            select(ReviewCycle)
            .where(
                and_(
                    ReviewCycle.certification_project_id == project.id,
                    ReviewCycle.status == "active",
                    ReviewCycle.change_entry_id.is_(None),
                    ReviewCycle.cycle_type == "submission",
                )
            )
            .order_by(ReviewCycle.created_at.desc())
            .limit(1)
        )
        from_cycle = from_cycle_result.scalar_one_or_none()

    from_lookup: dict[tuple[Optional[uuid.UUID], str], tuple[ReviewItem, Requirement]] = {}
    if from_cycle is not None:
        from_lookup = await _build_cycle_item_lookup(db, from_cycle.id)

    comparison = compare_baseline_requirements(
        target_requirements, from_lookup, set_name_by_document_id
    )
    matched, changed = comparison.matched, comparison.changed
    added, removed = comparison.added, comparison.removed

    preview_payload = {
        "from_cycle_id": str(from_cycle.id) if from_cycle is not None else None,
        "target_baselines": [
            {
                "document_id": str(document.id),
                "requirement_set_version_id": str(version.id),
                "version_number": version.version_number,
            }
            for document, version in target_baselines
        ],
        "matched": [item.model_dump(mode="json") for item in matched],
        "changed": [item.model_dump(mode="json") for item in changed],
        "added": [item.model_dump(mode="json") for item in added],
        "removed": [item.model_dump(mode="json") for item in removed],
    }
    migration = BaselineMigration(
        organization_id=current_user.organization_id,
        project_id=project.id,
        from_cycle_id=from_cycle.id if from_cycle else None,
        status="previewed",
        preview_json=json.dumps(preview_payload),
        created_by=current_user.id,
    )
    db.add(migration)
    await db.commit()
    await db.refresh(migration)

    return BaselineMigrationPreviewResponse(
        migration_id=migration.id,
        from_cycle_id=from_cycle.id if from_cycle is not None else None,
        target_version_ids=target_version_ids,
        matched=matched,
        changed=changed,
        added=added,
        removed=removed,
    )


@router.post(
    "/certification-projects/{project_id}/baseline-migrations/execute",
    response_model=BaselineMigrationExecuteResponse,
)
async def execute_project_baseline_migration(
    project_id: uuid.UUID,
    body: ProjectMigrationExecuteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    await require_access(db, CertificationProject, project_id, current_user, "edit")
    project = await _get_project_for_user(db, current_user, project_id)
    migration_result = await db.execute(
        select(BaselineMigration).where(
            and_(
                BaselineMigration.id == body.migration_id,
                BaselineMigration.project_id == project.id,
            )
        )
    )
    migration = migration_result.scalar_one_or_none()
    if migration is None:
        raise HTTPException(status_code=404, detail="Baseline migration preview not found")
    if migration.status != "previewed":
        raise HTTPException(
            status_code=409, detail="Baseline migration preview has already been executed"
        )
    if not migration.preview_json:
        raise HTTPException(status_code=409, detail="Baseline migration preview payload is missing")

    preview = json.loads(migration.preview_json)
    from_cycle_id_raw = preview.get("from_cycle_id")
    from_cycle: Optional[ReviewCycle] = None
    if from_cycle_id_raw:
        from_cycle_result = await db.execute(
            select(ReviewCycle).where(
                and_(
                    ReviewCycle.id == uuid.UUID(from_cycle_id_raw),
                    ReviewCycle.certification_project_id == project.id,
                    ReviewCycle.status == "active",
                )
            )
        )
        from_cycle = from_cycle_result.scalar_one_or_none()
        if from_cycle is None:
            raise HTTPException(status_code=409, detail="Predecessor cycle is not active")
        if from_cycle.change_entry_id or from_cycle.cycle_type != "submission":
            raise HTTPException(
                status_code=409,
                detail="Project baseline migration requires a submission assessment. Change and maintenance assessments retain their original scope.",
            )
    else:
        raise HTTPException(
            status_code=400, detail="Migration execution requires an active predecessor cycle"
        )

    target_baselines_raw = preview.get("target_baselines") or []
    if not target_baselines_raw:
        raise HTTPException(status_code=409, detail="Target baseline payload is missing")

    target_baselines: list[tuple[uuid.UUID, uuid.UUID]] = []
    for item in target_baselines_raw:
        target_baselines.append(
            (uuid.UUID(item["document_id"]), uuid.UUID(item["requirement_set_version_id"]))
        )
    for document_id, preview_version_id in target_baselines:
        latest_version = await get_current_approved_version_for_document(db, document_id)
        if latest_version is None or latest_version.id != preview_version_id:
            raise HTTPException(
                status_code=409,
                detail="Approved requirement versions changed after preview. Generate a new migration preview before executing.",
            )
    target_version_ids = [version_id for _, version_id in target_baselines]
    target_requirements = await load_requirements_for_versions(
        db,
        project.jurisdiction_id,
        target_version_ids,
        organization_id=current_user.organization_id,
    )
    target_lookup = {
        (requirement.document_id, requirement.reference_id): requirement
        for requirement in target_requirements
    }
    from_lookup = await _build_cycle_item_lookup(db, from_cycle.id)
    from_requirement_by_id = {
        requirement.id: (item, requirement) for item, requirement in from_lookup.values()
    }

    try:
        changed_actions = resolve_project_changed_decisions(
            preview.get("changed", []), body.changed_decisions
        )
    except ReviewMigrationDecisionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    cloned_file_paths: list[str] = []
    try:
        # The partial unique index is checked on each INSERT, including this flush.
        from_cycle.status = "archived"
        await db.flush()
        successor_cycle = ReviewCycle(
            organization_id=project.organization_id,
            certification_project_id=project.id,
            predecessor_cycle_id=from_cycle.id,
            cycle_type=from_cycle.cycle_type,
            name=f"{from_cycle.name} (migrated)"[:255],
            jurisdiction_id=from_cycle.jurisdiction_id,
            description=from_cycle.description,
            scope="documents",
            scope_filter=json.dumps([str(document_id) for document_id, _ in target_baselines]),
            deadline=from_cycle.deadline,
            status="active",
            created_by=current_user.id,
        )
        db.add(successor_cycle)
        await db.flush()

        for document_id, version_id in target_baselines:
            db.add(
                ReviewCycleRequirementBaseline(
                    review_cycle_id=successor_cycle.id,
                    document_id=document_id,
                    requirement_set_version_id=version_id,
                )
            )

        migration_result = await clone_review_cycle_items_for_migration(
            db=db,
            successor_cycle_id=successor_cycle.id,
            target_requirements=target_lookup.values(),
            previous_lookup=from_lookup,
            previous_lookup_by_source_id=from_requirement_by_id,
            should_carry_forward=lambda requirement, _previous_item, previous_requirement: (
                should_carry_forward_requirement(
                    requirement, previous_requirement, changed_actions
                )
            ),
            default_review_state_for_requirement=lambda requirement: (
                default_review_state_for_requirement(
                    requirement,
                    not_applicable_state=PROGRAM_NOT_APPLICABLE_REVIEW_STATE,
                )
            ),
            current_user_id=current_user.id,
        )
        cloned_file_paths = migration_result.cloned_file_paths
        migrated_items = migration_result.migrated_items

        migration.status = "executed"
        migration.from_cycle_id = from_cycle.id
        migration.to_cycle_id = successor_cycle.id
        migration.execution_json = json.dumps(
            {
                "to_cycle_id": str(successor_cycle.id),
                "migrated_items": migrated_items,
                "executed_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        await log_action(
            db,
            current_user,
            "migrate",
            "review_cycle_baseline",
            str(successor_cycle.id),
            new_value={
                "from_cycle_id": str(from_cycle.id),
                "to_cycle_id": str(successor_cycle.id),
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

    return BaselineMigrationExecuteResponse(
        created=True,
        from_cycle_id=from_cycle.id,
        to_cycle_id=successor_cycle.id,
        migrated_items=migrated_items,
    )


@router.get("/certification-projects/{project_id}/milestones", response_model=dict)
async def list_project_milestones(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project_query = _org_filter(
        select(CertificationProject).where(CertificationProject.id == project_id),
        CertificationProject,
        current_user,
    )
    project_result = await db.execute(project_query)
    project = project_result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Certification project not found")

    result = await db.execute(
        select(CertificationProjectMilestone)
        .where(CertificationProjectMilestone.project_id == project_id)
        .order_by(CertificationProjectMilestone.created_at.asc())
    )
    rows = result.scalars().all()
    return {
        "items": [CertificationProjectMilestoneResponse.model_validate(item) for item in rows],
        "total": len(rows),
    }


@router.post(
    "/certification-projects/{project_id}/milestones",
    response_model=CertificationProjectMilestoneResponse,
    status_code=201,
)
async def create_project_milestone(
    project_id: uuid.UUID,
    body: CertificationProjectMilestoneCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    await require_access(db, CertificationProject, project_id, current_user, "edit")
    project_query = _org_filter(
        select(CertificationProject).where(CertificationProject.id == project_id),
        CertificationProject,
        current_user,
    )
    project_result = await db.execute(project_query)
    project = project_result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Certification project not found")

    milestone = CertificationProjectMilestone(
        project_id=project.id,
        stage=body.stage,
        title=body.title,
        due_at=body.due_at,
        status=body.status,
        notes=body.notes,
    )
    db.add(milestone)

    await log_action(
        db,
        current_user,
        "create",
        "certification_project_milestone",
        str(milestone.id),
        new_value={
            "project_id": str(project.id),
            "stage": milestone.stage,
            "title": milestone.title,
            "status": milestone.status,
        },
    )

    await db.commit()
    await db.refresh(milestone)
    return milestone


@router.patch(
    "/certification-projects/{project_id}/milestones/{milestone_id}",
    response_model=CertificationProjectMilestoneResponse,
)
async def update_project_milestone(
    project_id: uuid.UUID,
    milestone_id: uuid.UUID,
    body: CertificationProjectMilestoneUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    await require_access(db, CertificationProject, project_id, current_user, "edit")
    project_query = _org_filter(
        select(CertificationProject).where(CertificationProject.id == project_id),
        CertificationProject,
        current_user,
    )
    project_result = await db.execute(project_query)
    project = project_result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Certification project not found")

    milestone_result = await db.execute(
        select(CertificationProjectMilestone).where(
            and_(
                CertificationProjectMilestone.id == milestone_id,
                CertificationProjectMilestone.project_id == project.id,
            )
        )
    )
    milestone = milestone_result.scalar_one_or_none()
    if milestone is None:
        raise HTTPException(status_code=404, detail="Milestone not found")

    old_value = {
        "stage": milestone.stage,
        "title": milestone.title,
        "due_at": milestone.due_at.isoformat() if milestone.due_at else None,
        "status": milestone.status,
        "notes": milestone.notes,
    }

    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(milestone, field, value)

    await log_action(
        db,
        current_user,
        "update",
        "certification_project_milestone",
        str(milestone.id),
        old_value=old_value,
        new_value={
            "stage": milestone.stage,
            "title": milestone.title,
            "due_at": milestone.due_at.isoformat() if milestone.due_at else None,
            "status": milestone.status,
            "notes": milestone.notes,
        },
    )

    await db.commit()
    await db.refresh(milestone)
    return milestone


@router.get("/submission-packages", response_model=dict)
async def list_submission_packages(
    project_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    limit = min(max(limit, 1), 1000)
    query = select(SubmissionPackage).join(
        CertificationProject,
        CertificationProject.id == SubmissionPackage.project_id,
    )
    query = _org_filter(query, CertificationProject, current_user)
    if project_id is not None:
        query = query.where(SubmissionPackage.project_id == project_id)
    if status:
        query = query.where(SubmissionPackage.status == status)

    result = await db.execute(query.order_by(SubmissionPackage.created_at.desc()))
    rows = result.scalars().all()
    return {
        "items": [_submission_package_response(item) for item in rows[skip : skip + limit]],
        "total": len(rows),
    }


@router.post("/submission-packages", response_model=SubmissionPackageResponse, status_code=201)
async def create_submission_package(
    body: SubmissionPackageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    await require_access(db, CertificationProject, body.project_id, current_user, "edit")
    project = await _get_project_for_user(db, current_user, body.project_id)
    if body.status != "draft":
        raise HTTPException(
            status_code=400,
            detail="Submission packages must be created in draft status",
        )
    cycle = await _resolve_submission_cycle_for_project(db, project.id, body.review_cycle_id)
    await _resolve_snapshot_for_org(db, current_user, body.snapshot_id)

    snapshot_id = body.snapshot_id
    if cycle is not None and cycle.snapshot_id is not None and snapshot_id is None:
        snapshot_id = cycle.snapshot_id
    if cycle is not None and cycle.snapshot_id is not None and snapshot_id != cycle.snapshot_id:
        raise HTTPException(
            status_code=400,
            detail="snapshot_id must match the linked submission review cycle snapshot",
        )

    item = SubmissionPackage(
        project_id=project.id,
        review_cycle_id=cycle.id if cycle else None,
        snapshot_id=snapshot_id,
        version=body.version,
        status=body.status,
        checklist_json=(
            _checklist_json_from_payload(body.checklist)
            if body.checklist is not None
            else body.checklist_json
        ),
        created_by=current_user.id,
    )
    db.add(item)

    await log_action(
        db,
        current_user,
        "create",
        "submission_package",
        str(item.id),
        new_value={
            "project_id": str(item.project_id),
            "review_cycle_id": str(item.review_cycle_id) if item.review_cycle_id else None,
            "snapshot_id": str(item.snapshot_id) if item.snapshot_id else None,
            "version": item.version,
            "status": item.status,
        },
    )

    await db.commit()
    await db.refresh(item)
    return _submission_package_response(item)


@router.patch("/submission-packages/{package_id}", response_model=SubmissionPackageResponse)
async def update_submission_package(
    package_id: uuid.UUID,
    body: SubmissionPackageUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    await _require_package_access(db, current_user, package_id, "edit")
    item = await _get_submission_package_for_user(db, current_user, package_id, lock=True)
    project = await _get_project_for_user(db, current_user, item.project_id)

    if item.status == "locked":
        raise HTTPException(status_code=400, detail="Locked submission package cannot be modified")
    if item.status != "draft":
        raise HTTPException(status_code=409, detail="Return the package to draft before editing its checklist or scope.")
    forbidden_fields = []
    for field in ["status", "approval_requested_at", "approved_by", "approved_at", "locked_at"]:
        if getattr(body, field) is not None:
            forbidden_fields.append(field)
    if forbidden_fields:
        field_list = ", ".join(forbidden_fields)
        raise HTTPException(
            status_code=400,
            detail=(
                "Direct update of governance fields is not allowed via PATCH. "
                f"Forbidden fields: {field_list}. "
                "Use submission-package lifecycle endpoints: "
                "POST /submission-packages/{id}/request-approval, "
                "POST /submission-packages/{id}/approve, "
                "POST /submission-packages/{id}/lock."
            ),
        )

    old_value = {
        "review_cycle_id": str(item.review_cycle_id) if item.review_cycle_id else None,
        "snapshot_id": str(item.snapshot_id) if item.snapshot_id else None,
        "checklist_json": item.checklist_json,
    }

    if body.review_cycle_id is not None:
        cycle = await _resolve_submission_cycle_for_project(db, project.id, body.review_cycle_id)
        item.review_cycle_id = cycle.id if cycle else None

    if body.snapshot_id is not None:
        await _resolve_snapshot_for_org(db, current_user, body.snapshot_id)
        item.snapshot_id = body.snapshot_id

    linked_cycle = None
    if item.review_cycle_id is not None:
        linked_cycle = await _resolve_submission_cycle_for_project(
            db, project.id, item.review_cycle_id
        )
        if linked_cycle is not None and linked_cycle.snapshot_id is not None:
            if item.snapshot_id is None:
                item.snapshot_id = linked_cycle.snapshot_id
            elif item.snapshot_id != linked_cycle.snapshot_id:
                raise HTTPException(
                    status_code=400,
                    detail="snapshot_id must match the linked submission review cycle snapshot",
                )

    if "checklist" in body.model_fields_set:
        item.checklist_json = _checklist_json_from_payload(body.checklist)
    elif "checklist_json" in body.model_fields_set:
        item.checklist_json = body.checklist_json

    await log_action(
        db,
        current_user,
        "update",
        "submission_package",
        str(item.id),
        old_value=old_value,
        new_value={
            "review_cycle_id": str(item.review_cycle_id) if item.review_cycle_id else None,
            "snapshot_id": str(item.snapshot_id) if item.snapshot_id else None,
            "checklist_json": item.checklist_json,
        },
    )

    await db.commit()
    await db.refresh(item)
    return _submission_package_response(item)


@router.post("/submission-packages/{package_id}/return-to-draft", response_model=SubmissionPackageResponse)
async def return_submission_package_to_draft(
    package_id: uuid.UUID,
    body: SubmissionPackageReturnRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "approver", "admin")),
):
    await _require_package_access(db, current_user, package_id, "edit")
    package = await _get_submission_package_for_user(db, current_user, package_id, lock=True)
    if package.status not in {"pending_approval", "approved"}:
        raise HTTPException(status_code=409, detail="Only packages awaiting approval or approved packages can return to draft. Create a new version for a locked package.")
    reason = body.reason.strip()
    if not reason:
        raise HTTPException(status_code=422, detail="Explain why this package needs changes.")
    old = {"status": package.status, "approved_by": str(package.approved_by) if package.approved_by else None, "approved_at": package.approved_at.isoformat() if package.approved_at else None}
    package.status = "draft"
    package.approval_requested_at = None
    package.approved_by = None
    package.approved_at = None
    await log_action(db, current_user, "return_to_draft", "submission_package", str(package.id), old_value=old, new_value={"status": "draft", "reason": reason})
    await db.commit()
    await db.refresh(package)
    return _submission_package_response(package)


@router.get(
    "/submission-packages/{package_id}/gate-check",
    response_model=SubmissionPackageGateCheckResponse,
)
async def get_submission_package_gate_check(
    package_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    package = await _get_submission_package_for_user(db, current_user, package_id)
    project = await _get_project_for_user(db, current_user, package.project_id)
    return await _build_submission_package_gate_check(db, package, project)


@router.post(
    "/submission-packages/{package_id}/request-approval",
    response_model=SubmissionPackageResponse,
)
async def request_submission_package_approval(
    package_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    await _require_package_access(db, current_user, package_id, "edit")
    package = await _get_submission_package_for_user(db, current_user, package_id, lock=True)
    project = await _get_project_for_user(db, current_user, package.project_id)

    if package.status == "locked":
        raise HTTPException(status_code=400, detail="Locked submission package cannot be modified")

    if package.status != "draft":
        raise HTTPException(status_code=409, detail="Only draft packages can request approval.")

    if package.review_cycle_id is None:
        submission_cycle = await _get_project_submission_cycle(db, project.id)
        if submission_cycle is not None:
            package.review_cycle_id = submission_cycle.id
            if submission_cycle.snapshot_id is not None and package.snapshot_id is None:
                package.snapshot_id = submission_cycle.snapshot_id

    if package.review_cycle_id is not None and package.snapshot_id is None:
        linked_cycle = await _resolve_submission_cycle_for_project(db, project.id, package.review_cycle_id)
        if linked_cycle is not None:
            package.snapshot_id = linked_cycle.snapshot_id

    gate_check = await _build_submission_package_gate_check(db, package, project)
    if not gate_check.checks_passed:
        raise HTTPException(status_code=400, detail={"gates": gate_check.blocking_reasons})

    previous_status = package.status
    package.status = "pending_approval"
    package.approval_requested_at = datetime.now(timezone.utc)
    package.locked_at = None

    await log_action(
        db,
        current_user,
        "request_approval",
        "submission_package",
        str(package.id),
        old_value={"status": previous_status},
        new_value={
            "status": package.status,
            "approval_requested_at": package.approval_requested_at.isoformat(),
        },
    )
    await db.commit()
    await db.refresh(package)
    return _submission_package_response(package)


@router.post(
    "/submission-packages/{package_id}/approve",
    response_model=SubmissionPackageResponse,
)
async def approve_submission_package(
    package_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("approver", "admin")),
):
    await _require_package_access(db, current_user, package_id, "approve")
    package = await _get_submission_package_for_user(db, current_user, package_id, lock=True)
    project = await _get_project_for_user(db, current_user, package.project_id)

    if package.status == "locked":
        raise HTTPException(status_code=400, detail="Submission package is already locked")
    if package.status not in {"pending_approval", "approved"}:
        raise HTTPException(
            status_code=400,
            detail="Submission package must be in pending_approval before approval",
        )

    gate_check = await _build_submission_package_gate_check(db, package, project)
    if not gate_check.checks_passed:
        raise HTTPException(status_code=400, detail={"gates": gate_check.blocking_reasons})

    previous_status = package.status
    package.status = "approved"
    if package.approval_requested_at is None:
        package.approval_requested_at = datetime.now(timezone.utc)
    package.approved_by = current_user.id
    package.approved_at = datetime.now(timezone.utc)
    package.locked_at = None

    await log_action(
        db,
        current_user,
        "approve",
        "submission_package",
        str(package.id),
        old_value={"status": previous_status},
        new_value={
            "status": package.status,
            "approved_by": str(package.approved_by),
            "approved_at": package.approved_at.isoformat() if package.approved_at else None,
        },
    )
    await db.commit()
    await db.refresh(package)
    return _submission_package_response(package)


@router.post(
    "/submission-packages/{package_id}/lock",
    response_model=SubmissionPackageResponse,
)
async def lock_submission_package(
    package_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("approver", "admin")),
):
    await _require_package_access(db, current_user, package_id, "approve")
    package = await _get_submission_package_for_user(db, current_user, package_id, lock=True)
    project = await _get_project_for_user(db, current_user, package.project_id)

    if package.status not in {"approved", "locked"}:
        raise HTTPException(
            status_code=400,
            detail="Submission package must be approved before lock",
        )
    if package.status == "locked":
        return _submission_package_response(package)

    gate_check = await _build_submission_package_gate_check(db, package, project)
    if not gate_check.checks_passed:
        raise HTTPException(status_code=400, detail={"gates": gate_check.blocking_reasons})

    package.status = "locked"
    package.locked_at = datetime.now(timezone.utc)
    if package.approved_by is None:
        package.approved_by = current_user.id
    if package.approved_at is None:
        package.approved_at = datetime.now(timezone.utc)

    maintenance_plan_ids: list[str] = []
    baseline_docs_result = await db.execute(
        select(CertificationProjectRequirementBaseline.document_id).where(
            CertificationProjectRequirementBaseline.project_id == project.id
        )
    )
    baseline_document_ids = [document_id for (document_id,) in baseline_docs_result.all()]
    if not baseline_document_ids and project.source_document_id is not None:
        baseline_document_ids = [project.source_document_id]

    if baseline_document_ids:
        source_query = _org_filter(
            select(Document).where(Document.id.in_(baseline_document_ids)),
            Document,
            current_user,
        )
        source_result = await db.execute(source_query)
        source_documents = source_result.scalars().all()
        for source_document in source_documents:
            plan = await ensure_maintenance_plan_for_document(
                db,
                source_document,
                created_by=current_user.id,
                only_missing=True,
            )
            if plan is not None:
                maintenance_plan_ids.append(str(plan.id))

    project.stage = "follow_up"
    project.status = "completed"
    if project.completed_at is None:
        project.completed_at = datetime.now(timezone.utc)

    await log_action(
        db,
        current_user,
        "lock",
        "submission_package",
        str(package.id),
        new_value={
            "status": package.status,
            "locked_at": package.locked_at.isoformat() if package.locked_at else None,
            "maintenance_plan_ids": maintenance_plan_ids,
        },
    )
    await log_action(
        db,
        current_user,
        "complete",
        "certification_project",
        str(project.id),
        new_value={
            "stage": project.stage,
            "status": project.status,
            "completed_at": project.completed_at.isoformat() if project.completed_at else None,
        },
    )

    await db.commit()
    await db.refresh(package)
    return _submission_package_response(package)


@router.get("/submission-packages/{package_id}/artifacts", response_model=dict)
async def list_submission_package_artifacts(
    package_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    package_query = (
        select(SubmissionPackage)
        .join(CertificationProject, CertificationProject.id == SubmissionPackage.project_id)
        .where(SubmissionPackage.id == package_id)
    )
    package_query = _org_filter(package_query, CertificationProject, current_user)
    package_result = await db.execute(package_query)
    package = package_result.scalar_one_or_none()
    if package is None:
        raise HTTPException(status_code=404, detail="Submission package not found")

    result = await db.execute(
        select(SubmissionPackageArtifact)
        .where(SubmissionPackageArtifact.submission_package_id == package_id)
        .order_by(SubmissionPackageArtifact.created_at.asc())
    )
    rows = result.scalars().all()
    return {
        "items": [SubmissionPackageArtifactResponse.model_validate(item) for item in rows],
        "total": len(rows),
    }


@router.post(
    "/submission-packages/{package_id}/artifacts",
    response_model=SubmissionPackageArtifactResponse,
    status_code=201,
)
async def create_submission_package_artifact(
    package_id: uuid.UUID,
    body: SubmissionPackageArtifactCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    await _require_package_access(db, current_user, package_id, "edit")
    package = await _get_submission_package_for_user(db, current_user, package_id, lock=True)
    if package.status != "draft":
        raise HTTPException(status_code=409, detail="Artifacts can only be changed in a draft package. Locked packages are retained unchanged.")

    item = SubmissionPackageArtifact(
        submission_package_id=package_id,
        artifact_type=body.artifact_type,
        name=body.name,
        file_path=body.file_path,
        link_url=body.link_url,
        required=body.required,
        included=body.included,
        notes=body.notes,
    )
    db.add(item)

    await log_action(
        db,
        current_user,
        "create",
        "submission_package_artifact",
        str(item.id),
        new_value={
            "submission_package_id": str(item.submission_package_id),
            "artifact_type": item.artifact_type,
            "name": item.name,
        },
    )

    await db.commit()
    await db.refresh(item)
    return item


@router.patch(
    "/submission-packages/{package_id}/artifacts/{artifact_id}",
    response_model=SubmissionPackageArtifactResponse,
)
async def update_submission_package_artifact(
    package_id: uuid.UUID,
    artifact_id: uuid.UUID,
    body: SubmissionPackageArtifactUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    await _require_package_access(db, current_user, package_id, "edit")
    package = await _get_submission_package_for_user(db, current_user, package_id, lock=True)
    if package.status != "draft":
        raise HTTPException(status_code=409, detail="Artifacts can only be changed in a draft package. Locked packages are retained unchanged.")

    artifact_result = await db.execute(
        select(SubmissionPackageArtifact).where(
            and_(
                SubmissionPackageArtifact.id == artifact_id,
                SubmissionPackageArtifact.submission_package_id == package_id,
            )
        )
    )
    artifact = artifact_result.scalar_one_or_none()
    if artifact is None:
        raise HTTPException(status_code=404, detail="Submission package artifact not found")

    old_value = {
        "artifact_type": artifact.artifact_type,
        "name": artifact.name,
        "file_path": artifact.file_path,
        "link_url": artifact.link_url,
        "required": artifact.required,
        "included": artifact.included,
        "notes": artifact.notes,
    }
    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(artifact, field, value)

    await log_action(
        db,
        current_user,
        "update",
        "submission_package_artifact",
        str(artifact.id),
        old_value=old_value,
        new_value={
            "artifact_type": artifact.artifact_type,
            "name": artifact.name,
            "file_path": artifact.file_path,
            "link_url": artifact.link_url,
            "required": artifact.required,
            "included": artifact.included,
            "notes": artifact.notes,
        },
    )

    await db.commit()
    await db.refresh(artifact)
    return artifact


@router.post(
    "/submission-packages/{package_id}/bundle-manifest",
    response_model=ExportManifestResponse,
    status_code=201,
)
async def create_submission_package_bundle_manifest(
    package_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin", "approver")),
):
    await _require_package_access(db, current_user, package_id, "export")
    package_query = (
        select(SubmissionPackage)
        .join(CertificationProject, CertificationProject.id == SubmissionPackage.project_id)
        .where(SubmissionPackage.id == package_id)
    )
    package_query = _org_filter(package_query, CertificationProject, current_user)
    package_result = await db.execute(package_query)
    package = package_result.scalar_one_or_none()
    if package is None:
        raise HTTPException(status_code=404, detail="Submission package not found")

    artifacts_result = await db.execute(
        select(SubmissionPackageArtifact)
        .where(SubmissionPackageArtifact.submission_package_id == package_id)
        .order_by(
            SubmissionPackageArtifact.artifact_type.asc(), SubmissionPackageArtifact.name.asc()
        )
    )
    artifacts = artifacts_result.scalars().all()

    payload = {
        "submission_package": {
            "id": str(package.id),
            "project_id": str(package.project_id),
            "review_cycle_id": str(package.review_cycle_id) if package.review_cycle_id else None,
            "snapshot_id": str(package.snapshot_id) if package.snapshot_id else None,
            "version": package.version,
            "status": package.status,
            "approval_requested_at": (
                package.approval_requested_at.isoformat() if package.approval_requested_at else None
            ),
            "approved_by": str(package.approved_by) if package.approved_by else None,
            "approved_at": package.approved_at.isoformat() if package.approved_at else None,
            "locked_at": package.locked_at.isoformat() if package.locked_at else None,
            "checklist_json": package.checklist_json,
            "created_at": package.created_at.isoformat() if package.created_at else None,
        },
        "artifacts": [
            {
                "id": str(artifact.id),
                "artifact_type": artifact.artifact_type,
                "name": artifact.name,
                "file_path": artifact.file_path,
                "link_url": artifact.link_url,
                "required": artifact.required,
                "included": artifact.included,
                "notes": artifact.notes,
                "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
            }
            for artifact in artifacts
        ],
    }

    signature = sign_manifest("submission_package", str(package.id), payload)
    manifest = ExportManifest(
        organization_id=current_user.organization_id,
        scope_type="submission_package",
        scope_id=str(package.id),
        payload_json=json.dumps(payload, sort_keys=True),
        hash_algo="sha256",
        signature=signature,
        signed_by=current_user.id,
    )
    db.add(manifest)

    await log_action(
        db,
        current_user,
        "create",
        "export_manifest",
        str(manifest.id),
        new_value={
            "scope_type": manifest.scope_type,
            "scope_id": manifest.scope_id,
            "hash_algo": manifest.hash_algo,
        },
    )

    await db.commit()
    await db.refresh(manifest)
    return manifest


@router.get("/maintenance-plans", response_model=dict)
async def list_maintenance_plans(
    certification_project_id: Optional[uuid.UUID] = None,
    jurisdiction_id: Optional[uuid.UUID] = None,
    document_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    limit = min(max(limit, 1), 1000)
    query = _org_filter(select(MaintenancePlan), MaintenancePlan, current_user)
    if certification_project_id is not None:
        query = query.where(MaintenancePlan.certification_project_id == certification_project_id)
    if jurisdiction_id is not None:
        query = query.where(MaintenancePlan.jurisdiction_id == jurisdiction_id)
    if document_id is not None:
        query = query.where(MaintenancePlan.document_id == document_id)
    if status:
        query = query.where(MaintenancePlan.status == status)

    result = await db.execute(query.order_by(MaintenancePlan.created_at.desc()))
    rows = result.scalars().all()
    return {
        "items": [
            MaintenancePlanResponse.model_validate(item) for item in rows[skip : skip + limit]
        ],
        "total": len(rows),
    }


@router.post("/maintenance-plans", response_model=MaintenancePlanResponse, status_code=201)
async def create_maintenance_plan(
    body: MaintenancePlanCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    if body.certification_project_id is not None:
        project = await require_access(db, CertificationProject, body.certification_project_id, current_user, "edit")
        if project.jurisdiction_id != body.jurisdiction_id:
            raise HTTPException(400, "Maintenance project must match jurisdiction")
        if body.document_id and not await db.scalar(select(CertificationProjectRequirementBaseline.project_id).where(
            CertificationProjectRequirementBaseline.project_id == project.id,
            CertificationProjectRequirementBaseline.document_id == body.document_id,
        )):
            raise HTTPException(400, "Maintenance source must belong to project baseline")
    if body.document_id is not None:
        await get_org_owned_or_404(
            db,
            Document,
            body.document_id,
            current_user,
            detail="Document not found",
        )
    await get_active_user_in_org_or_404(
        db,
        body.owner_id,
        current_user,
        detail="Owner not found",
    )

    item = MaintenancePlan(
        certification_project_id=body.certification_project_id,
        organization_id=current_user.organization_id,
        jurisdiction_id=body.jurisdiction_id,
        document_id=body.document_id,
        name=body.name,
        cadence_days=body.cadence_days,
        reminder_days=body.reminder_days,
        escalation_days=body.escalation_days,
        next_run_at=body.next_run_at,
        status=body.status,
        auto_generated=body.auto_generated,
        owner_id=body.owner_id,
        created_by=current_user.id,
    )
    db.add(item)
    await db.flush()

    await log_action(
        db,
        current_user,
        "create",
        "maintenance_plan",
        str(item.id),
        new_value={
            "name": item.name,
            "jurisdiction_id": str(item.jurisdiction_id),
            "document_id": str(item.document_id) if item.document_id else None,
            "cadence_days": item.cadence_days,
        },
    )
    await db.commit()
    await db.refresh(item)
    return item


@router.patch("/maintenance-plans/{plan_id}", response_model=MaintenancePlanResponse)
async def update_maintenance_plan(
    plan_id: uuid.UUID,
    body: MaintenancePlanUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    query = _org_filter(
        select(MaintenancePlan).where(MaintenancePlan.id == plan_id),
        MaintenancePlan,
        current_user,
    )
    result = await db.execute(query)
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Maintenance plan not found")

    if item.certification_project_id:
        await require_access(db, CertificationProject, item.certification_project_id, current_user, "edit")
    if "certification_project_id" in body.model_fields_set:
        if item.certification_project_id and body.certification_project_id != item.certification_project_id:
            raise HTTPException(409, "Create a separate plan to change its protected project context")
        if body.certification_project_id:
            project = await require_access(db, CertificationProject, body.certification_project_id, current_user, "edit")
            if project.jurisdiction_id != item.jurisdiction_id:
                raise HTTPException(400, "Maintenance project must match jurisdiction")
            if item.document_id and not await db.scalar(select(CertificationProjectRequirementBaseline.project_id).where(
                CertificationProjectRequirementBaseline.project_id == project.id,
                CertificationProjectRequirementBaseline.document_id == item.document_id,
            )):
                raise HTTPException(400, "Maintenance source must belong to project baseline")
            item.certification_project_id = project.id

    old_value = {
        "name": item.name,
        "cadence_days": item.cadence_days,
        "status": item.status,
        "next_run_at": item.next_run_at.isoformat() if item.next_run_at else None,
    }
    await get_active_user_in_org_or_404(
        db,
        body.owner_id,
        current_user,
        detail="Owner not found",
    )

    for field in [
        "name",
        "cadence_days",
        "reminder_days",
        "escalation_days",
        "next_run_at",
        "last_run_at",
        "status",
        "owner_id",
    ]:
        value = getattr(body, field)
        if value is not None:
            setattr(item, field, value)

    await log_action(
        db,
        current_user,
        "update",
        "maintenance_plan",
        str(item.id),
        old_value=old_value,
        new_value={
            "name": item.name,
            "cadence_days": item.cadence_days,
            "status": item.status,
            "next_run_at": item.next_run_at.isoformat() if item.next_run_at else None,
        },
    )

    await db.commit()
    await db.refresh(item)
    return item


@router.post("/maintenance-plans/generate", response_model=dict)
async def generate_maintenance_plan_defaults(
    body: MaintenancePlanGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    summary = await generate_maintenance_plans(
        db,
        current_user=current_user,
        jurisdiction_id=body.jurisdiction_id,
        only_missing=body.only_missing,
    )

    await log_action(
        db,
        current_user,
        "generate",
        "maintenance_plan",
        "bulk",
        new_value=summary,
    )
    await db.commit()
    return summary


@router.post("/maintenance-plans/run-due", response_model=dict)
async def run_due_maintenance_cycles(
    certification_project_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    if certification_project_id:
        await require_access(db, CertificationProject, certification_project_id, current_user, "edit")
    summary = await generate_due_review_cycles(db, current_user=current_user, certification_project_id=certification_project_id)
    await log_action(
        db,
        current_user,
        "generate",
        "certification_project" if certification_project_id else "maintenance_cycle",
        str(certification_project_id) if certification_project_id else "due",
        new_value=summary if certification_project_id else None,
    )
    await db.commit()
    return summary


@router.get("/maintenance-events", response_model=dict)
async def list_maintenance_events(
    maintenance_plan_id: Optional[uuid.UUID] = None,
    skip: int = 0,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    limit = min(max(limit, 1), 1000)
    query = select(MaintenanceEvent).join(
        MaintenancePlan, MaintenancePlan.id == MaintenanceEvent.maintenance_plan_id
    )
    query = _org_filter(query, MaintenancePlan, current_user)
    if maintenance_plan_id is not None:
        query = query.where(MaintenanceEvent.maintenance_plan_id == maintenance_plan_id)

    result = await db.execute(query.order_by(MaintenanceEvent.created_at.desc()))
    rows = result.scalars().all()
    return {
        "items": [
            MaintenanceEventResponse.model_validate(item) for item in rows[skip : skip + limit]
        ],
        "total": len(rows),
    }


@router.get("/evidence-items", response_model=dict)
async def list_evidence_items(
    requirement_id: Optional[uuid.UUID] = None,
    review_status: Optional[str] = None,
    stale_only: bool = False,
    skip: int = 0,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    limit = min(max(limit, 1), 1000)
    query = _org_filter(select(EvidenceItem), EvidenceItem, current_user)
    if requirement_id is not None:
        query = query.where(EvidenceItem.requirement_id == requirement_id)
    if review_status:
        query = query.where(EvidenceItem.review_status == review_status)
    if stale_only:
        now = datetime.now(timezone.utc)
        query = query.where(EvidenceItem.valid_to.is_not(None), EvidenceItem.valid_to < now)

    result = await db.execute(query.order_by(EvidenceItem.created_at.desc()))
    rows = result.scalars().all()
    return {
        "items": [EvidenceItemResponse.model_validate(item) for item in rows[skip : skip + limit]],
        "total": len(rows),
    }


@router.post("/evidence-items", response_model=EvidenceItemResponse, status_code=201)
async def create_evidence_item(
    body: EvidenceItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.review_status not in {"draft", "in_review", "rejected", "approved"}:
        raise HTTPException(status_code=422, detail="Invalid evidence review status")
    if body.review_status in {"approved", "rejected"}:
        raise HTTPException(
            status_code=403, detail="Evidence decision requires a review transition"
        )

    await get_org_owned_or_404(
        db,
        Requirement,
        body.requirement_id,
        current_user,
        detail="Requirement not found",
    )
    await get_active_user_in_org_or_404(
        db,
        body.owner_id,
        current_user,
        detail="Owner not found",
    )
    await get_active_user_in_org_or_404(
        db,
        body.reviewer_id,
        current_user,
        detail="Reviewer not found",
    )

    item = EvidenceItem(
        organization_id=current_user.organization_id,
        requirement_id=body.requirement_id,
        evidence_type=body.evidence_type,
        title=body.title,
        body=body.body,
        file_path=body.file_path,
        link_url=body.link_url,
        owner_id=body.owner_id,
        reviewer_id=body.reviewer_id,
        review_status=body.review_status,
        valid_from=body.valid_from,
        valid_to=body.valid_to,
        expires_in_days=body.expires_in_days,
        created_by=current_user.id,
    )
    db.add(item)

    await log_action(
        db,
        current_user,
        "create",
        "evidence_item",
        str(item.id),
        new_value={
            "requirement_id": str(item.requirement_id),
            "evidence_type": item.evidence_type,
            "title": item.title,
            "review_status": item.review_status,
        },
    )
    await db.commit()
    await db.refresh(item)
    return item


@router.patch("/evidence-items/{item_id}", response_model=EvidenceItemResponse)
async def update_evidence_item(
    item_id: uuid.UUID,
    body: EvidenceItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = _org_filter(
        select(EvidenceItem).where(EvidenceItem.id == item_id), EvidenceItem, current_user
    )
    result = await db.execute(query.with_for_update())
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Evidence item not found")

    if {"approved_by", "approved_at"} & body.model_fields_set:
        raise HTTPException(status_code=422, detail="Approval attribution is set by the server")
    if body.review_status is not None and body.review_status not in {
        "draft", "in_review", "rejected", "approved"
    }:
        raise HTTPException(status_code=422, detail="Invalid evidence review status")
    if body.review_status in {"approved", "rejected"} and current_user.role not in {
        "approver", "admin"
    }:
        raise HTTPException(status_code=403, detail="Insufficient role to decide evidence")
    if (
        item.review_status == "approved"
        and body.review_status in {"draft", "in_review", "rejected"}
        and current_user.role not in {"approver", "admin"}
    ):
        raise HTTPException(status_code=403, detail="Insufficient role to change evidence approval")

    old_value = {
        "title": item.title,
        "review_status": item.review_status,
        "approved_by": str(item.approved_by) if item.approved_by else None,
        "approved_at": item.approved_at.isoformat() if item.approved_at else None,
        "valid_to": item.valid_to.isoformat() if item.valid_to else None,
    }
    await get_active_user_in_org_or_404(
        db,
        body.owner_id,
        current_user,
        detail="Owner not found",
    )
    await get_active_user_in_org_or_404(
        db,
        body.reviewer_id,
        current_user,
        detail="Reviewer not found",
    )
    evidence_fields = {
        "title",
        "body",
        "file_path",
        "link_url",
        "owner_id",
        "reviewer_id",
        "valid_from",
        "valid_to",
        "expires_in_days",
    }
    evidence_changed = any(
        field in body.model_fields_set
        and getattr(body, field) is not None
        and getattr(item, field) != getattr(body, field)
        for field in evidence_fields
    )
    for field in [
        "title",
        "body",
        "file_path",
        "link_url",
        "owner_id",
        "reviewer_id",
        "valid_from",
        "valid_to",
        "expires_in_days",
    ]:
        value = getattr(body, field)
        if value is not None:
            setattr(item, field, value)

    # Edits to approved evidence must invalidate the earlier approval unless an
    # authorised reviewer explicitly approves the new version in this request.
    if body.review_status == "approved":
        if (
            item.review_status != "approved"
            or evidence_changed
            or item.approved_by is None
            or item.approved_at is None
        ):
            item.approved_by = current_user.id
            item.approved_at = datetime.now(timezone.utc)
        item.review_status = "approved"
    elif body.review_status is not None or (item.review_status == "approved" and evidence_changed):
        item.review_status = body.review_status or "draft"
        item.approved_by = None
        item.approved_at = None

    await log_action(
        db,
        current_user,
        "update",
        "evidence_item",
        str(item.id),
        old_value=old_value,
        new_value={
            "title": item.title,
            "review_status": item.review_status,
            "approved_by": str(item.approved_by) if item.approved_by else None,
            "approved_at": item.approved_at.isoformat() if item.approved_at else None,
            "valid_to": item.valid_to.isoformat() if item.valid_to else None,
        },
    )
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/evidence-validations", response_model=dict)
async def list_evidence_validations(
    evidence_item_id: Optional[uuid.UUID] = None,
    skip: int = 0,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    limit = min(max(limit, 1), 1000)
    query = select(EvidenceValidation).join(
        EvidenceItem, EvidenceItem.id == EvidenceValidation.evidence_item_id
    )
    query = _org_filter(query, EvidenceItem, current_user)
    if evidence_item_id is not None:
        query = query.where(EvidenceValidation.evidence_item_id == evidence_item_id)

    result = await db.execute(query.order_by(EvidenceValidation.created_at.desc()))
    rows = result.scalars().all()
    return {
        "items": [
            EvidenceValidationResponse.model_validate(item) for item in rows[skip : skip + limit]
        ],
        "total": len(rows),
    }


@router.post("/evidence-validations", response_model=EvidenceValidationResponse, status_code=201)
async def create_evidence_validation(
    body: EvidenceValidationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    evidence_query = _org_filter(
        select(EvidenceItem).where(EvidenceItem.id == body.evidence_item_id),
        EvidenceItem,
        current_user,
    )
    evidence_result = await db.execute(evidence_query)
    evidence_item = evidence_result.scalar_one_or_none()
    if evidence_item is None:
        raise HTTPException(status_code=404, detail="Evidence item not found")

    item = EvidenceValidation(
        evidence_item_id=body.evidence_item_id,
        validator_id=current_user.id,
        validation_status=body.validation_status,
        comment=body.comment,
    )
    db.add(item)

    await log_action(
        db,
        current_user,
        "create",
        "evidence_validation",
        str(item.id),
        new_value={
            "evidence_item_id": str(item.evidence_item_id),
            "validation_status": item.validation_status,
        },
    )
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/integrations/connections", response_model=dict)
async def list_integration_connections(
    provider: Optional[str] = None,
    enabled: Optional[bool] = None,
    skip: int = 0,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    limit = min(max(limit, 1), 1000)
    query = _org_filter(select(IntegrationConnection), IntegrationConnection, current_user)
    if provider:
        query = query.where(IntegrationConnection.provider == provider)
    if enabled is not None:
        query = query.where(IntegrationConnection.enabled == enabled)

    result = await db.execute(query.order_by(IntegrationConnection.created_at.desc()))
    rows = result.scalars().all()
    return {
        "items": [
            IntegrationConnectionResponse.model_validate(item) for item in rows[skip : skip + limit]
        ],
        "total": len(rows),
    }


@router.post(
    "/integrations/connections",
    response_model=IntegrationConnectionResponse,
    status_code=201,
)
async def create_integration_connection(
    body: IntegrationConnectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    item = IntegrationConnection(
        organization_id=current_user.organization_id,
        provider=body.provider.strip().lower(),
        name=body.name.strip(),
        config_json=body.config_json,
        enabled=body.enabled,
        created_by=current_user.id,
    )
    db.add(item)

    await log_action(
        db,
        current_user,
        "create",
        "integration_connection",
        str(item.id),
        new_value={
            "provider": item.provider,
            "name": item.name,
            "enabled": item.enabled,
        },
    )
    await db.commit()
    await db.refresh(item)
    return item


@router.patch(
    "/integrations/connections/{connection_id}",
    response_model=IntegrationConnectionResponse,
)
async def update_integration_connection(
    connection_id: uuid.UUID,
    body: IntegrationConnectionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    query = _org_filter(
        select(IntegrationConnection).where(IntegrationConnection.id == connection_id),
        IntegrationConnection,
        current_user,
    )
    result = await db.execute(query)
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Integration connection not found")

    old_value = {
        "name": item.name,
        "enabled": item.enabled,
        "last_sync_status": item.last_sync_status,
        "last_sync_message": item.last_sync_message,
    }

    for field in [
        "name",
        "config_json",
        "enabled",
        "last_sync_status",
        "last_sync_message",
        "last_sync_at",
    ]:
        value = getattr(body, field)
        if value is not None:
            setattr(item, field, value)

    await log_action(
        db,
        current_user,
        "update",
        "integration_connection",
        str(item.id),
        old_value=old_value,
        new_value={
            "name": item.name,
            "enabled": item.enabled,
            "last_sync_status": item.last_sync_status,
            "last_sync_message": item.last_sync_message,
        },
    )
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/export-manifests", response_model=dict)
async def list_export_manifests(
    scope_type: Optional[str] = None,
    scope_id: Optional[str] = None,
    skip: int = 0,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    limit = min(max(limit, 1), 1000)
    query = _org_filter(select(ExportManifest), ExportManifest, current_user)
    if scope_type:
        query = query.where(ExportManifest.scope_type == scope_type)
    if scope_id:
        query = query.where(ExportManifest.scope_id == scope_id)

    result = await db.execute(query.order_by(ExportManifest.created_at.desc()))
    rows = result.scalars().all()
    return {
        "items": [
            ExportManifestResponse.model_validate(item) for item in rows[skip : skip + limit]
        ],
        "total": len(rows),
    }


@router.post("/export-manifests", response_model=ExportManifestResponse, status_code=201)
async def create_export_manifest(
    body: ExportManifestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin", "approver")),
):
    if body.scope_type in {"certification_project", "submission_package", "review_cycle", "review_package", "snapshot"}:
        try:
            scope_id = uuid.UUID(body.scope_id)
        except (ValueError, TypeError):
            raise HTTPException(422, "A valid scope identifier is required")
        if body.scope_type == "certification_project":
            await require_access(db, CertificationProject, scope_id, current_user, "export")
        elif body.scope_type == "submission_package":
            await _require_package_access(db, current_user, scope_id, "export")
        else:
            from app.services.access import access_clause
            model = Snapshot if body.scope_type == "snapshot" else ReviewCycle
            result = await db.scalar(_org_filter(select(model.id).where(model.id == scope_id), model, current_user).where(access_clause(model, current_user, "export")))
            if result is None:
                raise HTTPException(404, "Not found")
    signature = sign_manifest(body.scope_type, body.scope_id, body.payload)
    item = ExportManifest(
        organization_id=current_user.organization_id,
        scope_type=body.scope_type,
        scope_id=body.scope_id,
        payload_json=json.dumps(body.payload, sort_keys=True),
        hash_algo="sha256",
        signature=signature,
        signed_by=current_user.id,
    )
    db.add(item)

    await log_action(
        db,
        current_user,
        "create",
        "export_manifest",
        str(item.id),
        new_value={
            "scope_type": item.scope_type,
            "scope_id": item.scope_id,
            "hash_algo": item.hash_algo,
        },
    )
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/export-manifests/{manifest_id}/verify", response_model=dict)
async def verify_export_manifest_signature(
    manifest_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = _org_filter(
        select(ExportManifest).where(ExportManifest.id == manifest_id),
        ExportManifest,
        current_user,
    )
    result = await db.execute(query)
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Export manifest not found")

    payload = json.loads(item.payload_json)
    valid = verify_manifest(item.scope_type, item.scope_id, payload, item.signature)
    return {
        "manifest_id": str(item.id),
        "scope_type": item.scope_type,
        "scope_id": item.scope_id,
        "hash_algo": item.hash_algo,
        "valid": valid,
    }
