import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.api.tenant import apply_org_scope, get_active_user_in_org_or_404, get_org_owned_or_404
from app.database import get_db
from app.models.jurisdiction import Jurisdiction
from app.models.preparation import PreparationCase, PreparationResponse, PreparationTemplate
from app.models.program import CertificationProject
from app.models.user import User
from app.schemas.preparation import (
    CaseCreate,
    CaseOut,
    CasePatch,
    RequirementsPreview,
    ResponsePut,
    ReuseRequest,
    ReuseSuggestion,
    RevisionRequest,
    SpreadsheetPreview,
    TemplateCreate,
    TemplateFields,
    TemplateOut,
    TemplatePatch,
)
from app.schemas.preparation_quality import ImportEnhancementRequest, ImportEnhancementResponse
from app.services.access import (
    effective_permissions,
    initialize_access,
    protect_child,
    require_access,
)
from app.services.audit import log_action
from app.services.preparation import (
    advance_case,
    audit_response_snapshot,
    build_case_response,
    checked_evidence_problem,
    create_private_case,
    ensure_answer,
    field_for,
    fields_for,
    get_case,
    get_valid_evidence,
    response_evidence,
    save_response,
    set_case_originals,
    valid_value,
)
from app.services.preparation_import import MAX_UPLOAD_BYTES, preview_spreadsheet
from app.services.preparation_requirements import (
    checked_template_fields,
    ensure_template_jurisdiction,
    requirements_preview,
)
from app.services.preparation_starters import starter_templates

router = APIRouter(prefix="/api/v1/preparation", tags=["preparation"])
MANAGER = ("manager", "admin")
EDITOR = ("contributor", "manager", "admin")


def template_out(template: PreparationTemplate) -> TemplateOut:
    return TemplateOut(
        id=template.id,
        name=template.name,
        description=template.description,
        kind=template.kind,
        fields=json.loads(template.fields_json),
        revision=template.revision,
        active=template.active,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


async def validate_project(
    db: AsyncSession, project_id: uuid.UUID | None, jurisdiction_id: uuid.UUID, user: User
):
    if project_id is None:
        return
    project = await get_org_owned_or_404(db, CertificationProject, project_id, user)
    if project.jurisdiction_id != jurisdiction_id:
        raise HTTPException(422, "Project market differs from form")


@router.get("/templates")
async def list_templates(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = apply_org_scope(select(PreparationTemplate), PreparationTemplate, user)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    templates = (
        (
            await db.execute(
                query.order_by(PreparationTemplate.created_at.desc(), PreparationTemplate.id)
                .offset(skip)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return {"items": [template_out(item) for item in templates], "total": total}


@router.post("/templates", response_model=TemplateOut, status_code=201)
async def create_template(
    body: TemplateCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(*MANAGER)),
):
    template = PreparationTemplate(
        organization_id=user.organization_id,
        name=body.name.strip(),
        description=body.description,
        kind=body.kind,
        fields_json=json.dumps(await checked_template_fields(db, user, body.fields)),
        created_by=user.id,
    )
    if not template.name:
        raise HTTPException(422, "Name is required")
    db.add(template)
    await db.flush()
    await log_action(
        db, user, "create", "preparation_template", str(template.id), new_value={"revision": 1}
    )
    await db.commit()
    await db.refresh(template)
    return template_out(template)


@router.post("/templates/import-preview", response_model=SpreadsheetPreview)
async def import_template_preview(
    file: UploadFile = File(...),
    sheet_name: str | None = Form(default=None, max_length=255),
    user: User = Depends(require_role(*MANAGER)),
):
    try:
        content = await file.read(MAX_UPLOAD_BYTES + 1)
        return await run_in_threadpool(
            preview_spreadsheet, content, file.filename or "", sheet_name
        )
    finally:
        await file.close()


@router.post("/templates/import-enhancements", response_model=ImportEnhancementResponse)
async def import_template_enhancements(
    body: ImportEnhancementRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(*MANAGER)),
):
    if not body.external_processing_confirmed:
        raise HTTPException(422, "Confirm external Jev processing before checking the preview")
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.services.installation_settings import resolve_installation_settings
    from app.services.preparation_quality import enhance_import

    settings = await resolve_installation_settings(db)
    # Provider batches run concurrently; each settings read owns a separate session.
    sessions = async_sessionmaker(bind=db.bind, expire_on_commit=False)

    async def should_continue():
        async with sessions() as fresh_db:
            current = await resolve_installation_settings(fresh_db)
            return (
                current.jev_enabled
                and bool(current.typesafe_api_key)
                and current.jev_model == settings.jev_model
                and current.jev_settings_revision == settings.jev_settings_revision
            )

    return await enhance_import(body, settings, should_continue=should_continue)


@router.get("/templates/import-template")
async def download_import_template(user: User = Depends(require_role(*MANAGER))):
    return FileResponse(
        Path(__file__).resolve().parents[1] / "templates" / "preparation-question-template.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="preparation-question-template.xlsx",
    )


@router.get("/templates/requirements-preview", response_model=RequirementsPreview)
async def preview_requirement_questions(
    document_id: uuid.UUID,
    jurisdiction_id: uuid.UUID,
    version_id: uuid.UUID | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(*MANAGER)),
):
    return await requirements_preview(
        db, user, document_id, jurisdiction_id, version_id, skip, limit
    )


@router.patch("/templates/{template_id}", response_model=TemplateOut)
async def patch_template(
    template_id: uuid.UUID,
    body: TemplatePatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(*MANAGER)),
):
    template = await get_org_owned_or_404(db, PreparationTemplate, template_id, user)
    changes = body.model_dump(exclude_unset=True, exclude={"expected_revision"})
    if "name" in changes:
        changes["name"] = (changes["name"] or "").strip()
        if not changes["name"]:
            raise HTTPException(422, "Name is required")
    if "fields" in changes:
        if changes["fields"] is None:
            raise HTTPException(422, "Fields cannot be null")
        changes.pop("fields")
        changes["fields_json"] = json.dumps(
            await checked_template_fields(db, user, body.fields, json.loads(template.fields_json))
        )
    if any(changes.get(key) is None for key in ("kind", "active") if key in changes):
        raise HTTPException(422, "Kind and active cannot be null")
    result = await db.execute(
        update(PreparationTemplate)
        .where(
            PreparationTemplate.id == template.id,
            PreparationTemplate.revision == body.expected_revision,
        )
        .values(**changes, revision=body.expected_revision + 1, updated_at=datetime.now(UTC))
    )
    if result.rowcount != 1:
        raise HTTPException(409, "Saved blank form changed; reload before editing")
    await log_action(
        db,
        user,
        "update",
        "preparation_template",
        str(template.id),
        new_value={"revision": body.expected_revision + 1},
    )
    await db.commit()
    await db.refresh(template)
    return template_out(template)


@router.get("/starters")
async def starters(user: User = Depends(get_current_user)):
    return {"items": starter_templates()}


@router.post("/cases", response_model=CaseOut, status_code=201)
async def create_case(
    body: CaseCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(*MANAGER)),
):
    template = None
    if body.template_id is not None:
        template = await get_org_owned_or_404(db, PreparationTemplate, body.template_id, user)
        if not template.active:
            raise HTTPException(422, "Saved blank form is inactive")
        ensure_template_jurisdiction(template.fields_json, body.jurisdiction_id)
    jurisdiction = await db.get(Jurisdiction, body.jurisdiction_id)
    if jurisdiction is None or not jurisdiction.active:
        raise HTTPException(422, "Jurisdiction is inactive or missing")
    await validate_project(db, body.project_id, body.jurisdiction_id, user)
    await get_active_user_in_org_or_404(db, body.owner_id, user)
    if not body.name.strip():
        raise HTTPException(422, "Name is required")
    if template is None:
        case = await create_private_case(
            db,
            user,
            jurisdiction_id=body.jurisdiction_id,
            name=body.name.strip(),
            owner_id=body.owner_id,
            due_date=body.due_date,
            fields=body.fields,
            original_evidence_ids=body.original_evidence_ids,
            project_id=body.project_id,
            visibility=body.visibility,
        )
    else:
        case = PreparationCase(
            organization_id=user.organization_id,
            template_id=template.id,
            template_name=template.name,
            template_revision=template.revision,
            fields_json=template.fields_json,
            kind=template.kind,
            jurisdiction_id=body.jurisdiction_id,
            project_id=body.project_id,
            name=body.name.strip(),
            owner_id=body.owner_id,
            due_date=body.due_date,
            created_by=user.id,
        )
        db.add(case)
        await db.flush()
        await initialize_access(db, "preparation_case", case.id, user, visibility=body.visibility)
        if body.project_id is not None:
            await protect_child(
                db,
                "certification_project",
                body.project_id,
                "preparation_case",
                case.id,
                user,
            )
        if body.original_evidence_ids:
            await set_case_originals(db, case, body.original_evidence_ids, user)
    await log_action(
        db, user, "create", "preparation_case", str(case.id), new_value={"revision": 1}
    )
    await db.commit()
    await db.refresh(case)
    return await build_case_response(db, case, user=user)


@router.get("/cases")
async def list_cases(
    jurisdiction_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    kind: str | None = None,
    status: str | None = None,
    q: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = apply_org_scope(select(PreparationCase), PreparationCase, user)
    if project_id:
        await get_org_owned_or_404(db, CertificationProject, project_id, user)
        await require_access(db, "certification_project", project_id, user)
        query = query.where(PreparationCase.project_id == project_id)
    if jurisdiction_id:
        query = query.where(PreparationCase.jurisdiction_id == jurisdiction_id)
    if kind:
        query = query.where(PreparationCase.kind == kind)
    if status:
        query = query.where(PreparationCase.status == status)
    if q:
        query = query.where(PreparationCase.name.ilike(f"%{q[:200]}%"))
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    cases = (
        (
            await db.execute(
                query.order_by(PreparationCase.created_at.desc(), PreparationCase.id)
                .offset(skip)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    evidence_check_cache = {}
    return {
        "items": [
            await build_case_response(db, case, evidence_check_cache, user=user) for case in cases
        ],
        "total": total,
    }


@router.get("/cases/{case_id}", response_model=CaseOut)
async def read_case(
    case_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await build_case_response(db, await get_case(db, case_id, user), user=user)


@router.patch("/cases/{case_id}", response_model=CaseOut)
async def patch_case(
    case_id: uuid.UUID,
    body: CasePatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(*MANAGER)),
):
    case = await get_case(db, case_id, user, "edit")
    changes = body.model_dump(exclude_unset=True, exclude={"expected_revision"})
    if case.status == "archived" and changes != {"status": "active"}:
        raise HTTPException(409, "Archived form may only be reactivated")
    if "name" in changes:
        changes["name"] = (changes["name"] or "").strip()
        if not changes["name"]:
            raise HTTPException(422, "Name is required")
    if "owner_id" in changes:
        await get_active_user_in_org_or_404(db, changes["owner_id"], user)
    if "project_id" in changes:
        await validate_project(db, changes["project_id"], case.jurisdiction_id, user)
    if changes.get("status") is None and "status" in changes:
        raise HTTPException(422, "Status cannot be null")
    if "fields" in changes:
        if case.template_id is not None or body.fields is None:
            raise HTTPException(422, "Only private form questions can be edited here")
        TemplateFields(fields=body.fields)
        old = {item.key: item for item in fields_for(case)}
        new = {item.key: item for item in body.fields}
        responses = (
            await db.scalars(
                select(PreparationResponse).where(PreparationResponse.case_id == case.id)
            )
        ).all()
        for response in responses:
            original = old[response.field_key]
            replacement = new.get(response.field_key)
            if (
                replacement is None
                or (response.value_json is not None or response.not_applicable_reason)
                and (
                    replacement.type != original.type
                    or replacement.options != original.options
                    or replacement.source != original.source
                )
            ):
                raise HTTPException(
                    422,
                    f"Answered question {response.field_key} cannot change in meaning",
                )
        checked_fields = await checked_template_fields(
            db, user, body.fields, json.loads(case.fields_json)
        )
        changes.pop("fields")
        changes["fields_json"] = json.dumps(checked_fields)
        ensure_template_jurisdiction(changes["fields_json"], case.jurisdiction_id)
        if changes["fields_json"] != case.fields_json:
            for response in responses:
                response.accepted_at = None
                response.accepted_by = None
    if "original_evidence_ids" in changes:
        if body.original_evidence_ids is None:
            raise HTTPException(422, "Original evidence IDs cannot be null")
        await set_case_originals(db, case, body.original_evidence_ids, user)
        changes.pop("original_evidence_ids")
        changes["original_evidence_ids_json"] = case.original_evidence_ids_json
    await advance_case(db, case, body.expected_revision, allow_archived=case.status == "archived")
    for key, value in changes.items():
        setattr(case, key, value)
    await log_action(
        db,
        user,
        "update",
        "preparation_case",
        str(case.id),
        new_value={
            "revision": case.revision,
            **{key: str(value) for key, value in changes.items()},
        },
    )
    await db.commit()
    await db.refresh(case)
    return await build_case_response(db, case, user=user)


@router.put("/cases/{case_id}/responses/{field_key}", response_model=CaseOut)
async def put_response(
    case_id: uuid.UUID,
    field_key: str,
    body: ResponsePut,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(*EDITOR)),
):
    case = await get_case(db, case_id, user, "edit")
    field = field_for(case, field_key)
    evidence = await get_valid_evidence(db, body.evidence_ids, user)
    prior = (
        await db.execute(
            select(PreparationResponse).where(
                PreparationResponse.case_id == case.id, PreparationResponse.field_key == field.key
            )
        )
    ).scalar_one_or_none()
    if prior:
        for item in (await response_evidence(db, [prior.id])).get(prior.id, []):
            await require_access(db, "preparation_evidence", item.id, user)
        if prior.reused_from_case_id:
            await require_access(db, "preparation_case", prior.reused_from_case_id, user)
    before = await audit_response_snapshot(db, prior)
    ensure_answer(field, body.value, body.not_applicable_reason, evidence)
    # The edit access check holds the case row lock. Identical autosave retries
    # honour revision/lifecycle guards but do not revoke an accepted answer.
    if case.status == "archived":
        raise HTTPException(409, "Form is archived")
    if case.revision != body.expected_revision:
        raise HTTPException(409, "Form changed; reload before editing")
    saved_value = before["value"] if before else None
    saved_reason = before["not_applicable_reason"] if before else None
    saved_evidence = before["evidence_ids"] if before else []
    if (
        saved_value == body.value
        and saved_reason == ((body.not_applicable_reason or "").strip() or None)
        and saved_evidence == sorted(str(item.id) for item in evidence)
    ):
        return await build_case_response(db, case, user=user)
    for item in evidence:
        await protect_child(db, "preparation_case", case.id, "preparation_evidence", item.id, user)
    saved = await save_response(
        db,
        case,
        field,
        body.expected_revision,
        value=body.value,
        reason=body.not_applicable_reason,
        evidence=evidence,
    )
    await log_action(
        db,
        user,
        "update",
        "preparation_response",
        f"{case.id}:{field.key}",
        old_value=before,
        new_value={"revision": case.revision, "response": await audit_response_snapshot(db, saved)},
    )
    await db.commit()
    await db.refresh(case)
    return await build_case_response(db, case, user=user)


@router.post("/cases/{case_id}/responses/{field_key}/accept", response_model=CaseOut)
async def accept_response(
    case_id: uuid.UUID,
    field_key: str,
    body: RevisionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(*MANAGER)),
):
    case = await get_case(db, case_id, user, "approve")
    field = field_for(case, field_key)
    response = (
        await db.execute(
            select(PreparationResponse).where(
                PreparationResponse.case_id == case.id, PreparationResponse.field_key == field.key
            )
        )
    ).scalar_one_or_none()
    if response is None:
        raise HTTPException(422, "Response is missing")
    evidence = (await response_evidence(db, [response.id])).get(response.id, [])
    value = json.loads(response.value_json) if response.value_json is not None else None
    reason = (response.not_applicable_reason or "").strip()
    if not reason and not (
        bool(evidence) if field.type == "evidence" else valid_value(field, value)
    ):
        raise HTTPException(422, "Response is missing or invalid")
    for item in evidence:
        await require_access(db, "preparation_evidence", item.id, user)
        if await checked_evidence_problem(item, datetime.now(UTC).date()):
            raise HTTPException(422, "Evidence is not currently valid")
    before = await audit_response_snapshot(db, response)
    await advance_case(db, case, body.expected_revision)
    response.accepted_by = user.id
    response.accepted_at = datetime.now(UTC)
    await log_action(
        db,
        user,
        "accept",
        "preparation_response",
        f"{case.id}:{field.key}",
        old_value=before,
        new_value={
            "revision": case.revision,
            "response": await audit_response_snapshot(db, response),
        },
    )
    await db.commit()
    await db.refresh(case)
    return await build_case_response(db, case, user=user)


@router.get("/cases/{case_id}/reuse")
async def reuse_suggestions(
    case_id: uuid.UUID,
    field_key: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target = await get_case(db, case_id, user)
    field = field_for(target, field_key)
    if not field.reuse_key:
        return {"items": []}
    sources = (
        (
            await db.execute(
                apply_org_scope(
                    select(PreparationCase)
                    .where(PreparationCase.id != target.id, PreparationCase.status != "archived")
                    .order_by(PreparationCase.created_at.desc())
                    .limit(500),
                    PreparationCase,
                    user,
                )
            )
        )
        .scalars()
        .all()
    )
    if not sources:
        return {"items": []}
    source_fields = {
        source.id: [
            item
            for item in fields_for(source)
            if item.reuse_key == field.reuse_key and item.type == field.type
        ]
        for source in sources
    }
    keys = {item.key for fields in source_fields.values() for item in fields}
    if not keys:
        return {"items": []}
    responses = (
        (
            await db.execute(
                select(PreparationResponse).where(
                    PreparationResponse.case_id.in_([source.id for source in sources]),
                    PreparationResponse.field_key.in_(keys),
                )
            )
        )
        .scalars()
        .all()
    )
    response_lookup = {(response.case_id, response.field_key): response for response in responses}
    evidence_lookup = await response_evidence(db, [response.id for response in responses])
    evidence_check_cache = {}
    today = datetime.now(UTC).date()
    items = []
    for source in sources:
        for source_field in source_fields[source.id]:
            response = response_lookup.get((source.id, source_field.key))
            if response is None or response.not_applicable_reason:
                continue
            evidence = evidence_lookup.get(response.id, [])
            value = json.loads(response.value_json) if response.value_json is not None else None
            if not (bool(evidence) if field.type == "evidence" else valid_value(field, value)):
                continue
            invalid_evidence = False
            for item in evidence:
                if "view" not in await effective_permissions(
                    db, "preparation_evidence", item.id, user
                ):
                    invalid_evidence = True
                    break
                if await checked_evidence_problem(item, today, evidence_check_cache):
                    invalid_evidence = True
                    break
            if invalid_evidence:
                continue
            items.append(
                ReuseSuggestion(
                    source_case_id=source.id,
                    source_case_name=source.name,
                    source_jurisdiction_id=source.jurisdiction_id,
                    source_field_key=source_field.key,
                    value=value,
                    accepted_at=response.accepted_at,
                )
            )
            if len(items) >= 100:
                return {"items": items}
    return {"items": items}


@router.post("/cases/{case_id}/responses/{field_key}/reuse", response_model=CaseOut)
async def reuse_response(
    case_id: uuid.UUID,
    field_key: str,
    body: ReuseRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(*EDITOR)),
):
    target = await get_case(db, case_id, user, "edit")
    source = await get_case(db, body.source_case_id, user)
    if target.id == source.id or source.status == "archived":
        raise HTTPException(422, "Source form is unavailable")
    await protect_child(db, "preparation_case", source.id, "preparation_case", target.id, user)
    target_field = field_for(target, field_key)
    source_field = field_for(source, body.source_field_key)
    if (
        not target_field.reuse_key
        or target_field.reuse_key != source_field.reuse_key
        or target_field.type != source_field.type
    ):
        raise HTTPException(422, "Fields are not reusable")
    response = (
        await db.execute(
            select(PreparationResponse).where(
                PreparationResponse.case_id == source.id,
                PreparationResponse.field_key == source_field.key,
            )
        )
    ).scalar_one_or_none()
    if response is None or response.not_applicable_reason:
        raise HTTPException(422, "Source response is unavailable")
    evidence = (await response_evidence(db, [response.id])).get(response.id, [])
    value = json.loads(response.value_json) if response.value_json is not None else None
    if not (
        bool(evidence) if target_field.type == "evidence" else valid_value(target_field, value)
    ):
        raise HTTPException(422, "Source response is invalid")
    for item in evidence:
        await require_access(db, "preparation_evidence", item.id, user)
        if await checked_evidence_problem(item, datetime.now(UTC).date()):
            raise HTTPException(422, "Source evidence is not currently valid")
    if len(await get_valid_evidence(db, [item.id for item in evidence], user)) != len(evidence):
        raise HTTPException(404, "Evidence not found")
    prior = (
        await db.execute(
            select(PreparationResponse).where(
                PreparationResponse.case_id == target.id,
                PreparationResponse.field_key == target_field.key,
            )
        )
    ).scalar_one_or_none()
    if prior:
        for item in (await response_evidence(db, [prior.id])).get(prior.id, []):
            await require_access(db, "preparation_evidence", item.id, user)
        if prior.reused_from_case_id:
            await require_access(db, "preparation_case", prior.reused_from_case_id, user)
    before = await audit_response_snapshot(db, prior)
    for item in evidence:
        await protect_child(
            db, "preparation_case", target.id, "preparation_evidence", item.id, user
        )
    saved = await save_response(
        db,
        target,
        target_field,
        body.expected_revision,
        value=value,
        reason=None,
        evidence=evidence,
        reused_from_case_id=source.id,
        reused_from_field_key=source_field.key,
    )
    await log_action(
        db,
        user,
        "reuse",
        "preparation_response",
        f"{target.id}:{field_key}",
        old_value=before,
        new_value={
            "revision": target.revision,
            "source_case_id": str(source.id),
            "source_case_revision": source.revision,
            "source_field_key": source_field.key,
            "response": await audit_response_snapshot(db, saved),
        },
    )
    await db.commit()
    await db.refresh(target)
    return await build_case_response(db, target, user=user)
