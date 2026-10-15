"""Historical source audience checks shared by handovers and certification packages."""

import json
import uuid

from fastapi import HTTPException

from app.models.preparation import PreparationCase
from app.services.access import require_access
from app.services.documentation import checked_evidence


async def readonly_authorize(db, model, resource_id, user, action="view"):
    """Current grant read for immutable archives; never take a live-owner write lock."""
    from sqlalchemy import select
    from app.services.access import access_clause, tenant_clause

    if not user.active or action not in {"view", "export"}:
        raise HTTPException(404, "Not found")
    row = await db.scalar(
        select(model)
        .where(
            model.id == resource_id,
            tenant_clause(model, user) if hasattr(model, "organization_id") else True,
            access_clause(model, user, action),
        )
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise HTTPException(404, "Not found")
    return row


async def validate_snapshot_sources(db, snapshot, user, action="export"):
    if action not in ("view", "export"):
        raise ValueError("Invalid snapshot source action")
    from app.models.documentation import (
        DocumentationRegister,
        DocumentationExpectation,
        AuditorRequestMapping,
    )
    from app.models.preparation import PreparationEvidence
    from app.models.program import CertificationProject

    register = await readonly_authorize(
        db, DocumentationRegister, snapshot.register_id, user, action
    )
    data = json.loads(snapshot.content_json)

    async def project(id_):
        item = await readonly_authorize(db, CertificationProject, uuid.UUID(str(id_)), user, action)
        if item.jurisdiction_id != register.jurisdiction_id:
            raise HTTPException(404, "Original project scope is unavailable")

    if data.get("project_id"):
        await project(data["project_id"])
    for row in data["expectations"]:
        if row.get("project_id"):
            await project(row["project_id"])
        await readonly_authorize(db, DocumentationExpectation, uuid.UUID(row["id"]), user, action)
    for row in data["auditor_requests"]:
        await project(row["project_id"])
        await readonly_authorize(db, PreparationCase, uuid.UUID(str(row["case_id"])), user, action)
        await readonly_authorize(db, AuditorRequestMapping, uuid.UUID(row["id"]), user, action)
    for id_ in set(json.loads(snapshot.evidence_ids_json)) | set(
        data.get("referenced_evidence_ids", [])
    ):
        await readonly_authorize(db, PreparationEvidence, uuid.UUID(id_), user, action)
    await validate_frozen_process_sources(db, data, user, action)
    return data


async def snapshot_case_ids(db, expectations, requests):
    from sqlalchemy import select
    from app.models.documentation import DocumentationProcessTarget
    from app.models.preparation import PreparationResponse

    ids = {item.case_id for item in requests}
    ids.update(
        (
            await db.scalars(
                select(DocumentationProcessTarget.case_id).where(
                    DocumentationProcessTarget.expectation_id.in_(
                        [item.id for item in expectations]
                    ),
                    DocumentationProcessTarget.case_id.is_not(None),
                )
            )
        ).all()
    )
    if ids:
        ids.update(
            (
                await db.scalars(
                    select(PreparationResponse.reused_from_case_id).where(
                        PreparationResponse.case_id.in_(ids),
                        PreparationResponse.reused_from_case_id.is_not(None),
                    )
                )
            ).all()
        )
    return ids


def snapshot_review_cycle_ids(register, expectations):
    """Retain the default context and each independently chosen row review."""
    from app.services.documentation_processes import effective_process_register

    ids = {register.review_cycle_id} if register.review_cycle_id else set()
    ids.update(
        context.review_cycle_id
        for item in expectations
        if (context := effective_process_register(register, item)).review_cycle_id
    )
    return ids


async def lock_snapshot_projects(db, register, project_id, user, expectations, requests):
    """REGISTER is already locked; take every needed PROJECT before canonical owners."""
    from sqlalchemy import select
    from app.models.program import CertificationProject
    from app.models.review import ReviewCycle

    project_ids = {project_id} if project_id else set()
    project_ids.update(item.project_id for item in expectations + requests if item.project_id)
    for cycle_id in sorted(snapshot_review_cycle_ids(register, expectations), key=str):
        cycle = await readonly_authorize(db, ReviewCycle, cycle_id, user, "export")
        if cycle.certification_project_id:
            project_ids.add(cycle.certification_project_id)
    case_ids = await snapshot_case_ids(db, expectations, requests)
    if case_ids:
        project_ids.update(
            (
                await db.scalars(
                    select(PreparationCase.project_id).where(
                        PreparationCase.id.in_(case_ids), PreparationCase.project_id.is_not(None)
                    )
                )
            ).all()
        )
    for id_ in sorted(project_ids, key=str):
        await require_access(db, CertificationProject, id_, user, "export")
    return project_ids


async def lock_snapshot_owners(
    db, register, expectations, requests, user, locked_project_ids, selected_evidence_ids
):
    """Fence owner writes before any full collection projection or file capture."""
    from sqlalchemy import select
    from app.models.application import Application
    from app.models.documentation import (
        DocumentationAssessmentEvidence,
        DocumentationCoverage,
        AuditorRequestEvidence,
    )
    from app.models.preparation import (
        PreparationResponse,
        PreparationResponseEvidence,
        PreparationEvidence,
    )
    from app.models.review import ReviewCycle, ReviewItem
    from app.services.documentation import lock_evidence
    from app.services.review_assurance import frozen_payload

    cycles = []
    for cycle_id in sorted(snapshot_review_cycle_ids(register, expectations), key=str):
        cycle = await db.scalar(
            select(ReviewCycle)
            .where(ReviewCycle.id == cycle_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if cycle is None or (
            cycle.certification_project_id
            and cycle.certification_project_id not in locked_project_ids
        ):
            raise HTTPException(409, "Assessment scope changed; refresh before freezing")
        await require_access(db, ReviewCycle, cycle.id, user, "export")
        cycles.append(cycle)
    if register.application_id:
        application = await db.scalar(
            select(Application)
            .where(Application.id == register.application_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if application is None:
            raise HTTPException(404, "Application source is unavailable")
        await require_access(db, Application, application.id, user, "export")
    case_ids = await snapshot_case_ids(db, expectations, requests)
    cases = []
    if case_ids:
        cases = (
            await db.scalars(
                select(PreparationCase)
                .where(PreparationCase.id.in_(case_ids))
                .order_by(PreparationCase.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
        if any(case.project_id and case.project_id not in locked_project_ids for case in cases):
            raise HTTPException(409, "Form scope changed; refresh before freezing")
        if not (await snapshot_case_ids(db, expectations, requests)).issubset(case_ids):
            raise HTTPException(409, "Reused form scope changed; refresh before freezing")
        for case_id in sorted(case_ids, key=str):
            await require_access(db, PreparationCase, case_id, user, "export")
    evidence_ids = set(selected_evidence_ids)
    evidence_ids.update(
        (
            await db.scalars(
                select(DocumentationCoverage.evidence_id).where(
                    DocumentationCoverage.expectation_id.in_([item.id for item in expectations])
                )
            )
        ).all()
    )
    evidence_ids.update(
        (
            await db.scalars(
                select(AuditorRequestEvidence.evidence_id).where(
                    AuditorRequestEvidence.request_id.in_([item.id for item in requests])
                )
            )
        ).all()
    )
    if case_ids:
        evidence_ids.update(
            (
                await db.scalars(
                    select(PreparationResponseEvidence.evidence_id)
                    .join(
                        PreparationResponse,
                        PreparationResponse.id == PreparationResponseEvidence.response_id,
                    )
                    .where(PreparationResponse.case_id.in_(case_ids))
                )
            ).all()
        )
        for case in cases:
            evidence_ids.update(
                uuid.UUID(value) for value in json.loads(case.original_evidence_ids_json or "[]")
            )
    for cycle in cycles:
        evidence_ids.update(
            (
                await db.scalars(
                    select(DocumentationAssessmentEvidence.evidence_id)
                    .join(
                        ReviewItem, ReviewItem.id == DocumentationAssessmentEvidence.review_item_id
                    )
                    .where(ReviewItem.review_cycle_id == cycle.id)
                )
            ).all()
        )
        if cycle.closed_at:
            payload = await frozen_payload(db, cycle)
            evidence_ids.update(
                uuid.UUID(entry["evidence_id"])
                for row in payload["rows"]
                for entry in row.get("shared_evidence", [])
            )
    await lock_evidence(db, evidence_ids, user)
    if evidence_ids:
        await db.scalars(
            select(PreparationEvidence)
            .where(PreparationEvidence.id.in_(evidence_ids))
            .execution_options(populate_existing=True)
        )


async def freeze_process_targets(
    db, expectation, register, user, *, cache=None, evidence_cache=None
):
    """Resolve authoritative owner collections for a new snapshot, never local mirrors."""
    from types import SimpleNamespace
    from copy import deepcopy
    from sqlalchemy import select
    from app.models.documentation import DocumentationProcessTarget
    from app.models.review import ReviewCycle, ReviewItemEvidenceFile
    from app.services.documentation_process_applications import resolve_application_target
    from app.services.documentation_processes import read_review_target
    from app.services.review_assurance import evidence_download_path, frozen_payload
    from app.services.preparation_files import file_digest
    from starlette.concurrency import run_in_threadpool

    from app.services.documentation_processes import effective_process_register

    register = effective_process_register(register, expectation)

    mappings = (
        await db.scalars(
            select(DocumentationProcessTarget)
            .where(DocumentationProcessTarget.expectation_id == expectation.id)
            .order_by(DocumentationProcessTarget.id)
        )
    ).all()
    targets, evidence, sources = [], [], []
    if cache is None:
        cache = {}
    for mapping in mappings:
        key = (
            register.review_cycle_id,
            mapping.review_item_id,
            register.application_id,
            mapping.case_id,
            mapping.field_key,
        )
        if key in cache:
            saved_target, saved_evidence, saved_source = cache[key]
            target = deepcopy(saved_target)
            if str(target["requirement_id"]) != str(mapping.requirement_id) or str(
                target["requirement_set_version_id"]
            ) != str(mapping.requirement_set_version_id):
                raise HTTPException(
                    409,
                    "A process target changed requirement version; review its mapping before freezing",
                )
            target["id"] = str(mapping.id)
            targets.append(target)
            evidence.extend(saved_evidence)
            sources.append(deepcopy(saved_source))
            continue
        evidence_start = len(evidence)
        if mapping.review_item_id:
            target = await read_review_target(
                db,
                mapping.review_item_id,
                register,
                user,
                cycle_id=register.review_cycle_id,
                action="export",
                evidence_cache=evidence_cache,
            )
            cycle_id = register.review_cycle_id
            cycle = await db.get(ReviewCycle, cycle_id)
            source = {
                "kind": "review_item",
                "review_cycle_id": str(cycle.id),
                "review_item_id": str(mapping.review_item_id),
                "project_id": (
                    str(cycle.certification_project_id) if cycle.certification_project_id else None
                ),
                "shared_evidence_ids": [],
                "review_file_ids": [],
            }
        else:
            target = await resolve_application_target(
                db,
                register.application_id,
                mapping.case_id,
                mapping.field_key,
                register,
                user,
                action="export",
                evidence_cache=evidence_cache,
            )
            cycle = None
            case = await db.get(PreparationCase, mapping.case_id)
            source = {
                "kind": "application_response",
                "application_id": str(register.application_id),
                "case_id": str(mapping.case_id),
                "project_id": str(case.project_id) if case.project_id else None,
                "field_key": mapping.field_key,
                "shared_evidence_ids": [],
                "review_file_ids": [],
            }
        if str(target["requirement_id"]) != str(mapping.requirement_id) or str(
            target["requirement_set_version_id"]
        ) != str(mapping.requirement_set_version_id):
            raise HTTPException(
                409,
                "A process target changed requirement version; review its mapping before freezing",
            )
        source.update(
            requirement_id=str(mapping.requirement_id),
            requirement_set_version_id=str(mapping.requirement_set_version_id),
        )
        collection = target["collection"]
        source["shared_evidence_ids"].extend(
            str(value) for value in collection.get("original_evidence_ids", [])
        )
        source["reused_case_ids"] = (
            [collection["reused_from_case_id"]] if collection.get("reused_from_case_id") else []
        )
        if collection.get("unavailable") or collection.get("warning"):
            raise HTTPException(404, "A canonical process source is unavailable")
        payload = await frozen_payload(db, cycle) if cycle and cycle.closed_at else None
        for entry in collection["items"]:
            if entry["kind"] == "shared_evidence":
                evidence_id = uuid.UUID(str(entry["evidence_id"]))
                item = await checked_evidence(db, evidence_id, user, "export")
                source["shared_evidence_ids"].append(str(item.id))
                if payload:
                    frozen_row = next(
                        (
                            row
                            for row in payload["rows"]
                            if row["item"]["id"] == str(mapping.review_item_id)
                        ),
                        None,
                    )
                    frozen = next(
                        (
                            row
                            for row in (frozen_row or {}).get("shared_evidence", [])
                            if str(row["evidence_id"]) == str(item.id)
                        ),
                        None,
                    )
                    if frozen is None:
                        raise HTTPException(
                            409, "Shared evidence is absent from its completed review"
                        )
                    values = {
                        key: frozen.get(key, getattr(item, key))
                        for key in (
                            "title",
                            "kind",
                            "body",
                            "link_url",
                            "filename",
                            "sha256",
                            "size_bytes",
                        )
                    }
                    values.update(
                        id=item.id, valid_from=item.valid_from, valid_until=item.valid_until
                    )
                    if item.kind == "file":
                        file_entry = next(
                            (
                                row
                                for row in payload["files"]
                                if row["kind"] == "shared_evidence" and row["id"] == str(item.id)
                            ),
                            None,
                        )
                        if file_entry is None:
                            raise HTTPException(409, "Frozen shared evidence bytes are unavailable")
                        values.update(
                            sha256=file_entry["sha256"],
                            size_bytes=file_entry["size"],
                            _verified_source_path=closed_source_path(cycle, file_entry),
                        )
                    item = SimpleNamespace(**values)
                evidence.append(item)
            elif entry["kind"] == "review_file":
                file_id = uuid.UUID(str(entry["file_id"]))
                item = await db.get(ReviewItemEvidenceFile, file_id)
                if item is None or item.review_item_id != mapping.review_item_id:
                    raise HTTPException(404, "Review evidence file is unavailable")
                path = await evidence_download_path(db, cycle, item)
                digest = await run_in_threadpool(file_digest, path)
                evidence.append(
                    SimpleNamespace(
                        id=f"review-file:{item.id}",
                        kind="file",
                        title=item.filename,
                        filename=item.filename,
                        body=item.description,
                        link_url=None,
                        sha256=digest,
                        size_bytes=path.stat().st_size,
                        valid_from=None,
                        valid_until=None,
                        _verified_source_path=path,
                    )
                )
                source["review_file_ids"].append(str(item.id))
        cache[key] = (deepcopy(target), evidence[evidence_start:], deepcopy(source))
        target["id"] = str(mapping.id)
        targets.append(target)
        sources.append(source)
    return targets, evidence, sources


def closed_source_path(cycle, entry):
    from pathlib import Path
    from fastapi import HTTPException
    from app.config import settings

    root = (Path(settings.upload_dir) / "review-snapshots" / str(cycle.snapshot_id)).resolve()
    path = (root / entry["path"]).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(409, "Completed-review evidence bytes are unavailable")
    return path


async def validate_frozen_process_sources(db, data, user, action):
    """Recheck original owner scopes without depending on today's register bindings."""
    from sqlalchemy import select
    from fastapi import HTTPException
    from app.models.application import Application
    from app.models.preparation import PreparationEvidence
    from app.models.review import ReviewCycle, ReviewItem, ReviewItemEvidenceFile
    from app.services.access import access_clause, tenant_clause

    roots = data.get("process_sources", [])
    for source in roots:
        if source.get("application_id"):
            await readonly_authorize(
                db, Application, uuid.UUID(source["application_id"]), user, action
            )
        if source.get("case_id"):
            await readonly_authorize(
                db, PreparationCase, uuid.UUID(source["case_id"]), user, action
            )
        for case_id in source.get("reused_case_ids", []):
            await readonly_authorize(db, PreparationCase, uuid.UUID(case_id), user, action)
        if source.get("project_id"):
            from app.models.program import CertificationProject

            await readonly_authorize(
                db, CertificationProject, uuid.UUID(source["project_id"]), user, action
            )
        if source.get("review_cycle_id"):
            cycle = await db.scalar(
                select(ReviewCycle).where(
                    ReviewCycle.id == uuid.UUID(source["review_cycle_id"]),
                    tenant_clause(ReviewCycle, user),
                    access_clause(ReviewCycle, user, action),
                )
            )
            if cycle is None:
                raise HTTPException(404, "Original review scope is unavailable")
        if source.get("review_item_id"):
            item = await db.scalar(
                select(ReviewItem).where(
                    ReviewItem.id == uuid.UUID(source["review_item_id"]),
                    access_clause(ReviewItem, user, action),
                )
            )
            if item is None or (
                user.role == "assigned_reviewer" and item.assigned_reviewer_id != user.id
            ):
                raise HTTPException(404, "Original review item is unavailable")
        for id_ in source.get("shared_evidence_ids", []):
            await readonly_authorize(db, PreparationEvidence, uuid.UUID(id_), user, action)
        for id_ in source.get("review_file_ids", []):
            existing = await db.get(ReviewItemEvidenceFile, uuid.UUID(id_))
            item = await db.scalar(
                select(ReviewItemEvidenceFile).where(
                    ReviewItemEvidenceFile.id == uuid.UUID(id_),
                    access_clause(ReviewItemEvidenceFile, user, action),
                )
            )
            if existing is not None and item is None:
                raise HTTPException(404, "Original review evidence file is unavailable")
            if item is not None and str(item.review_item_id) != source["review_item_id"]:
                raise HTTPException(404, "Original review evidence file is unavailable")
            # A deleted legacy upload retains the frozen original owner audience.
            # Its stored bytes are verified by the archive builder; never read a
            # replacement file or relax the original cycle/item rights above.
