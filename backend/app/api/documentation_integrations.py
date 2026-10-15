"""Local imports, explicit optional suggestions and internal frozen handovers."""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.models.documentation import (
    DocumentationRegister,
    DocumentationSection,
    DocumentationExpectation,
    ExpectationRequirement,
    AuditorRequestMapping,
    DocumentationCoverage,
    AuditorRequestEvidence,
    AuditorRequestExpectation,
)
from app.models.documentation_integrations import (
    DocumentationImport,
    DocumentationImportRow,
    DocumentationSnapshot,
    DocumentationSuggestionRun,
)
from app.models.preparation import PreparationCase
from app.models.program import RequirementSetVersion
from app.models.requirement import Requirement
from app.models.review import ReviewCycle
from app.schemas.documentation import ExpectationCreate, AuditorRequestCreate, SectionCreate
from app.schemas.documentation_integrations import (
    ImportConfirm,
    SnapshotCreate,
    SuggestionCreate,
    SuggestionResume,
    SuggestionDecision,
    AuditorImport,
    ImportRemap,
)
from app.schemas.preparation import PreparationField
from app.services.access import access_clause, require_access, tenant_clause
from app.services.audit import log_action
from app.services.documentation import (
    get_register,
    get_expectation,
    create_expectation,
    create_section,
    section_name_key,
    advance_expectation,
    invalidate_review,
    checked_evidence,
    build_expectation_response,
    create_auditor_request,
    build_request_response,
    get_request,
    requirement_link_values,
    validate_requirement_links,
    expectation_clause,
)
from app.services.documentation_processes import effective_process_register
from app.services.documentation_snapshots import (
    validate_snapshot_sources,
    freeze_process_targets,
    lock_snapshot_projects,
    lock_snapshot_owners,
    snapshot_review_cycle_ids,
)
from app.services.documentation_import import build_import_preview, row_from_values
from app.services.documentation_export import (
    build_documentation_archive,
    freeze_evidence_files,
    frozen_evidence,
)
from app.services.documentation_suggestions import (
    fingerprint,
    settings_fingerprint,
    suggest_batch,
    POLICY_VERSION,
    BATCH_SIZE,
)
from app.services.installation_settings import resolve_installation_settings_snapshot
from app.services.preparation_import import MAX_UPLOAD_BYTES

router = APIRouter(prefix="/api/v1/documentation", tags=["documentation"])


def serialise(value):
    return json.dumps(value, ensure_ascii=False, default=str)


async def lock_register(db, register, revision):
    locked = await db.scalar(
        select(DocumentationRegister)
        .where(DocumentationRegister.id == register.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if locked.revision != revision:
        raise HTTPException(409, "Register changed; refresh before continuing")
    return locked


async def read_import(db, register, import_id):
    item = await db.get(DocumentationImport, import_id)
    if item is None or item.register_id != register.id:
        raise HTTPException(404, "Import not found")
    return item, json.loads(item.preview_json)


@router.post("/registers/{register_id}/imports/preview")
async def preview_import(
    register_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    register = await get_register(db, register_id, user, "edit")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    await file.close()
    existing = (
        await db.scalars(
            select(DocumentationExpectation).where(
                DocumentationExpectation.register_id == register.id,
                expectation_clause(user, "view"),
            )
        )
    ).all()
    data = await run_in_threadpool(
        build_import_preview, content, Path(file.filename or "spreadsheet.xlsx").name, existing
    )
    provenance = (
        await db.scalars(
            select(DocumentationImportRow).where(
                DocumentationImportRow.register_id == register.id,
                DocumentationImportRow.input_fingerprint == data["input_fingerprint"],
            )
        )
    ).all()
    repeated = {(row.sheet, row.row_number): str(row.expectation_id) for row in provenance}
    visible = {str(item.id) for item in existing}
    for row in data["rows"]:
        target = repeated.get((row["sheet"], row["row_number"]))
        if target in visible:
            row["existing_expectation_id"] = target
    item = DocumentationImport(
        register_id=register.id,
        input_fingerprint=data["input_fingerprint"],
        filename=data["filename"],
        register_revision=register.revision,
        preview_json=serialise(data),
        created_by=user.id,
    )
    db.add(item)
    await db.flush()
    await log_action(
        db,
        user,
        "preview",
        "documentation_import",
        str(item.id),
        new_value={"row_count": len(data["rows"]), "input_fingerprint": item.input_fingerprint},
    )
    await db.commit()
    return dict(data, id=str(item.id), revision=register.revision)


@router.post("/registers/{register_id}/imports/{import_id}/confirm")
async def confirm_import(
    register_id: uuid.UUID,
    import_id: uuid.UUID,
    body: ImportConfirm,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    register = await get_register(db, register_id, user, "edit")
    register = await lock_register(db, register, body.revision)
    item, data = await read_import(db, register, import_id)
    rows = {row["key"]: row for row in data["rows"]}
    if len({choice.row_key for choice in body.choices}) != len(body.choices) or any(
        choice.row_key not in rows for choice in body.choices
    ):
        raise HTTPException(422, "Choose each valid source row at most once")
    sections = await ensure_import_sections(db, register, user, data)
    counts = {"created": 0, "updated": 0, "skipped": 0, "repeated": 0}
    for choice in body.choices:
        row = rows[choice.row_key]
        if choice.action == "skip":
            counts["skipped"] += 1
            continue
        previous = await db.scalar(
            select(DocumentationImportRow).where(
                DocumentationImportRow.register_id == register.id,
                DocumentationImportRow.input_fingerprint == item.input_fingerprint,
                DocumentationImportRow.sheet == row["sheet"],
                DocumentationImportRow.row_number == row["row_number"],
            )
        )
        if previous:
            await get_expectation(db, previous.expectation_id, user, "edit")
            counts["repeated"] += 1
            continue
        values = {
            key: row.get(key, "")
            for key in ("title", "description", "category", "source_reference", "document_name")
        }
        values["required_documentation"] = row.get(
            "required_documentation", row.get("original_title", row["title"])
        )
        values["document_name"] = row.get(
            "document_name", row.get("metadata", {}).get("Document", "")
        )
        values["section_id"] = sections[row["sheet"]].id
        if choice.action == "create":
            if choice.expectation_id is not None:
                raise HTTPException(422, "Creation must not include a merge target")
            target = await create_expectation(db, register, user, ExpectationCreate(**values))
            counts["created"] += 1
        else:
            if choice.expectation_id is None or choice.expectation_revision is None:
                raise HTTPException(422, "Updating requires an explicit target and its revision")
            target = await get_expectation(
                db, choice.expectation_id, user, "edit", revision=choice.expectation_revision
            )
            if target.register_id != register.id:
                raise HTTPException(422, "Target belongs to a different register")
            for key, value in values.items():
                setattr(target, key, value)
            invalidate_review(target)
            await advance_expectation(db, target, user, "import_update")
            counts["updated"] += 1
        db.add(
            DocumentationImportRow(
                register_id=register.id,
                input_fingerprint=item.input_fingerprint,
                sheet=row["sheet"],
                row_number=row["row_number"],
                expectation_id=target.id,
                original_json=serialise(
                    dict(row, imported_section_id=str(sections[row["sheet"]].id))
                ),
            )
        )
    await db.flush()
    await log_action(db, user, "confirm", "documentation_import", str(item.id), new_value=counts)
    await db.commit()
    return dict(counts, revision=register.revision)


@router.post("/registers/{register_id}/imports/{import_id}/auditor-requests")
async def import_auditor_requests(
    register_id: uuid.UUID,
    import_id: uuid.UUID,
    body: AuditorImport,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    register = await get_register(db, register_id, user, "edit")
    register = await lock_register(db, register, body.revision)
    item, data = await read_import(db, register, import_id)
    case = await require_access(db, PreparationCase, body.case_id, user, "edit")
    case = await db.scalar(
        select(PreparationCase)
        .where(PreparationCase.id == case.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if case.status == "archived":
        raise HTTPException(409, "Form is archived")
    if (
        case.project_id is None
        or case.jurisdiction_id != register.jurisdiction_id
        or case.kind != "audit"
    ):
        raise HTTPException(422, "Choose an audit form linked to a project in this jurisdiction")
    rows = {row["key"]: row for row in data["rows"]}
    if len({choice.row_key for choice in body.choices}) != len(body.choices) or any(
        choice.row_key not in rows for choice in body.choices
    ):
        raise HTTPException(422, "Choose each valid source row once")
    fields = json.loads(case.fields_json)
    count = repeated = 0
    prepared = []
    for choice in body.choices:
        if choice.action == "skip":
            continue
        row = rows[choice.row_key]
        field_key = (
            "request_"
            + fingerprint(
                {"hash": item.input_fingerprint, "sheet": row["sheet"], "row": row["row_number"]}
            )[:40]
        )
        previous = await db.scalar(
            select(AuditorRequestMapping).where(
                AuditorRequestMapping.register_id == register.id,
                AuditorRequestMapping.case_id == case.id,
                AuditorRequestMapping.field_key == field_key,
                AuditorRequestMapping.list_revision == body.list_revision,
            )
        )
        if previous:
            repeated += 1
            continue
        if choice.action == "update":
            target = await get_expectation(db, choice.expectation_id, user, "edit", revision=choice.expectation_revision)
            if target.register_id != register.id or target.project_id not in (None, case.project_id):
                raise HTTPException(422, "Choose a documentation row in this register and project scope")
        try:
            field = PreparationField(
                key=field_key,
                label=row["title"],
                section=row["sheet"],
                help_text=row["description"] or None,
                type="evidence",
                required=True,
            )
            request = AuditorRequestCreate(
                case_id=case.id,
                field_key=field_key,
                project_id=case.project_id,
                request_id=row["source_reference"] or row["key"],
                request_wording=row.get("original_title", row["title"])
                + ("\n" + row["description"] if row["description"] else ""),
                list_revision=body.list_revision,
                direction=body.direction,
                period=body.period or None,
                expectation_ids=[choice.expectation_id] if choice.expectation_id else [],
            )
        except ValidationError as error:
            raise HTTPException(422,
                f"Source row {row['sheet']}:{row['row_number']} cannot be imported as an auditor request; "
                "check its request reference and text limits") from error
        if not any(existing["key"] == field_key for existing in fields):
            fields.append(field.model_dump(mode="json"))
        if len(fields) > 500:
            raise HTTPException(422, "A form supports at most 500 questions")
        prepared.append(request)
    if prepared:
        case.fields_json = serialise(fields)
    for request in prepared:
        await create_auditor_request(db, register, user, request)
        count += 1
    if count:
        from app.services.preparation import advance_case
        await advance_case(db, case, case.revision)
        await log_action(
            db,
            user,
            "import_auditor_requests",
            "preparation_case",
            str(case.id),
            new_value={"count": count, "list_revision": body.list_revision},
        )
    await db.commit()
    return {
        "created": count,
        "repeated": repeated,
        "revision": register.revision,
        "case_revision": case.revision,
    }


@router.post("/registers/{register_id}/snapshots", status_code=201)
async def create_snapshot(
    register_id: uuid.UUID,
    body: SnapshotCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    register = await get_register(db, register_id, user, "export")
    register = await lock_register(db, register, body.revision)
    mapped_expectation_ids = set()
    if body.project_id is not None:
        mapped_expectation_ids = set(
            (
                await db.scalars(
                    select(AuditorRequestExpectation.expectation_id)
                    .join(
                        AuditorRequestMapping,
                        AuditorRequestMapping.id == AuditorRequestExpectation.request_id,
                    )
                    .where(
                        AuditorRequestMapping.register_id == register.id,
                        AuditorRequestMapping.project_id == body.project_id,
                    )
                )
            ).all()
        )
    selected_requests = (
        await db.scalars(
            select(AuditorRequestMapping).where(
                AuditorRequestMapping.register_id == register.id,
                AuditorRequestMapping.project_id == body.project_id if body.project_id else True,
            )
        )
    ).all()
    selected_expectations = []
    for item in (
        await db.scalars(
            select(DocumentationExpectation)
            .where(DocumentationExpectation.register_id == register.id)
            .order_by(DocumentationExpectation.id)
        )
    ).all():
        if body.project_id is not None:
            if item.project_id is not None and item.project_id != body.project_id:
                continue
            links = await requirement_link_values(db, item.id)
            if item.project_id is None and not links and item.id not in mapped_expectation_ids:
                continue
            effective = effective_process_register(register, item)
            if effective.review_cycle_id:
                review_project_id = await db.scalar(
                    select(ReviewCycle.certification_project_id).where(
                        ReviewCycle.id == effective.review_cycle_id,
                        tenant_clause(ReviewCycle, user),
                    )
                )
                if review_project_id != body.project_id:
                    continue
            try:
                await validate_requirement_links(db, effective, user, links, body.project_id)
            except HTTPException as error:
                if error.status_code == 422:
                    continue
                raise
        selected_expectations.append(item)
    permitted = set(
        (
            await db.scalars(
                select(DocumentationExpectation.id).where(
                    DocumentationExpectation.id.in_([item.id for item in selected_expectations]),
                    expectation_clause(user, "export"),
                )
            )
        ).all()
    )
    if permitted != {item.id for item in selected_expectations}:
        raise HTTPException(404, "Snapshot source is unavailable")
    projects = await lock_snapshot_projects(
        db, register, body.project_id, user, selected_expectations, selected_requests
    )
    await lock_snapshot_owners(
        db, register, selected_expectations, selected_requests, user, projects, body.evidence_ids
    )
    target_cache = {}
    evidence_cache = {}
    expectations = []
    canonical_evidence = []
    process_sources = []
    from app.services.documentation_processes import register_process_summary

    process_summary = await register_process_summary(db, register, user)
    if getattr(register, "application_id", None):
        from app.models.application import Application

        await require_access(db, Application, register.application_id, user, "export")
        process_sources.append(
            {"kind": "application", "application_id": str(register.application_id)}
        )
    from app.services.documentation_processes import get_review_process

    for cycle_id in sorted(snapshot_review_cycle_ids(register, selected_expectations), key=str):
        cycle = await get_review_process(db, cycle_id, register, user, "export")
        process_sources.append(
            {
                "kind": "review",
                "review_cycle_id": str(cycle.id),
                "project_id": (
                    str(cycle.certification_project_id) if cycle.certification_project_id else None
                ),
            }
        )
    referenced_evidence_ids = set()
    for item in selected_expectations:
        for id_ in (
            await db.scalars(
                select(DocumentationCoverage.evidence_id).where(
                    DocumentationCoverage.expectation_id == item.id
                )
            )
        ).all():
            await checked_evidence(db, id_, user, "export")
            referenced_evidence_ids.add(str(id_))
        targets, target_evidence, target_sources = await freeze_process_targets(
            db, item, register, user, cache=target_cache, evidence_cache=evidence_cache
        )
        response = await build_expectation_response(db, item, user, process_targets=targets)
        canonical_evidence.extend(target_evidence)
        process_sources.extend(target_sources)
        response = response.model_dump(mode="json") if hasattr(response, "model_dump") else response
        response["process_targets"] = targets
        expectations.append(
            response.model_dump(mode="json") if hasattr(response, "model_dump") else response
        )
    requests = []
    for item in selected_requests:
        await get_request(db, item.id, user, "export")
        for id_ in (
            await db.scalars(
                select(AuditorRequestEvidence.evidence_id).where(
                    AuditorRequestEvidence.request_id == item.id
                )
            )
        ).all():
            await checked_evidence(db, id_, user, "export")
            referenced_evidence_ids.add(str(id_))
        response = await build_request_response(db, item, user)
        requests.append(
            response.model_dump(mode="json") if hasattr(response, "model_dump") else response
        )
    evidence = [
        await checked_evidence(db, id_, user, "export") for id_ in sorted(set(body.evidence_ids))
    ]
    unique_evidence = {}
    for item in canonical_evidence + evidence:
        unique_evidence.setdefault((str(item.id), item.sha256, item.body, item.link_url), item)
    frozen = await run_in_threadpool(
        freeze_evidence_files, list(unique_evidence.values()), user.organization_id
    )
    section_rows = (
        await db.scalars(
            select(DocumentationSection)
            .where(DocumentationSection.register_id == register.id)
            .order_by(DocumentationSection.position, DocumentationSection.id)
        )
    ).all()
    relevant_sections = {
        uuid.UUID(str(row["section_id"])) for row in expectations if row.get("section_id")
    }
    data = {
        "format_version": 3,
        "process": process_summary,
        "process_sources": process_sources,
        "sections": [
            {"id": str(section.id), "name": section.name, "position": section.position}
            for section in section_rows
            if body.project_id is None or section.id in relevant_sections
        ],
        "project_id": str(body.project_id) if body.project_id else None,
        "referenced_evidence_ids": sorted(referenced_evidence_ids),
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "register": {
            "id": str(register.id),
            "revision": register.revision,
            "name": register.name,
            "description": register.description,
            "jurisdiction_id": str(register.jurisdiction_id),
        },
        "expectations": expectations,
        "auditor_requests": requests,
        "frozen_evidence": frozen,
    }
    item = DocumentationSnapshot(
        register_id=register.id,
        register_revision=register.revision,
        content_json=serialise(data),
        evidence_ids_json=serialise([str(e.id) for e in evidence]),
        created_by=user.id,
    )
    db.add(item)
    await db.flush()
    from app.services.documentation_packages import index_snapshot_sources

    await index_snapshot_sources(db, item, data)
    await log_action(
        db,
        user,
        "freeze",
        "documentation_snapshot",
        str(item.id),
        new_value={"register_revision": register.revision, "evidence_count": len(evidence)},
    )
    await db.commit()
    return {
        "id": str(item.id),
        "register_revision": item.register_revision,
        "created_at": item.created_at,
        "evidence_count": len(evidence),
    }


@router.get("/registers/{register_id}/snapshots")
async def list_snapshots(
    register_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    register = await get_register(db, register_id, user, "export")
    items = (
        await db.scalars(
            select(DocumentationSnapshot)
            .where(DocumentationSnapshot.register_id == register.id)
            .order_by(DocumentationSnapshot.created_at.desc())
        )
    ).all()
    visible = []
    for item in items:
        try:
            await validate_snapshot_sources(db, item, user)
        except HTTPException as error:
            if error.status_code in (403, 404):
                continue
            raise
        visible.append(
            {
                "id": str(item.id),
                "register_revision": item.register_revision,
                "created_at": item.created_at,
                "evidence_count": len(json.loads(item.evidence_ids_json)),
            }
        )
    return visible


@router.get("/snapshots/{snapshot_id}/download")
async def download_snapshot(
    snapshot_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = await db.get(DocumentationSnapshot, snapshot_id)
    if item is None:
        raise HTTPException(404, "Snapshot not found")
    data = await validate_snapshot_sources(db, item, user)
    evidence = frozen_evidence(data["frozen_evidence"], user.organization_id)
    stream = await run_in_threadpool(build_documentation_archive, data, evidence)
    await log_action(
        db,
        user,
        "export",
        "documentation_snapshot",
        str(item.id),
        new_value={"register_revision": item.register_revision},
    )
    try:
        await db.commit()
    except BaseException:
        stream.close()
        raise

    def chunks():
        try:
            while chunk := stream.read(1024 * 1024):
                yield chunk
        finally:
            stream.close()

    return StreamingResponse(
        chunks(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="cap-documentation-{item.id}.zip"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
        background=BackgroundTask(stream.close),
    )


@router.post("/registers/{register_id}/imports/{import_id}/remap")
async def remap_import(
    register_id: uuid.UUID,
    import_id: uuid.UUID,
    body: ImportRemap,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    register = await get_register(db, register_id, user, "edit")
    original, data = await read_import(db, register, import_id)
    sheets = {sheet["name"]: sheet for sheet in data["sheets"]}
    if len({sheet.name for sheet in body.sheets}) != len(body.sheets):
        raise HTTPException(422, "Choose each sheet at most once")
    for sheet in data["sheets"]:
        sheet["included"] = False
    rows = []
    for chosen in body.sheets:
        sheet = sheets.get(chosen.name)
        if (
            sheet is None
            or "metadata_rows" in sheet
            or chosen.header_row > len(sheet["raw_rows"])
            or not any(
                key in chosen.mapping for key in ("required_documentation", "title", "description")
            )
        ):
            raise HTTPException(
                422, "Choose a valid sheet, header row and required documentation column"
            )
        raw = sheet["raw_rows"]
        headers = raw[chosen.header_row - 1]
        if any(not 0 <= column < len(headers) for column in chosen.mapping.values()):
            raise HTTPException(422, "Choose columns present in the selected sheet")
        for number, values in enumerate(raw[chosen.header_row :], chosen.header_row + 1):
            row = row_from_values(chosen.name, number, values, headers, chosen.mapping)
            if row is not None:
                rows.append(row)
        sheet.update(
            header_row=chosen.header_row, headers=headers, mapping=chosen.mapping, included=True
        )
    if not rows or len(rows) > 2000:
        raise HTTPException(422, "Select between 1 and 2,000 substantive rows")
    data["rows"] = rows
    # Revisions of a preview remain immutable: a remap creates a new preview ID.
    item = DocumentationImport(
        register_id=register.id,
        input_fingerprint=original.input_fingerprint,
        filename=original.filename,
        register_revision=register.revision,
        preview_json=serialise(data),
        created_by=user.id,
    )
    db.add(item)
    await db.flush()
    await db.commit()
    return dict(data, id=str(item.id), revision=register.revision)


def run_response(item):
    payload = json.loads(item.input_json)
    return {
        "id": str(item.id),
        "status": item.status,
        "cursor": item.cursor,
        "total": len(payload["rows"]),
        "input_fingerprint": item.input_fingerprint,
        "provider": item.provider,
        "model": item.model,
        "policy_version": item.policy_version,
        "suggestions": json.loads(item.suggestions_json),
        "message": item.last_error,
        "processing": payload.get("processing", {}),
    }


async def get_run(db, run_id, user, action="view", lock=False):
    query = select(DocumentationSuggestionRun).where(DocumentationSuggestionRun.id == run_id)
    if lock:
        query = query.with_for_update()
    item = await db.scalar(query.execution_options(populate_existing=True))
    if item is None:
        raise HTTPException(404, "Suggestion run not found")
    register = await get_register(db, item.register_id, user, action)
    if item.provider != "local":
        await get_register(db, item.register_id, user, "export")
    payload = json.loads(item.input_json)
    await suggestion_sources(db, register, payload, user, action, external=item.provider != "local")
    return item, register, payload


async def approved_candidates(db, register, user, requirement_ids=None):
    query = (
        select(Requirement)
        .join(
            RequirementSetVersion,
            RequirementSetVersion.id == Requirement.requirement_set_version_id,
        )
        .where(
            tenant_clause(Requirement, user),
            tenant_clause(RequirementSetVersion, user),
            Requirement.jurisdiction_id == register.jurisdiction_id,
            RequirementSetVersion.status == "approved",
        )
    )
    if requirement_ids is not None:
        query = query.where(Requirement.id.in_([uuid.UUID(str(id_)) for id_ in requirement_ids]))
    result = (await db.scalars(query.order_by(Requirement.id).limit(10000))).all()
    return [
        {
            "id": str(row.id),
            "reference_id": row.reference_id,
            "title": row.title or "",
            "text": row.text[:4000],
            "requirement_set_version_id": str(row.requirement_set_version_id),
        }
        for row in result
    ]


async def suggestion_sources(db, register, payload, user, action, *, external):
    """Batch current and original-scope authorisation without locking sources across HTTP."""
    from app.models.preparation import PreparationEvidence
    from app.models.program import CertificationProject

    rows = payload["rows"]
    ids = [uuid.UUID(row["id"]) for row in rows]
    permitted = (
        await db.execute(
            select(DocumentationExpectation.id, DocumentationExpectation.revision).where(
                DocumentationExpectation.id.in_(ids),
                DocumentationExpectation.register_id == register.id,
                expectation_clause(user, action),
                expectation_clause(user, "export") if external else True,
            )
        )
    ).all()
    if len(permitted) != len(ids):
        raise HTTPException(404, "Suggestion source is unavailable")
    projects = {uuid.UUID(row["project_id"]) for row in rows if row.get("project_id")}
    if projects:
        visible = set(
            (
                await db.scalars(
                    select(CertificationProject.id).where(
                        CertificationProject.id.in_(projects),
                        tenant_clause(CertificationProject, user),
                        access_clause(CertificationProject, user, "export" if external else action),
                    )
                )
            ).all()
        )
        if visible != projects:
            raise HTTPException(404, "Suggestion source is unavailable")
    evidence_ids = {uuid.UUID(row["id"]) for row in payload.get("evidence", [])}
    evidence = (
        (
            await db.scalars(
                select(PreparationEvidence)
                .where(
                    PreparationEvidence.id.in_(evidence_ids),
                    tenant_clause(PreparationEvidence, user),
                    access_clause(PreparationEvidence, user, "export" if external else "view"),
                )
                .execution_options(populate_existing=True)
            )
        ).all()
        if evidence_ids
        else []
    )
    if {row.id for row in evidence} != evidence_ids:
        raise HTTPException(404, "Suggestion source is unavailable")
    return dict(permitted), {str(row.id): row for row in evidence}


async def validate_suggestion_freshness(
    db, item, register, payload, user, *, allow_applied=False, file_cache=None
):
    settings = await assistance_settings(db)
    suggestions = json.loads(item.suggestions_json) if allow_applied else []
    expected_register_revision = max(
        [item.register_revision]
        + [entry.get("applied_register_revision", 0) for entry in suggestions]
    )
    if (
        register.revision != expected_register_revision
        or item.policy_version != POLICY_VERSION
        or item.settings_fingerprint != settings_fingerprint(settings, item.provider)
    ):
        raise HTTPException(409, "Source content or provider settings changed; start a fresh run")
    revisions, evidence = await suggestion_sources(
        db, register, payload, user, "edit", external=item.provider != "local"
    )
    applied = {
        entry["expectation_id"]: entry["applied_expectation_revision"]
        for entry in suggestions
        if entry.get("applied_expectation_revision")
    }
    if any(
        revisions.get(uuid.UUID(row["id"])) != applied.get(row["id"], row["revision"])
        for row in payload["rows"]
    ):
        raise HTTPException(409, "Documentation changed; start a fresh run")
    file_cache = {} if file_cache is None else file_cache
    for row in payload.get("evidence", []):
        source = evidence[row["id"]]
        if evidence_fingerprint(source) != row["source_fingerprint"]:
            raise HTTPException(409, "Selected evidence changed; start a fresh run")
        if source.kind == "file":
            from app.services.preparation_files import checked_evidence_path, verify_evidence_file

            path = checked_evidence_path(source)
            stat = path.stat()
            signature = (
                source.sha256,
                source.size_bytes,
                stat.st_size,
                stat.st_mtime_ns,
                stat.st_ctime_ns,
            )
            if file_cache.get(source.id) != signature:
                await run_in_threadpool(verify_evidence_file, source)
                file_cache[source.id] = signature
    selected = payload.get("requirements", [])
    current = {
        row["id"]: row
        for row in await approved_candidates(db, register, user, [row["id"] for row in selected])
    }
    if any(current.get(row["id"]) != row for row in selected):
        raise HTTPException(409, "Approved requirement content changed; start a fresh run")
    return settings


async def prepare_suggestions(register_id, body, db, user, *, persist=True):
    register = await get_register(db, register_id, user, "edit")
    if register.revision != body.revision:
        raise HTTPException(409, "Register changed; refresh before requesting suggestions")
    if persist and body.mode != "local" and not body.external_processing_confirmed:
        raise HTTPException(422, "Confirm external processing for this run")
    if body.mode != "local":
        await get_register(db, register_id, user, "export")
    rows = []
    candidates = (
        await db.scalars(
            select(DocumentationExpectation)
            .where(DocumentationExpectation.register_id == register.id)
            .order_by(DocumentationExpectation.id)
        )
    ).all()
    chosen_ids = set(body.expectation_ids)
    for item in candidates:
        if chosen_ids and item.id not in chosen_ids:
            continue
        try:
            await get_expectation(db, item.id, user, "export" if body.mode != "local" else "edit")
        except HTTPException as error:
            if chosen_ids or error.status_code not in (403, 404):
                raise
            continue
        rows.append(
            {
                "id": str(item.id),
                "revision": item.revision,
                "title": item.title,
                "description": (
                    (item.required_documentation or item.title)
                    + ("\n" + item.description if item.description else "")
                )[:4000],
                "source_reference": (item.source_reference or "")[:2000],
                "project_id": str(item.project_id) if item.project_id else None,
            }
        )
    if not rows or (chosen_ids and chosen_ids != {uuid.UUID(row["id"]) for row in rows}):
        raise HTTPException(422, "Choose accessible expectations in this register")
    if len(rows) > 2000:
        raise HTTPException(413, "Choose at most 2,000 expectations per run")
    snippets = []
    for id_ in sorted(set(body.evidence_ids)):
        evidence = await checked_evidence(
            db, id_, user, "export" if body.mode != "local" else "view"
        )
        text = evidence.body or ""
        # File extraction is local and bounded. References are never fetched.
        if evidence.kind == "file":
            from app.services.preparation_files import verify_evidence_file

            path = await run_in_threadpool(verify_evidence_file, evidence)
            if path.suffix.lower() in (".txt", ".md", ".csv"):

                def text_excerpt():
                    with path.open("rb") as source:
                        return source.read(16000).decode("utf-8", errors="replace")

                text = await run_in_threadpool(text_excerpt)
            elif path.suffix.lower() == ".pdf":

                def pdf_excerpt():
                    from contextlib import closing
                    import pypdfium2 as pdfium

                    with pdfium.PdfDocument(path) as document:
                        parts = []
                        for index in range(min(len(document), 5)):
                            with (
                                closing(document[index]) as page,
                                closing(page.get_textpage()) as textpage,
                            ):
                                parts.append(textpage.get_text_bounded()[:4000])
                        return "\n".join(parts)[:4000]

                try:
                    text = await run_in_threadpool(pdf_excerpt)
                except Exception:
                    raise HTTPException(
                        422, "Selected PDF could not be read locally; use a verified text note"
                    ) from None
        if evidence.kind == "link":
            text = ""
        snippets.append(
            {
                "id": str(evidence.id),
                "title": evidence.title,
                "text": text[:4000],
                "sha256": evidence.sha256,
                "source_fingerprint": evidence_fingerprint(evidence),
            }
        )
    if body.mode == "ai" and not any(row["text"] for row in snippets):
        raise HTTPException(
            422, "Choose evidence with readable supplied content; links are references only"
        )
    settings = await assistance_settings(db)
    unavailable = (
        body.mode == "jev" and (not settings.jev_enabled or not settings.typesafe_api_key)
    ) or (body.mode == "ai" and settings.ai_provider == "none")
    from app.services.documentation_suggestions import shortlist

    all_requirements = await approved_candidates(db, register, user)
    selected_requirements = {}
    for row in rows:
        text = row["title"] + " " + row["description"] + " " + row["source_reference"]
        for candidate in shortlist(text, all_requirements):
            selected_requirements[candidate["id"]] = candidate
        for candidate in all_requirements:
            if (
                candidate["reference_id"]
                and candidate["reference_id"].casefold() in row["source_reference"].casefold()
            ):
                selected_requirements[candidate["id"]] = candidate
    processing = {
        "mode": body.mode,
        "provider": settings.ai_provider if body.mode == "ai" else body.mode,
        "model": (
            settings.jev_model
            if body.mode == "jev"
            else settings.ai_model if body.mode == "ai" else "local"
        ),
        "settings_revision": (
            settings.jev_settings_revision
            if body.mode == "jev"
            else getattr(settings, "documentation_ai_revision", 0)
        ),
        "policy_version": POLICY_VERSION,
    }
    payload = {
        "rows": rows,
        "requirements": sorted(selected_requirements.values(), key=lambda row: row["id"]),
        "evidence": snippets,
        "processing": processing,
    }
    input_hash = fingerprint(payload)
    if not persist:
        from app.services.documentation_suggestions import shortlist

        forwarded = []
        if body.mode == "jev":
            for row in rows:
                candidates = shortlist(
                    row["title"] + " " + row["description"] + " " + row["source_reference"],
                    payload["requirements"],
                )
                duplicates = shortlist(
                    row["title"],
                    [{**r, "text": r["description"]} for r in rows if r["id"] != row["id"]],
                )
                forwarded.append(
                    {
                        "expectation_id": row["id"],
                        "candidates": [
                            {
                                "id": c["id"],
                                "reference": c["reference_id"],
                                "text": c["text"][:1500],
                            }
                            for c in candidates
                        ],
                        "duplicate_candidates": [
                            {
                                "id": c["id"],
                                "title": c["title"][:500],
                                "description": c["description"][:1000],
                            }
                            for c in duplicates
                        ],
                    }
                )
        return {
            "input_fingerprint": input_hash,
            "provider": body.mode,
            "model": settings.jev_model if body.mode == "jev" else settings.ai_model,
            "expectations": rows,
            "processing": processing,
            "requirements": forwarded,
            "requirement_candidates": payload["requirements"],
            "evidence": snippets if body.mode == "ai" else [],
            "unavailable": unavailable,
        }
    if body.mode != "local" and body.input_fingerprint != input_hash:
        raise HTTPException(
            409, "Preview the exact selected content before confirming this external run"
        )
    item = DocumentationSuggestionRun(
        register_id=register.id,
        register_revision=register.revision,
        input_fingerprint=fingerprint(payload),
        settings_fingerprint=settings_fingerprint(settings, body.mode),
        policy_version=POLICY_VERSION,
        provider=body.mode,
        model=(
            settings.jev_model
            if body.mode == "jev"
            else settings.ai_model if body.mode == "ai" else "local"
        ),
        status="unavailable" if unavailable else "pending",
        last_error=(
            "Provider unavailable; local review and import remain available."
            if unavailable
            else None
        ),
        cursor=0,
        input_json=serialise(payload),
        suggestions_json="[]",
        created_by=user.id,
    )
    db.add(item)
    await db.flush()
    await log_action(
        db,
        user,
        "start",
        "documentation_suggestion_run",
        str(item.id),
        new_value={
            "provider": item.provider,
            "model": item.model,
            "input_fingerprint": item.input_fingerprint,
            "external_processing_confirmed": body.external_processing_confirmed,
        },
    )
    await db.commit()
    return run_response(item)


@router.get("/suggestions/{run_id}")
async def read_suggestions(
    run_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    item, _, _ = await get_run(db, run_id, user)
    return run_response(item)


@router.post("/suggestions/{run_id}/cancel")
async def cancel_suggestions(
    run_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    item, _, _ = await get_run(db, run_id, user, "edit", lock=True)
    item.status = "cancelled"
    await db.commit()
    return run_response(item)


@router.post("/suggestions/{run_id}/resume")
async def resume_suggestions(
    run_id: uuid.UUID,
    body: SuggestionResume,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item, register, payload = await get_run(db, run_id, user, "edit", lock=True)
    if item.status not in ("pending", "partial"):
        return run_response(item)
    if item.provider != "local" and not body.external_processing_confirmed:
        raise HTTPException(422, "Confirm external processing before resuming this run")
    try:
        settings = await validate_suggestion_freshness(db, item, register, payload, user)
    except HTTPException as error:
        if error.status_code not in (403, 404, 409):
            raise
        item.status = "stale"
        item.last_error = "Source access, content or provider settings changed; start a fresh run."
        await db.commit()
        return run_response(item)
    cursor = item.cursor
    item.last_error = None
    item.status = "running"
    await db.commit()  # Cancellation can proceed while the bounded provider call is running.

    file_cache = {}

    async def fresh():
        await db.refresh(item)
        await db.refresh(register)
        if item.status != "running":
            return False
        try:
            if not await db.scalar(
                select(DocumentationRegister.id).where(
                    DocumentationRegister.id == register.id,
                    tenant_clause(DocumentationRegister, user),
                    access_clause(DocumentationRegister, user, "edit"),
                    (
                        access_clause(DocumentationRegister, user, "export")
                        if item.provider != "local"
                        else True
                    ),
                )
            ):
                return False
            await validate_suggestion_freshness(
                db, item, register, payload, user, file_cache=file_cache
            )
        except HTTPException:
            return False
        return True

    try:
        results = await suggest_batch(
            payload, settings, item.provider, cursor, should_continue=fresh
        )
        await db.scalar(
            select(DocumentationSuggestionRun)
            .where(DocumentationSuggestionRun.id == item.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if not await fresh():
            if item.status == "running":
                item.status = "stale"
                item.last_error = (
                    "Source access, content or provider settings changed; start a fresh run."
                )
        else:
            old = json.loads(item.suggestions_json)
            item.suggestions_json = serialise(old + results)
            item.cursor = min(cursor + BATCH_SIZE, len(payload["rows"]))
            item.status = "completed" if item.cursor == len(payload["rows"]) else "partial"
    except Exception:
        await db.scalar(
            select(DocumentationSuggestionRun)
            .where(DocumentationSuggestionRun.id == item.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if item.status == "running":
            item.status = "partial"
            item.last_error = "Provider check could not be completed. Retry this batch or cancel; manual review remains available."
    await db.commit()
    return run_response(item)


@router.post("/suggestions/{run_id}/decisions")
async def decide_suggestion(
    run_id: uuid.UUID,
    body: SuggestionDecision,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item, register, payload = await get_run(db, run_id, user, "edit", lock=True)
    suggestions = json.loads(item.suggestions_json)
    if body.index >= len(suggestions):
        raise HTTPException(422, "Suggestion not found")
    suggestion = suggestions[body.index]
    if suggestion.get("status") != "pending":
        raise HTTPException(409, "Suggestion was already reviewed")
    if body.decision != "dismiss":
        await validate_suggestion_freshness(db, item, register, payload, user, allow_applied=True)
        target = await get_expectation(db, uuid.UUID(suggestion["expectation_id"]), user, "edit")
        effective = effective_process_register(register, target)
        category = body.category if body.decision == "edit" else suggestion.get("category")
        if category and category != "uncertain":
            target.category = category
        requirement_id = body.requirement_id
        if requirement_id is not None:
            allowed = next(
                (
                    row
                    for row in await approved_candidates(db, effective, user, [requirement_id])
                    if row["id"] == str(requirement_id)
                ),
                None,
            )
            if allowed is None:
                raise HTTPException(422, "Choose an existing approved requirement version")
            await validate_requirement_links(
                db,
                effective,
                user,
                [
                    {
                        "requirement_id": requirement_id,
                        "requirement_set_version_id": uuid.UUID(
                            allowed["requirement_set_version_id"]
                        ),
                    }
                ],
                target.project_id,
            )
            if not await db.get(ExpectationRequirement, (target.id, requirement_id)):
                db.add(
                    ExpectationRequirement(
                        expectation_id=target.id,
                        requirement_id=requirement_id,
                        requirement_set_version_id=uuid.UUID(allowed["requirement_set_version_id"]),
                    )
                )
        if body.rationale:
            target.interpretation = body.rationale
        invalidate_review(target)
        await advance_expectation(db, target, user, "apply_suggestion")
        suggestion["applied_register_revision"] = register.revision
        suggestion["applied_expectation_revision"] = target.revision
    suggestion["status"] = body.decision
    suggestion["reviewed_by"] = str(user.id)
    suggestions[body.index] = suggestion
    item.suggestions_json = serialise(suggestions)
    await log_action(
        db,
        user,
        "review_suggestion",
        "documentation_suggestion_run",
        str(item.id),
        new_value={"index": body.index, "decision": body.decision},
    )
    await db.commit()
    return run_response(item)


async def assistance_settings(db):
    settings, public = await resolve_installation_settings_snapshot(db)
    return settings.model_copy(update={"documentation_ai_revision": public.ai.revision})


@router.post("/registers/{register_id}/suggestions/preview")
async def preview_suggestions(
    register_id: uuid.UUID,
    body: SuggestionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await prepare_suggestions(register_id, body, db, user, persist=False)


@router.post("/registers/{register_id}/suggestions")
async def create_suggestions(
    register_id: uuid.UUID,
    body: SuggestionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await prepare_suggestions(register_id, body, db, user)


def evidence_fingerprint(item):
    return fingerprint(
        {
            key: str(getattr(item, key)) if getattr(item, key) is not None else None
            for key in (
                "kind",
                "title",
                "body",
                "link_url",
                "sha256",
                "size_bytes",
                "valid_from",
                "valid_until",
                "archived",
            )
        }
    )


async def ensure_import_sections(db, register, user, preview):
    """Append recognised workbook sheets in order and reuse their stable identities."""
    existing = list(
        (
            await db.scalars(
                select(DocumentationSection)
                .where(DocumentationSection.register_id == register.id)
                .order_by(DocumentationSection.position, DocumentationSection.id)
            )
        ).all()
    )
    by_key = {section.name_key: section for section in existing}
    by_id = {section.id: section for section in existing}
    previous_sources = (
        await db.execute(
            select(DocumentationImportRow, DocumentationExpectation.section_id)
            .join(
                DocumentationExpectation,
                DocumentationExpectation.id == DocumentationImportRow.expectation_id,
            )
            .where(
                DocumentationImportRow.register_id == register.id,
                DocumentationImportRow.input_fingerprint == preview["input_fingerprint"],
            )
        )
    ).all()
    source_sections = {}
    for source, current_section_id in previous_sources:
        original_section_id = json.loads(source.original_json).get("imported_section_id")
        section = (
            by_id.get(uuid.UUID(original_section_id))
            if original_section_id
            else by_id.get(current_section_id)
        )
        if section is not None:
            source_sections.setdefault(source.sheet, section)
    position = max((section.position for section in existing), default=-1) + 1
    output = {}
    for sheet in preview["sheets"]:
        if not sheet.get("included", bool(sheet.get("mapping"))) or "metadata_rows" in sheet:
            continue
        section = source_sections.get(sheet["name"]) or by_key.get(section_name_key(sheet["name"]))
        if section is None:
            section = await create_section(
                db,
                register,
                user,
                SectionCreate(revision=register.revision, name=sheet["name"], position=position),
            )
            by_key[section.name_key] = section
            position += 1
        output[sheet["name"]] = section
    return output
