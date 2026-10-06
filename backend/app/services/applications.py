"""Application readiness, revision fencing and immutable approval packs."""

import hashlib
import io
import json
import uuid
import zipfile
from datetime import UTC, datetime

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, update

from app.api.tenant import org_clause
from app.models.application import (
    Application,
    ApplicationComponent,
    ApplicationFollowup,
    ApplicationSnapshot,
)
from app.models.audit import AuditLog
from app.models.preparation import PreparationCase, PreparationEvidence
from app.schemas.preparation_evidence import EvidenceResponse
from app.services.access import access_details, effective_permissions, require_access
from app.services.access_audit import full_content_access_clause
from app.services.application_documents import build_application_documents
from app.services.preparation import build_case_response, checked_evidence_problem
from app.services.preparation_files import checked_evidence_path, clean_filename

MAX_PACK_BYTES = 200 * 1024 * 1024


def values(row, keys):
    return jsonable_encoder({key: getattr(row, key) for key in keys.split()})


def component_data(row):
    return values(
        row, "id name kind required included owner_id due_date case_id evidence_id profile_item_key"
    )


def followup_data(row):
    return {
        **values(row, "id question owner_id due_date response status resolved_at created_at"),
        "evidence_ids": json.loads(row.evidence_ids_json),
    }


def snapshot_data(row):
    return values(
        row, "id version approved_at approved_by submitted_at reference notes sha256 size_bytes"
    )


async def get_application(db, application_id, user, action="view"):
    return await require_access(db, Application, application_id, user, action)


async def require_pack_sources(db, record, user, action="view"):
    """Historical archives retain the access boundaries of every captured source."""
    for case in record.get("forms", []):
        await require_access(db, PreparationCase, uuid.UUID(case["id"]), user, action)
    for evidence in record.get("evidence", []):
        await require_access(db, PreparationEvidence, uuid.UUID(evidence["id"]), user, action)


async def advance(db, application, expected_revision, allowed):
    if application.status not in allowed:
        raise HTTPException(409, "This action is unavailable at the current application stage")
    result = await db.execute(
        update(Application)
        .where(
            Application.id == application.id,
            Application.revision == expected_revision,
            Application.status == application.status,
        )
        .values(revision=expected_revision + 1, updated_at=datetime.now(UTC))
    )
    if result.rowcount != 1:
        raise HTTPException(409, "Application changed; reload before editing")
    application.revision = expected_revision + 1


async def collect(db, application, user, *, lock=False, evidence_check_cache=None):
    if evidence_check_cache is None:
        evidence_check_cache = {}
    components = list(
        (
            await db.scalars(
                select(ApplicationComponent)
                .where(ApplicationComponent.application_id == application.id)
                .order_by(ApplicationComponent.id)
            )
        ).all()
    )
    followups = list(
        (
            await db.scalars(
                select(ApplicationFollowup)
                .where(ApplicationFollowup.application_id == application.id)
                .order_by(ApplicationFollowup.created_at, ApplicationFollowup.id)
            )
        ).all()
    )
    case_ids = {item.case_id for item in components if item.included and item.case_id}
    query = (
        select(PreparationCase)
        .where(PreparationCase.id.in_(case_ids), org_clause(PreparationCase, user))
        .order_by(PreparationCase.id)
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    cases = {item.id: item for item in (await db.scalars(query)).all()}
    case_data = {
        key: (await build_case_response(db, case, evidence_check_cache)).model_dump(mode="json")
        for key, case in cases.items()
    }
    evidence_ids = {item.evidence_id for item in components if item.included and item.evidence_id}
    for data in case_data.values():
        data["responses"].sort(key=lambda response: response["field_key"])
        for response in data["responses"]:
            response["evidence_ids"].sort()
            evidence_ids.update(uuid.UUID(key) for key in response["evidence_ids"])
        evidence_ids.update(uuid.UUID(key) for key in data.get("original_evidence_ids", []))
    for item in followups:
        evidence_ids.update(uuid.UUID(key) for key in json.loads(item.evidence_ids_json))
    query = (
        select(PreparationEvidence)
        .where(PreparationEvidence.id.in_(evidence_ids), org_clause(PreparationEvidence, user))
        .order_by(PreparationEvidence.id)
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    evidence = {item.id: item for item in (await db.scalars(query)).all()}
    problems = {
        key: await checked_evidence_problem(item, datetime.now(UTC).date(), evidence_check_cache)
        for key, item in evidence.items()
    }
    blockers = []

    def block(code, message, component_id=None):
        item = {"code": code, "message": message}
        if component_id:
            item["component_id"] = str(component_id)
        return item

    outputs = []
    hidden_sources = bool(evidence_ids - set(evidence))
    for item in components:
        source_type = "preparation_case" if item.case_id else "preparation_evidence"
        source_id = item.case_id or item.evidence_id
        case_has_hidden_evidence = item.case_id in case_data and any(
            uuid.UUID(key) not in evidence
            for response in case_data[item.case_id]["responses"]
            for key in response["evidence_ids"]
        )
        if item.case_id in case_data and any(
            uuid.UUID(key) not in evidence
            for key in case_data[item.case_id].get("original_evidence_ids", [])
        ):
            case_has_hidden_evidence = True
        if item.case_id in case_data:
            for key in case_data[item.case_id].get("original_evidence_ids", []):
                if "view" not in await effective_permissions(
                    db, "preparation_evidence", uuid.UUID(key), user
                ):
                    case_has_hidden_evidence = True
        if case_has_hidden_evidence or (
            source_id
            and "view" not in await effective_permissions(db, source_type, source_id, user)
        ):
            hidden_sources = True
            blockers.append(block("restricted_source", "A component requires additional access"))
            continue
        issues = []
        case = case_data.get(item.case_id)
        if item.required and not item.included:
            blockers.append(
                block("excluded_required", f"{item.name}: required form or document is excluded", item.id)
            )
        if item.included:
            if not item.case_id and not item.evidence_id:
                issues.append(
                    block("missing_component", f"{item.name}: attach a form or document", item.id)
                )
            if item.case_id:
                if not case or cases[item.case_id].jurisdiction_id != application.jurisdiction_id:
                    issues.append(
                        block("unavailable_case", f"{item.name}: form unavailable", item.id)
                    )
                else:
                    # Navigation metadata is presentation-only: keep the source rules and
                    # immutable pack record unchanged. Sources have passed access checks above.
                    fields = {field["key"]: field for field in case["fields"]}
                    for issue in case["readiness"]["blockers"]:
                        field = fields.get(issue.get("field_key"), {})
                        issues.append({
                            **block(issue["code"], f"{item.name}: {issue['message']}", item.id),
                            "case_id": str(item.case_id),
                            "field_key": issue.get("field_key") or None,
                            "field_label": field.get("label"),
                            "field_type": field.get("type"),
                            "section": field.get("section"),
                        })
            if item.evidence_id and (
                item.evidence_id not in evidence or problems.get(item.evidence_id)
            ):
                issues.append(
                    block(
                        "invalid_evidence", f"{item.name}: document is not currently valid", item.id
                    )
                )
            blockers.extend(issues)
        outputs.append(
            {
                **component_data(item),
                "case_name": case["name"] if case else None,
                "form_field_count": len(case["fields"]) if case else 0,
                "ready": item.included and not issues,
                "blockers": issues,
            }
        )
    if not any(item.included for item in components):
        blockers.append(block("empty_pack", "Include at least one form, annex or document"))
    for item in followups:
        if item.status != "resolved":
            blockers.append(
                block("open_followup", f"Resolve authority query: {item.question[:150]}")
            )
    # All linked evidence, including optional answers and resolved follow-up responses, stays current.
    for key in evidence_ids:
        if key not in evidence or problems.get(key):
            blockers.append(
                block(
                    "invalid_evidence", "A linked evidence item is unavailable or no longer valid"
                )
            )
    record = {
        "application": values(
            application,
            "id name scope jurisdiction_id applicant authority description owner_id due_date",
        ),
        "profile_snapshot": json.loads(application.profile_snapshot_json)
        if application.profile_snapshot_json
        else None,
        "setup_answers": json.loads(application.setup_answers_json)
        if application.setup_answers_json
        else None,
        "components": [component_data(item) for item in components if item.included],
        "forms": [case_data[key] for key in sorted(case_data, key=str)],
        "followups": [followup_data(item) for item in followups],
        "evidence": [
            EvidenceResponse.model_validate(item).model_dump(mode="json")
            for item in evidence.values()
        ],
    }
    fingerprint = hashlib.sha256(
        json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    required = [item for item in outputs if item["required"]]
    readiness = {
        "ready": not blockers,
        "required_count": len(required),
        "ready_count": sum(item["ready"] for item in required),
        "blockers": blockers,
    }
    if hidden_sources:
        readiness = {
            "ready": False,
            "required_count": 0,
            "ready_count": 0,
            "blockers": [
                block("restricted_source", "Additional access is required to review this pack")
            ],
        }
    return outputs, followups, readiness, record, fingerprint, list(evidence.values())


async def detail(db, application, user, evidence_check_cache=None):
    policy = await access_details(db, "application", application.id, user)
    permissions = policy["effective_permissions"]
    access = {
        "visibility": policy["visibility"],
        "permissions": permissions,
        "revision": policy["revision"],
    }
    if "view" not in permissions:
        return {
            **values(application, "id name status due_date"),
            "access": access,
            "summary_only": True,
        }
    components, followups, readiness, _, fingerprint, _ = await collect(
        db, application, user, evidence_check_cache=evidence_check_cache
    )
    snapshots = list(
        (
            await db.scalars(
                select(ApplicationSnapshot)
                .where(ApplicationSnapshot.application_id == application.id)
                .order_by(ApplicationSnapshot.version.desc())
            )
        ).all()
    )
    if application.status == "in_review" and application.review_fingerprint != fingerprint:
        readiness["ready"] = False
        readiness["blockers"].append(
            {
                "code": "review_stale",
                "message": "Pack changed during review. Return to draft and request review again.",
            }
        )
    if application.status == "approved" and snapshots and snapshots[0].fingerprint != fingerprint:
        readiness["ready"] = False
        readiness["blockers"].append(
            {
                "code": "approval_stale",
                "message": "Pack changed after approval. Return to draft and approve a new version.",
            }
        )
    history = (
        await db.scalars(
            select(AuditLog)
            .where(
                AuditLog.entity_type == "application",
                AuditLog.entity_id == str(application.id),
                org_clause(AuditLog, user),
            )
            .order_by(AuditLog.timestamp.desc())
            .limit(200)
        )
    ).all()
    partial = any(item["code"] == "restricted_source" for item in readiness["blockers"])
    history_visible = bool(
        await db.scalar(
            select(Application.id).where(
                Application.id == application.id, full_content_access_clause(Application, user)
            )
        )
    )
    return {
        **values(
            application,
            "id name scope jurisdiction_id applicant authority description owner_id due_date status revision outcome created_at updated_at",
        ),
        "access": access,
        "profile_snapshot": None
        if partial
        else (
            json.loads(application.profile_snapshot_json)
            if application.profile_snapshot_json
            else None
        ),
        "setup_answers": None
        if partial
        else (
            json.loads(application.setup_answers_json) if application.setup_answers_json else None
        ),
        "components": components,
        "followups": [] if partial else [followup_data(item) for item in followups],
        "readiness": readiness,
        "snapshots": []
        if partial or not history_visible
        else [snapshot_data(item) for item in snapshots],
        "history": [
            {
                **values(item, "id action user_name timestamp"),
                "details": {},
            }
            for item in ([] if partial or not history_visible else history)
        ],
    }


def build_archive(record, evidence, version, approved_at, approved_by):
    """Capture actual bytes once; later downloads never consult mutable source files."""
    record = {
        "format_version": 1,
        "purpose": "Internally approved application pack; download does not submit it to an authority.",
        "version": version,
        "approved_at": approved_at.isoformat(),
        "approved_by": str(approved_by),
        **record,
    }
    payload = json.dumps(record, sort_keys=True, indent=2).encode()
    documents = {"application.json": payload, **build_application_documents(record)}
    total = sum(len(content) for content in documents.values())
    if total > MAX_PACK_BYTES or len(evidence) > 1000:
        raise HTTPException(413, "Application pack exceeds its 200 MB or 1000 evidence item limit")
    output = io.BytesIO()
    manifest = []
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in documents.items():
            archive.writestr(name, content)
            manifest.append(
                {
                    "path": name,
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "size_bytes": len(content),
                }
            )
        for item in evidence:
            if item.kind != "file":
                continue
            path = checked_evidence_path(item)
            if total + path.stat().st_size > MAX_PACK_BYTES:
                raise HTTPException(413, "Application pack exceeds 200 MB")
            name = f"evidence/{item.id}/{clean_filename(item.filename)}"
            digest = hashlib.sha256()
            size = 0
            with path.open("rb") as source, archive.open(name, "w") as target:
                while chunk := source.read(1024 * 1024):
                    total += len(chunk)
                    size += len(chunk)
                    if total > MAX_PACK_BYTES:
                        raise HTTPException(413, "Application pack exceeds 200 MB")
                    digest.update(chunk)
                    target.write(chunk)
            if size != item.size_bytes or digest.hexdigest() != item.sha256:
                raise HTTPException(
                    409, "Evidence changed while preparing approval; upload a verified copy"
                )
            manifest.append({"path": name, "sha256": digest.hexdigest(), "size_bytes": size})
        archive.writestr("manifest.json", json.dumps({"files": manifest}, indent=2))
    return output.getvalue()


async def transition(db, application, action, body, user):
    allowed = {
        "request-review": {"draft"},
        "approve": {"in_review"},
        "return-to-draft": {"in_review", "approved", "submitted", "follow_up", "completed"},
        "record-submission": {"approved"},
        "start-follow-up": {"submitted"},
        "complete": {"submitted", "follow_up"},
    }
    if action not in allowed:
        raise HTTPException(404, "Unknown workflow action")
    await advance(db, application, body.expected_revision, allowed[action])
    _, followups, readiness, record, fingerprint, evidence = await collect(
        db, application, user, lock=True
    )
    if action in {"request-review", "approve", "record-submission"} and not readiness["ready"]:
        raise HTTPException(
            422, {"message": "Application pack is not ready", "blockers": readiness["blockers"]}
        )
    latest = (
        await db.scalars(
            select(ApplicationSnapshot)
            .where(ApplicationSnapshot.application_id == application.id)
            .order_by(ApplicationSnapshot.version.desc())
            .limit(1)
        )
    ).first()
    if action == "approve":
        await require_pack_sources(db, record, user, "export")
        if application.review_fingerprint != fingerprint:
            raise HTTPException(
                409, "Pack changed during review. Return to draft and request review again."
            )
        now = datetime.now(UTC)
        version = latest.version + 1 if latest else 1
        archive = await run_in_threadpool(build_archive, record, evidence, version, now, user.id)
        db.add(
            ApplicationSnapshot(
                application_id=application.id,
                version=version,
                fingerprint=fingerprint,
                approved_by=user.id,
                approved_at=now,
                archive=archive,
                sha256=hashlib.sha256(archive).hexdigest(),
                size_bytes=len(archive),
            )
        )
        application.status = "approved"
    elif action == "record-submission":
        if not latest or latest.fingerprint != fingerprint:
            raise HTTPException(
                409, "Pack changed after approval. Return to draft and approve a new version."
            )
        if not body.reference or body.submitted_at is None:
            raise HTTPException(422, "Submission reference and date are required")
        submitted = body.submitted_at
        if submitted.tzinfo is None:
            raise HTTPException(422, "Submission date must include a timezone")
        approved = (
            latest.approved_at.replace(tzinfo=UTC)
            if latest.approved_at.tzinfo is None
            else latest.approved_at
        )
        if submitted < approved or submitted > datetime.now(UTC):
            raise HTTPException(422, "Submission date must be between approval and now")
        latest.submitted_at, latest.reference, latest.notes = submitted, body.reference, body.notes
        application.status = "submitted"
    elif action == "return-to-draft":
        if not body.reason:
            raise HTTPException(422, "A reason is required to return to draft")
        application.status, application.outcome, application.review_fingerprint = (
            "draft",
            None,
            None,
        )
    elif action == "complete":
        if any(item.status != "resolved" for item in followups):
            raise HTTPException(422, "Resolve outstanding authority queries before completion")
        if not body.outcome:
            raise HTTPException(422, "Record the authority outcome before completing")
        application.status, application.outcome = "completed", body.outcome
    elif action == "start-follow-up":
        application.status = "follow_up"
    else:
        application.status = "in_review"
        application.review_fingerprint = fingerprint
