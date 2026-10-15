"""Reuse shared evidence in assessment work without copying the library or changing decisions."""
import json
import uuid
from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import delete, select

from app.models.documentation import DocumentationAssessmentEvidence, EvidenceGroup, EvidenceGroupVersion
from app.models.preparation import PreparationEvidence
from app.models.review import ReviewItem, Snapshot
from app.services.access import access_clause, require_access, tenant_clause
from app.services.audit import log_action
from app.services.documentation import checked_evidence
from app.services.preparation import checked_evidence_problem


async def require_shared_sources(db, cycle, user, action="view"):
    """Frozen content retains every source's current permission, even after closure."""
    ids = set((await db.scalars(select(DocumentationAssessmentEvidence.evidence_id).join(
        ReviewItem, ReviewItem.id == DocumentationAssessmentEvidence.review_item_id).where(
            ReviewItem.review_cycle_id == cycle.id))).all())
    if cycle.closed_at and cycle.snapshot_id:
        snapshot = await db.get(Snapshot, cycle.snapshot_id)
        payload = json.loads(snapshot.data_json) if snapshot else {}
        if isinstance(payload, dict):
            for row in payload.get("rows", []):
                ids.update(entry["evidence_id"] for entry in row.get("shared_evidence", []))
    for evidence_id in sorted(ids, key=str):
        await require_access(db, PreparationEvidence, uuid.UUID(str(evidence_id)), user, action)


async def shared_evidence_for_items(db, item_ids, organization_id, evidence_cache=None, fresh=False):
    rows = (await db.execute(select(DocumentationAssessmentEvidence, PreparationEvidence)
        .join(PreparationEvidence, PreparationEvidence.id == DocumentationAssessmentEvidence.evidence_id)
        .where(DocumentationAssessmentEvidence.review_item_id.in_(item_ids),
            PreparationEvidence.organization_id == organization_id).execution_options(populate_existing=fresh))).all()
    output = {item_id: [] for item_id in item_ids}
    evidence_ids = {evidence.id for _, evidence in rows}
    groups = {evidence_id: current_id for evidence_id, current_id in (await db.execute(
        select(EvidenceGroupVersion.evidence_id, EvidenceGroup.current_evidence_id).join(
            EvidenceGroup, EvidenceGroup.id == EvidenceGroupVersion.group_id).where(
                EvidenceGroupVersion.evidence_id.in_(evidence_ids)))).all()} if evidence_ids else {}
    evidence_cache = {} if evidence_cache is None else evidence_cache
    for link, evidence in rows:
        problems = []
        if evidence.id in groups and groups[evidence.id] != evidence.id:
            problems.append("superseded_evidence")
        problem = await checked_evidence_problem(evidence, date.today(), evidence_cache)
        if problem:
            problems.append(problem)
        output[link.review_item_id].append({"evidence_id": evidence.id, "title": evidence.title,
            "kind": evidence.kind, "body": evidence.body, "link_url": evidence.link_url,
            "filename": evidence.filename, "sha256": evidence.sha256, "size_bytes": evidence.size_bytes,
            "locator": link.locator, "rationale": link.rationale, "problems": problems})
    return output


async def replace_shared_evidence(db, cycle, item, user, body):
    if user.role not in {"contributor", "manager", "approver", "assigned_reviewer", "admin"}:
        raise HTTPException(403, "This role cannot edit review evidence")
    if user.role == "assigned_reviewer" and item.assigned_reviewer_id != user.id:
        raise HTTPException(403, "You can only edit items assigned to you")
    if cycle.status != "active" or cycle.closed_at:
        raise HTTPException(409, "This review is read-only")
    # Cycle lock is held by the caller, matching every assessment mutation and closure.
    current_time = item.evidence_changed_at
    expected = body.expected_evidence_changed_at
    def canonical(value):
        return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value
    if canonical(current_time) != canonical(expected):
        raise HTTPException(409, "Review evidence has changed. Reload before saving.")
    existing = (await db.scalars(select(DocumentationAssessmentEvidence).where(
        DocumentationAssessmentEvidence.review_item_id == item.id))).all()
    from app.services.documentation import lock_evidence
    await lock_evidence(db, {link.evidence_id for link in existing} | {link.evidence_id for link in body.links}, user)
    for link in existing:
        await checked_evidence(db, link.evidence_id, user, lock=True)
    seen = set()
    for link in body.links:
        if link.evidence_id in seen:
            raise HTTPException(422, "Evidence can only be linked once")
        seen.add(link.evidence_id)
        await checked_evidence(db, link.evidence_id, user, current=True)
    wanted = {(link.evidence_id, link.locator, link.rationale) for link in body.links}
    if wanted != {(link.evidence_id, link.locator, link.rationale) for link in existing}:
        await db.execute(delete(DocumentationAssessmentEvidence).where(DocumentationAssessmentEvidence.review_item_id == item.id))
        for link in body.links:
            db.add(DocumentationAssessmentEvidence(review_item_id=item.id, created_by=user.id, **link.model_dump()))
        item.evidence_changed_at = datetime.now(timezone.utc)
        await log_action(db, user, "link_shared_evidence", "review_item", str(item.id), new_value={"evidence_changed_at": item.evidence_changed_at.isoformat()})
        await db.flush()
    return {"items": (await shared_evidence_for_items(db, [item.id], cycle.organization_id))[item.id], "evidence_changed_at": item.evidence_changed_at}


async def redact_shared_evidence(db, entries, user):
    if not entries:
        return [], None
    ids = [uuid.UUID(str(entry["evidence_id"])) for entry in entries]
    visible = set((await db.scalars(select(PreparationEvidence.id).where(PreparationEvidence.id.in_(ids),
        tenant_clause(PreparationEvidence, user), access_clause(PreparationEvidence, user, "view")))).all())
    filtered = [entry for entry in entries if uuid.UUID(str(entry["evidence_id"])) in visible]
    warning = "Some supporting evidence is unavailable" if len(filtered) != len(entries) else None
    return filtered, warning


async def review_evidence_collection(db, cycle, item, user, action="view", evidence_cache=None):
    collections = await review_evidence_collections(db, cycle, [item], user, action, evidence_cache)
    collection = collections.get(item.id)
    if collection is None:
        raise HTTPException(409, "Assessment item is missing from its frozen review")
    return collection


async def review_evidence_collections(db, cycle, review_items, user, action="view", evidence_cache=None):
    """Read one authorised owner collection batch, including frozen provenance."""
    from collections import defaultdict
    from app.models.program import CertificationProject
    from app.models.review import ReviewCycle, ReviewItemEvidenceFile
    from app.services.access import get_policy
    from app.services.review_assurance import evidence_download_path, frozen_payload, serialise

    await require_access(db, ReviewCycle, cycle.id, user, action)
    for item in review_items:
        if item.review_cycle_id != cycle.id or (user.role == "assigned_reviewer" and item.assigned_reviewer_id != user.id):
            raise HTTPException(404, "Assessment item not found")
    if action == "export":
        await require_shared_sources(db, cycle, user, "export")
    can_edit = user.role in {"contributor", "manager", "approver", "assigned_reviewer", "admin"} and cycle.status == "active" and not cycle.closed_at
    if can_edit and cycle.certification_project_id:
        policy = await get_policy(db, "certification_project", cycle.certification_project_id)
        legacy_reviewer = user.role in {"assigned_reviewer", "approver"} and (policy is None or (policy.visibility == "organisation" and policy.parent_id is None))
        if not legacy_reviewer:
            can_edit = bool(await db.scalar(select(CertificationProject.id).where(
                CertificationProject.id == cycle.certification_project_id,
                tenant_clause(CertificationProject, user), access_clause(CertificationProject, user, "edit"))))
    ids = {item.id for item in review_items}
    sources = {}
    file_problems = {}
    if cycle.closed_at:
        payload = await frozen_payload(db, cycle)
        frozen_rows = {uuid.UUID(row["item"]["id"]): row for row in payload["rows"]}
        for item in review_items:
            row = frozen_rows.get(item.id)
            if row is not None:
                sources[item.id] = (row.get("shared_evidence", []), row.get("files", []),
                    row["item"].get("evidence_changed_at"), row["item"].get("review_evidence") or "")
    else:
        shared = await shared_evidence_for_items(db, ids, cycle.organization_id, evidence_cache=evidence_cache)
        files = defaultdict(list)
        for entry in (await db.scalars(select(ReviewItemEvidenceFile).where(
            ReviewItemEvidenceFile.review_item_id.in_(ids)).order_by(
                ReviewItemEvidenceFile.uploaded_at, ReviewItemEvidenceFile.id))).all():
            files[entry.review_item_id].append(serialise(entry))
            try:
                await evidence_download_path(db, cycle, entry)
            except (HTTPException, OSError):
                file_problems[str(entry.id)] = ["invalid_evidence_file"]
        sources = {item.id: (shared[item.id], files[item.id], item.evidence_changed_at, item.review_evidence or "")
            for item in review_items}
    evidence_ids = {uuid.UUID(str(entry["evidence_id"])) for shared, *_ in sources.values() for entry in shared}
    visible = set((await db.scalars(select(PreparationEvidence.id).where(
        PreparationEvidence.id.in_(evidence_ids), tenant_clause(PreparationEvidence, user),
        access_clause(PreparationEvidence, user, "view")))).all()) if evidence_ids else set()
    output = {}
    for item_id, (shared, files, changed_at, notes) in sources.items():
        permitted = [entry for entry in shared if uuid.UUID(str(entry["evidence_id"])) in visible]
        warning = "Some supporting evidence is unavailable" if len(permitted) != len(shared) else None
        output[item_id] = collection_response(cycle, item_id, permitted, files, changed_at, notes,
            warning, can_edit, file_problems)
    return output


def collection_response(cycle, item_id, shared, files, changed_at, notes, warning, can_edit, file_problems):
    from app.services.review_assessment import plain_text
    root = f"/review-cycles/{cycle.id}/items/{item_id}"
    items = []
    for evidence in shared:
        record = {**evidence, "kind": "shared_evidence", "evidence_kind": evidence["kind"]}
        if evidence["kind"] == "file":
            record["download_href"] = f"{root}/shared-evidence/{evidence['evidence_id']}/download"
        items.append(record)
    for evidence in files:
        items.append({"kind": "review_file", "file_id": evidence["id"],
            "title": evidence["filename"], "filename": evidence["filename"],
            "description": evidence.get("description"),
            "problems": file_problems.get(str(evidence["id"]), []),
            "download_href": f"{root}/files/{evidence['id']}/download"})
    summary = plain_text(notes)
    return {"items": items, "shared_evidence": shared, "shared_evidence_uri": f"{root}/shared-evidence",
        "legacy_files_uri": f"{root}/files", "evidence_changed_at": changed_at,
        "readonly": cycle.status != "active" or bool(cycle.closed_at), "can_edit": can_edit,
        "warning": warning, "has_review_notes": bool(summary), "review_notes_summary": summary[:1000]}
