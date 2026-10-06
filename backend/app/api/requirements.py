import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, delete, func, select, update, case, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.api.tenant import apply_org_scope, get_active_user_in_org_or_404, get_org_owned_or_404
from app.database import get_db
from app.models.document import Document
from app.models.change_management import ChangeRequirementImpact
from app.models.extraction import ExtractionRun, ExtractionRunDiagnostic
from app.models.jurisdiction import Jurisdiction
from app.models.program import (
    CertificationProject,
    CertificationProjectRequirementBaseline,
    RequirementSetVersion,
    ReviewCycleRequirementBaseline,
)
from app.models.requirement import ExtractionFeedback, ExtractedRequirement, Requirement, RequirementStatus
from app.models.evidence import EvidenceFile, EvidenceLink, EvidenceNote
from app.models.review import ReviewItem, ReviewItemComment, ReviewItemEvidenceFile
from app.models.user import User
from app.schemas.document import DocumentResponse
from app.schemas.import_recovery import ImportRecoveryDecision, ImportReconciliationRequest
from app.schemas.requirement import (
    AssignRequest,
    RequirementCreateRequest,
    RequirementResponse,
    RequirementStatusResponse,
    EvidenceCounts,
    RequirementSetCreateRequest,
    RequirementUpdate,
    RequirementWithStatusResponse,
    RequirementSetSummaryResponse,
    RequirementSetVersionApproveRequest,
    RequirementSetVersionCloneRequest,
    RequirementSetVersionResponse,
    RequirementSetVersionSubmitRequest,
    StatusChangeRequest,
)
from app.services.source_validation import (
    numbered_hierarchy_errors, structure_errors, structured_baseline_reconciliation,
    validate_baseline, validate_extraction_complete,
)
from app.services.import_recovery import correction_error
from app.services.audit import log_action
from app.services.maintenance import frequency_to_days
from app.services.reference_hierarchy import (
    normalize_reference_or_raise,
    resolve_requirement_parent_id,
)

router = APIRouter(prefix="/api/v1/requirements", tags=["requirements"])


@router.get("/sets/{document_id}/versions/{version_id}/import-reconciliation")
async def preview_structured_import_reconciliation(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = await _get_document_for_user(db, current_user, document_id)
    version = await _get_version_for_document(db, document_id, version_id)
    if version is None:
        raise HTTPException(404, "Requirement set version not found")
    report, _, _ = await structured_baseline_reconciliation(db, version, document)
    if report is None:
        return None
    return report


@router.post("/sets/{document_id}/versions/{version_id}/import-reconciliation")
async def reconcile_structured_import(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    body: ImportReconciliationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    document = await _get_document_for_user(db, current_user, document_id)
    await db.refresh(document, with_for_update=True)
    version = await _get_version_for_document(db, document_id, version_id)
    if version is None:
        raise HTTPException(404, "Requirement set version not found")
    await db.refresh(version, with_for_update=True)
    if version.status != "draft" or document.status not in {"draft", "extracted", "reviewed", "changes_requested"}:
        raise HTTPException(409, "Only an editable draft can be reconciled.")
    await validate_extraction_complete(db, document)
    report, sources, staged = await structured_baseline_reconciliation(db, version, document)
    if report is None:
        raise HTTPException(409, "A current structured extraction is required.")
    if (report["source_fingerprint"] != body.source_fingerprint or
            report["draft_fingerprint"] != body.draft_fingerprint):
        raise HTTPException(409, "Source or draft changed. Review the differences again.")
    if report["stale"] or report["duplicate"]:
        raise HTTPException(422, "Remove stale or duplicate linked draft rows before reconciliation.")

    linked = {row.source_extraction_id: row for row in staged if row.active and row.source_extraction_id}
    for source in sources:
        if source.id in linked:
            continue
        copy = Requirement(
            organization_id=document.organization_id, jurisdiction_id=document.jurisdiction_id,
            document_id=document.id, requirement_set_version_id=version.id,
            source_extraction_id=source.id, reference_id=source.reference_id,
            title=source.title, text=source.text, requirement_type=source.requirement_type,
            sort_order=source.sort_order, active=True,
        )
        db.add(copy)
        await db.flush()
        linked[source.id] = copy
        db.add(RequirementStatus(requirement_id=copy.id, status="not_started",
                                 comment="Added during structured import reconciliation",
                                 changed_by=current_user.id, changed_at=datetime.now(timezone.utc)))
    for source in sources:
        if source.id in {uuid.UUID(item["id"]) for item in report["missing"]}:
            linked[source.id].parent_id = linked[source.parent_id].id if source.parent_id else None
    await db.flush()
    final, _, final_rows = await structured_baseline_reconciliation(db, version, document)
    active_rows = [row for row in final_rows if row.active]
    errors = structure_errors(active_rows) + numbered_hierarchy_errors(active_rows)
    if errors or final["missing"] or final["stale"] or final["duplicate"]:
        raise HTTPException(422, {"message": "Fix the draft hierarchy before reconciliation.",
                                  "gates": [{"message": x} for x in errors[:25]]})
    await log_action(db, current_user, "reconcile", "structured_baseline_reconciliation", str(version.id),
                     new_value={"source_fingerprint": final["source_fingerprint"],
                                "draft_fingerprint": final["draft_fingerprint"],
                                "difference_count": len(final["differences"]),
                                "added_count": len(report["missing"])})
    await db.commit()
    final["reconciled"] = True
    return final


@router.post("/sets/{document_id}/import-recovery/{extraction_id}")
async def resolve_structured_import_candidate(
    document_id: uuid.UUID,
    extraction_id: uuid.UUID,
    body: ImportRecoveryDecision,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin", "approver")),
):
    """Resolve one ambiguous candidate without changing immutable source text."""
    document = await _get_document_for_user(db, current_user, document_id)
    # Extraction reruns lock the document before switching current_extraction_id.
    # Hold the same lock through the decision and audit commit.
    await db.refresh(document, with_for_update=True)
    if document.status not in {"extracted", "reviewed", "draft", "changes_requested"}:
        raise HTTPException(409, "This import is not an editable draft.")
    if not document.current_extraction_id:
        raise HTTPException(409, "This requirement set has no current extraction run.")
    run = await db.get(ExtractionRun, document.current_extraction_id)
    if not run or run.document_id != document.id or run.pipeline_version != "opendataloader_v1" or run.status != "completed":
        raise HTTPException(409, "A completed structured extraction is required.")

    rows = list((await db.scalars(
        select(ExtractedRequirement).where(
            ExtractedRequirement.document_id == document.id,
            ExtractedRequirement.extraction_run_id == run.id,
        ).with_for_update()
    )).all())
    by_id = {row.id: row for row in rows}
    row = by_id.get(extraction_id)
    if row is None:
        raise HTTPException(404, "Source candidate not found.")
    if row.status == "rejected" or (not row.needs_review and not row.reference_id.startswith("unresolved-")):
        raise HTTPException(409, "This source candidate is already resolved.")

    old_value = {"reference_id": row.reference_id, "status": row.status,
                 "needs_review": row.needs_review, "review_reason": row.review_reason}
    if body.action == "correct":
        reference = (body.reference_id or "").strip().rstrip(".")
        parent_reference = body.parent_reference.strip().rstrip(".") if body.parent_reference is not None else None
        active = {item.reference_id: item for item in rows if item.status != "rejected" and item.id != row.id}
        problem = correction_error(reference, parent_reference, set(active))
        if problem:
            raise HTTPException(422, problem)
        if reference in active:
            raise HTTPException(422, f"Reference {reference} already exists in this import.")
        row.reference_id = reference
        row.parent_id = active[parent_reference or reference.rpartition(".")[0]].id if (parent_reference or reference.rpartition(".")[0]) else None
        if body.corrected_text is not None:
            if not body.corrected_text.strip():
                raise HTTPException(422, "Corrected text cannot be empty.")
            row.text = body.corrected_text
            row.title = body.corrected_text.splitlines()[0][:500]
        if body.requirement_type:
            row.requirement_type = body.requirement_type
        row.status = "accepted"
        row.needs_review = False
        row.review_reason = None
    elif body.action == "attach_continuation":
        if not any(reason in (row.review_reason or "") for reason in ("orphan_continuation", "ambiguous_unnumbered_table_row")):
            raise HTTPException(422, "Only an unnumbered table row can be attached.")
        target = by_id.get(body.target_id)
        if target is None or target.id == row.id or target.status == "rejected" or target.reference_id.startswith("unresolved-"):
            raise HTTPException(422, "Select an active numbered target in this extraction run.")
        target.text = target.text.rstrip() + "\n" + row.original_text.strip()
        target.needs_review = True
        target.review_reason = "Attached continuation: verify wording against source PDF"
        row.status = "rejected"
        row.needs_review = False
        row.review_reason = f"attached_to:{target.id}"
    else:
        row.status = "rejected"
        row.needs_review = False
        row.review_reason = "excluded_by_reviewer"

    await log_action(db, current_user, "resolve", "structured_import_candidate", str(row.id),
                     old_value=old_value,
                     new_value={"action": body.action, "reference_id": row.reference_id,
                                "status": row.status, "target_id": str(body.target_id) if body.target_id else None})
    await db.commit()
    return {"id": str(row.id), "action": body.action, "status": row.status}


async def _get_document_for_user(
    db: AsyncSession,
    current_user: User,
    document_id: uuid.UUID,
) -> Document:
    return await get_org_owned_or_404(
        db,
        Document,
        document_id,
        current_user,
        detail="Requirement set not found",
    )


async def _get_requirement_for_user(
    db: AsyncSession,
    current_user: User,
    requirement_id: uuid.UUID,
) -> Requirement:
    return await get_org_owned_or_404(
        db,
        Requirement,
        requirement_id,
        current_user,
        detail="Requirement not found",
    )


async def _get_version_for_document(
    db: AsyncSession,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
) -> Optional[RequirementSetVersion]:
    result = await db.execute(
        select(RequirementSetVersion).where(
            and_(
                RequirementSetVersion.id == version_id,
                RequirementSetVersion.document_id == document_id,
            )
        )
    )
    return result.scalar_one_or_none()


async def _get_latest_draft_version_for_document(
    db: AsyncSession,
    document_id: uuid.UUID,
) -> Optional[RequirementSetVersion]:
    result = await db.execute(
        select(RequirementSetVersion)
        .where(
            and_(
                RequirementSetVersion.document_id == document_id,
                RequirementSetVersion.status == "draft",
            )
        )
        .order_by(RequirementSetVersion.version_number.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _resolve_mutable_version_for_requirement_write(
    db: AsyncSession,
    document_id: uuid.UUID,
    requested_version_id: Optional[uuid.UUID],
) -> RequirementSetVersion:
    document = await db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Requirement set not found")
    await db.refresh(document, with_for_update=True)
    version: Optional[RequirementSetVersion]
    if requested_version_id is not None:
        version = await _get_version_for_document(db, document_id, requested_version_id)
        if version is None:
            raise HTTPException(status_code=404, detail="Requirement set version not found")
    else:
        version = await _get_latest_draft_version_for_document(db, document_id)
        if version is None:
            raise HTTPException(
                status_code=409,
                detail="No editable draft version exists for this requirement set. Clone the current version first.",
            )

    await db.refresh(version, with_for_update=True)
    if version.document_id != document.id:
        raise HTTPException(status_code=409, detail="Requirement set version does not belong to this document.")
    if version.status != "draft":
        raise HTTPException(
            status_code=409,
            detail="This requirement set version is locked. Clone it to a draft version before editing.",
        )
    return version


async def _ensure_mutable_requirement(db: AsyncSession, requirement: Requirement) -> None:
    if requirement.requirement_set_version_id is None:
        if requirement.document_id is None:
            return
        raise HTTPException(
            status_code=409,
            detail="Requirement is not attached to an editable requirement set version.",
        )
    document = await db.get(Document, requirement.document_id)
    if document is None:
        raise HTTPException(status_code=409, detail="Requirement set not found")
    await db.refresh(document, with_for_update=True)
    version = await db.get(RequirementSetVersion, requirement.requirement_set_version_id)
    if version is None:
        raise HTTPException(status_code=409, detail="Requirement set version not found")
    await db.refresh(version, with_for_update=True)
    if version.document_id != document.id:
        raise HTTPException(status_code=409, detail="Requirement set version does not belong to this requirement.")
    if version.status != "draft":
        raise HTTPException(
            status_code=409,
            detail="This requirement set version is locked. Clone it to a draft version before editing.",
        )
    await db.refresh(requirement, with_for_update=True)
    if requirement.requirement_set_version_id != version.id:
        raise HTTPException(status_code=409, detail="Requirement changed. Reload the draft before editing.")


@router.post("/sets", response_model=DocumentResponse, status_code=201)
async def create_requirement_set(
    body: RequirementSetCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    name = body.name.strip()
    document_type = body.document_type.strip()
    testing_frequency = body.testing_frequency.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name cannot be empty")
    if not document_type:
        raise HTTPException(status_code=400, detail="document_type cannot be empty")
    if not testing_frequency:
        raise HTTPException(status_code=400, detail="testing_frequency cannot be empty")

    jurisdiction_result = await db.execute(
        select(Jurisdiction).where(Jurisdiction.id == body.jurisdiction_id)
    )
    jurisdiction = jurisdiction_result.scalar_one_or_none()
    if jurisdiction is None:
        raise HTTPException(status_code=400, detail="Invalid jurisdiction_id")
    if not jurisdiction.active:
        raise HTTPException(status_code=400, detail="Jurisdiction is inactive")

    document = Document(
        organization_id=current_user.organization_id,
        jurisdiction_id=body.jurisdiction_id,
        filename=None,
        name=name,
        document_type=document_type,
        version=body.version.strip() if body.version else None,
        effective_date=body.effective_date,
        status="draft",
        file_path=None,
        uploaded_by=current_user.id,
        testing_frequency=testing_frequency,
        cadence_interval_days=frequency_to_days(testing_frequency),
    )
    db.add(document)
    await db.flush()

    initial_version = RequirementSetVersion(
        organization_id=current_user.organization_id,
        document_id=document.id,
        version_number=1,
        status="draft",
        is_current=True,
        created_by=current_user.id,
    )
    db.add(initial_version)

    await log_action(
        db,
        current_user,
        "create",
        "requirements_set",
        str(document.id),
        new_value={
            "name": document.name,
            "document_type": document.document_type,
            "status": document.status,
            "jurisdiction_id": str(document.jurisdiction_id),
        },
    )
    await db.commit()
    await db.refresh(document)
    return document


@router.post("", response_model=RequirementResponse, status_code=201)
async def create_requirement(
    body: RequirementCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    requirement_set = await _get_document_for_user(db, current_user, body.document_id)
    target_version = await _resolve_mutable_version_for_requirement_write(
        db,
        body.document_id,
        body.requirement_set_version_id,
    )
    fields_set = body.model_fields_set
    try:
        normalized_reference_id = normalize_reference_or_raise(
            body.reference_id,
            detail="reference_id cannot be empty",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    parent_id: Optional[uuid.UUID] = None
    if "parent_id" not in fields_set:
        parent_id = await resolve_requirement_parent_id(
            db,
            requirement_set_version_id=target_version.id,
            reference_id=normalized_reference_id,
        )
    elif body.parent_id is not None:
        parent_result = await db.execute(
            apply_org_scope(
                select(Requirement).where(Requirement.id == body.parent_id),
                Requirement,
                current_user,
            )
        )
        parent = parent_result.scalar_one_or_none()
        if parent is None or parent.document_id != body.document_id:
            raise HTTPException(
                status_code=400,
                detail="parent_id must refer to a requirement in the same requirement set",
            )
        if parent.requirement_set_version_id != target_version.id:
            raise HTTPException(
                status_code=400,
                detail="parent_id must refer to a requirement in the same requirement set version",
            )
        parent_id = parent.id

    max_sort_result = await db.execute(
        select(func.max(Requirement.sort_order)).where(
            Requirement.requirement_set_version_id == target_version.id
        )
    )
    max_sort = max_sort_result.scalar()
    next_sort_order = int(max_sort) + 1 if max_sort is not None else 0

    requirement_type = (body.requirement_type or "mandatory").strip()
    if not requirement_type:
        raise HTTPException(status_code=400, detail="requirement_type cannot be empty")
    await get_active_user_in_org_or_404(
        db,
        body.default_owner_id,
        current_user,
        detail="Default owner not found",
    )

    requirement = Requirement(
        organization_id=requirement_set.organization_id,
        jurisdiction_id=requirement_set.jurisdiction_id,
        document_id=body.document_id,
        requirement_set_version_id=target_version.id,
        reference_id=normalized_reference_id,
        title=body.title.strip() if body.title and body.title.strip() else None,
        text=(body.text or "").strip(),
        requirement_type=requirement_type,
        parent_id=parent_id,
        default_owner_id=body.default_owner_id,
        active=True,
        sort_order=next_sort_order,
    )
    db.add(requirement)
    await db.flush()

    status_entry = RequirementStatus(
        requirement_id=requirement.id,
        status="not_started",
        comment="Created manually",
        changed_by=current_user.id,
        changed_at=datetime.now(timezone.utc),
    )
    db.add(status_entry)

    await log_action(
        db,
        current_user,
        "create",
        "requirement",
        str(requirement.id),
        new_value={
            "document_id": str(body.document_id),
            "reference_id": requirement.reference_id,
            "requirement_type": requirement.requirement_type,
        },
    )
    await db.commit()
    await db.refresh(requirement)
    return requirement


@router.get("/sets/{document_id}/versions", response_model=dict)
async def list_requirement_set_versions(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_document_for_user(db, current_user, document_id)

    versions_result = await db.execute(
        select(RequirementSetVersion)
        .where(RequirementSetVersion.document_id == document_id)
        .order_by(RequirementSetVersion.version_number.desc())
    )
    versions = versions_result.scalars().all()
    return {
        "items": [RequirementSetVersionResponse.model_validate(item) for item in versions],
        "total": len(versions),
    }


@router.post(
    "/sets/{document_id}/versions/clone",
    response_model=RequirementSetVersionResponse,
    status_code=201,
)
async def clone_requirement_set_version(
    document_id: uuid.UUID,
    body: RequirementSetVersionCloneRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    document = await _get_document_for_user(db, current_user, document_id)

    source_version = await _get_version_for_document(db, document_id, body.source_version_id)
    if source_version is None:
        raise HTTPException(status_code=404, detail="Source requirement set version not found")

    max_version_result = await db.execute(
        select(func.max(RequirementSetVersion.version_number)).where(
            RequirementSetVersion.document_id == document_id
        )
    )
    next_version_number = int(max_version_result.scalar() or 0) + 1

    new_version = RequirementSetVersion(
        organization_id=document.organization_id,
        document_id=document.id,
        version_number=next_version_number,
        status="draft",
        is_current=False,
        based_on_version_id=source_version.id,
        change_summary=body.change_summary,
        created_by=current_user.id,
    )
    db.add(new_version)
    await db.flush()

    source_requirements_result = await db.execute(
        select(Requirement)
        .where(Requirement.requirement_set_version_id == source_version.id)
        .order_by(Requirement.sort_order.asc(), Requirement.created_at.asc())
    )
    source_requirements = source_requirements_result.scalars().all()

    if not source_requirements and source_version.version_number == 1:
        legacy_requirements_result = await db.execute(
            select(Requirement)
            .where(
                and_(
                    Requirement.document_id == document.id,
                    Requirement.requirement_set_version_id.is_(None),
                )
            )
            .order_by(Requirement.sort_order.asc(), Requirement.created_at.asc())
        )
        source_requirements = legacy_requirements_result.scalars().all()

    cloned_requirement_ids: dict[uuid.UUID, Requirement] = {}
    for source_requirement in source_requirements:
        cloned_requirement = Requirement(
            organization_id=source_requirement.organization_id,
            jurisdiction_id=source_requirement.jurisdiction_id,
            source_extraction_id=source_requirement.source_extraction_id,
            document_id=source_requirement.document_id,
            requirement_set_version_id=new_version.id,
            source_requirement_id=source_requirement.id,
            reference_id=source_requirement.reference_id,
            title=source_requirement.title,
            text=source_requirement.text,
            requirement_type=source_requirement.requirement_type,
            parent_id=None,
            default_owner_id=source_requirement.default_owner_id,
            active=source_requirement.active,
            version=1,
            sort_order=source_requirement.sort_order,
        )
        db.add(cloned_requirement)
        await db.flush()
        cloned_requirement_ids[source_requirement.id] = cloned_requirement

    for source_requirement in source_requirements:
        if source_requirement.parent_id is None:
            continue
        cloned_requirement = cloned_requirement_ids.get(source_requirement.id)
        cloned_parent = cloned_requirement_ids.get(source_requirement.parent_id)
        if cloned_requirement is not None and cloned_parent is not None:
            cloned_requirement.parent_id = cloned_parent.id

    document.status = "draft"

    await log_action(
        db,
        current_user,
        "clone",
        "requirement_set_version",
        str(new_version.id),
        new_value={
            "document_id": str(document.id),
            "based_on_version_id": str(source_version.id),
            "version_number": new_version.version_number,
            "requirements_cloned": len(source_requirements),
        },
    )
    await db.commit()
    await db.refresh(new_version)
    return new_version


@router.post(
    "/sets/{document_id}/versions/{version_id}/submit",
    response_model=RequirementSetVersionResponse,
)
async def submit_requirement_set_version(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    body: RequirementSetVersionSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    document = await _get_document_for_user(db, current_user, document_id)
    await db.refresh(document, with_for_update=True)
    version = await _get_version_for_document(db, document_id, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Requirement set version not found")
    await db.refresh(version, with_for_update=True)
    if version.status != "draft":
        raise HTTPException(
            status_code=409,
            detail="Only draft requirement set versions can be submitted",
        )

    requirements_count_result = await db.execute(
        select(func.count(Requirement.id)).where(
            and_(
                Requirement.requirement_set_version_id == version.id,
                Requirement.active.is_(True),
            )
        )
    )
    requirements_count = int(requirements_count_result.scalar() or 0)
    if requirements_count <= 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot submit an empty requirement set version",
        )

    await validate_baseline(db, version.id)
    version.status = "pending_approval"
    if body.change_summary is not None:
        version.change_summary = body.change_summary
    document.status = "pending_approval"

    await log_action(
        db,
        current_user,
        "submit",
        "requirement_set_version",
        str(version.id),
        new_value={
            "document_id": str(document.id),
            "version_number": version.version_number,
            "requirements_count": requirements_count,
            "status": version.status,
        },
    )
    await db.commit()
    await db.refresh(version)
    return version


@router.post(
    "/sets/{document_id}/versions/{version_id}/approve",
    response_model=RequirementSetVersionResponse,
)
async def approve_requirement_set_version(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    body: RequirementSetVersionApproveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "approver", "admin")),
):
    document = await _get_document_for_user(db, current_user, document_id)
    await db.refresh(document, with_for_update=True)
    version = await _get_version_for_document(db, document_id, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Requirement set version not found")
    await db.refresh(version, with_for_update=True)
    if version.status != "pending_approval":
        raise HTTPException(
            status_code=409,
            detail="Only pending_approval requirement set versions can be approved",
        )

    requirements_count_result = await db.execute(
        select(func.count(Requirement.id)).where(
            and_(
                Requirement.requirement_set_version_id == version.id,
                Requirement.active.is_(True),
            )
        )
    )
    requirements_count = int(requirements_count_result.scalar() or 0)
    if requirements_count <= 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot approve an empty requirement set version",
        )

    await db.execute(
        update(RequirementSetVersion)
        .where(RequirementSetVersion.document_id == document_id)
        .values(is_current=False)
    )
    now = datetime.now(timezone.utc)
    await validate_baseline(db, version.id)
    version.status = "approved"
    version.is_current = True
    version.approved_by = current_user.id
    version.approved_at = now
    version.locked_at = now

    if body.comment:
        existing_summary = version.change_summary.strip() if version.change_summary else ""
        version.change_summary = (
            f"{existing_summary}\nApproval note: {body.comment}".strip()
            if existing_summary
            else f"Approval note: {body.comment}"
        )

    document.status = "approved"
    document.approved_by = current_user.id
    document.approval_comment = body.comment

    await log_action(
        db,
        current_user,
        "approve",
        "requirement_set_version",
        str(version.id),
        new_value={
            "document_id": str(document.id),
            "version_number": version.version_number,
            "requirements_count": requirements_count,
            "status": version.status,
            "is_current": version.is_current,
        },
    )
    await db.commit()
    await db.refresh(version)
    return version


@router.get("/sets", response_model=dict)
async def list_requirement_sets(
    skip: int = 0,
    limit: int = 500,
    search: Optional[str] = Query(None, description="Search by document name or filename"),
    status: Optional[str] = Query(None, description="Filter by document status"),
    document_type: Optional[str] = Query(None, description="Filter by document type"),
    document_id: Optional[uuid.UUID] = Query(None, description="Filter by document"),
    jurisdiction_id: Optional[uuid.UUID] = Query(None, description="Filter by jurisdiction"),
    include_archived_documents: bool = Query(
        True, description="Include documents that have been archived"
    ),
    include_empty_sets: bool = Query(False, description="Include documents with 0 requirements"),
    include_archived_sets: bool = Query(
        False,
        description="Include requirement sets where all requirements are inactive/archived",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    limit = min(max(limit, 1), 10000)
    skip = max(skip, 0)

    active_count_expr = func.coalesce(func.sum(case((Requirement.active.is_(True), 1), else_=0)), 0)
    total_count_expr = func.count(Requirement.id)
    current_version_subq = (
        select(
            RequirementSetVersion.document_id.label("document_id"),
            RequirementSetVersion.id.label("version_id"),
            RequirementSetVersion.version_number.label("version_number"),
            RequirementSetVersion.status.label("version_status"),
        )
        .where(RequirementSetVersion.is_current.is_(True))
        .subquery()
    )

    def apply_where(q):
        q = apply_org_scope(q, Document, current_user)
        if search:
            term = f"%{search.strip()}%"
            if term != "%%":
                q = q.where(or_(Document.name.ilike(term), Document.filename.ilike(term)))
        if status:
            q = q.where(Document.status == status)
        if document_type:
            q = q.where(Document.document_type == document_type)
        if not include_archived_documents:
            q = q.where(Document.archived_at.is_(None))
        if document_id:
            q = q.where(Document.id == document_id)
        if jurisdiction_id:
            q = q.where(Document.jurisdiction_id == jurisdiction_id)
        return q

    def apply_having(q):
        # Default behavior (include_empty_sets=false, include_archived_sets=false):
        # show only sets with at least 1 active requirement.
        if not include_empty_sets and not include_archived_sets:
            return q.having(active_count_expr > 0)

        # Show empty docs only: include docs with 0 requirements, but still exclude archived sets.
        if include_empty_sets and not include_archived_sets:
            return q.having(or_(active_count_expr > 0, total_count_expr == 0))

        # Show archived sets only: include sets with requirements (active or archived), but exclude empty docs.
        if not include_empty_sets and include_archived_sets:
            return q.having(total_count_expr > 0)

        # Show everything: no HAVING filter.
        return q

    query = (
        select(
            Document.id,
            Document.jurisdiction_id,
            Document.filename,
            Document.name,
            Document.document_type,
            Document.version,
            Document.testing_frequency,
            Document.status,
            Document.archived_at,
            total_count_expr.label("requirements_total"),
            active_count_expr.label("requirements_active"),
            current_version_subq.c.version_id,
            current_version_subq.c.version_number,
            current_version_subq.c.version_status,
            Document.file_path,
        )
        .select_from(Document)
        .outerjoin(current_version_subq, current_version_subq.c.document_id == Document.id)
        .outerjoin(
            Requirement,
            and_(
                Requirement.document_id == Document.id,
                or_(
                    Requirement.requirement_set_version_id == current_version_subq.c.version_id,
                    and_(
                        current_version_subq.c.version_id.is_(None),
                        Requirement.requirement_set_version_id.is_(None),
                    ),
                ),
            ),
        )
        .group_by(
            Document.id,
            current_version_subq.c.version_id,
            current_version_subq.c.version_number,
            current_version_subq.c.version_status,
        )
        .order_by(Document.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    query = apply_where(query)
    query = apply_having(query)

    # Total should reflect the same WHERE/HAVING filters as the result set.
    ids_query = (
        select(Document.id)
        .select_from(Document)
        .outerjoin(current_version_subq, current_version_subq.c.document_id == Document.id)
        .outerjoin(
            Requirement,
            and_(
                Requirement.document_id == Document.id,
                or_(
                    Requirement.requirement_set_version_id == current_version_subq.c.version_id,
                    and_(
                        current_version_subq.c.version_id.is_(None),
                        Requirement.requirement_set_version_id.is_(None),
                    ),
                ),
            ),
        )
        .group_by(Document.id)
    )
    ids_query = apply_where(ids_query)
    ids_query = apply_having(ids_query)
    ids_subq = ids_query.subquery()
    total_result = await db.execute(select(func.count()).select_from(ids_subq))
    total = total_result.scalar() or 0

    result = await db.execute(query)
    rows = result.all()

    items = [
        RequirementSetSummaryResponse(
            document_id=row[0],
            jurisdiction_id=row[1],
            filename=row[2],
            name=row[3],
            document_type=row[4],
            version=row[5],
            testing_frequency=row[6],
            document_status=row[7],
            archived_at=row[8],
            requirements_total=int(row[9] or 0),
            requirements_active=int(row[10] or 0),
            current_version_id=row[11],
            current_version_number=row[12],
            current_version_status=row[13],
            has_source=Document.source_available(row[2], row[14]),
        )
        for row in rows
    ]

    return {"items": items, "total": total}


@router.delete("/sets/{document_id}", status_code=204)
async def hard_delete_requirement_set(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    """Hard-delete a requirement set and all associated data + uploaded files.

    This endpoint is intentionally destructive and is primarily used for cleaning up
    test / mis-imported requirement sets.
    """
    document = await _get_document_for_user(db, current_user, document_id)

    impact = await db.scalar(
        select(ChangeRequirementImpact.id)
        .join(RequirementSetVersion, RequirementSetVersion.id == ChangeRequirementImpact.requirement_set_version_id)
        .where(RequirementSetVersion.document_id == document_id).limit(1)
    )
    if impact:
        raise HTTPException(409, "This requirement set is linked to a change impact. Archive it to retain the change history.")

    published = await db.scalar(select(RequirementSetVersion.id).where(
        RequirementSetVersion.document_id == document_id,
        RequirementSetVersion.status == "approved").limit(1))
    reviewed = await db.scalar(select(ReviewItem.id).join(Requirement,
        Requirement.id == ReviewItem.requirement_id).where(Requirement.document_id == document_id).limit(1))
    project_source = await db.scalar(select(CertificationProject.id).where(
        CertificationProject.source_document_id == document_id).limit(1))
    project_baseline = await db.scalar(select(CertificationProjectRequirementBaseline.document_id).where(
        CertificationProjectRequirementBaseline.document_id == document_id).limit(1))
    if document.status == "approved" or published or reviewed or project_source or project_baseline:
        raise HTTPException(409, "This requirement set is approved or used by a review or certification project. Archive it to retain its source and evidence.")

    old_value = {
        "filename": document.filename,
        "name": document.name,
        "status": document.status,
        "archived_at": document.archived_at.isoformat() if document.archived_at else None,
    }

    # Clear current extraction FK before deleting extraction runs.
    if document.current_extraction_id is not None:
        document.current_extraction_id = None
        await db.flush()

    # Collect requirement IDs for this set.
    req_ids_result = await db.execute(
        select(Requirement.id).where(Requirement.document_id == document_id)
    )
    requirement_ids = req_ids_result.scalars().all()
    version_ids_result = await db.execute(
        select(RequirementSetVersion.id).where(RequirementSetVersion.document_id == document_id)
    )
    version_ids = version_ids_result.scalars().all()

    # Collect extracted requirement IDs for this set (used to null out any stray references).
    extraction_ids_result = await db.execute(
        select(ExtractedRequirement.id).where(ExtractedRequirement.document_id == document_id)
    )
    extraction_ids = extraction_ids_result.scalars().all()

    # Collect extraction run IDs (for counts).
    run_ids_result = await db.execute(
        select(ExtractionRun.id).where(ExtractionRun.document_id == document_id)
    )
    run_ids = run_ids_result.scalars().all()

    # Collect review item IDs linked to this set's requirements.
    review_item_ids: list[uuid.UUID] = []
    if requirement_ids:
        item_ids_result = await db.execute(
            select(ReviewItem.id).where(ReviewItem.requirement_id.in_(requirement_ids))
        )
        review_item_ids = item_ids_result.scalars().all()

    files_to_remove: set[str] = set()
    if document.file_path:
        files_to_remove.add(document.file_path)

    # Queue review-item files for removal after the database commit.
    if review_item_ids:
        ri_files_result = await db.execute(
            select(ReviewItemEvidenceFile).where(
                ReviewItemEvidenceFile.review_item_id.in_(review_item_ids)
            )
        )
        ri_files = ri_files_result.scalars().all()
        files_to_remove.update(file.file_path for file in ri_files if file.file_path)

        await db.execute(
            delete(ReviewItemComment).where(ReviewItemComment.review_item_id.in_(review_item_ids))
        )
        await db.execute(
            delete(ReviewItemEvidenceFile).where(
                ReviewItemEvidenceFile.review_item_id.in_(review_item_ids)
            )
        )
        await db.execute(delete(ReviewItem).where(ReviewItem.id.in_(review_item_ids)))

    # Queue requirement evidence files, then delete their database rows.
    if requirement_ids:
        evidence_files_result = await db.execute(
            select(EvidenceFile).where(EvidenceFile.requirement_id.in_(requirement_ids))
        )
        evidence_files = evidence_files_result.scalars().all()
        files_to_remove.update(file.file_path for file in evidence_files if file.file_path)

        await db.execute(
            delete(EvidenceNote).where(EvidenceNote.requirement_id.in_(requirement_ids))
        )
        await db.execute(
            delete(EvidenceLink).where(EvidenceLink.requirement_id.in_(requirement_ids))
        )
        await db.execute(
            delete(EvidenceFile).where(EvidenceFile.requirement_id.in_(requirement_ids))
        )
        await db.execute(
            delete(RequirementStatus).where(RequirementStatus.requirement_id.in_(requirement_ids))
        )
        await db.execute(delete(Requirement).where(Requirement.id.in_(requirement_ids)))

    if version_ids:
        await db.execute(
            delete(ReviewCycleRequirementBaseline).where(
                ReviewCycleRequirementBaseline.requirement_set_version_id.in_(version_ids)
            )
        )
    await db.execute(
        delete(ReviewCycleRequirementBaseline).where(
            ReviewCycleRequirementBaseline.document_id == document_id
        )
    )
    await db.execute(
        delete(CertificationProjectRequirementBaseline).where(
            CertificationProjectRequirementBaseline.document_id == document_id
        )
    )
    await db.execute(
        update(CertificationProject)
        .where(CertificationProject.source_document_id == document_id)
        .values(source_document_id=None)
    )
    # Quality evidence is document-scoped and must be removed before target versions/runs.
    from app.models.requirement_quality import RequirementQualityRun, RequirementQualityFinding
    quality_ids = select(RequirementQualityRun.id).where(RequirementQualityRun.document_id == document_id)
    await db.execute(delete(RequirementQualityFinding).where(RequirementQualityFinding.run_id.in_(quality_ids)))
    await db.execute(delete(RequirementQualityRun).where(RequirementQualityRun.document_id == document_id))
    await db.execute(
        delete(RequirementSetVersion).where(RequirementSetVersion.document_id == document_id)
    )

    # Null out any remaining requirements that reference this set's extracted requirements.
    if extraction_ids:
        await db.execute(
            Requirement.__table__.update()
            .where(Requirement.source_extraction_id.in_(extraction_ids))
            .values(source_extraction_id=None)
        )

    # Feedback and diagnostics refer to extraction rows without cascading deletes.
    # Remove them before their extracted requirements and runs.
    if run_ids or extraction_ids:
        await db.execute(
            delete(ExtractionFeedback).where(
                or_(
                    ExtractionFeedback.extraction_run_id.in_(run_ids),
                    ExtractionFeedback.extracted_requirement_id.in_(extraction_ids),
                )
            )
        )
    await db.execute(
        delete(ExtractionRunDiagnostic).where(ExtractionRunDiagnostic.document_id == document_id)
    )

    # Delete extraction artifacts.
    await db.execute(
        delete(ExtractedRequirement).where(ExtractedRequirement.document_id == document_id)
    )
    await db.execute(delete(ExtractionRun).where(ExtractionRun.document_id == document_id))

    await log_action(
        db,
        current_user,
        "delete",
        "requirements_set",
        str(document.id),
        old_value=old_value,
        new_value={
            "requirements_deleted": len(requirement_ids),
            "review_items_deleted": len(review_item_ids),
            "extracted_requirements_deleted": len(extraction_ids),
            "extraction_runs_deleted": len(run_ids),
            "requirement_set_versions_deleted": len(version_ids),
            "files_queued_for_removal": len(files_to_remove),
        },
    )

    await db.delete(document)
    await db.commit()

    # Keep files intact if any database operation fails and rolls back.
    for file_path in files_to_remove:
        try:
            os.remove(file_path)
        except OSError:
            pass


@router.get("", response_model=dict)
async def list_requirements(
    skip: int = 0,
    limit: int = 20,
    status: Optional[str] = Query(None, description="Filter by current status"),
    document_id: Optional[str] = Query(None, description="Filter by document"),
    requirement_set_version_id: Optional[uuid.UUID] = Query(
        None, description="Filter by requirement set version"
    ),
    assigned_to: Optional[str] = Query(None, description="Filter by assigned user"),
    search: Optional[str] = Query(None, description="Search in text and reference_id"),
    active_only: bool = Query(True, description="Only show active requirements"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assigned_to_uuid: Optional[uuid.UUID] = None
    document_id_uuid: Optional[uuid.UUID] = None
    if assigned_to:
        try:
            assigned_to_uuid = uuid.UUID(assigned_to)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid assigned_to UUID")
    if document_id:
        try:
            document_id_uuid = uuid.UUID(document_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid document_id UUID")
        await _get_document_for_user(db, current_user, document_id_uuid)

    latest_status_subq = select(
        RequirementStatus.requirement_id.label("requirement_id"),
        RequirementStatus.status.label("status"),
        RequirementStatus.assigned_to.label("assigned_to"),
        RequirementStatus.changed_at.label("changed_at"),
        func.row_number()
        .over(
            partition_by=RequirementStatus.requirement_id,
            order_by=RequirementStatus.changed_at.desc(),
        )
        .label("rn"),
    ).subquery()

    join_condition = and_(
        Requirement.id == latest_status_subq.c.requirement_id,
        latest_status_subq.c.rn == 1,
    )

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

    # Build base query
    query = (
        select(
            Requirement,
            latest_status_subq.c.status,
            latest_status_subq.c.assigned_to,
            notes_subq.c.notes_count,
            files_subq.c.files_count,
            links_subq.c.links_count,
        )
        .outerjoin(latest_status_subq, join_condition)
        .outerjoin(notes_subq, Requirement.id == notes_subq.c.requirement_id)
        .outerjoin(files_subq, Requirement.id == files_subq.c.requirement_id)
        .outerjoin(links_subq, Requirement.id == links_subq.c.requirement_id)
    )
    count_query = (
        select(func.count(Requirement.id))
        .select_from(Requirement)
        .outerjoin(latest_status_subq, join_condition)
    )
    query = apply_org_scope(query, Requirement, current_user)
    count_query = apply_org_scope(count_query, Requirement, current_user)

    if active_only:
        query = query.where(Requirement.active.is_(True))
        count_query = count_query.where(Requirement.active.is_(True))

    if requirement_set_version_id is not None:
        query = query.where(Requirement.requirement_set_version_id == requirement_set_version_id)
        count_query = count_query.where(
            Requirement.requirement_set_version_id == requirement_set_version_id
        )
    elif document_id_uuid is not None:
        selected_version: Optional[uuid.UUID] = None
        draft_version_result = await db.execute(
            select(RequirementSetVersion.id)
            .where(
                and_(
                    RequirementSetVersion.document_id == document_id_uuid,
                    RequirementSetVersion.status == "draft",
                )
            )
            .order_by(RequirementSetVersion.version_number.desc())
            .limit(1)
        )
        draft_version_id = draft_version_result.scalar_one_or_none()
        if draft_version_id is not None:
            draft_requirement_count_result = await db.execute(
                select(func.count(Requirement.id)).where(
                    Requirement.requirement_set_version_id == draft_version_id
                )
            )
            draft_requirement_count = int(draft_requirement_count_result.scalar() or 0)
            if draft_requirement_count > 0:
                selected_version = draft_version_id

        if selected_version is None:
            current_version_result = await db.execute(
                select(RequirementSetVersion.id).where(
                    and_(
                        RequirementSetVersion.document_id == document_id_uuid,
                        RequirementSetVersion.is_current.is_(True),
                    )
                )
            )
            selected_version = current_version_result.scalar_one_or_none()

        if selected_version is not None:
            query = query.where(Requirement.requirement_set_version_id == selected_version)
            count_query = count_query.where(
                Requirement.requirement_set_version_id == selected_version
            )
        else:
            query = query.where(Requirement.document_id == document_id_uuid)
            count_query = count_query.where(Requirement.document_id == document_id_uuid)

    if search:
        search_filter = Requirement.text.ilike(f"%{search}%") | Requirement.reference_id.ilike(
            f"%{search}%"
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    if status:
        query = query.where(latest_status_subq.c.status == status)
        count_query = count_query.where(latest_status_subq.c.status == status)

    if assigned_to_uuid:
        query = query.where(latest_status_subq.c.assigned_to == assigned_to_uuid)
        count_query = count_query.where(latest_status_subq.c.assigned_to == assigned_to_uuid)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    query = query.order_by(Requirement.sort_order).offset(skip).limit(limit)
    result = await db.execute(query)
    rows = result.all()

    items = []
    for req, current_status, current_assigned_to, notes_count, files_count, links_count in rows:
        item = RequirementWithStatusResponse(
            **RequirementResponse.model_validate(req).model_dump(),
            current_status=current_status,
            assigned_to=current_assigned_to,
            evidence_counts=EvidenceCounts(
                notes=notes_count or 0,
                files=files_count or 0,
                links=links_count or 0,
            ),
        )
        items.append(item)

    return {"items": items, "total": total}


@router.get("/{requirement_id}", response_model=RequirementWithStatusResponse)
async def get_requirement(
    requirement_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    requirement = await _get_requirement_for_user(db, current_user, requirement_id)

    # Get status history
    status_result = await db.execute(
        select(RequirementStatus)
        .where(RequirementStatus.requirement_id == requirement.id)
        .order_by(RequirementStatus.changed_at.desc())
    )
    status_history = status_result.scalars().all()

    latest_status = status_history[0] if status_history else None

    return RequirementWithStatusResponse(
        **RequirementResponse.model_validate(requirement).model_dump(),
        current_status=latest_status.status if latest_status else None,
        assigned_to=latest_status.assigned_to if latest_status else None,
        status_history=[RequirementStatusResponse.model_validate(s) for s in status_history],
    )


@router.put("/{requirement_id}/status", response_model=RequirementWithStatusResponse)
async def change_status(
    requirement_id: uuid.UUID,
    body: StatusChangeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    requirement = await _get_requirement_for_user(db, current_user, requirement_id)

    # Check for special status requiring elevated permissions
    if body.status == "not_applicable":
        if current_user.role not in ["manager", "approver", "admin"]:
            raise HTTPException(
                status_code=403,
                detail="Only approvers, managers, or admins can mark requirements as not applicable",
            )

    # Get current status to preserve assigned_to
    current_result = await db.execute(
        select(RequirementStatus)
        .where(RequirementStatus.requirement_id == requirement.id)
        .order_by(RequirementStatus.changed_at.desc())
        .limit(1)
    )
    current_status = current_result.scalar_one_or_none()

    # Create new status entry
    new_status = RequirementStatus(
        requirement_id=requirement.id,
        status=body.status,
        assigned_to=current_status.assigned_to if current_status else None,
        comment=body.comment,
        changed_by=current_user.id,
        changed_at=datetime.now(timezone.utc),
    )
    db.add(new_status)

    await log_action(
        db,
        current_user,
        "status_change",
        "requirement",
        str(requirement.id),
        old_value={"status": current_status.status if current_status else None},
        new_value={"status": body.status, "comment": body.comment},
    )
    await db.commit()

    return await get_requirement(requirement_id, db, current_user)


@router.put("/{requirement_id}/assign", response_model=RequirementWithStatusResponse)
async def assign_requirement(
    requirement_id: uuid.UUID,
    body: AssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    requirement = await _get_requirement_for_user(db, current_user, requirement_id)
    await get_active_user_in_org_or_404(
        db,
        body.assigned_to,
        current_user,
        detail="Assigned user not found",
    )

    # Get current status
    current_result = await db.execute(
        select(RequirementStatus)
        .where(RequirementStatus.requirement_id == requirement.id)
        .order_by(RequirementStatus.changed_at.desc())
        .limit(1)
    )
    current_status = current_result.scalar_one_or_none()

    # Create new status entry with assignment
    new_status = RequirementStatus(
        requirement_id=requirement.id,
        status=current_status.status if current_status else "not_started",
        assigned_to=body.assigned_to,
        comment=body.comment,
        changed_by=current_user.id,
        changed_at=datetime.now(timezone.utc),
    )
    db.add(new_status)

    await log_action(
        db,
        current_user,
        "assign",
        "requirement",
        str(requirement.id),
        old_value={
            "assigned_to": (
                str(current_status.assigned_to)
                if current_status and current_status.assigned_to
                else None
            )
        },
        new_value={"assigned_to": str(body.assigned_to), "comment": body.comment},
    )
    await db.commit()

    return await get_requirement(requirement_id, db, current_user)


@router.delete("/by-document/{document_id}", status_code=204)
async def delete_requirements_by_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    document = await _get_document_for_user(db, current_user, document_id)

    published = await db.scalar(select(RequirementSetVersion.id).where(
        RequirementSetVersion.document_id == document_id,
        RequirementSetVersion.status == "approved",
    ).limit(1))
    reviewed = await db.scalar(select(ReviewItem.id).join(
        Requirement, Requirement.id == ReviewItem.requirement_id,
    ).where(Requirement.document_id == document_id).limit(1))
    project_source = await db.scalar(select(CertificationProject.id).where(
        CertificationProject.source_document_id == document_id,
    ).limit(1))
    project_baseline = await db.scalar(select(CertificationProjectRequirementBaseline.document_id).where(
        CertificationProjectRequirementBaseline.document_id == document_id,
    ).limit(1))
    if document.status == "approved" or published or reviewed or project_source or project_baseline:
        raise HTTPException(409, "This requirement set is approved or used by a review or certification project. Archive it to retain its source and evidence.")

    extraction_ids_result = await db.execute(
        select(ExtractedRequirement.id).where(ExtractedRequirement.document_id == document_id)
    )
    extraction_ids = [row[0] for row in extraction_ids_result.all()]

    req_result = await db.execute(
        select(Requirement.id).where(
            (Requirement.document_id == document_id)
            | (Requirement.source_extraction_id.in_(extraction_ids) if extraction_ids else False)
        )
    )
    requirement_ids = [row[0] for row in req_result.all()]

    if not requirement_ids:
        raise HTTPException(status_code=404, detail="No requirements found for document")

    await db.execute(delete(EvidenceNote).where(EvidenceNote.requirement_id.in_(requirement_ids)))
    await db.execute(delete(EvidenceFile).where(EvidenceFile.requirement_id.in_(requirement_ids)))
    await db.execute(delete(EvidenceLink).where(EvidenceLink.requirement_id.in_(requirement_ids)))
    await db.execute(
        delete(RequirementStatus).where(RequirementStatus.requirement_id.in_(requirement_ids))
    )
    await db.execute(delete(ReviewItem).where(ReviewItem.requirement_id.in_(requirement_ids)))
    await db.execute(delete(Requirement).where(Requirement.id.in_(requirement_ids)))

    await log_action(
        db,
        current_user,
        "delete",
        "requirements_set",
        str(document_id),
        old_value={"requirements_count": len(requirement_ids)},
    )
    await db.commit()


@router.post("/by-document/{document_id}/archive", response_model=dict)
async def archive_requirements_by_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    await _get_document_for_user(db, current_user, document_id)

    req_result = await db.execute(
        select(Requirement.id).where(Requirement.document_id == document_id)
    )
    requirement_ids = [row[0] for row in req_result.all()]

    if not requirement_ids:
        raise HTTPException(status_code=404, detail="No requirements found for document")

    await db.execute(
        update(Requirement).where(Requirement.id.in_(requirement_ids)).values(active=False)
    )

    await log_action(
        db,
        current_user,
        "archive",
        "requirements_set",
        str(document_id),
        old_value={"requirements_count": len(requirement_ids), "active": True},
        new_value={"active": False},
    )
    await db.commit()

    return {"archived": len(requirement_ids)}


@router.post("/by-document/{document_id}/restore", response_model=dict)
async def restore_requirements_by_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    await _get_document_for_user(db, current_user, document_id)

    req_result = await db.execute(
        select(Requirement.id).where(Requirement.document_id == document_id)
    )
    requirement_ids = [row[0] for row in req_result.all()]

    if not requirement_ids:
        raise HTTPException(status_code=404, detail="No requirements found for document")

    await db.execute(
        update(Requirement).where(Requirement.id.in_(requirement_ids)).values(active=True)
    )

    await log_action(
        db,
        current_user,
        "restore",
        "requirements_set",
        str(document_id),
        old_value={"requirements_count": len(requirement_ids), "active": False},
        new_value={"active": True},
    )
    await db.commit()

    return {"restored": len(requirement_ids)}


@router.put("/{requirement_id}", response_model=RequirementResponse)
async def update_requirement(
    requirement_id: uuid.UUID,
    body: RequirementUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    requirement = await _get_requirement_for_user(db, current_user, requirement_id)
    await _ensure_mutable_requirement(db, requirement)

    old_value = {
        "reference_id": requirement.reference_id,
        "title": requirement.title,
        "text": requirement.text,
        "requirement_type": requirement.requirement_type,
        "parent_id": str(requirement.parent_id) if requirement.parent_id else None,
        "default_owner_id": (
            str(requirement.default_owner_id) if requirement.default_owner_id else None
        ),
    }

    fields_set = body.model_fields_set
    reference_changed = False
    if "reference_id" in fields_set:
        try:
            requirement.reference_id = normalize_reference_or_raise(
                body.reference_id,
                detail="reference_id cannot be empty",
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        reference_changed = True
    if "title" in fields_set:
        requirement.title = body.title
    if "text" in fields_set:
        requirement.text = body.text or ""
    if "requirement_type" in fields_set:
        requirement.requirement_type = body.requirement_type or requirement.requirement_type
    if "default_owner_id" in fields_set:
        await get_active_user_in_org_or_404(
            db,
            body.default_owner_id,
            current_user,
            detail="Default owner not found",
        )
        requirement.default_owner_id = body.default_owner_id
    if reference_changed or body.sync_parent_from_reference is True:
        requirement.parent_id = await resolve_requirement_parent_id(
            db,
            requirement_set_version_id=requirement.requirement_set_version_id,
            reference_id=requirement.reference_id,
            exclude_requirement_id=requirement.id,
        )

    requirement.version += 1

    new_value = {
        "reference_id": requirement.reference_id,
        "title": requirement.title,
        "text": requirement.text,
        "requirement_type": requirement.requirement_type,
        "parent_id": str(requirement.parent_id) if requirement.parent_id else None,
        "default_owner_id": (
            str(requirement.default_owner_id) if requirement.default_owner_id else None
        ),
        "version": requirement.version,
    }

    await log_action(
        db, current_user, "update", "requirement", str(requirement.id), old_value, new_value
    )
    await db.commit()
    await db.refresh(requirement)
    return requirement


@router.put("/{requirement_id}/deactivate", response_model=RequirementResponse)
async def deactivate_requirement(
    requirement_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    requirement = await _get_requirement_for_user(db, current_user, requirement_id)
    await _ensure_mutable_requirement(db, requirement)

    requirement.active = False
    await log_action(
        db,
        current_user,
        "deactivate",
        "requirement",
        str(requirement.id),
        old_value={"active": True},
        new_value={"active": False},
    )
    await db.commit()
    await db.refresh(requirement)
    return requirement


@router.put("/{requirement_id}/reactivate", response_model=RequirementResponse)
async def reactivate_requirement(
    requirement_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    requirement = await _get_requirement_for_user(db, current_user, requirement_id)
    await _ensure_mutable_requirement(db, requirement)

    requirement.active = True
    await log_action(
        db,
        current_user,
        "reactivate",
        "requirement",
        str(requirement.id),
        old_value={"active": False},
        new_value={"active": True},
    )
    await db.commit()
    await db.refresh(requirement)
    return requirement
