"""Project licence-form evidence through its existing preparation owner."""

import hashlib
import json
import uuid
from datetime import UTC, datetime
from urllib.parse import quote

from fastapi import HTTPException
from sqlalchemy import func, select, tuple_

from app.models.application import Application, ApplicationComponent
from app.models.document import Document
from app.models.preparation import (
    PreparationCase,
    PreparationEvidence,
    PreparationResponse,
    PreparationResponseEvidence,
)
from app.models.program import RequirementSetVersion
from app.models.requirement import Requirement
from app.services.access import access_clause, effective_permissions, require_access, tenant_clause
from app.services.preparation import checked_evidence_problem, field_for, fields_for


def application_href(application_id, case_id=None, field_key=None):
    result = f"/licence-applications?application={application_id}"
    if case_id is not None:
        result += f"&case={case_id}"
    if field_key is not None:
        result += "&field=" + quote(field_key, safe="")
    return result


async def application_summary(db, application_id, register, user, action="view"):
    await register_access(db, register, user, action)
    application = await require_access(db, Application, application_id, user, action)
    if application.jurisdiction_id != register.jurisdiction_id:
        raise HTTPException(422, "Application and register jurisdictions must match")
    return {
        "kind": "application",
        "id": str(application.id),
        "name": application.name,
        "href": application_href(application.id),
        "available": True,
        "status": application.status,
        "readonly": application.status != "draft",
    }


async def application_options(db, register, user, q="", skip=0, limit=100):
    await register_access(db, register, user)
    query = select(Application).where(
        tenant_clause(Application, user),
        access_clause(Application, user, "view"),
        Application.jurisdiction_id == register.jurisdiction_id,
    )
    if q.strip():
        query = query.where(Application.name.icontains(q.strip()[:200], autoescape=True))
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    skip, limit = max(0, skip), min(500, max(1, limit))
    rows = list(
        (
            await db.scalars(
                query.order_by(Application.name, Application.id).offset(skip).limit(limit)
            )
        ).all()
    )
    return {
        "items": [
            {
                "kind": "application",
                "id": str(row.id),
                "name": row.name,
                "href": application_href(row.id),
                "available": True,
                "status": row.status,
            }
            for row in rows
        ],
        "total": total,
    }


def requirement_field_source(field):
    source = field.source
    if (
        source is None
        or source.kind != "requirement"
        or source.requirement_id is None
        or source.requirement_set_version_id is None
    ):
        raise HTTPException(422, "Choose a form question with an approved requirement source")
    return source


def validate_field_requirement(field, register, requirement, version, document):
    source = requirement_field_source(field)
    if requirement is None or version is None or document is None:
        raise HTTPException(404, "Requirement source is unavailable")
    if (
        version.status != "approved"
        or requirement.requirement_set_version_id != version.id
        or requirement.document_id != version.document_id
        or source.document_id != version.document_id
        or source.jurisdiction_id != register.jurisdiction_id
        or source.text_sha256 != hashlib.sha256(requirement.text.encode("utf-8")).hexdigest()
    ):
        raise HTTPException(
            422, "The form question must retain the same approved requirement version"
        )
    return requirement, version


async def batch_field_sources(db, fields, register, user):
    """Bound SQL parameters and load each approved-source identity once for the picker."""
    sources = [
        field.source for field in fields if field.source and field.source.kind == "requirement"
    ]

    async def load(model, ids, jurisdiction=False):
        result = {}
        ordered = sorted({id_ for id_ in ids if id_ is not None}, key=str)
        for offset in range(0, len(ordered), 1000):
            query = select(model).where(
                model.id.in_(ordered[offset : offset + 1000]), tenant_clause(model, user)
            )
            if jurisdiction:
                query = query.where(model.jurisdiction_id == register.jurisdiction_id)
            result.update({row.id: row for row in (await db.scalars(query)).all()})
        return result

    requirements = await load(Requirement, [source.requirement_id for source in sources], True)
    versions = await load(
        RequirementSetVersion, [source.requirement_set_version_id for source in sources]
    )
    documents = await load(Document, [version.document_id for version in versions.values()], True)
    return requirements, versions, documents


async def approved_field_requirement(db, field, register, user, source_context=None):
    source = requirement_field_source(field)
    if source_context is not None:
        requirements, versions, documents = source_context
        requirement = requirements.get(source.requirement_id)
        version = versions.get(source.requirement_set_version_id)
        document = documents.get(version.document_id) if version else None
    else:
        requirement = await db.scalar(
            select(Requirement).where(
                Requirement.id == source.requirement_id,
                tenant_clause(Requirement, user),
                Requirement.jurisdiction_id == register.jurisdiction_id,
            )
        )
        version = await db.scalar(
            select(RequirementSetVersion).where(
                RequirementSetVersion.id == source.requirement_set_version_id,
                tenant_clause(RequirementSetVersion, user),
            )
        )
        document = (
            await db.scalar(
                select(Document).where(
                    Document.id == version.document_id,
                    tenant_clause(Document, user),
                    Document.jurisdiction_id == register.jurisdiction_id,
                )
            )
            if version
            else None
        )
    return validate_field_requirement(field, register, requirement, version, document)


async def application_case(db, application_id, case_id, register, user, action="view"):
    await register_access(db, register, user, action)
    application = await require_access(db, Application, application_id, user, action)
    if application.jurisdiction_id != register.jurisdiction_id:
        raise HTTPException(422, "Application and register jurisdictions must match")
    member = await db.scalar(
        select(ApplicationComponent.id).where(
            ApplicationComponent.application_id == application.id,
            ApplicationComponent.case_id == case_id,
            ApplicationComponent.included.is_(True),
        )
    )
    if member is None:
        raise HTTPException(404, "The form is no longer included in this application")
    case = await require_access(db, PreparationCase, case_id, user, action)
    if case.jurisdiction_id != register.jurisdiction_id:
        raise HTTPException(422, "Form and register jurisdictions must match")
    for original_id in json.loads(case.original_evidence_ids_json or "[]"):
        await require_access(db, PreparationEvidence, uuid.UUID(original_id), user, action)
    return application, case


async def application_targets(db, application_id, register, user, q="", skip=0, limit=100):
    from app.services.documentation_processes import requirement_picker_text
    summary = await application_summary(db, application_id, register, user)
    cases = (
        await db.scalars(
            select(PreparationCase)
            .join(ApplicationComponent, ApplicationComponent.case_id == PreparationCase.id)
            .where(
                ApplicationComponent.application_id == application_id,
                ApplicationComponent.included.is_(True),
                tenant_clause(PreparationCase, user),
                access_clause(PreparationCase, user, "view"),
                PreparationCase.jurisdiction_id == register.jurisdiction_id,
            )
            .order_by(PreparationCase.name, PreparationCase.id)
            .distinct()
        )
    ).all()
    case_fields = {case.id: fields_for(case) for case in cases}
    source_context = await batch_field_sources(
        db, [field for fields in case_fields.values() for field in fields], register, user
    )
    wording_by_id = {id_: requirement_picker_text(requirement.text)
        for id_, requirement in source_context[0].items()}
    items = []
    needle = " ".join(q.casefold().split())
    for case in cases:
        try:
            await application_case(db, application_id, case.id, register, user)
        except HTTPException as error:
            if error.status_code in (403, 404):
                continue
            raise
        for field in case_fields[case.id]:
            try:
                requirement, version = await approved_field_requirement(
                    db, field, register, user, source_context
                )
            except HTTPException as error:
                if error.status_code in (404, 422):
                    continue
                raise
            wording = wording_by_id[requirement.id]
            if (
                needle
                and needle not in " ".join(f"{case.name} {field.label} {requirement.reference_id} {requirement.title or ''} {wording}".casefold().split())
            ):
                continue
            items.append(
                {
                    "kind": "application_response",
                    "case_id": str(case.id),
                    "field_key": field.key,
                    "case_name": case.name,
                    "form_name": case.name,
                    "available": True,
                    "title": field.label,
                    "requirement_id": str(requirement.id),
                    "requirement_set_version_id": str(version.id),
                    "version_number": version.version_number,
                    "set_name": source_context[2][version.document_id].name or source_context[2][version.document_id].filename,
                    "process_name": summary["name"],
                    "requirement_text": wording[:1000],
                    "requirement_text_truncated": len(wording) > 1000,
                    "reference_id": requirement.reference_id,
                    "href": application_href(application_id, case.id, field.key),
                    "application_status": summary["status"],
                    "readonly": case.status == "archived" or summary["status"] != "draft",
                }
            )
    skip, limit = max(0, skip), min(500, max(1, limit))
    return {"items": items[skip : skip + limit], "total": len(items)}


async def prefetch_application_targets(db, register, mappings, user, cache, evidence_cache):
    """Resolve a page from request-local owner data; single and batch reads share rules."""
    selected = [row for row in mappings if row.case_id is not None]
    if not selected or register.application_id is None:
        return
    cases, application = {}, None
    for case_id in sorted({row.case_id for row in selected}, key=str):
        try:
            application, cases[case_id] = await application_case(
                db, register.application_id, case_id, register, user
            )
        except HTTPException as error:
            if error.status_code not in {403, 404, 422}:
                raise
    if application is None:
        for row in selected:
            cache[(None, row.case_id, row.field_key, "view")] = None
        return
    fields = []
    for row in selected:
        if row.case_id in cases:
            try:
                fields.append(field_for(cases[row.case_id], row.field_key))
            except HTTPException:
                pass
    sources = await batch_field_sources(db, fields, register, user)
    responses = {
        (row.case_id, row.field_key): row
        for row in (
            await db.scalars(
                select(PreparationResponse).where(
                    tuple_(PreparationResponse.case_id, PreparationResponse.field_key).in_(
                        [(row.case_id, row.field_key) for row in selected if row.case_id in cases]
                    )
                )
            )
        ).all()
    }
    links = {row.id: [] for row in responses.values()}
    for response_id, evidence_id in (
        await db.execute(
            select(PreparationResponseEvidence.response_id, PreparationResponseEvidence.evidence_id)
            .where(PreparationResponseEvidence.response_id.in_(links))
            .order_by(PreparationResponseEvidence.evidence_id)
        )
    ).all():
        links[response_id].append(evidence_id)
    ids = sorted({id_ for values in links.values() for id_ in values}, key=str)
    evidence = {}
    for offset in range(0, len(ids), 1000):
        evidence.update(
            {
                row.id: row
                for row in (
                    await db.scalars(
                        select(PreparationEvidence).where(
                            PreparationEvidence.id.in_(ids[offset : offset + 1000]),
                            tenant_clause(PreparationEvidence, user),
                            access_clause(PreparationEvidence, user, "view"),
                        )
                    )
                ).all()
            }
        )
    reused_ids = {row.reused_from_case_id for row in responses.values() if row.reused_from_case_id}
    visible_reused = (
        set(
            (
                await db.scalars(
                    select(PreparationCase.id).where(
                        PreparationCase.id.in_(reused_ids),
                        tenant_clause(PreparationCase, user),
                        access_clause(PreparationCase, user, "view"),
                    )
                )
            ).all()
        )
        if reused_ids
        else set()
    )
    editable_cases = (
        set(
            (
                await db.scalars(
                    select(PreparationCase.id).where(
                        PreparationCase.id.in_(cases),
                        tenant_clause(PreparationCase, user),
                        access_clause(PreparationCase, user, "edit"),
                    )
                )
            ).all()
        )
        if cases
        else set()
    )
    context = {
        "application": application,
        "cases": cases,
        "sources": sources,
        "responses": responses,
        "links": links,
        "evidence": evidence,
        "visible_reused": visible_reused,
        "editable_cases": editable_cases,
    }
    for row in selected:
        key = (None, row.case_id, row.field_key, "view")
        if key in cache:
            continue
        try:
            cache[key] = await resolve_application_target(
                db,
                register.application_id,
                row.case_id,
                row.field_key,
                register,
                user,
                evidence_cache=evidence_cache,
                context=context,
            )
        except HTTPException as error:
            if error.status_code not in {403, 404, 409, 422}:
                raise
            cache[key] = None


async def resolve_application_target(
    db,
    application_id,
    case_id,
    field_key,
    register,
    user,
    action="view",
    evidence_cache=None,
    context=None,
):
    if context is None:
        application, case = await application_case(
            db, application_id, case_id, register, user, action
        )
    else:
        application, case = context["application"], context["cases"].get(case_id)
        if case is None:
            raise HTTPException(404, "Form source is unavailable")
    field = field_for(case, field_key)
    requirement, version = await approved_field_requirement(
        db, field, register, user, context["sources"] if context is not None else None
    )
    response = (
        context["responses"].get((case.id, field.key))
        if context is not None
        else await db.scalar(
            select(PreparationResponse).where(
                PreparationResponse.case_id == case.id, PreparationResponse.field_key == field.key
            )
        )
    )
    items = []
    unavailable = False
    evidence_ids = []
    if response is not None:
        ids = (
            context["links"][response.id]
            if context is not None
            else (
                await db.scalars(
                    select(PreparationResponseEvidence.evidence_id)
                    .where(PreparationResponseEvidence.response_id == response.id)
                    .order_by(PreparationResponseEvidence.evidence_id)
                )
            ).all()
        )
        for id_ in ids:
            try:
                evidence = (
                    context["evidence"].get(id_)
                    if context is not None
                    else await require_access(db, PreparationEvidence, id_, user, action)
                )
                if evidence is None:
                    raise HTTPException(404, "Evidence source is unavailable")
            except HTTPException as error:
                if error.status_code in (403, 404):
                    unavailable = True
                    continue
                raise
            evidence_ids.append(str(evidence.id))
            problem = await checked_evidence_problem(
                evidence, datetime.now(UTC).date(), evidence_cache
            )
            items.append(
                {
                    "kind": "shared_evidence",
                    "id": str(evidence.id),
                    "evidence_id": str(evidence.id),
                    "title": evidence.title,
                    "evidence_kind": evidence.kind,
                    "filename": evidence.filename,
                    "body": evidence.body,
                    "link_url": evidence.link_url,
                    "sha256": evidence.sha256,
                    "size_bytes": evidence.size_bytes,
                    "download_href": (
                        f"/preparation/evidence/{evidence.id}/download"
                        if evidence.kind == "file"
                        else None
                    ),
                    "problems": [problem] if problem else [],
                }
            )
        if response.reused_from_case_id:
            try:
                if context is not None:
                    if response.reused_from_case_id not in context["visible_reused"]:
                        raise HTTPException(404, "Reused form source is unavailable")
                else:
                    await require_access(
                        db, PreparationCase, response.reused_from_case_id, user, action
                    )
            except HTTPException as error:
                if error.status_code in (403, 404):
                    unavailable = True
                else:
                    raise
    can_edit = (
        application.status == "draft"
        and (
            case.id in context["editable_cases"]
            if context is not None
            else "edit" in await effective_permissions(db, "preparation_case", case.id, user)
        )
        and user.role in {"contributor", "manager", "admin"}
    )
    response_data = (
        None
        if unavailable
        else {
            "value": (
                json.loads(response.value_json)
                if response is not None and response.value_json is not None
                else None
            ),
            "not_applicable_reason": (
                response.not_applicable_reason if response is not None else None
            ),
            "evidence_ids": evidence_ids,
            "accepted_at": response.accepted_at if response is not None else None,
            "review_status": response.review_status if response is not None else "pending_review",
        }
    )
    return {
        "kind": "application_response",
        "application_id": str(application.id),
        "application_status": application.status,
        "case_id": str(case.id),
        "field_key": field.key,
        "case_name": case.name,
        "form_name": case.name,
        "available": True,
        "requirement_id": str(requirement.id),
        "requirement_set_version_id": str(version.id),
        "version_number": version.version_number,
        "set_name": field.source.document_name,
        "reference_id": requirement.reference_id,
        "title": field.label,
        "href": application_href(application.id, case.id, field.key),
        "collection": {
            "items": items,
            "revision": case.revision,
            "case_revision": case.revision,
            "application_status": application.status,
            "readonly_reason": (
                "Return the application to draft to change this collection."
                if application.status != "draft"
                else "The form is archived." if case.status == "archived" else None
            ),
            "evidence_changed_at": None,
            "can_edit": can_edit and case.status != "archived" and not unavailable,
            "warning": "Some supporting evidence is unavailable" if unavailable else None,
            "current_value": response_data["value"] if response_data else None,
            "not_applicable_reason": (
                response_data["not_applicable_reason"] if response_data else None
            ),
            "response_uri": f"/preparation/cases/{case.id}/responses/{quote(field.key, safe='')}",
            "readonly": case.status == "archived" or not can_edit or unavailable,
            "unavailable": unavailable,
            "response": response_data,
            "original_evidence_ids": json.loads(case.original_evidence_ids_json or "[]"),
            "reused_from_case_id": (
                str(response.reused_from_case_id)
                if response is not None and response.reused_from_case_id
                else None
            ),
            "owner_write_href": f"/api/v1/preparation/cases/{case.id}/responses/{quote(field.key, safe='')}",
        },
    }


async def read_application_target(db, mapping, register, user, action="view", evidence_cache=None):
    application_id = getattr(register, "application_id", None)
    if application_id is None:
        raise HTTPException(404, "The register is no longer linked to this application")
    result = await resolve_application_target(
        db,
        application_id,
        mapping.case_id,
        mapping.field_key,
        register,
        user,
        action=action,
        evidence_cache=evidence_cache,
    )
    if result["requirement_id"] != str(mapping.requirement_id) or result[
        "requirement_set_version_id"
    ] != str(mapping.requirement_set_version_id):
        raise HTTPException(409, "The mapped form question changed source; choose a target again")
    result["id"] = str(mapping.id)
    return result


async def register_access(db, register, user, action="view"):
    from app.models.documentation import DocumentationRegister

    await require_access(db, DocumentationRegister, register.id, user, action)
