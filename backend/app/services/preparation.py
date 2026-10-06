import hashlib
import json
import uuid
from datetime import UTC, date, datetime

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.tenant import org_clause
from app.models.preparation import (
    PreparationCase,
    PreparationEvidence,
    PreparationResponse,
    PreparationResponseEvidence,
)
from app.models.user import User
from app.schemas.preparation import (
    CaseOut,
    PreparationField,
    Readiness,
    ResponseOut,
    TemplateFields,
)
from app.services.access import (
    access_details,
    effective_permissions,
    initialize_access,
    protect_child,
    require_access,
)
from app.services.preparation_files import verify_evidence_file
from app.services.preparation_requirements import (
    checked_template_fields,
    ensure_template_jurisdiction,
)


async def create_private_case(
    db,
    user,
    *,
    jurisdiction_id,
    name,
    owner_id,
    due_date,
    fields,
    original_evidence_ids,
    project_id=None,
    visibility="secret",
):
    """Make a case with its own copied definition and protected source originals."""
    TemplateFields(fields=fields)
    checked_fields = await checked_template_fields(db, user, fields)
    fields_json = json.dumps(checked_fields)
    ensure_template_jurisdiction(fields_json, jurisdiction_id)
    evidence = await get_valid_evidence(db, original_evidence_ids, user)
    case = PreparationCase(
        organization_id=user.organization_id,
        template_id=None,
        template_name="Private application form",
        template_revision=1,
        fields_json=fields_json,
        original_evidence_ids_json=json.dumps([str(item.id) for item in evidence]),
        kind="licence_application",
        jurisdiction_id=jurisdiction_id,
        project_id=project_id,
        name=name,
        owner_id=owner_id,
        due_date=due_date,
        created_by=user.id,
    )
    db.add(case)
    await db.flush()
    await initialize_access(db, "preparation_case", case.id, user, visibility=visibility)
    if project_id is not None:
        await protect_child(
            db, "certification_project", project_id, "preparation_case", case.id, user
        )
    for original in evidence:
        await protect_child(
            db, "preparation_case", case.id, "preparation_evidence", original.id, user
        )
    return case


async def set_case_originals(db, case, original_evidence_ids, user):
    """Retain source files under this case's access policy, without changing its questions."""
    originals = await get_valid_evidence(db, original_evidence_ids, user)
    for original in originals:
        await protect_child(
            db, "preparation_case", case.id, "preparation_evidence", original.id, user
        )
    case.original_evidence_ids_json = json.dumps([str(item.id) for item in originals])


def fields_for(case: PreparationCase) -> list[PreparationField]:
    return [PreparationField.model_validate(item) for item in json.loads(case.fields_json)]


def field_for(case: PreparationCase, key: str) -> PreparationField:
    field = next((item for item in fields_for(case) if item.key == key), None)
    if field is None:
        raise HTTPException(404, "Field not found")
    return field


def valid_value(field: PreparationField, value) -> bool:
    if value is None or isinstance(value, str) and not value.strip():
        return False
    if field.type in {"text", "multiline"}:
        return isinstance(value, str) and len(value) <= 10000
    if field.type == "yes_no":
        return type(value) is bool
    if field.type == "number":
        return type(value) in {int, float} and -1e15 < value < 1e15
    if field.type == "date":
        if not isinstance(value, str):
            return False
        try:
            return date.fromisoformat(value).isoformat() == value
        except ValueError:
            return False
    if field.type == "choice":
        return isinstance(value, str) and value in field.options
    return False  # Evidence fields are answered with at least one current evidence item.


async def checked_evidence_problem(
    evidence: PreparationEvidence,
    today: date,
    cache: dict[uuid.UUID, str | None] | None = None,
) -> str | None:
    """Check metadata and file bytes without hashing on the event loop.

    The optional cache is scoped to a single API request, so shared library items
    linked to several cases are hashed once in a portfolio response.
    """
    if evidence.archived:
        return "archived_evidence"
    if evidence.valid_from and evidence.valid_from > today:
        return "future_evidence"
    if evidence.valid_until and evidence.valid_until < today:
        return "expired_evidence"
    if evidence.kind != "file":
        return None
    if cache is not None and evidence.id in cache:
        return cache[evidence.id]
    try:
        await run_in_threadpool(verify_evidence_file, evidence)
        problem = None
    except (HTTPException, OSError):
        problem = "invalid_evidence_file"
    if cache is not None:
        cache[evidence.id] = problem
    return problem


async def response_evidence(db: AsyncSession, response_ids: list[uuid.UUID]):
    if not response_ids:
        return {}
    rows = (
        await db.execute(
            select(PreparationResponseEvidence.response_id, PreparationEvidence)
            .join(
                PreparationEvidence,
                PreparationResponseEvidence.evidence_id == PreparationEvidence.id,
            )
            .where(PreparationResponseEvidence.response_id.in_(response_ids))
        )
    ).all()
    result = {response_id: [] for response_id in response_ids}
    for response_id, evidence in rows:
        result[response_id].append(evidence)
    return result


async def audit_response_snapshot(
    db: AsyncSession, response: PreparationResponse | None
) -> dict | None:
    if response is None:
        return None
    evidence = (await response_evidence(db, [response.id])).get(response.id, [])
    value = json.loads(response.value_json) if response.value_json is not None else None
    return {
        "field_key": response.field_key,
        "value": value,
        "value_sha256": hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest(),
        "not_applicable_reason": response.not_applicable_reason,
        "evidence_ids": sorted(str(item.id) for item in evidence),
        "accepted_by": str(response.accepted_by) if response.accepted_by else None,
        "accepted_at": response.accepted_at.isoformat() if response.accepted_at else None,
        "reused_from_case_id": (
            str(response.reused_from_case_id) if response.reused_from_case_id else None
        ),
        "reused_from_field_key": response.reused_from_field_key,
    }


async def build_case_response(
    db: AsyncSession,
    case: PreparationCase,
    evidence_check_cache: dict[uuid.UUID, str | None] | None = None,
    *,
    user: User | None = None,
) -> CaseOut:
    fields = fields_for(case)
    responses = (
        (
            await db.execute(
                select(PreparationResponse).where(PreparationResponse.case_id == case.id)
            )
        )
        .scalars()
        .all()
    )
    evidence_by_response = await response_evidence(db, [response.id for response in responses])
    if user is not None:
        visible_responses = []
        for response in responses:
            allowed = True
            for item in evidence_by_response.get(response.id, []):
                if "view" not in await effective_permissions(
                    db, "preparation_evidence", item.id, user
                ):
                    allowed = False
            if response.reused_from_case_id and "view" not in await effective_permissions(
                db, "preparation_case", response.reused_from_case_id, user
            ):
                allowed = False
            if allowed:
                visible_responses.append(response)
        responses = visible_responses
    original_evidence_ids = [
        uuid.UUID(key) for key in json.loads(case.original_evidence_ids_json or "[]")
    ]
    if user is not None:
        for original_id in original_evidence_ids:
            if "view" not in await effective_permissions(
                db, "preparation_evidence", original_id, user
            ):
                raise HTTPException(403, "Original form evidence requires access")
    response_by_key = {response.field_key: response for response in responses}
    today = datetime.now(UTC).date()
    blockers = []
    answered = accepted = 0
    for field in fields:
        response = response_by_key.get(field.key)
        if response is None:
            if field.required:
                blockers.append(
                    dict(field_key=field.key, code="missing", message="Response required")
                )
            continue
        evidence = evidence_by_response.get(response.id, [])
        problem = None
        for item in evidence:
            problem = await checked_evidence_problem(item, today, evidence_check_cache)
            if problem:
                break
        if problem:
            blockers.append(
                dict(
                    field_key=field.key,
                    code=problem,
                    message="Attached evidence is not currently valid",
                )
            )
        if not field.required:
            continue
        reason = (response.not_applicable_reason or "").strip()
        value = json.loads(response.value_json) if response.value_json is not None else None
        has_answer = bool(reason) or (
            bool(evidence) if field.type == "evidence" else valid_value(field, value)
        )
        if not has_answer:
            blockers.append(dict(field_key=field.key, code="missing", message="Response required"))
            continue
        answered += 1
        if not problem:
            if response.accepted_at is None:
                blockers.append(
                    dict(
                        field_key=field.key,
                        code="pending_acceptance",
                        message="Manager acceptance required",
                    )
                )
            else:
                accepted += 1
    if not any(field.required for field in fields):
        blockers.append(
            dict(field_key="", code="empty_form", message="At least one required field is needed")
        )
    if case.status == "archived":
        blockers.append(dict(field_key="", code="archived_case", message="Form is archived"))
    readiness = Readiness(
        required_count=sum(field.required for field in fields),
        answered_count=answered,
        accepted_count=accepted,
        blockers=blockers,
        ready=not blockers,
    )
    access = None
    if user is not None:
        policy = await access_details(db, "preparation_case", case.id, user)
        access = {
            "visibility": policy["visibility"],
            "permissions": policy["effective_permissions"],
            "revision": policy["revision"],
        }
    return CaseOut(
        access=access,
        id=case.id,
        name=case.name,
        kind=case.kind,
        jurisdiction_id=case.jurisdiction_id,
        project_id=case.project_id,
        owner_id=case.owner_id,
        due_date=case.due_date,
        status=case.status,
        revision=case.revision,
        template_id=case.template_id,
        template_name=case.template_name,
        template_revision=case.template_revision,
        original_evidence_ids=original_evidence_ids,
        fields=fields,
        created_at=case.created_at,
        updated_at=case.updated_at,
        readiness=readiness,
        responses=[
            ResponseOut(
                field_key=response.field_key,
                value=json.loads(response.value_json) if response.value_json is not None else None,
                not_applicable_reason=response.not_applicable_reason,
                evidence_ids=[item.id for item in evidence_by_response.get(response.id, [])],
                accepted_by=response.accepted_by,
                accepted_at=response.accepted_at,
                reused_from_case_id=response.reused_from_case_id,
                reused_from_field_key=response.reused_from_field_key,
            )
            for response in responses
        ],
    )


async def get_case(
    db: AsyncSession, case_id: uuid.UUID, user: User, action="view"
) -> PreparationCase:
    return await require_access(db, PreparationCase, case_id, user, action)


async def advance_case(
    db: AsyncSession, case: PreparationCase, expected_revision: int, *, allow_archived: bool = False
):
    if case.status == "archived" and not allow_archived:
        raise HTTPException(409, "Form is archived")
    result = await db.execute(
        update(PreparationCase)
        .where(
            PreparationCase.id == case.id,
            PreparationCase.revision == expected_revision,
            PreparationCase.status == case.status,
        )
        .values(revision=expected_revision + 1, updated_at=datetime.now(UTC))
    )
    if result.rowcount != 1:
        raise HTTPException(409, "Form changed; reload before editing")
    case.revision = expected_revision + 1


async def get_valid_evidence(db: AsyncSession, ids: list[uuid.UUID], user: User):
    if len(ids) != len(set(ids)):
        raise HTTPException(422, "Duplicate evidence IDs")
    if not ids:
        return []
    items = (
        (
            await db.execute(
                select(PreparationEvidence).where(
                    PreparationEvidence.id.in_(ids), org_clause(PreparationEvidence, user)
                )
            )
        )
        .scalars()
        .all()
    )
    if len(items) != len(ids):
        raise HTTPException(404, "Evidence not found")
    return items


def ensure_answer(
    field: PreparationField, value, reason: str | None, evidence: list[PreparationEvidence]
):
    if reason and reason.strip():
        if value is not None or evidence:
            raise HTTPException(422, "Not-applicable response cannot also have a value or evidence")
        return
    if field.type == "evidence":
        if value is not None:
            raise HTTPException(422, "Evidence field value must be null")
    elif value is not None and not valid_value(field, value):
        raise HTTPException(422, "Value does not match field type")


async def save_response(
    db: AsyncSession,
    case: PreparationCase,
    field: PreparationField,
    expected_revision: int,
    *,
    value,
    reason: str | None,
    evidence: list[PreparationEvidence],
    reused_from_case_id=None,
    reused_from_field_key=None,
):
    ensure_answer(field, value, reason, evidence)
    existing_ids = (
        (
            await db.execute(
                select(PreparationResponseEvidence.evidence_id)
                .join(
                    PreparationResponse,
                    PreparationResponseEvidence.response_id == PreparationResponse.id,
                )
                .where(
                    PreparationResponse.case_id == case.id,
                    PreparationResponse.field_key != field.key,
                )
            )
        )
        .scalars()
        .all()
    )
    if len(set(existing_ids) | {item.id for item in evidence}) > 200:
        raise HTTPException(422, "Form may reference at most 200 distinct evidence items")
    await advance_case(db, case, expected_revision)
    response = (
        await db.execute(
            select(PreparationResponse).where(
                PreparationResponse.case_id == case.id, PreparationResponse.field_key == field.key
            )
        )
    ).scalar_one_or_none()
    if response is None:
        response = PreparationResponse(case_id=case.id, field_key=field.key)
        db.add(response)
        await db.flush()
    response.value_json = json.dumps(value) if value is not None else None
    response.not_applicable_reason = reason.strip() if reason and reason.strip() else None
    response.accepted_by = None
    response.accepted_at = None
    response.reused_from_case_id = reused_from_case_id
    response.reused_from_field_key = reused_from_field_key
    for link in (
        (
            await db.execute(
                select(PreparationResponseEvidence).where(
                    PreparationResponseEvidence.response_id == response.id
                )
            )
        )
        .scalars()
        .all()
    ):
        await db.delete(link)
    await db.flush()
    db.add_all(
        [
            PreparationResponseEvidence(response_id=response.id, evidence_id=item.id)
            for item in evidence
        ]
    )
    await db.flush()
    return response
