"""Copy scoped source requirements into blank, independently editable form questions."""

import hashlib
import json
import uuid

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.tenant import apply_org_scope, get_org_owned_or_404
from app.models.document import Document
from app.models.extraction import ExtractionRun
from app.models.jurisdiction import Jurisdiction
from app.models.program import RequirementSetVersion
from app.models.requirement import ExtractedRequirement, Requirement
from app.models.user import User
from app.schemas.preparation import PreparationField, RequirementFieldSource


def field_source(
    document: Document,
    version: RequirementSetVersion | None,
    requirement: Requirement | ExtractedRequirement,
    run: ExtractionRun | None = None,
):
    extracted = isinstance(requirement, ExtractedRequirement)
    return RequirementFieldSource(
        kind="extracted_requirement" if extracted else "requirement",
        document_id=document.id,
        document_name=document.name or document.filename or "Requirement set",
        document_status=document.status,
        jurisdiction_id=document.jurisdiction_id,
        requirement_id=None if extracted else requirement.id,
        extracted_requirement_id=requirement.id if extracted else None,
        requirement_set_version_id=version.id if version else None,
        version_number=version.version_number if version else None,
        version_status=version.status if version else None,
        reference_id=requirement.reference_id,
        source_extraction_id=requirement.id if extracted else requirement.source_extraction_id,
        extraction_run_id=run.id if run else None,
        extraction_status=run.status if run else None,
        extraction_review_status=requirement.status if extracted else None,
        text_sha256=hashlib.sha256(requirement.text.encode("utf-8")).hexdigest(),
    )


async def requirements_preview(
    db: AsyncSession,
    user: User,
    document_id: uuid.UUID,
    jurisdiction_id: uuid.UUID,
    version_id: uuid.UUID | None,
    skip: int,
    limit: int,
) -> dict:
    document = await get_org_owned_or_404(
        db, Document, document_id, user, detail="Requirement set not found"
    )
    if document.jurisdiction_id != jurisdiction_id:
        raise HTTPException(422, "Requirement set jurisdiction differs from this space")
    jurisdiction = await db.get(Jurisdiction, jurisdiction_id)
    if jurisdiction is None or not jurisdiction.active:
        raise HTTPException(422, "Jurisdiction is inactive or missing")
    versions = apply_org_scope(
        select(RequirementSetVersion).where(RequirementSetVersion.document_id == document.id),
        RequirementSetVersion,
        user,
    )
    if version_id is not None:
        versions = versions.where(RequirementSetVersion.id == version_id)
    version = await db.scalar(
        versions.order_by(RequirementSetVersion.version_number.desc()).limit(1)
    )
    if version_id is not None and version is None:
        raise HTTPException(404, "Requirement set version not found")
    query = apply_org_scope(
        select(Requirement).where(
            Requirement.document_id == document.id,
            Requirement.jurisdiction_id == jurisdiction_id,
            Requirement.active.is_(True),
            Requirement.requirement_set_version_id == (version.id if version else None),
        ),
        Requirement,
        user,
    )
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    source_model = Requirement
    run = None
    if not total and version_id is None and document.current_extraction_id:
        run = await db.get(ExtractionRun, document.current_extraction_id)
        if run is None or run.document_id != document.id or run.status != "completed":
            raise HTTPException(
                409, "The PDF extraction must finish before its questions can be imported"
            )
        source_model = ExtractedRequirement
        version = None
        query = select(ExtractedRequirement).where(
            ExtractedRequirement.document_id == document.id,
            ExtractedRequirement.extraction_run_id == run.id,
            func.lower(ExtractedRequirement.status) != "rejected",
        )
        total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    requirements = (
        await db.scalars(
            query.order_by(source_model.sort_order, source_model.created_at, source_model.id)
            .offset(skip)
            .limit(limit)
        )
    ).all()
    parent_ids = {item.parent_id for item in requirements if item.parent_id}
    parents = (
        (await db.scalars(query.where(source_model.id.in_(parent_ids)))).all() if parent_ids else []
    )
    parent_by_id = {item.id: item for item in parents}
    fields, unavailable = [], []
    for requirement in requirements:
        text = requirement.text
        if not text.strip() or len(text) > 10000:
            unavailable.append(
                {
                    "requirement_id": requirement.id,
                    "reference_id": requirement.reference_id,
                    "reason": (
                        "No question text"
                        if not text.strip()
                        else "Requirement exceeds 10,000 characters. Split it into smaller questions in Requirements first."
                    ),
                }
            )
            continue
        label = f"{requirement.reference_id} {text}".strip()
        help_text = None
        if len(label) > 2000:
            label = f"{requirement.reference_id} {requirement.title or 'Requirement text'}".strip()
            help_text = text
        parent = parent_by_id.get(requirement.parent_id)
        section = "General"
        if parent is not None:
            heading = f"{parent.reference_id} {parent.title or ''}".strip()
            section = heading if len(heading) <= 100 else parent.reference_id
        fields.append(
            PreparationField(
                key=f"req_{requirement.id.hex}",
                label=label,
                section=section,
                help_text=help_text,
                type="multiline",
                required=requirement.requirement_type == "mandatory",
                source=field_source(document, version, requirement, run),
            )
        )
    warnings = []
    if run is None and (version is None or version.status != "approved"):
        warnings.append(
            "This source has not been approved. Review extracted text against the original form before using it."
        )
    if run is not None:
        warnings.append(
            "These questions come from the current completed PDF extraction, before requirement-set approval. Review extraction errors and answer types; this import does not approve the source."
        )
    if document.archived_at is not None:
        warnings.append(
            "This requirement set is archived. Check that it is still the form you need."
        )
    if unavailable:
        warnings.append(
            f"{len(unavailable)} item(s) on this page cannot be imported. Review their reasons below; no text has been shortened."
        )
    return {
        "source": {
            "kind": "extracted_requirements" if run else "requirements",
            "document_id": document.id,
            "name": document.name or document.filename or "Requirement set",
            "status": document.status,
            "jurisdiction_id": document.jurisdiction_id,
            "version_id": version.id if version else None,
            "version_number": version.version_number if version else None,
            "version_status": version.status if version else None,
            "has_source": document.has_source,
            "extraction_run_id": run.id if run else document.current_extraction_id,
            "extraction_status": run.status if run else None,
        },
        "fields": fields,
        "unavailable": unavailable,
        "warnings": warnings,
        "total": total,
        "skip": skip,
        "limit": limit,
    }


async def checked_template_fields(
    db: AsyncSession,
    user: User,
    fields: list[PreparationField],
    existing_fields: list[dict] | None = None,
) -> list[dict]:
    """Verify newly attached provenance; retain already saved historical snapshots."""
    existing_sources = {item["key"]: item.get("source") for item in (existing_fields or [])}
    sources = []
    for field in fields:
        source = field.source
        if source is None:
            continue
        if existing_sources.get(field.key) == source.model_dump(mode="json"):
            continue
        sources.append(field)
    # A template contains no more than 100 fields. Batch each source table so a
    # complete form import does not make one database round trip per question.
    document_ids = {field.source.document_id for field in sources}
    documents = (
        {
            item.id: item
            for item in await db.scalars(
                apply_org_scope(
                    select(Document).where(Document.id.in_(document_ids)), Document, user
                )
            )
        }
        if document_ids
        else {}
    )
    requirement_ids = {
        field.source.requirement_id for field in sources if field.source.requirement_id
    }
    requirements = (
        {
            item.id: item
            for item in await db.scalars(
                apply_org_scope(
                    select(Requirement).where(Requirement.id.in_(requirement_ids)),
                    Requirement,
                    user,
                )
            )
        }
        if requirement_ids
        else {}
    )
    extracted_ids = {
        field.source.extracted_requirement_id
        for field in sources
        if field.source.extracted_requirement_id
    }
    extracted = (
        {
            item.id: item
            for item in await db.scalars(
                select(ExtractedRequirement).where(
                    ExtractedRequirement.id.in_(extracted_ids),
                    ExtractedRequirement.document_id.in_(document_ids),
                )
            )
        }
        if extracted_ids
        else {}
    )
    run_ids = {
        field.source.extraction_run_id for field in sources if field.source.extraction_run_id
    }
    runs = (
        {
            item.id: item
            for item in await db.scalars(
                select(ExtractionRun).where(
                    ExtractionRun.id.in_(run_ids), ExtractionRun.document_id.in_(document_ids)
                )
            )
        }
        if run_ids
        else {}
    )
    version_ids = {
        field.source.requirement_set_version_id
        for field in sources
        if field.source.requirement_set_version_id
    }
    versions = (
        {
            item.id: item
            for item in await db.scalars(
                apply_org_scope(
                    select(RequirementSetVersion).where(RequirementSetVersion.id.in_(version_ids)),
                    RequirementSetVersion,
                    user,
                )
            )
        }
        if version_ids
        else {}
    )
    for field in sources:
        source = field.source
        document = documents.get(source.document_id)
        if source.kind == "extracted_requirement":
            requirement = extracted.get(source.extracted_requirement_id)
            run = runs.get(source.extraction_run_id)
            if (
                document is None
                or requirement is None
                or run is None
                or requirement.document_id != document.id
                or run.document_id != document.id
                or requirement.extraction_run_id != run.id
            ):
                raise HTTPException(404, "Question source not found")
            canonical = field_source(document, None, requirement, run)
            if (
                run.status != "completed"
                or document.current_extraction_id != run.id
                or requirement.status.lower() == "rejected"
                or canonical.text_sha256 != source.text_sha256
            ):
                raise HTTPException(
                    409, "Source extraction changed. Preview it again before saving this form."
                )
            field.source = canonical
            continue
        requirement = requirements.get(source.requirement_id)
        version = versions.get(source.requirement_set_version_id)
        if (
            document is None
            or requirement is None
            or requirement.document_id != document.id
            or requirement.jurisdiction_id != document.jurisdiction_id
            or requirement.requirement_set_version_id != source.requirement_set_version_id
            or (
                source.requirement_set_version_id
                and (version is None or version.document_id != document.id)
            )
        ):
            raise HTTPException(404, "Question source not found")
        canonical = field_source(document, version, requirement)
        if not requirement.active or canonical.text_sha256 != source.text_sha256:
            raise HTTPException(
                409, "Source requirements changed. Preview them again before saving this form."
            )
        field.source = canonical
    return [field.model_dump(mode="json") for field in fields]


def ensure_template_jurisdiction(fields_json: str, jurisdiction_id: uuid.UUID) -> None:
    for field in json.loads(fields_json):
        source = field.get("source")
        if source and source.get("jurisdiction_id") != str(jurisdiction_id):
            raise HTTPException(422, "Form question source jurisdiction differs from this space")
