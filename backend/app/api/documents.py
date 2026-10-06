import os
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.api.tenant import apply_org_scope, get_org_owned_or_404
from app.config import settings
from app.services.pdf_parser import NATIVE_PIPELINE_VERSION
from app.database import get_db
from app.models.document import Document
from app.models.extraction import ExtractionRun, ExtractionRunDiagnostic
from app.models.jurisdiction import Jurisdiction
from app.models.program import RequirementSetVersion
from app.models.requirement import (
    ExtractionFeedback,
    ExtractedRequirement,
    Requirement,
    RequirementStatus,
)
from app.models.user import User
from app.schemas.document import (
    DocumentResponse,
    DocumentWithExtractionResponse,
    DocumentMetadataUpdate,
    ExtractionBatchDistributionItem,
    ExtractionFeedbackCreate,
    ExtractionFeedbackBatchRequest,
    ExtractionFeedbackBatchResponse,
    ExtractionFeedbackBatchFailure,
    ExtractionFeedbackBatchDistributions,
    ExtractionFeedbackResponse,
    ExtractionBatchRequest,
    ExtractionBatchResult,
    ExtractionReorderRequest,
    ExtractionReorderResponse,
    ExtractedRequirementResponse,
    ExtractedRequirementUpdate,
)
from app.schemas.extraction import (
    ExtractionProgressResponse,
    ExtractionRunDiagnosticsResponse,
    ExtractionRunResponse,
)
from app.services.source_validation import validate_baseline, validate_extraction_complete
from app.services.audit import log_action
from app.services.extraction_events import stream_events
from app.services.file_utils import save_upload_file
from app.services.maintenance import frequency_to_days
from app.services.reference_hierarchy import (
    normalize_reference_or_raise,
    resolve_extracted_requirement_parent_id,
)

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


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
        detail="Document not found",
    )


async def _lock_document_for_extraction_edit(
    db: AsyncSession, current_user: User, document_id: uuid.UUID,
) -> Document:
    document = await _get_document_for_user(db, current_user, document_id)
    # Recovery, submission, approval and extraction reruns use this row lock.
    # Refresh after waiting so an edit cannot apply a stale review decision.
    await db.refresh(document, with_for_update=True)
    return document


async def _lock_current_extraction_for_edit(
    db: AsyncSession, current_user: User, document_id: uuid.UUID,
) -> Document:
    document = await _lock_document_for_extraction_edit(db, current_user, document_id)
    if document.status not in {"extracted", "reviewed", "draft", "changes_requested"}:
        raise HTTPException(409, "This document is not an editable draft.")
    if not document.current_extraction_id:
        raise HTTPException(409, "This document has no current extraction run.")
    run = await db.get(ExtractionRun, document.current_extraction_id)
    if not run or run.document_id != document.id or run.status != "completed":
        raise HTTPException(409, "A completed current extraction run is required.")
    return document


def _require_current_extraction(document: Document, extraction: ExtractedRequirement) -> None:
    if extraction.extraction_run_id != document.current_extraction_id:
        raise HTTPException(409, "Extraction is not part of the current run.")


def _section_prefix_from_reference(reference_id: Optional[str]) -> str:
    normalized = (reference_id or "").strip().lower()
    if not normalized:
        return "unknown"
    first_token = normalized.split()[0]
    if not first_token:
        return "unknown"
    if "." in first_token:
        prefix = first_token.split(".", 1)[0]
        return prefix or "unknown"
    return first_token


def _confidence_band(value: float) -> str:
    if value < 0.50:
        return "0.00-0.49"
    if value < 0.75:
        return "0.50-0.74"
    return "0.75-1.00"


def _to_distribution(counter: Counter[str]) -> list[ExtractionBatchDistributionItem]:
    return [
        ExtractionBatchDistributionItem(key=key, total=total)
        for key, total in sorted(counter.items(), key=lambda item: item[0])
    ]


async def _get_or_create_draft_version(
    db: AsyncSession,
    document: Document,
    created_by: uuid.UUID,
) -> RequirementSetVersion:
    existing_result = await db.execute(
        select(RequirementSetVersion)
        .where(RequirementSetVersion.document_id == document.id)
        .order_by(RequirementSetVersion.version_number.desc())
        .limit(1)
    )
    existing = existing_result.scalar_one_or_none()
    if existing is None:
        version = RequirementSetVersion(
            organization_id=document.organization_id,
            document_id=document.id,
            version_number=1,
            status="draft",
            is_current=True,
            created_by=created_by,
        )
        db.add(version)
        await db.flush()
        return version

    if existing.status == "draft":
        return existing

    new_version = RequirementSetVersion(
        organization_id=document.organization_id,
        document_id=document.id,
        version_number=existing.version_number + 1,
        status="draft",
        is_current=False,
        based_on_version_id=existing.id,
        created_by=created_by,
    )
    db.add(new_version)
    await db.flush()
    await _clone_requirements_to_version(
        db,
        document_id=document.id,
        source_version_id=existing.id,
        target_version_id=new_version.id,
    )
    return new_version


async def _clone_requirements_to_version(
    db: AsyncSession,
    document_id: uuid.UUID,
    source_version_id: uuid.UUID,
    target_version_id: uuid.UUID,
) -> int:
    source_requirements_result = await db.execute(
        select(Requirement)
        .where(Requirement.requirement_set_version_id == source_version_id)
        .order_by(Requirement.sort_order.asc(), Requirement.created_at.asc())
    )
    source_requirements = source_requirements_result.scalars().all()

    if not source_requirements:
        legacy_requirements_result = await db.execute(
            select(Requirement)
            .where(
                and_(
                    Requirement.document_id == document_id,
                    Requirement.requirement_set_version_id.is_(None),
                )
            )
            .order_by(Requirement.sort_order.asc(), Requirement.created_at.asc())
        )
        source_requirements = legacy_requirements_result.scalars().all()

    cloned_by_source_id: dict[uuid.UUID, Requirement] = {}
    for source_requirement in source_requirements:
        cloned_requirement = Requirement(
            organization_id=source_requirement.organization_id,
            jurisdiction_id=source_requirement.jurisdiction_id,
            source_extraction_id=source_requirement.source_extraction_id,
            document_id=source_requirement.document_id,
            requirement_set_version_id=target_version_id,
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
        cloned_by_source_id[source_requirement.id] = cloned_requirement

    for source_requirement in source_requirements:
        if source_requirement.parent_id is None:
            continue
        cloned_requirement = cloned_by_source_id.get(source_requirement.id)
        cloned_parent = cloned_by_source_id.get(source_requirement.parent_id)
        if cloned_requirement is not None and cloned_parent is not None:
            cloned_requirement.parent_id = cloned_parent.id

    return len(source_requirements)


async def _ensure_extracted_requirements_in_version(
    db: AsyncSession,
    document: Document,
    version: RequirementSetVersion,
    changed_by: uuid.UUID,
    comment: str,
) -> int:
    existing_count_result = await db.execute(
        select(func.count(Requirement.id)).where(
            Requirement.requirement_set_version_id == version.id
        )
    )
    existing_count = int(existing_count_result.scalar() or 0)
    if existing_count > 0:
        return existing_count

    if not document.current_extraction_id:
        return 0

    extractions_result = await db.execute(
        select(ExtractedRequirement)
        .where(
            and_(
                ExtractedRequirement.document_id == document.id,
                ExtractedRequirement.extraction_run_id == document.current_extraction_id,
                ExtractedRequirement.status != "rejected",
            )
        )
        .order_by(ExtractedRequirement.sort_order.asc(), ExtractedRequirement.created_at.asc())
    )
    extractions = extractions_result.scalars().all()
    extracted_to_requirement: dict[uuid.UUID, Requirement] = {}

    for ext in extractions:
        requirement = Requirement(
            organization_id=document.organization_id,
            source_extraction_id=ext.id,
            jurisdiction_id=document.jurisdiction_id,
            document_id=document.id,
            requirement_set_version_id=version.id,
            reference_id=ext.reference_id,
            title=ext.title,
            text=ext.text,
            requirement_type=ext.requirement_type,
            parent_id=None,
            sort_order=ext.sort_order,
        )
        db.add(requirement)
        await db.flush()
        extracted_to_requirement[ext.id] = requirement

        status_entry = RequirementStatus(
            requirement_id=requirement.id,
            status="not_started",
            comment=comment,
            changed_by=changed_by,
            changed_at=datetime.now(timezone.utc),
        )
        db.add(status_entry)

    # Resolve the complete graph after insertion, independent of display/source order.
    for ext in extractions:
        if ext.parent_id is not None:
            parent = extracted_to_requirement.get(ext.parent_id)
            if parent is None:
                raise HTTPException(422, f"{ext.reference_id}: restore or reparent the excluded parent before approval")
            extracted_to_requirement[ext.id].parent_id = parent.id
    await db.flush()
    return len(extractions)


@router.post("", response_model=DocumentResponse, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    document_type: str = Form(..., min_length=1, max_length=50),
    jurisdiction_id: uuid.UUID = Form(...),
    name: Optional[str] = Form(None),
    version: Optional[str] = Form(None),
    testing_frequency: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    if file.content_type and file.content_type not in {"application/pdf", "application/x-pdf"}:
        raise HTTPException(status_code=400, detail="Invalid PDF content type")

    document_type = document_type.strip()
    if not document_type:
        raise HTTPException(422, "Document category is required")

    # Sanitize filename
    safe_filename = "".join(c for c in file.filename if c.isalnum() or c in "._- ")
    unique_filename = f"{uuid.uuid4()}_{safe_filename}"

    jurisdiction_result = await db.execute(
        select(Jurisdiction).where(Jurisdiction.id == jurisdiction_id)
    )
    jurisdiction = jurisdiction_result.scalar_one_or_none()
    if jurisdiction is None:
        raise HTTPException(status_code=400, detail="Invalid jurisdiction_id")
    if not jurisdiction.active:
        raise HTTPException(status_code=400, detail="Jurisdiction is inactive")

    os.makedirs(settings.upload_dir, exist_ok=True)
    file_path = os.path.join(settings.upload_dir, unique_filename)
    max_bytes = settings.max_document_upload_mb * 1024 * 1024
    await save_upload_file(file, file_path, max_bytes, enforce_pdf_header=True)

    document = Document(
        organization_id=current_user.organization_id,
        jurisdiction_id=jurisdiction_id,
        filename=file.filename,
        name=name.strip() if name else None,
        document_type=document_type,
        version=version,
        status="uploaded",
        file_path=file_path,
        uploaded_by=current_user.id,
        testing_frequency=testing_frequency.strip() if testing_frequency else None,
        cadence_interval_days=frequency_to_days(testing_frequency),
    )
    db.add(document)
    await log_action(
        db,
        current_user,
        "create",
        "document",
        str(document.id),
        new_value={"filename": document.filename, "document_type": document.document_type},
    )
    await db.commit()
    await db.refresh(document)
    return document


@router.get("", response_model=dict)
async def list_documents(
    skip: int = 0,
    limit: int = 20,
    status_filter: Optional[str] = None,
    document_type: Optional[str] = None,
    jurisdiction_id: Optional[uuid.UUID] = None,
    include_archived: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = apply_org_scope(select(Document), Document, current_user)
    count_query = apply_org_scope(select(func.count(Document.id)), Document, current_user)

    if not include_archived:
        query = query.where(Document.archived_at.is_(None))
        count_query = count_query.where(Document.archived_at.is_(None))

    if status_filter:
        query = query.where(Document.status == status_filter)
        count_query = count_query.where(Document.status == status_filter)
    if document_type:
        query = query.where(Document.document_type == document_type)
        count_query = count_query.where(Document.document_type == document_type)
    if jurisdiction_id:
        query = query.where(Document.jurisdiction_id == jurisdiction_id)
        count_query = count_query.where(Document.jurisdiction_id == jurisdiction_id)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    query = query.order_by(Document.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    documents = result.scalars().all()

    # Fetch current extraction runs for documents that have them
    doc_ids_with_extraction = [d.id for d in documents if d.current_extraction_id]
    extraction_runs = {}
    if doc_ids_with_extraction:
        runs_result = await db.execute(
            select(ExtractionRun).where(
                ExtractionRun.id.in_(
                    [d.current_extraction_id for d in documents if d.current_extraction_id]
                )
            )
        )
        for run in runs_result.scalars().all():
            extraction_runs[run.id] = run

    # Build response with extraction info
    items = []
    for doc in documents:
        doc_dict = DocumentWithExtractionResponse.model_validate(doc).model_dump()
        if doc.current_extraction_id and doc.current_extraction_id in extraction_runs:
            doc_dict["current_extraction"] = ExtractionRunResponse.model_validate(
                extraction_runs[doc.current_extraction_id]
            ).model_dump()
        else:
            doc_dict["current_extraction"] = None
        items.append(doc_dict)

    return {"items": items, "total": total}


@router.get("/{document_id}/source")
async def view_source_pdf(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = await _get_document_for_user(db, current_user, document_id)
    if not document.has_source:
        raise HTTPException(404, "This requirement set has no source PDF.")
    if not os.path.isfile(document.file_path):
        raise HTTPException(
            404, "The source PDF is missing. Ask the installation operator to restore it."
        )
    return FileResponse(
        document.file_path,
        media_type="application/pdf",
        filename=document.filename,
        content_disposition_type="inline",
        headers={"Cache-Control": "private, no-store"},
    )


@router.get("/{document_id}", response_model=DocumentWithExtractionResponse)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = await _get_document_for_user(db, current_user, document_id)

    # Load current extraction if exists
    current_extraction = None
    if document.current_extraction_id:
        run_result = await db.execute(
            select(ExtractionRun).where(ExtractionRun.id == document.current_extraction_id)
        )
        current_extraction = run_result.scalar_one_or_none()

    response = DocumentWithExtractionResponse.model_validate(document).model_dump()
    response["current_extraction"] = (
        ExtractionRunResponse.model_validate(current_extraction).model_dump()
        if current_extraction
        else None
    )
    return response


@router.put("/{document_id}", response_model=DocumentResponse)
async def update_document_metadata(
    document_id: uuid.UUID,
    body: DocumentMetadataUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "approver", "admin")),
):
    document = await _get_document_for_user(db, current_user, document_id)

    old_value = {
        "name": document.name,
        "document_type": document.document_type,
        "version": document.version,
        "effective_date": document.effective_date.isoformat() if document.effective_date else None,
        "testing_frequency": document.testing_frequency,
    }

    # Use `model_fields_set` so callers can explicitly clear optional fields by sending `null`.
    if "name" in body.model_fields_set:
        document.name = body.name.strip() if body.name and body.name.strip() else None
    if "document_type" in body.model_fields_set:
        if body.document_type is None:
            raise HTTPException(status_code=400, detail="document_type cannot be null")
        document_type = body.document_type.strip()
        if not document_type:
            raise HTTPException(status_code=400, detail="document_type cannot be empty")
        document.document_type = document_type
    if "version" in body.model_fields_set:
        document.version = body.version.strip() if body.version and body.version.strip() else None
    if "effective_date" in body.model_fields_set:
        document.effective_date = body.effective_date
    if "testing_frequency" in body.model_fields_set:
        document.testing_frequency = (
            body.testing_frequency.strip()
            if body.testing_frequency and body.testing_frequency.strip()
            else None
        )

    new_value = {
        "name": document.name,
        "document_type": document.document_type,
        "version": document.version,
        "effective_date": document.effective_date.isoformat() if document.effective_date else None,
        "testing_frequency": document.testing_frequency,
    }

    await log_action(
        db,
        current_user,
        "update",
        "document",
        str(document.id),
        old_value=old_value,
        new_value=new_value,
    )
    await db.commit()
    await db.refresh(document)
    return document


@router.get("/{document_id}/extraction-runs", response_model=dict)
async def list_extraction_runs(
    document_id: uuid.UUID,
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all extraction runs for a document."""
    await _get_document_for_user(db, current_user, document_id)

    count_query = select(func.count(ExtractionRun.id)).where(
        ExtractionRun.document_id == document_id
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    query = (
        select(ExtractionRun)
        .where(ExtractionRun.document_id == document_id)
        .order_by(ExtractionRun.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(query)
    runs = result.scalars().all()

    return {
        "items": [ExtractionRunResponse.model_validate(r) for r in runs],
        "total": total,
    }


@router.get("/{document_id}/extraction-progress", response_model=ExtractionProgressResponse)
async def get_extraction_progress(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get lightweight progress info for the current extraction."""
    document = await _get_document_for_user(db, current_user, document_id)

    if not document.current_extraction_id:
        raise HTTPException(status_code=404, detail="No active extraction")

    run_result = await db.execute(
        select(ExtractionRun).where(ExtractionRun.id == document.current_extraction_id)
    )
    run = run_result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Extraction run not found")

    return ExtractionProgressResponse.model_validate(run)


@router.get("/{document_id}/extraction-runs/{run_id}/events/stream")
async def stream_extraction_events(
    document_id: uuid.UUID,
    run_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_document_for_user(db, current_user, document_id)

    run_result = await db.execute(select(ExtractionRun).where(ExtractionRun.id == run_id))
    run = run_result.scalar_one_or_none()
    if run is None or run.document_id != document_id:
        raise HTTPException(status_code=404, detail="Extraction run not found")

    async def event_generator():
        async for payload in stream_events(str(run_id)):
            if await request.is_disconnected():
                break
            if payload:
                yield f"data: {payload}\n\n"
            else:
                yield ": ping\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=headers,
    )


@router.get("/{document_id}/extraction-runs/{run_id}", response_model=ExtractionRunResponse)
async def get_extraction_run(
    document_id: uuid.UUID,
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get details of a specific extraction run."""
    await _get_document_for_user(db, current_user, document_id)

    result = await db.execute(
        select(ExtractionRun).where(
            ExtractionRun.id == run_id,
            ExtractionRun.document_id == document_id,
        )
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Extraction run not found")

    return ExtractionRunResponse.model_validate(run)


@router.get(
    "/{document_id}/extraction-runs/{run_id}/diagnostics",
    response_model=ExtractionRunDiagnosticsResponse,
)
async def get_extraction_run_diagnostics(
    document_id: uuid.UUID,
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_document_for_user(db, current_user, document_id)

    run_result = await db.execute(
        select(ExtractionRun).where(
            ExtractionRun.id == run_id,
            ExtractionRun.document_id == document_id,
        )
    )
    run = run_result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Extraction run not found")

    diag_result = await db.execute(
        select(ExtractionRunDiagnostic).where(
            ExtractionRunDiagnostic.extraction_run_id == run_id,
            ExtractionRunDiagnostic.document_id == document_id,
        )
    )
    diagnostics = diag_result.scalar_one_or_none()
    if diagnostics is None:
        raise HTTPException(status_code=404, detail="Extraction diagnostics not found")

    return ExtractionRunDiagnosticsResponse.model_validate(
        {
            "extraction_run_id": diagnostics.extraction_run_id,
            "document_id": diagnostics.document_id,
            "parseability_score": diagnostics.parseability_score,
            "fallback_trigger_reason": diagnostics.fallback_trigger_reason,
            "strategy_counts": diagnostics.strategy_counts,
            "decision_payload": diagnostics.decision_payload,
            "page_metrics": diagnostics.page_metrics,
            "canonical_blocks": diagnostics.canonical_blocks,
            "created_at": diagnostics.created_at,
        }
    )


@router.post("/{document_id}/extraction-runs/{run_id}/cancel", response_model=ExtractionRunResponse)
async def cancel_extraction_run(
    document_id: uuid.UUID,
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    document = await _get_document_for_user(db, current_user, document_id)
    document = (
        await db.execute(
            select(Document).where(Document.id == document.id)
            .with_for_update().execution_options(populate_existing=True)
        )
    ).scalar_one()
    run = (
        await db.execute(
            select(ExtractionRun).where(
                ExtractionRun.id == run_id,
                ExtractionRun.document_id == document_id,
            ).with_for_update().execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Extraction run not found")

    if document.current_extraction_id != run.id:
        raise HTTPException(
            status_code=400, detail="Only the active extraction run can be cancelled"
        )

    if run.status not in ["pending", "running"]:
        raise HTTPException(status_code=400, detail="Extraction run is not active")

    run.status = "cancelled"
    run.error_message = "Cancelled by user"
    run.completed_at = datetime.now(timezone.utc)
    document.status = "extraction_cancelled"

    await log_action(
        db,
        current_user,
        "cancel",
        "extraction_run",
        str(run.id),
        new_value={"status": run.status, "document_id": str(document.id)},
    )
    await db.commit()
    await db.refresh(run)
    return run


@router.get("/{document_id}/extractions", response_model=dict)
async def list_extractions(
    document_id: uuid.UUID,
    skip: int = 0,
    limit: int = 1000,
    run_id: Optional[uuid.UUID] = None,
    needs_review: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    limit = min(max(limit, 1), 10000)
    await _get_document_for_user(db, current_user, document_id)

    count_query = select(func.count(ExtractedRequirement.id)).where(
        ExtractedRequirement.document_id == document_id
    )
    if run_id:
        count_query = count_query.where(ExtractedRequirement.extraction_run_id == run_id)
    if needs_review is not None:
        count_query = count_query.where(ExtractedRequirement.needs_review == needs_review)
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    query = select(ExtractedRequirement).where(ExtractedRequirement.document_id == document_id)
    if run_id:
        query = query.where(ExtractedRequirement.extraction_run_id == run_id)
    if needs_review is not None:
        query = query.where(ExtractedRequirement.needs_review == needs_review)
    query = query.order_by(ExtractedRequirement.sort_order).offset(skip).limit(limit)
    result = await db.execute(query)
    extractions = result.scalars().all()

    return {
        "items": [ExtractedRequirementResponse.model_validate(e) for e in extractions],
        "total": total,
    }


@router.post(
    "/{document_id}/extractions/reorder",
    response_model=ExtractionReorderResponse,
)
async def reorder_extractions(
    document_id: uuid.UUID,
    body: ExtractionReorderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    document = await _lock_current_extraction_for_edit(db, current_user, document_id)

    if body.run_id != document.current_extraction_id:
        raise HTTPException(409, "The selected extraction run is no longer current.")

    rows_result = await db.execute(
        select(ExtractedRequirement)
        .where(
            ExtractedRequirement.document_id == document_id,
            ExtractedRequirement.extraction_run_id == body.run_id,
        )
        .order_by(ExtractedRequirement.sort_order.asc(), ExtractedRequirement.id.asc())
    )
    rows = list(rows_result.scalars().all())
    scope_ids = [row.id for row in rows]
    ordered_ids = body.ordered_ids

    if len(ordered_ids) != len(set(ordered_ids)):
        raise HTTPException(status_code=400, detail="ordered_ids must not contain duplicates")

    if len(scope_ids) != len(ordered_ids):
        raise HTTPException(
            status_code=400,
            detail="ordered_ids must include exactly all extraction IDs for the selected run",
        )

    scope_set = set(scope_ids)
    ordered_set = set(ordered_ids)
    if scope_set != ordered_set:
        missing_ids = [
            str(extraction_id) for extraction_id in scope_ids if extraction_id not in ordered_set
        ]
        extra_ids = [
            str(extraction_id) for extraction_id in ordered_ids if extraction_id not in scope_set
        ]
        raise HTTPException(
            status_code=400,
            detail={
                "message": "ordered_ids must include exactly all extraction IDs for the selected run",
                "missing_ids": missing_ids,
                "extra_ids": extra_ids,
            },
        )

    rows_by_id = {row.id: row for row in rows}
    for index, extraction_id in enumerate(ordered_ids):
        rows_by_id[extraction_id].sort_order = index
        rows_by_id[extraction_id].quality_auto_editable = False

    await log_action(
        db,
        current_user,
        "reorder",
        "extracted_requirement_batch",
        str(document.id),
        new_value={
            "run_id": str(body.run_id),
            "updated_count": len(ordered_ids),
            "ordered_ids": [str(extraction_id) for extraction_id in ordered_ids],
        },
    )
    await db.commit()
    return ExtractionReorderResponse(updated_count=len(ordered_ids), ordered_ids=ordered_ids)


@router.put(
    "/{document_id}/extractions/{extraction_id}", response_model=ExtractedRequirementResponse
)
async def update_extraction(
    document_id: uuid.UUID,
    extraction_id: uuid.UUID,
    body: ExtractedRequirementUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin", "approver")),
):
    document = await _lock_current_extraction_for_edit(db, current_user, document_id)
    result = await db.execute(
        select(ExtractedRequirement).where(
            ExtractedRequirement.id == extraction_id,
            ExtractedRequirement.document_id == document_id,
        )
    )
    extraction = result.scalar_one_or_none()
    if extraction is None:
        raise HTTPException(status_code=404, detail="Extraction not found")
    _require_current_extraction(document, extraction)
    extraction.quality_auto_editable = False

    old_value = {
        "reference_id": extraction.reference_id,
        "title": extraction.title,
        "text": extraction.text,
        "requirement_type": extraction.requirement_type,
        "parent_id": str(extraction.parent_id) if extraction.parent_id else None,
        "needs_review": extraction.needs_review,
        "review_reason": extraction.review_reason,
    }

    fields_set = body.model_fields_set
    reference_changed = False
    if "reference_id" in fields_set:
        try:
            extraction.reference_id = normalize_reference_or_raise(
                body.reference_id,
                detail="reference_id cannot be empty",
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        reference_changed = True
    if body.title is not None:
        extraction.title = body.title
    if body.text is not None:
        extraction.text = body.text
    if body.requirement_type is not None:
        extraction.requirement_type = body.requirement_type
    if body.status is not None:
        extraction.status = body.status
    if body.needs_review is not None:
        extraction.needs_review = body.needs_review
    if body.review_reason is not None:
        extraction.review_reason = body.review_reason
    if reference_changed or body.sync_parent_from_reference is True:
        extraction.parent_id = await resolve_extracted_requirement_parent_id(
            db,
            document_id=document_id,
            extraction_run_id=extraction.extraction_run_id,
            reference_id=extraction.reference_id,
            exclude_extracted_requirement_id=extraction.id,
        )

    new_value = {
        "reference_id": extraction.reference_id,
        "title": extraction.title,
        "text": extraction.text,
        "requirement_type": extraction.requirement_type,
        "parent_id": str(extraction.parent_id) if extraction.parent_id else None,
        "needs_review": extraction.needs_review,
        "review_reason": extraction.review_reason,
    }

    await log_action(
        db,
        current_user,
        "update",
        "extracted_requirement",
        str(extraction.id),
        old_value,
        new_value,
    )
    await db.commit()
    await db.refresh(extraction)
    return extraction


@router.post(
    "/{document_id}/extractions/{extraction_id}/feedback",
    response_model=ExtractionFeedbackResponse,
)
async def record_extraction_feedback(
    document_id: uuid.UUID,
    extraction_id: uuid.UUID,
    body: ExtractionFeedbackCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin", "approver")),
):
    document = await _lock_current_extraction_for_edit(db, current_user, document_id)
    result = await db.execute(
        select(ExtractedRequirement).where(
            ExtractedRequirement.id == extraction_id,
            ExtractedRequirement.document_id == document_id,
        )
    )
    extraction = result.scalar_one_or_none()
    if extraction is None:
        raise HTTPException(status_code=404, detail="Extraction not found")
    _require_current_extraction(document, extraction)
    extraction.quality_auto_editable = False

    action = (body.action or "").strip().lower()
    if action not in {"accept", "edit", "reject"}:
        raise HTTPException(status_code=400, detail="action must be one of: accept, edit, reject")
    if action == "edit" and not body.corrected_reference_id and not body.corrected_text:
        raise HTTPException(
            status_code=400,
            detail="edit feedback requires corrected_reference_id and/or corrected_text",
        )

    feedback = ExtractionFeedback(
        extraction_run_id=extraction.extraction_run_id,
        extracted_requirement_id=extraction.id,
        action=action,
        corrected_reference_id=body.corrected_reference_id,
        corrected_text=body.corrected_text,
        created_by=current_user.id,
    )
    db.add(feedback)

    if action == "accept":
        extraction.needs_review = False
        extraction.review_reason = None
    elif action == "edit":
        if body.corrected_reference_id:
            try:
                extraction.reference_id = normalize_reference_or_raise(
                    body.corrected_reference_id,
                    detail="corrected_reference_id cannot be empty",
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            extraction.parent_id = await resolve_extracted_requirement_parent_id(
                db,
                document_id=document_id,
                extraction_run_id=extraction.extraction_run_id,
                reference_id=extraction.reference_id,
                exclude_extracted_requirement_id=extraction.id,
            )
        if body.corrected_text:
            extraction.text = body.corrected_text
        extraction.needs_review = False
        extraction.review_reason = None
    elif action == "reject":
        extraction.status = "rejected"
        extraction.needs_review = False
        extraction.review_reason = "rejected_by_reviewer"

    await log_action(
        db,
        current_user,
        "feedback",
        "extracted_requirement",
        str(extraction.id),
        new_value={
            "action": action,
            "corrected_reference_id": body.corrected_reference_id,
            "corrected_text": body.corrected_text,
        },
    )

    await db.commit()
    await db.refresh(feedback)
    return feedback


@router.post(
    "/{document_id}/extractions/feedback-batch",
    response_model=ExtractionFeedbackBatchResponse,
)
async def record_extraction_feedback_batch(
    document_id: uuid.UUID,
    body: ExtractionFeedbackBatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin", "approver")),
):
    document = await _lock_current_extraction_for_edit(db, current_user, document_id)

    if body.run_id is not None and body.run_id != document.current_extraction_id:
        raise HTTPException(409, "The selected extraction run is no longer current.")

    query = select(ExtractedRequirement).where(
        ExtractedRequirement.document_id == document_id,
        ExtractedRequirement.extraction_run_id == document.current_extraction_id,
    )
    if body.filter.needs_review_only:
        query = query.where(ExtractedRequirement.needs_review.is_(True))
    if body.filter.confidence_min is not None:
        query = query.where(ExtractedRequirement.confidence_score >= body.filter.confidence_min)
    if body.filter.confidence_max is not None:
        query = query.where(ExtractedRequirement.confidence_score <= body.filter.confidence_max)

    requirement_types = {
        value.strip().lower() for value in body.filter.requirement_types if value and value.strip()
    }
    if requirement_types:
        query = query.where(
            func.lower(ExtractedRequirement.requirement_type).in_(requirement_types)
        )

    include_statuses = {
        value.strip().lower() for value in body.filter.include_statuses if value and value.strip()
    }
    if include_statuses:
        query = query.where(func.lower(ExtractedRequirement.status).in_(include_statuses))

    exclude_statuses = {
        value.strip().lower() for value in body.filter.exclude_statuses if value and value.strip()
    }
    if exclude_statuses:
        query = query.where(func.lower(ExtractedRequirement.status).notin_(exclude_statuses))

    query = query.order_by(ExtractedRequirement.sort_order.asc(), ExtractedRequirement.id.asc())
    result = await db.execute(query)
    matched_rows = list(result.scalars().all())

    section_prefixes = {
        value.strip().lower() for value in body.filter.section_prefixes if value and value.strip()
    }
    review_reasons = {
        value.strip().lower() for value in body.filter.review_reasons if value and value.strip()
    }

    if section_prefixes or review_reasons:
        filtered_rows: list[ExtractedRequirement] = []
        for row in matched_rows:
            section_prefix = _section_prefix_from_reference(row.reference_id)
            normalized_reason = (row.review_reason or "none").strip().lower()
            if section_prefixes and section_prefix not in section_prefixes:
                continue
            if review_reasons and normalized_reason not in review_reasons:
                continue
            filtered_rows.append(row)
        matched_rows = filtered_rows

    review_reason_dist = Counter(
        (row.review_reason or "none").strip().lower() or "none" for row in matched_rows
    )
    requirement_type_dist = Counter(
        (row.requirement_type or "unknown").strip().lower() or "unknown" for row in matched_rows
    )
    section_prefix_dist = Counter(
        _section_prefix_from_reference(row.reference_id) for row in matched_rows
    )
    confidence_band_dist = Counter(
        _confidence_band(float(row.confidence_score)) for row in matched_rows
    )

    affected_ids_all: list[uuid.UUID] = []
    failures: list[ExtractionFeedbackBatchFailure] = []

    if not body.preview_only:
        for row in matched_rows:
            if row.extraction_run_id is None:
                failures.append(
                    ExtractionFeedbackBatchFailure(
                        extraction_id=row.id,
                        code="extraction_run_missing",
                        detail="Extraction is not linked to an extraction run",
                    )
                )
                continue

            try:
                if body.action.type == "accept":
                    row.needs_review = False
                    row.review_reason = None
                elif body.action.type == "reject":
                    row.quality_auto_editable = False
                    row.status = "rejected"
                    row.needs_review = False
                    row.review_reason = "rejected_by_reviewer"
                else:
                    if body.action.edit and body.action.edit.requirement_type is not None:
                        row.requirement_type = body.action.edit.requirement_type
                    if body.action.edit and body.action.edit.status is not None:
                        row.status = body.action.edit.status
                    row.needs_review = False
                    row.review_reason = None
                row.quality_auto_editable = False
                affected_ids_all.append(row.id)
            except Exception as exc:  # pragma: no cover - defensive path
                failures.append(
                    ExtractionFeedbackBatchFailure(
                        extraction_id=row.id,
                        code="apply_failed",
                        detail=str(exc),
                    )
                )

    affected_ids = affected_ids_all[:500]
    affected_ids_truncated = len(affected_ids_all) > 500

    response = ExtractionFeedbackBatchResponse(
        preview_only=body.preview_only,
        matched_count=len(matched_rows),
        affected_count=len(affected_ids_all),
        affected_ids=affected_ids,
        affected_ids_truncated=affected_ids_truncated,
        failures=failures,
        distributions=ExtractionFeedbackBatchDistributions(
            by_review_reason=_to_distribution(review_reason_dist),
            by_requirement_type=_to_distribution(requirement_type_dist),
            by_section_prefix=_to_distribution(section_prefix_dist),
            by_confidence_band=_to_distribution(confidence_band_dist),
        ),
    )

    await log_action(
        db,
        current_user,
        "feedback_batch",
        "extracted_requirement_batch",
        str(document_id),
        new_value={
            "preview_only": body.preview_only,
            "run_id": str(body.run_id) if body.run_id else None,
            "matched_count": response.matched_count,
            "affected_count": response.affected_count,
            "failure_count": len(response.failures),
            "action_type": body.action.type,
            "filters": {
                "needs_review_only": body.filter.needs_review_only,
                "confidence_min": body.filter.confidence_min,
                "confidence_max": body.filter.confidence_max,
                "requirement_types": sorted(requirement_types),
                "section_prefixes": sorted(section_prefixes),
                "review_reasons": sorted(review_reasons),
                "include_statuses": sorted(include_statuses),
                "exclude_statuses": sorted(exclude_statuses),
            },
        },
    )

    await db.commit()
    return response


@router.post(
    "/{document_id}/extractions/reconcile-batch",
    response_model=ExtractionBatchResult,
)
async def reconcile_extractions_batch(
    document_id: uuid.UUID,
    body: ExtractionBatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    document = await _lock_current_extraction_for_edit(db, current_user, document_id)

    # Reject stale references before applying any operation, including republish.
    referenced_ids = {
        extraction_id
        for operation in body.operations
        if operation.action.strip().lower() in {"edit", "reject", "merge", "split"}
        for extraction_id in ([operation.extraction_id] if operation.extraction_id else [])
        + operation.source_ids
    }
    if referenced_ids:
        referenced_rows = (await db.scalars(
            select(ExtractedRequirement).where(
                ExtractedRequirement.document_id == document_id,
                ExtractedRequirement.id.in_(referenced_ids),
            )
        )).all()
        if any(row.extraction_run_id != document.current_extraction_id for row in referenced_rows):
            raise HTTPException(409, "Batch contains an extraction from an older run.")

    result = ExtractionBatchResult(processed=0)

    for idx, operation in enumerate(body.operations):
        action = operation.action.strip().lower()
        result.processed += 1

        if action == "comment":
            if not operation.comment or not operation.comment.strip():
                result.errors.append(f"operation {idx}: comment text is required")
                continue
            await log_action(
                db,
                current_user,
                "comment",
                "extracted_requirement_batch",
                str(document_id),
                new_value={"comment": operation.comment.strip()},
            )
            result.comments_added += 1
            continue

        if action == "republish":
            document.status = "extracted"
            continue

        target_id: Optional[uuid.UUID] = operation.extraction_id
        if target_id is None and operation.source_ids:
            target_id = operation.source_ids[0]

        if action == "edit":
            if target_id is None:
                result.errors.append(f"operation {idx}: extraction_id is required for edit")
                continue
            extraction_result = await db.execute(
                select(ExtractedRequirement).where(
                    ExtractedRequirement.id == target_id,
                    ExtractedRequirement.document_id == document_id,
                    ExtractedRequirement.extraction_run_id == document.current_extraction_id,
                )
            )
            extraction = extraction_result.scalar_one_or_none()
            if extraction is None:
                result.errors.append(f"operation {idx}: extraction {target_id} not found")
                continue
            if operation.reference_id is not None:
                try:
                    extraction.reference_id = normalize_reference_or_raise(
                        operation.reference_id,
                        detail="reference_id cannot be empty",
                    )
                except ValueError as exc:
                    result.errors.append(f"operation {idx}: {exc}")
                    continue
                extraction.parent_id = await resolve_extracted_requirement_parent_id(
                    db,
                    document_id=document_id,
                    extraction_run_id=extraction.extraction_run_id,
                    reference_id=extraction.reference_id,
                    exclude_extracted_requirement_id=extraction.id,
                )
            if operation.title is not None:
                extraction.title = operation.title
            if operation.text is not None:
                extraction.text = operation.text
            if operation.requirement_type is not None:
                extraction.requirement_type = operation.requirement_type
            if operation.status is not None:
                extraction.status = operation.status
            extraction.quality_auto_editable = False
            result.updated_ids.append(extraction.id)
            continue

        if action == "reject":
            ids = operation.source_ids or ([target_id] if target_id else [])
            if not ids:
                result.errors.append(f"operation {idx}: source_ids or extraction_id is required")
                continue
            query = select(ExtractedRequirement).where(
                ExtractedRequirement.document_id == document_id,
                ExtractedRequirement.extraction_run_id == document.current_extraction_id,
                ExtractedRequirement.id.in_(ids),
            )
            rows_result = await db.execute(query)
            rows = rows_result.scalars().all()
            found_ids = {row.id for row in rows}
            missing = [str(req_id) for req_id in ids if req_id not in found_ids]
            if missing:
                result.errors.append(
                    f"operation {idx}: missing extractions for reject: {', '.join(missing)}"
                )
            for row in rows:
                row.quality_auto_editable = False
                row.status = "rejected"
                result.rejected_ids.append(row.id)
            continue

        if action == "merge":
            ids = operation.source_ids or ([target_id] if target_id else [])
            if len(ids) < 2:
                result.errors.append(f"operation {idx}: merge requires at least two source_ids")
                continue
            query = select(ExtractedRequirement).where(
                ExtractedRequirement.document_id == document_id,
                ExtractedRequirement.extraction_run_id == document.current_extraction_id,
                ExtractedRequirement.id.in_(ids),
            )
            rows_result = await db.execute(query)
            rows = rows_result.scalars().all()
            if len(rows) != len(ids):
                result.errors.append(f"operation {idx}: one or more merge sources not found")
                continue
            rows_by_id = {row.id: row for row in rows}
            ordered_rows = [rows_by_id[item_id] for item_id in ids if item_id in rows_by_id]
            primary = ordered_rows[0]
            merged_text_parts = [part.text.strip() for part in ordered_rows if part.text.strip()]
            if operation.text:
                primary.text = operation.text.strip()
            else:
                primary.text = "\n\n".join(merged_text_parts)
            if operation.reference_id is not None:
                try:
                    primary.reference_id = normalize_reference_or_raise(
                        operation.reference_id,
                        detail="reference_id cannot be empty",
                    )
                except ValueError as exc:
                    result.errors.append(f"operation {idx}: {exc}")
                    continue
                primary.parent_id = await resolve_extracted_requirement_parent_id(
                    db,
                    document_id=document_id,
                    extraction_run_id=primary.extraction_run_id,
                    reference_id=primary.reference_id,
                    exclude_extracted_requirement_id=primary.id,
                )
            if operation.title is not None:
                primary.title = operation.title
            if operation.requirement_type is not None:
                primary.requirement_type = operation.requirement_type
            primary.quality_auto_editable = False
            primary.status = operation.status or "pending"
            result.updated_ids.append(primary.id)

            for row in ordered_rows[1:]:
                row.quality_auto_editable = False
                row.status = "rejected"
                result.rejected_ids.append(row.id)
            continue

        if action == "split":
            if target_id is None:
                result.errors.append(f"operation {idx}: extraction_id is required for split")
                continue
            if not operation.split_items:
                result.errors.append(f"operation {idx}: split_items is required for split")
                continue

            extraction_result = await db.execute(
                select(ExtractedRequirement).where(
                    ExtractedRequirement.id == target_id,
                    ExtractedRequirement.document_id == document_id,
                    ExtractedRequirement.extraction_run_id == document.current_extraction_id,
                )
            )
            extraction = extraction_result.scalar_one_or_none()
            if extraction is None:
                result.errors.append(f"operation {idx}: extraction {target_id} not found")
                continue

            extraction.quality_auto_editable = False
            extraction.status = "rejected"
            result.rejected_ids.append(extraction.id)

            base_sort = extraction.sort_order
            for offset, split_item in enumerate(operation.split_items, start=1):
                try:
                    split_reference_id = normalize_reference_or_raise(
                        split_item.reference_id,
                        detail="split_items.reference_id cannot be empty",
                    )
                except ValueError as exc:
                    result.errors.append(f"operation {idx}: {exc}")
                    continue
                split_row = ExtractedRequirement(
                    document_id=extraction.document_id,
                    extraction_run_id=extraction.extraction_run_id,
                    reference_id=split_reference_id,
                    title=split_item.title,
                    text=split_item.text,
                    original_text=split_item.text,
                    requirement_type=split_item.requirement_type,
                    parent_id=None,
                    page_number=extraction.page_number,
                    confidence_score=extraction.confidence_score,
                    status=split_item.status,
                    needs_review=False,
                    review_reason=None,
                    source_excerpt=split_item.text[:280],
                    parser_strategy=extraction.parser_strategy,
                    sort_order=base_sort + offset,
                )
                db.add(split_row)
                await db.flush()
                split_row.parent_id = await resolve_extracted_requirement_parent_id(
                    db,
                    document_id=document_id,
                    extraction_run_id=split_row.extraction_run_id,
                    reference_id=split_row.reference_id,
                    exclude_extracted_requirement_id=split_row.id,
                )
                result.created_ids.append(split_row.id)
            continue

        result.errors.append(f"operation {idx}: unsupported action '{operation.action}'")

    if body.republish:
        document.status = "extracted"

    await log_action(
        db,
        current_user,
        "reconcile",
        "extracted_requirement_batch",
        str(document_id),
        new_value={
            "processed": result.processed,
            "updated": len(result.updated_ids),
            "created": len(result.created_ids),
            "rejected": len(result.rejected_ids),
            "errors": len(result.errors),
            "republish": bool(body.republish),
        },
    )

    await db.commit()
    return result


@router.post("/{document_id}/extract", response_model=DocumentWithExtractionResponse)
async def trigger_extraction(
    document_id: uuid.UUID,
    allow_external_ai: bool = False,
    use_jev: bool = False,
    jev_settings_revision: int | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    document = await _get_document_for_user(db, current_user, document_id)

    document = (
        await db.execute(
            select(Document)
            .where(Document.id == document.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()

    if not document.has_source:
        raise HTTPException(409, "This requirement set has no source PDF to extract.")
    if not os.path.isfile(document.file_path):
        raise HTTPException(404, "The source PDF is missing. Ask the installation operator to restore it.")

    if document.status not in [
        "uploaded",
        "extraction_failed",
        "extraction_cancelled",
        "extracted",
    ]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot extract from document in status '{document.status}'",
        )

    structured = settings.pdf_structure_engine == "opendataloader"
    if structured:
        from app.services.structured_pdf import structured_pdf_available

        if not structured_pdf_available():
            raise HTTPException(
                503,
                "OpenDataLoader PDF extraction is unavailable. Install the optional package and Java before retrying.",
            )

    from app.services.installation_settings import resolve_installation_settings

    runtime_settings = await resolve_installation_settings(db)
    ai_provider, ai_model = runtime_settings.ai_provider, runtime_settings.ai_model
    if structured:
        ai_provider, ai_model = "local", "opendataloader_2.5.11"
    elif ai_provider == "none":
        ai_provider, ai_model = "local", "rule_based_review_required"

    if ai_provider in {"openai", "anthropic"}:
        from app.services.ai_provider import ProviderConfig
        try:
            ProviderConfig.from_settings(runtime_settings)
        except ValueError as exc:
            raise HTTPException(503, str(exc)) from None
        if not allow_external_ai:
            raise HTTPException(400, "This extraction sends document text and possibly page images to the configured AI provider. Confirm external AI processing to continue.")

    quality_request = None
    quality_skip_reason = None
    if use_jev:
        from app.services.quality_jobs import quality_config
        try:
            quality_request = await quality_config(db, allow_external_ai, jev_settings_revision)
        except HTTPException as exc:
            if exc.status_code == 400:
                raise  # External consent is mandatory even when Jev is optional.
            from app.services.jev_provider import JevConfig
            quality_request = (JevConfig.from_settings(runtime_settings),
                jev_settings_revision if jev_settings_revision is not None else runtime_settings.jev_settings_revision)
            quality_skip_reason = "Jev check was skipped because its settings changed or enhancement is unavailable. Baseline extraction continues."


    # Create extraction run record
    extraction_run = ExtractionRun(
        document_id=document.id,
        status="pending",
        ai_provider=ai_provider,
        ai_model=ai_model,
        pipeline_version=(
            "opendataloader_v1"
            if structured
            else NATIVE_PIPELINE_VERSION
        ),
    )
    db.add(extraction_run)
    await db.flush()  # Get the ID
    if quality_request:
        from app.services.quality_jobs import create_quality_run
        quality_run = await create_quality_run(db, document, current_user, *quality_request, extraction_run_id=extraction_run.id, mode="import")
        if quality_skip_reason:
            quality_run.status = "skipped"
            quality_run.warnings = [quality_skip_reason]
            quality_run.completed_at = datetime.now(timezone.utc)

    # Update document status and link to extraction run
    document.status = "pending_extraction"
    document.current_extraction_id = extraction_run.id

    await log_action(
        db,
        current_user,
        "update",
        "document",
        str(document.id),
        old_value={"status": "uploaded"},
        new_value={"status": "pending_extraction", "extraction_run_id": str(extraction_run.id)},
    )
    await db.commit()

    # Dispatch intent is the committed run. A failed or ambiguous publish is
    # retried by the watchdog; Celery I/O runs in a thread, off the API loop.
    from app.services.extraction_jobs import dispatch_run
    await dispatch_run(db, extraction_run.id)

    await db.refresh(document)
    await db.refresh(extraction_run)

    response = DocumentWithExtractionResponse.model_validate(document).model_dump()
    response["current_extraction"] = ExtractionRunResponse.model_validate(
        extraction_run
    ).model_dump()
    return response


@router.post("/{document_id}/prepare-edit", response_model=dict)
async def prepare_document_for_edit(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    document = await _lock_document_for_extraction_edit(db, current_user, document_id)

    draft_version = await _get_or_create_draft_version(db, document, current_user.id)
    if document.current_extraction_id:
        requirements_count = await _ensure_extracted_requirements_in_version(
            db,
            document=document,
            version=draft_version,
            changed_by=current_user.id,
            comment="Requirement staged from document extraction",
        )
    else:
        count_result = await db.execute(
            select(func.count(Requirement.id)).where(
                Requirement.requirement_set_version_id == draft_version.id
            )
        )
        requirements_count = int(count_result.scalar() or 0)

    await db.commit()
    return {
        "status": "ok",
        "version_id": str(draft_version.id),
        "requirements_count": requirements_count,
    }


@router.post("/{document_id}/submit", response_model=DocumentResponse)
async def submit_for_approval(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    document = await _get_document_for_user(db, current_user, document_id)

    await validate_extraction_complete(db, document)

    if document.status not in ["draft", "extracted", "reviewed", "changes_requested"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot submit document in status '{document.status}'",
        )

    if document.current_extraction_id:
        unresolved_result = await db.execute(
            select(func.count(ExtractedRequirement.id)).where(
                and_(
                    ExtractedRequirement.document_id == document.id,
                    ExtractedRequirement.extraction_run_id == document.current_extraction_id,
                    ExtractedRequirement.needs_review.is_(True),
                    ExtractedRequirement.status != "rejected",
                )
            )
        )
        unresolved_count = int(unresolved_result.scalar() or 0)
        if unresolved_count > 0:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Resolve all flagged extraction review items before submit "
                    f"({unresolved_count} remaining)."
                ),
            )

    old_status = document.status
    version = await _get_or_create_draft_version(db, document, current_user.id)
    if document.current_extraction_id:
        await _ensure_extracted_requirements_in_version(
            db,
            document=document,
            version=version,
            changed_by=current_user.id,
            comment="Requirement staged from document extraction",
        )
    await validate_baseline(db, version.id)
    document.status = "pending_approval"
    version.status = "pending_approval"
    await log_action(
        db,
        current_user,
        "update",
        "document",
        str(document.id),
        old_value={"status": old_status},
        new_value={
            "status": "pending_approval",
            "requirement_set_version_id": str(version.id),
            "requirement_set_version_number": version.version_number,
        },
    )
    await db.commit()
    await db.refresh(document)
    return document


@router.post("/{document_id}/approve", response_model=DocumentResponse)
async def approve_document(
    document_id: uuid.UUID,
    comment: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "approver", "admin")),
):
    document = await _get_document_for_user(db, current_user, document_id)

    await validate_extraction_complete(db, document)
    if document.status != "pending_approval":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve document in status '{document.status}'",
        )

    if not document.name or not document.name.strip():
        raise HTTPException(status_code=400, detail="Document name is required for approval")
    if not document.testing_frequency or not document.testing_frequency.strip():
        raise HTTPException(status_code=400, detail="Testing frequency is required for approval")

    version_result = await db.execute(
        select(RequirementSetVersion)
        .where(
            and_(
                RequirementSetVersion.document_id == document.id,
                RequirementSetVersion.status == "pending_approval",
            )
        )
        .order_by(RequirementSetVersion.version_number.desc())
        .limit(1)
    )
    pending_version = version_result.scalar_one_or_none()
    if pending_version is None:
        pending_version = await _get_or_create_draft_version(db, document, current_user.id)
        pending_version.status = "pending_approval"

    now = datetime.now(timezone.utc)

    if not document.current_extraction_id:
        # Manual requirement set: requirements already exist.
        requirements_result = await db.execute(
            select(func.count(Requirement.id)).where(
                Requirement.requirement_set_version_id == pending_version.id
            )
        )
        requirements_count = int(requirements_result.scalar() or 0)
        if requirements_count <= 0:
            legacy_result = await db.execute(
                select(func.count(Requirement.id)).where(
                    and_(
                        Requirement.document_id == document_id,
                        Requirement.requirement_set_version_id.is_(None),
                    )
                )
            )
            requirements_count = int(legacy_result.scalar() or 0)
            if requirements_count > 0:
                await db.execute(
                    update(Requirement)
                    .where(
                        and_(
                            Requirement.document_id == document_id,
                            Requirement.requirement_set_version_id.is_(None),
                        )
                    )
                    .values(requirement_set_version_id=pending_version.id)
                )

        if requirements_count <= 0:
            raise HTTPException(
                status_code=400,
                detail="Cannot approve an empty requirement set (no requirements found)",
            )

        await db.execute(
            update(RequirementSetVersion)
            .where(RequirementSetVersion.document_id == document.id)
            .values(is_current=False)
        )
        await validate_baseline(db, pending_version.id)
        pending_version.status = "approved"
        pending_version.is_current = True
        pending_version.approved_by = current_user.id
        pending_version.approved_at = now
        pending_version.locked_at = now
        document.status = "approved"
        document.approved_by = current_user.id
        document.approval_comment = comment

        await log_action(
            db,
            current_user,
            "approve",
            "requirements_set",
            str(document.id),
            new_value={"status": "approved", "requirements_count": requirements_count},
        )
        await db.commit()
        await db.refresh(document)
        return document

    requirements_count = await _ensure_extracted_requirements_in_version(
        db,
        document=document,
        version=pending_version,
        changed_by=current_user.id,
        comment="Requirement approved from document extraction",
    )
    if requirements_count <= 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot approve an empty requirement set (no requirements found)",
        )

    await db.execute(
        update(RequirementSetVersion)
        .where(RequirementSetVersion.document_id == document.id)
        .values(is_current=False)
    )
    await validate_baseline(db, pending_version.id)
    pending_version.status = "approved"
    pending_version.is_current = True
    pending_version.approved_by = current_user.id
    pending_version.approved_at = now
    pending_version.locked_at = now
    document.status = "approved"
    document.approved_by = current_user.id
    document.approval_comment = comment

    await log_action(
        db,
        current_user,
        "approve",
        "document",
        str(document.id),
        new_value={"status": "approved", "requirements_count": requirements_count},
    )
    await db.commit()
    await db.refresh(document)
    return document


@router.post("/{document_id}/reject", response_model=DocumentResponse)
async def reject_document(
    document_id: uuid.UUID,
    comment: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "approver", "admin")),
):
    document = await _get_document_for_user(db, current_user, document_id)

    if document.status != "pending_approval":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot reject document in status '{document.status}'",
        )

    pending_version_result = await db.execute(
        select(RequirementSetVersion)
        .where(
            and_(
                RequirementSetVersion.document_id == document.id,
                RequirementSetVersion.status == "pending_approval",
            )
        )
        .order_by(RequirementSetVersion.version_number.desc())
        .limit(1)
    )
    pending_version = pending_version_result.scalar_one_or_none()
    if pending_version is not None:
        pending_version.status = "draft"

    document.status = "changes_requested"
    document.approval_comment = comment

    await log_action(
        db,
        current_user,
        "reject",
        "document",
        str(document.id),
        new_value={"status": "changes_requested", "comment": comment},
    )
    await db.commit()
    await db.refresh(document)
    return document


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    document = await _get_document_for_user(db, current_user, document_id)

    if document.archived_at is not None or document.status == "archived":
        return

    old_value = {
        "filename": document.filename,
        "status": document.status,
        "archived_at": document.archived_at.isoformat() if document.archived_at else None,
    }

    # Archival preserves source bytes and extraction provenance for every baseline.
    document.status = "archived"
    document.archived_at = datetime.now(timezone.utc)

    await log_action(
        db,
        current_user,
        "archive",
        "document",
        str(document.id),
        old_value=old_value,
        new_value={
            "status": document.status,
            "archived_at": document.archived_at.isoformat() if document.archived_at else None,
        },
    )
    await db.commit()
