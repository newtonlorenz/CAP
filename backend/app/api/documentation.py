"""Authenticated documentation register workflows; domain services own policy."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.change_management import ChangeEntry, Component, ComponentRegister
from app.models.documentation import (
    AuditorRequestMapping, DocumentationExpectation, DocumentationRegister, DocumentationSection,
    EvidenceGroup, EvidenceGroupVersion, ExpectationRequirement,
)
from app.models.documentation_integrations import DocumentationImportRow
from app.models.preparation import PreparationCase, PreparationEvidence
from app.models.user import User
from app.schemas.documentation import (
    AuditorRequestCreate, AuditorRequestPatch, CoverageLinks, CoverageReview,
    ExpectationCreate, ExpectationPatch, GroupCreate, GroupVersion,
    ReferenceLinks, RegisterCreate, RegisterPatch, RequirementLinks, SectionCreate, SectionPatch, RegisterProcessPut, ProcessTargetsPut, RowReviewPut,
)
from app.services.access import access_clause, tenant_clause
from app.services import documentation as service
from app.services.preparation import fields_for

router = APIRouter(prefix="/api/v1/documentation", tags=["documentation"])
DB = Annotated[AsyncSession, Depends(get_db)]
Actor = Annotated[User, Depends(get_current_user)]


async def page(db, query, model, skip, limit):
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = (await db.scalars(query.order_by(model.created_at.desc(), model.id).offset(skip).limit(limit))).all()
    return rows, total


@router.get("/registers")
async def list_registers(db: DB, user: Actor, jurisdiction_id: uuid.UUID | None = None,
    q: str = Query("", max_length=255), skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)):
    query = select(DocumentationRegister).where(tenant_clause(DocumentationRegister, user), access_clause(DocumentationRegister, user, "view"))
    if jurisdiction_id:
        query = query.where(DocumentationRegister.jurisdiction_id == jurisdiction_id)
    if q:
        query = query.where(DocumentationRegister.name.icontains(q, autoescape=True))
    rows, total = await page(db, query, DocumentationRegister, skip, limit)
    return {"items": [await service.register_response(db, item, user) for item in rows], "total": total}


@router.post("/registers", status_code=201)
async def create_register(body: RegisterCreate, db: DB, user: Actor):
    item = await service.create_register(db, user, body)
    await db.commit()
    return await service.register_response(db, item, user)


@router.get("/registers/{register_id}")
async def read_register(register_id: uuid.UUID, db: DB, user: Actor):
    return await service.register_response(db, await service.get_register(db, register_id, user), user)


@router.patch("/registers/{register_id}")
async def patch_register(register_id: uuid.UUID, body: RegisterPatch, db: DB, user: Actor):
    item = await service.get_register(db, register_id, user, "edit", body.revision)
    changes = body.model_dump(exclude={"revision"}, exclude_unset=True)
    if "name" in changes and changes["name"] is None:
        raise HTTPException(422, "Register name cannot be empty")
    changed = {key: value for key, value in changes.items() if getattr(item, key) != value}
    if changed:
        for key, value in changed.items():
            setattr(item, key, value)
        await service.advance_register(db, item, user, "update", {"changed_fields": sorted(changed)})
    await db.commit()
    return await service.register_response(db, item, user)


@router.get("/registers/{register_id}/sections")
async def list_sections(register_id: uuid.UUID, db: DB, user: Actor):
    register = await service.get_register(db, register_id, user)
    sections = await service.ordered_sections(db, register.id)
    return {"items": [await service.section_response(db, section, register) for section in sections],
        "total": len(sections), "revision": register.revision}


@router.post("/registers/{register_id}/sections", status_code=201)
async def create_section(register_id: uuid.UUID, body: SectionCreate, db: DB, user: Actor):
    register = await service.get_register(db, register_id, user, "edit", body.revision)
    section = await service.create_section(db, register, user, body)
    await db.commit()
    return await service.section_response(db, section, register)


@router.patch("/sections/{section_id}")
async def patch_section(section_id: uuid.UUID, body: SectionPatch, db: DB, user: Actor):
    section = await service.get_section(db, section_id, user, "edit")
    await service.patch_section(db, section, user, body)
    await db.commit()
    register = await service.get_register(db, section.register_id, user)
    return await service.section_response(db, section, register)


@router.get("/registers/{register_id}/expectations")
async def list_expectations(register_id: uuid.UUID, db: DB, user: Actor,
    requirement_id: uuid.UUID | None = None, project_id: uuid.UUID | None = None,
    owner_id: uuid.UUID | None = None, unassigned: bool = False,
    category: str | None = Query(None, max_length=100),
    section_id: uuid.UUID | None = None, unsectioned: bool = False,
    q: str = Query("", max_length=255), skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)):
    register = await service.get_register(db, register_id, user)
    source_row = select(func.min(DocumentationImportRow.row_number)).where(
        DocumentationImportRow.expectation_id == DocumentationExpectation.id,
        DocumentationImportRow.register_id == register_id,
    ).correlate(DocumentationExpectation).scalar_subquery()
    query = select(DocumentationExpectation).outerjoin(DocumentationSection,
        (DocumentationSection.id == DocumentationExpectation.section_id)
        & (DocumentationSection.register_id == register_id)).where(
            DocumentationExpectation.register_id == register_id, service.expectation_clause(user))
    # The worksheet ordering must be applied in SQL before the page boundary.
    query = query.order_by(DocumentationSection.position.asc().nulls_last(),
        source_row.asc().nulls_last(), DocumentationExpectation.created_at.asc(),
        DocumentationExpectation.id)
    if section_id is not None:
        if unsectioned:
            raise HTTPException(422, "Choose a section or unsectioned rows, not both")
        await service.validate_section(db, section_id, register, user)
        query = query.where(DocumentationExpectation.section_id == section_id)
    elif unsectioned:
        query = query.where(DocumentationExpectation.section_id.is_(None))
    if requirement_id:
        query = query.where(DocumentationExpectation.id.in_(select(ExpectationRequirement.expectation_id).where(ExpectationRequirement.requirement_id == requirement_id)))
    if project_id:
        await service.validate_project(db, project_id, register, user)
        query = query.where(or_(DocumentationExpectation.project_id.is_(None), DocumentationExpectation.project_id == project_id))
    if owner_id is not None and unassigned:
        raise HTTPException(422, "Choose an owner or unassigned rows, not both")
    if owner_id is not None:
        query = query.where(DocumentationExpectation.owner_id == owner_id)
    elif unassigned:
        query = query.where(DocumentationExpectation.owner_id.is_(None))
    if category is not None:
        query = query.where(or_(DocumentationExpectation.category.is_(None), DocumentationExpectation.category == "")
            if category == "" else DocumentationExpectation.category == category)
    if q:
        query = query.where(or_(DocumentationExpectation.title.icontains(q, autoescape=True),
            DocumentationExpectation.required_documentation.icontains(q, autoescape=True),
            DocumentationExpectation.source_reference.icontains(q, autoescape=True),
            DocumentationExpectation.description.icontains(q, autoescape=True),
            DocumentationExpectation.document_name.icontains(q, autoescape=True)))
    rows, total = await page(db, query, DocumentationExpectation, skip, limit)
    return {"items": await service.build_expectation_responses(db, rows, user, register), "total": total}


@router.post("/registers/{register_id}/expectations", status_code=201)
async def create_expectation(register_id: uuid.UUID, body: ExpectationCreate, db: DB, user: Actor):
    item = await service.create_expectation(db, await service.get_register(db, register_id, user, "edit"), user, body)
    await db.commit()
    return await service.build_expectation_response(db, item, user)


@router.get("/expectations/{expectation_id}")
async def read_expectation(expectation_id: uuid.UUID, db: DB, user: Actor):
    return await service.build_expectation_response(db, await service.get_expectation(db, expectation_id, user), user)


@router.patch("/expectations/{expectation_id}")
async def patch_expectation(expectation_id: uuid.UUID, body: ExpectationPatch, db: DB, user: Actor):
    item = await service.get_expectation(db, expectation_id, user, "edit", body.revision)
    await service.patch_expectation(db, item, user, body)
    await db.commit()
    return await service.build_expectation_response(db, item, user)


@router.put("/expectations/{expectation_id}/requirements")
async def set_requirements(expectation_id: uuid.UUID, body: RequirementLinks, db: DB, user: Actor):
    item = await service.get_expectation(db, expectation_id, user, "edit", body.revision)
    await service.replace_requirements(db, item, user, body)
    await db.commit()
    return await service.build_expectation_response(db, item, user)


@router.put("/expectations/{expectation_id}/coverage")
async def set_coverage(expectation_id: uuid.UUID, body: CoverageLinks, db: DB, user: Actor):
    item = await service.get_expectation(db, expectation_id, user, "edit", body.revision)
    await service.replace_coverage(db, item, user, body)
    await db.commit()
    return await service.build_expectation_response(db, item, user)


@router.post("/expectations/{expectation_id}/review")
async def review(expectation_id: uuid.UUID, body: CoverageReview, db: DB, user: Actor):
    item = await service.get_expectation(db, expectation_id, user, "approve", body.revision)
    await service.review_coverage(db, item, user, body)
    await db.commit()
    return await service.build_expectation_response(db, item, user)


@router.put("/expectations/{expectation_id}/references")
async def set_references(expectation_id: uuid.UUID, body: ReferenceLinks, db: DB, user: Actor):
    item = await service.get_expectation(db, expectation_id, user, "edit", body.revision)
    await service.replace_references(db, item, user, body)
    await db.commit()
    return await service.build_expectation_response(db, item, user)


@router.get("/registers/{register_id}/reference-options")
async def reference_options(register_id: uuid.UUID, db: DB, user: Actor):
    register = await service.get_register(db, register_id, user)
    output = {"components": [], "changes": []}
    for model, key in ((Component, "components"), (ChangeEntry, "changes")):
        rows = (await db.scalars(select(model).join(ComponentRegister, ComponentRegister.id == model.register_id)
            .where(tenant_clause(ComponentRegister, user), ComponentRegister.jurisdiction_id == register.jurisdiction_id)
            .order_by(model.created_at.desc(), model.id))).all()
        output[key] = [{"id": item.id, "label": item.component_uid if model is Component else item.title,
            **({"version": item.version} if model is Component else {"status": item.status})} for item in rows]
    return output


@router.get("/registers/{register_id}/evidence-groups")
async def evidence_groups(register_id: uuid.UUID, db: DB, user: Actor,
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)):
    await service.get_register(db, register_id, user)
    query = select(EvidenceGroup).join(PreparationEvidence, PreparationEvidence.id == EvidenceGroup.current_evidence_id)
    query = query.where(EvidenceGroup.register_id == register_id, tenant_clause(PreparationEvidence, user), access_clause(PreparationEvidence, user, "view"))
    rows, total = await page(db, query, EvidenceGroup, skip, limit)
    return {"items": [await service.build_group_response(db, item, user) for item in rows], "total": total}


@router.post("/registers/{register_id}/evidence-groups", status_code=201)
async def create_evidence_group(register_id: uuid.UUID, body: GroupCreate, db: DB, user: Actor):
    register = await service.get_register(db, register_id, user, "edit")
    await service.checked_evidence(db, body.evidence_id, user, current=True)
    if await db.scalar(select(EvidenceGroupVersion.group_id).where(EvidenceGroupVersion.evidence_id == body.evidence_id)):
        raise HTTPException(409, "This evidence version already has a stable evidence identity")
    group = EvidenceGroup(id=uuid.uuid4(), register_id=register.id, title=body.title,
        current_evidence_id=body.evidence_id, revision=1, created_by=user.id)
    db.add(group)
    await db.flush()
    db.add(EvidenceGroupVersion(group_id=group.id, evidence_id=body.evidence_id, version=1))
    await service.advance_register(db, register, user, "create_evidence_group", {"evidence_group_id": str(group.id)})
    await db.commit()
    return await service.build_group_response(db, group, user)


@router.post("/evidence-groups/{group_id}/versions")
async def add_evidence_version(group_id: uuid.UUID, body: GroupVersion, db: DB, user: Actor):
    group = await db.scalar(select(EvidenceGroup).where(EvidenceGroup.id == group_id))
    if group is None:
        raise HTTPException(404, "Not found")
    await service.get_register(db, group.register_id, user, "edit")
    await db.execute(select(EvidenceGroup.id).where(EvidenceGroup.id == group_id).with_for_update())
    await db.refresh(group)
    service.check_revision(group, body.revision)
    await service.checked_evidence(db, group.current_evidence_id, user)
    await service.add_group_version(db, group, user, body.evidence_id)
    await db.commit()
    return await service.build_group_response(db, group, user)


@router.get("/registers/{register_id}/audit-fields")
async def audit_fields(register_id: uuid.UUID, project_id: uuid.UUID, db: DB, user: Actor):
    register = await service.get_register(db, register_id, user)
    await service.validate_project(db, project_id, register, user)
    rows = (await db.scalars(select(PreparationCase).where(PreparationCase.project_id == project_id,
        PreparationCase.kind == "audit", PreparationCase.jurisdiction_id == register.jurisdiction_id,
        tenant_clause(PreparationCase, user), access_clause(PreparationCase, user, "view")))).all()
    return {"cases": [{"id": case.id, "name": case.name, "revision": case.revision,
        "fields": [{"key": field.key, "label": field.label, "type": field.type} for field in fields_for(case)]} for case in rows]}


@router.get("/registers/{register_id}/auditor-requests")
async def auditor_requests(register_id: uuid.UUID, db: DB, user: Actor,
    project_id: uuid.UUID | None = None, list_revision: str | None = Query(None, max_length=100),
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)):
    register = await service.get_register(db, register_id, user)
    query = select(AuditorRequestMapping).where(AuditorRequestMapping.register_id == register_id, service.request_clause(user))
    if project_id:
        await service.validate_project(db, project_id, register, user)
        query = query.where(AuditorRequestMapping.project_id == project_id)
    if list_revision is not None:
        query = query.where(AuditorRequestMapping.list_revision == list_revision)
    rows, total = await page(db, query, AuditorRequestMapping, skip, limit)
    return {"items": [await service.build_request_response(db, row, user) for row in rows], "total": total}


@router.post("/registers/{register_id}/auditor-requests", status_code=201)
async def create_auditor_request(register_id: uuid.UUID, body: AuditorRequestCreate, db: DB, user: Actor):
    row = await service.create_auditor_request(db, await service.get_register(db, register_id, user, "edit"), user, body)
    await db.commit()
    return await service.build_request_response(db, row, user)


@router.patch("/auditor-requests/{request_id}")
async def update_auditor_request(request_id: uuid.UUID, body: AuditorRequestPatch, db: DB, user: Actor):
    row = await service.get_request(db, request_id, user, "edit", body.revision)
    await service.patch_auditor_request(db, row, user, body)
    await db.commit()
    return await service.build_request_response(db, row, user)


@router.get("/registers/{register_id}/reconciliation")
async def reconcile(register_id: uuid.UUID, project_id: uuid.UUID, db: DB, user: Actor,
    list_revision: str | None = Query(None, max_length=100)):
    register = await service.get_register(db, register_id, user)
    return await service.reconciliation(db, register, user, project_id, list_revision)


@router.get("/registers/{register_id}/process-options")
async def process_options(register_id: uuid.UUID, db: DB, user: Actor,
    q: str = Query("", max_length=255), skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100)):
    from app.services.documentation_processes import process_options as options
    register = await service.get_register(db, register_id, user)
    return await options(db, register, user, q, skip, limit)


@router.put("/registers/{register_id}/process")
async def set_process(register_id: uuid.UUID, body: RegisterProcessPut, db: DB, user: Actor):
    from app.services.documentation_processes import set_register_process
    register = await service.get_register(db, register_id, user, "edit", body.revision)
    await set_register_process(db, register, user, body)
    await db.commit()
    return await service.register_response(db, register, user)


@router.get("/registers/{register_id}/process-targets")
async def process_targets(register_id: uuid.UUID, db: DB, user: Actor,
    q: str = Query("", max_length=255), skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100)):
    from app.services.documentation_processes import process_targets as targets
    register = await service.get_register(db, register_id, user)
    return await targets(db, register, user, q, skip, limit)


@router.put("/expectations/{expectation_id}/process-targets")
async def match_process_targets(expectation_id: uuid.UUID, body: ProcessTargetsPut, db: DB, user: Actor):
    from app.services.documentation_processes import replace_process_targets
    item = await service.get_expectation(db, expectation_id, user, "edit", body.revision)
    register = await service.get_register(db, item.register_id, user, "edit")
    await replace_process_targets(db, item, register, user, body)
    await db.commit()
    return await service.build_expectation_response(db, item, user)


@router.get("/expectations/{expectation_id}/review-options")
async def row_review_options(expectation_id: uuid.UUID, db: DB, user: Actor,
    q: str = Query("", max_length=255), skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100)):
    from app.services.documentation_processes import review_options
    item = await service.get_expectation(db, expectation_id, user)
    register = await service.get_register(db, item.register_id, user)
    return await review_options(db, register, user, q, skip, limit, item.project_id)


@router.put("/expectations/{expectation_id}/review-process")
async def set_row_review(expectation_id: uuid.UUID, body: RowReviewPut, db: DB, user: Actor):
    from app.services.documentation_processes import set_row_review as update_review
    item = await service.get_expectation(db, expectation_id, user, "edit", body.revision)
    register = await service.get_register(db, item.register_id, user, "edit")
    await update_review(db, item, register, user, body)
    await db.commit()
    return await service.build_expectation_response(db, item, user)


@router.get("/expectations/{expectation_id}/process-targets")
async def row_process_targets(expectation_id: uuid.UUID, db: DB, user: Actor,
    q: str = Query("", max_length=255), skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100)):
    from app.services.documentation_processes import effective_process_register, process_targets
    item = await service.get_expectation(db, expectation_id, user)
    register = await service.get_register(db, item.register_id, user)
    return await process_targets(db, effective_process_register(register, item), user, q, skip, limit)
