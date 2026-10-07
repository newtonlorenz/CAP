"""HTTP transaction boundary for flexible application preparation and tracking."""

import io
import json
import uuid
import zipfile
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from app.api.deps import get_current_user, require_role
from app.api.tenant import (
    apply_org_scope,
    get_active_user_in_org_or_404,
    get_org_owned_or_404,
    org_clause,
)
from app.database import get_db
from app.models.application import (
    Application,
    ApplicationComponent,
    ApplicationFollowup,
    ApplicationSnapshot,
)
from app.models.jurisdiction import Jurisdiction
from app.models.preparation import (
    PreparationCase,
    PreparationEvidence,
    PreparationResponse,
    PreparationResponseEvidence,
    PreparationTemplate,
)
from app.models.user import User
from app.schemas.application import (
    ApplicationCreate,
    ApplicationPatch,
    ComponentCreate,
    ComponentPatch,
    DuplicateComponent,
    FollowupCreate,
    FollowupPatch,
    GuidedApplicationCreate,
    ProfilePatch,
    WorkflowAction,
)
from app.schemas.preparation import TemplateFields
from app.services.access import initialize_access, protect_child, require_access
from app.services.application_profiles import get_profile, patch_profile
from app.services.applications import (
    advance,
    detail,
    get_application,
    require_pack_sources,
    transition,
)
from app.services.audit import log_action
from app.services.preparation import (
    advance_case,
    checked_evidence_problem,
    create_private_case,
    fields_for,
    get_valid_evidence,
    set_case_originals,
)
from app.services.preparation_requirements import (
    checked_template_fields,
    ensure_template_jurisdiction,
)

DB = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]

router = APIRouter(prefix="/api/v1/applications", tags=["applications"])
manager = require_role("manager", "admin")
editor = require_role("contributor", "manager", "admin")
Manager = Annotated[User, Depends(manager)]
Editor = Annotated[User, Depends(editor)]


@router.get("/market-profile")
async def read_market_profile(jurisdiction_id: uuid.UUID, db: DB, user: CurrentUser):
    return await get_profile(db, jurisdiction_id, user)


@router.patch("/market-profile")
async def update_market_profile(body: ProfilePatch, db: DB, user: Manager):
    return await patch_profile(db, body, user)


async def finish(db, user, application, action, changes):
    await db.flush()
    await log_action(
        db,
        user,
        action,
        "application",
        str(application.id),
        new_value={"revision": application.revision, "status": application.status, **changes},
    )
    await db.commit()
    await db.refresh(application)
    return await detail(db, application, user)


async def child(db, model, child_id, application):
    item = (
        await db.scalars(
            select(model).where(model.id == child_id, model.application_id == application.id)
        )
    ).first()
    if item is None:
        raise HTTPException(404, "Application item not found")
    return item


@router.get("")
async def list_applications(
    db: DB,
    user: CurrentUser,
    q: str | None = None,
    status: str | None = None,
    scope: str | None = None,
    jurisdiction_id: uuid.UUID | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    query = apply_org_scope(select(Application), Application, user, action="summary")
    for key, value in (("status", status), ("scope", scope), ("jurisdiction_id", jurisdiction_id)):
        if value:
            query = query.where(getattr(Application, key) == value)
    if scope or jurisdiction_id:
        query = query.where(org_clause(Application, user))
    if q:
        query = query.where(Application.name.ilike(f"%{q[:200]}%"))
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = (
        await db.scalars(
            query.order_by(Application.updated_at.desc(), Application.id).offset(skip).limit(limit)
        )
    ).all()
    evidence_check_cache = {}
    return {
        "items": [await detail(db, item, user, evidence_check_cache) for item in rows],
        "total": total,
    }


@router.post("", status_code=201)
async def create_application(body: ApplicationCreate, db: DB, user: Manager):
    jurisdiction = await db.get(Jurisdiction, body.jurisdiction_id)
    if not jurisdiction or not jurisdiction.active:
        raise HTTPException(422, "Jurisdiction is missing or inactive")
    await get_active_user_in_org_or_404(db, body.owner_id, user)
    row = Application(
        **body.model_dump(exclude={"visibility"}),
        organization_id=user.organization_id,
        created_by=user.id,
    )
    db.add(row)
    await db.flush()
    await initialize_access(db, "application", row.id, user, visibility=body.visibility)
    return await finish(db, user, row, "create", body.model_dump(mode="json"))


@router.post("/guided", status_code=201)
async def create_guided_application(body: GuidedApplicationCreate, db: DB, user: Manager):
    profile = await get_profile(db, body.jurisdiction_id, user)
    if profile["version"] != body.profile_version:
        raise HTTPException(409, "Market profile changed; reload before creating the pack")
    if profile["status"] != "published" and not (
        profile["code"].upper() in {"SE", "SWE"} and not body.items
    ):
        raise HTTPException(422, "This market profile is still a draft")
    allowed = {item["key"]: item for item in profile["items"]}
    for item in body.items:
        if item.profile_item_key:
            source = allowed.get(item.profile_item_key)
            if source is None or source["kind"] != item.kind:
                raise HTTPException(422, "Unknown or mismatched market profile item")
        await get_active_user_in_org_or_404(db, item.owner_id, user)
    await get_active_user_in_org_or_404(db, body.owner_id, user)
    data = body.model_dump(exclude={"profile_version", "setup_answers", "items", "visibility"})
    row = Application(
        **data,
        organization_id=user.organization_id,
        created_by=user.id,
        profile_snapshot_json=json.dumps(profile, default=str),
        setup_answers_json=body.setup_answers.model_dump_json(),
    )
    db.add(row)
    await db.flush()
    await initialize_access(db, "application", row.id, user, visibility=body.visibility)
    for item in body.items:
        db.add(ApplicationComponent(application_id=row.id, **item.model_dump()))
    return await finish(db, user, row, "create_guided", {"profile_version": profile["version"]})


@router.get("/{application_id}")
async def read_application(application_id: uuid.UUID, db: DB, user: CurrentUser):
    return await detail(db, await get_application(db, application_id, user, "summary"), user)


@router.patch("/{application_id}")
async def patch_application(
    application_id: uuid.UUID, body: ApplicationPatch, db: DB, user: Manager
):
    row = await get_application(db, application_id, user, "edit")
    await advance(db, row, body.expected_revision, {"draft"})
    changes = body.model_dump(exclude_unset=True, exclude={"expected_revision"})
    if any(changes.get(key) is None for key in ("name", "scope") if key in changes):
        raise HTTPException(422, "Name and scope cannot be null")
    if "owner_id" in changes:
        await get_active_user_in_org_or_404(db, body.owner_id, user)
    for key, value in changes.items():
        setattr(row, key, value)
    return await finish(db, user, row, "update", body.model_dump(mode="json", exclude_unset=True))


async def validate_component(db, item, application, user):
    await get_active_user_in_org_or_404(db, item.owner_id, user)
    if item.case_id and item.evidence_id:
        raise HTTPException(422, "Choose either a form or a document")
    if (item.kind == "document" and item.case_id) or (item.kind != "document" and item.evidence_id):
        raise HTTPException(
            422, "Forms and annexes link a preparation case; documents link evidence"
        )
    if item.case_id:
        case = await get_org_owned_or_404(db, PreparationCase, item.case_id, user)
        if case.jurisdiction_id != application.jurisdiction_id or case.status == "archived":
            raise HTTPException(422, "Form must be active and in the application jurisdiction")
        await protect_child(
            db, "application", application.id, "preparation_case", item.case_id, user
        )
        evidence_ids = (
            await db.scalars(
                select(PreparationResponseEvidence.evidence_id)
                .join(
                    PreparationResponse,
                    PreparationResponse.id == PreparationResponseEvidence.response_id,
                )
                .where(PreparationResponse.case_id == item.case_id)
            )
        ).all()
        for evidence_id in set(evidence_ids):
            await protect_child(
                db, "preparation_case", item.case_id, "preparation_evidence", evidence_id, user
            )
        for evidence_id in json.loads(case.original_evidence_ids_json or "[]"):
            await protect_child(
                db,
                "preparation_case",
                item.case_id,
                "preparation_evidence",
                uuid.UUID(evidence_id),
                user,
            )
    if item.evidence_id:
        await get_org_owned_or_404(db, PreparationEvidence, item.evidence_id, user)
        await protect_child(
            db, "application", application.id, "preparation_evidence", item.evidence_id, user
        )


async def instantiate_component_form(db, template_id, item, application, user, originals=None):
    template = await get_org_owned_or_404(db, PreparationTemplate, template_id, user)
    if not template.active:
        raise HTTPException(422, "Saved blank form is inactive")
    ensure_template_jurisdiction(template.fields_json, application.jurisdiction_id)
    await get_active_user_in_org_or_404(db, item.owner_id, user)
    verified_originals = await get_valid_evidence(db, originals or [], user)
    case = PreparationCase(
        organization_id=user.organization_id,
        template_id=template.id,
        template_name=template.name,
        template_revision=template.revision,
        fields_json=template.fields_json,
        original_evidence_ids_json=json.dumps([str(value.id) for value in verified_originals]),
        kind=template.kind,
        jurisdiction_id=application.jurisdiction_id,
        name=item.name,
        owner_id=item.owner_id,
        due_date=item.due_date,
        created_by=user.id,
    )
    db.add(case)
    await db.flush()
    # Preserve existing organisation permissions explicitly so contextual evidence
    # can inherit the form without a contributor having to establish its owner.
    await initialize_access(db, "preparation_case", case.id, user, visibility="organisation")
    await log_action(
        db,
        user,
        "create",
        "preparation_case",
        str(case.id),
        new_value={"application_id": str(application.id), "revision": 1},
    )
    return case.id


async def instantiate_private_form(db, fields, originals, item, application, user):
    case = await create_private_case(
        db,
        user,
        jurisdiction_id=application.jurisdiction_id,
        name=item.name,
        owner_id=item.owner_id,
        due_date=item.due_date,
        fields=fields,
        original_evidence_ids=originals,
    )
    await log_action(
        db,
        user,
        "create",
        "preparation_case",
        str(case.id),
        new_value={"application_id": str(application.id), "revision": 1},
    )
    return case.id


@router.post("/{application_id}/components", status_code=201)
async def add_component(application_id: uuid.UUID, body: ComponentCreate, db: DB, user: Manager):
    row = await get_application(db, application_id, user, "edit")
    await advance(db, row, body.expected_revision, {"draft"})
    count = await db.scalar(
        select(func.count())
        .select_from(ApplicationComponent)
        .where(ApplicationComponent.application_id == row.id)
    )
    if count >= 200:
        raise HTTPException(422, "Application may contain at most 200 forms or documents")
    if sum(value is not None for value in (body.template_id, body.case_id, body.form_fields)) > 1:
        raise HTTPException(422, "Choose one form source")
    if body.original_evidence_ids and body.form_fields is None and body.template_id is None:
        raise HTTPException(422, "Original evidence requires a new form")
    if body.form_fields is not None and (body.kind == "document" or body.evidence_id):
        raise HTTPException(422, "Private fields require a form or annex")
    data = body.model_dump(
        exclude={"expected_revision", "template_id", "form_fields", "original_evidence_ids"}
    )
    item = ApplicationComponent(application_id=row.id, **data)
    if body.template_id:
        item.case_id = await instantiate_component_form(
            db, body.template_id, item, row, user, body.original_evidence_ids
        )
    if body.form_fields is not None:
        item.case_id = await instantiate_private_form(
            db, body.form_fields, body.original_evidence_ids, item, row, user
        )
    await validate_component(db, item, row, user)
    db.add(item)
    await db.flush()
    return await finish(
        db,
        user,
        row,
        "add_component",
        {"component_id": str(item.id), **body.model_dump(mode="json")},
    )


@router.patch("/{application_id}/components/{component_id}")
async def patch_component(
    application_id: uuid.UUID,
    component_id: uuid.UUID,
    body: ComponentPatch,
    db: DB,
    user: Manager,
):
    row = await get_application(db, application_id, user, "edit")
    await advance(db, row, body.expected_revision, {"draft"})
    item = await child(db, ApplicationComponent, component_id, row)
    if item.case_id:
        await require_access(db, PreparationCase, item.case_id, user)
    if item.evidence_id:
        await require_access(db, PreparationEvidence, item.evidence_id, user)
    changes = body.model_dump(
        exclude_unset=True,
        exclude={
            "expected_revision",
            "expected_case_revision",
            "template_id",
            "form_fields",
            "original_evidence_ids",
        },
    )
    if any(
        changes.get(key) is None
        for key in ("name", "kind", "required", "included")
        if key in changes
    ):
        raise HTTPException(422, "Name, kind, required and included cannot be null")
    for key, value in changes.items():
        setattr(item, key, value)
    if body.template_id:
        if body.case_id or body.evidence_id or item.evidence_id or item.kind == "document":
            raise HTTPException(422, "Choose either a saved blank form or an existing form")
        item.case_id = await instantiate_component_form(
            db, body.template_id, item, row, user, body.original_evidence_ids
        )
    if body.form_fields is not None:
        if body.template_id or body.case_id or body.evidence_id or item.kind == "document":
            raise HTTPException(422, "Private fields require a form or annex")
        if item.case_id:
            case = await get_org_owned_or_404(db, PreparationCase, item.case_id, user)
            await require_access(db, PreparationCase, case.id, user, "edit")
            if case.template_id is not None:
                raise HTTPException(
                    422, "Questions copied from a saved blank form cannot be edited here"
                )
            if body.expected_case_revision is None:
                raise HTTPException(
                    422, "Expected case revision is required when editing form questions"
                )
            TemplateFields(fields=body.form_fields)
            old = {field.key: field for field in fields_for(case)}
            new = {field.key: field for field in body.form_fields}
            responses = (
                await db.scalars(
                    select(PreparationResponse).where(PreparationResponse.case_id == case.id)
                )
            ).all()
            for response in responses:
                replacement = new.get(response.field_key)
                original = old[response.field_key]
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
                db, user, body.form_fields, json.loads(case.fields_json)
            )
            new_json = json.dumps(checked_fields)
            ensure_template_jurisdiction(new_json, case.jurisdiction_id)
            await advance_case(db, case, body.expected_case_revision)
            if new_json != case.fields_json:
                case.fields_json = new_json
                for response in responses:
                    response.accepted_by = None
                    response.accepted_at = None
            if body.original_evidence_ids is not None:
                originals = await get_valid_evidence(db, body.original_evidence_ids, user)
                for original in originals:
                    await protect_child(
                        db, "preparation_case", case.id, "preparation_evidence", original.id, user
                    )
                case.original_evidence_ids_json = json.dumps([str(value.id) for value in originals])
        else:
            item.case_id = await instantiate_private_form(
                db, body.form_fields, body.original_evidence_ids or [], item, row, user
            )
    elif body.original_evidence_ids is not None and body.template_id is None:
        if not item.case_id:
            raise HTTPException(422, "Original evidence requires a form")
        case = await get_org_owned_or_404(db, PreparationCase, item.case_id, user)
        await require_access(db, PreparationCase, case.id, user, "edit")
        if body.expected_case_revision is None:
            raise HTTPException(422, "Expected case revision is required when editing originals")
        await advance_case(db, case, body.expected_case_revision)
        await set_case_originals(db, case, body.original_evidence_ids, user)
    await validate_component(db, item, row, user)
    return await finish(
        db,
        user,
        row,
        "update_component",
        {"component_id": str(item.id), **body.model_dump(mode="json", exclude_unset=True)},
    )


@router.post("/{application_id}/components/{component_id}/duplicate", status_code=201)
async def duplicate_component(
    application_id: uuid.UUID,
    component_id: uuid.UUID,
    body: DuplicateComponent,
    db: DB,
    user: Manager,
):
    row = await get_application(db, application_id, user, "edit")
    await advance(db, row, body.expected_revision, {"draft"})
    source = await child(db, ApplicationComponent, component_id, row)
    if source.case_id is None:
        raise HTTPException(422, "Only forms and annexes can be duplicated")
    case = await get_org_owned_or_404(db, PreparationCase, source.case_id, user)
    await require_access(db, PreparationCase, case.id, user, "view")
    copy = ApplicationComponent(
        application_id=row.id,
        name=body.name,
        kind=source.kind,
        required=source.required,
        included=source.included,
        owner_id=source.owner_id,
        due_date=source.due_date,
        profile_item_key=source.profile_item_key,
    )
    duplicate = PreparationCase(
        organization_id=user.organization_id,
        template_id=case.template_id,
        template_name=case.template_name,
        template_revision=case.template_revision,
        fields_json=case.fields_json,
        original_evidence_ids_json="[]",
        kind=case.kind,
        jurisdiction_id=case.jurisdiction_id,
        name=body.name,
        owner_id=case.owner_id,
        due_date=case.due_date,
        created_by=user.id,
    )
    db.add(duplicate)
    await db.flush()
    await initialize_access(db, "preparation_case", duplicate.id, user, visibility="secret")
    copy.case_id = duplicate.id
    await validate_component(db, copy, row, user)
    db.add(copy)
    return await finish(db, user, row, "duplicate_component", {"component_id": str(copy.id)})


@router.post("/{application_id}/followups", status_code=201)
async def add_followup(application_id: uuid.UUID, body: FollowupCreate, db: DB, user: Manager):
    row = await get_application(db, application_id, user, "edit")
    await advance(db, row, body.expected_revision, {"draft", "follow_up"})
    await get_active_user_in_org_or_404(db, body.owner_id, user)
    count = await db.scalar(
        select(func.count())
        .select_from(ApplicationFollowup)
        .where(ApplicationFollowup.application_id == row.id)
    )
    if count >= 200:
        raise HTTPException(422, "Application may contain at most 200 authority queries")
    item = ApplicationFollowup(
        application_id=row.id, **body.model_dump(exclude={"expected_revision"})
    )
    db.add(item)
    await db.flush()
    return await finish(
        db, user, row, "add_followup", {"followup_id": str(item.id), **body.model_dump(mode="json")}
    )


@router.patch("/{application_id}/followups/{followup_id}")
async def patch_followup(
    application_id: uuid.UUID,
    followup_id: uuid.UUID,
    body: FollowupPatch,
    db: DB,
    user: Editor,
):
    row = await get_application(db, application_id, user, "edit")
    changes = body.model_dump(exclude_unset=True, exclude={"expected_revision"})
    if user.role == "contributor" and set(changes) - {"response", "evidence_ids"}:
        raise HTTPException(403, "Only managers can assign or resolve authority queries")
    await advance(db, row, body.expected_revision, {"draft", "follow_up"})
    item = await child(db, ApplicationFollowup, followup_id, row)
    for evidence_id in json.loads(item.evidence_ids_json):
        await require_access(db, PreparationEvidence, uuid.UUID(evidence_id), user)
    if any(
        changes.get(key) is None for key in ("question", "status", "evidence_ids") if key in changes
    ):
        raise HTTPException(422, "Question, status and evidence IDs cannot be null")
    if "owner_id" in changes:
        await get_active_user_in_org_or_404(db, body.owner_id, user)
    if "evidence_ids" in changes:
        await get_valid_evidence(db, changes.pop("evidence_ids"), user)
        for evidence_id in body.evidence_ids:
            await protect_child(
                db, "application", row.id, "preparation_evidence", evidence_id, user
            )
        item.evidence_ids_json = json.dumps([str(key) for key in body.evidence_ids])
    if {"response", "evidence_ids", "question"} & body.model_fields_set:
        item.status, item.resolved_at = "open", None
    for key, value in changes.items():
        setattr(item, key, value)
    if item.status == "resolved":
        ids = [uuid.UUID(key) for key in json.loads(item.evidence_ids_json)]
        if not (item.response or "").strip() and not ids:
            raise HTTPException(
                422, "A response or supporting evidence is required to resolve the query"
            )
        evidence = await get_valid_evidence(db, ids, user)
        for evidence_item in evidence:
            if await checked_evidence_problem(evidence_item, datetime.now(UTC).date()):
                raise HTTPException(422, "Follow-up evidence is not currently valid")
        item.resolved_at = datetime.now(UTC)
    else:
        item.resolved_at = None
    return await finish(
        db,
        user,
        row,
        "update_followup",
        {"followup_id": str(item.id), **body.model_dump(mode="json", exclude_unset=True)},
    )


@router.get("/{application_id}/snapshots/{snapshot_id}/export")
async def export_snapshot(
    application_id: uuid.UUID,
    snapshot_id: uuid.UUID,
    db: DB,
    user: CurrentUser,
):
    row = await get_application(db, application_id, user, "export")
    snapshot = (
        await db.scalars(
            select(ApplicationSnapshot)
            .where(
                ApplicationSnapshot.id == snapshot_id, ApplicationSnapshot.application_id == row.id
            )
            .options(undefer(ApplicationSnapshot.archive))
        )
    ).first()
    if snapshot is None:
        raise HTTPException(404, "Approved pack not found")
    with zipfile.ZipFile(io.BytesIO(snapshot.archive)) as archive:
        record = json.loads(archive.read("application.json"))
    await require_pack_sources(db, record, user, "export")
    return Response(
        snapshot.archive,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="application-{row.id}-v{snapshot.version}.zip"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


@router.post("/{application_id}/{action}")
async def workflow_action(
    application_id: uuid.UUID,
    action: str,
    body: WorkflowAction,
    db: DB,
    user: CurrentUser,
):
    row = await get_application(
        db,
        application_id,
        user,
        (
            "approve"
            if action == "approve" or (action == "return-to-draft" and user.role == "approver")
            else "edit"
        ),
    )
    roles = {"approver", "admin"} if action == "approve" else {"manager", "admin"}
    if action == "return-to-draft":
        roles.add("approver")
    if user.role not in roles:
        raise HTTPException(403, "Your role cannot perform this workflow action")
    await transition(db, row, action, body, user)
    return await finish(
        db, user, row, action.replace("-", "_"), body.model_dump(mode="json", exclude_unset=True)
    )
