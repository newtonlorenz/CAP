"""One assessment view for readiness, report rendering and immutable closure records."""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import and_, func, select
from sqlalchemy.inspection import inspect

from app.config import settings
from app.models.document import Document
from app.models.jurisdiction import Jurisdiction
from app.models.program import RequirementSetVersion
from app.models.requirement import Requirement, RequirementStatus, ExtractedRequirement
from app.models.review import ReviewItem, ReviewItemEvidenceFile, ReviewItemComment, Snapshot
from app.models.user import User
from app.services.review_assessment import current_rationale, plain_text


@dataclass
class AssessmentRow:
    item: ReviewItem
    requirement: Requirement
    document: Document | None
    status: str
    owner: User | None = None
    assigned: User | None = None
    responsible: User | None = None
    reviewer: User | None = None
    files: list = field(default_factory=list)
    comments: list = field(default_factory=list)
    source: dict = field(default_factory=dict)
    status_comment: str = ""


def file_digest(handle):
    digest = hashlib.sha256()
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def serialise(model):
    if model is None:
        return None
    keys = [column.key for column in inspect(type(model)).columns]
    if isinstance(model, User):
        keys = ["id", "full_name", "email", "organization_id", "role", "active"]
    # Internal filesystem locations never appear in portable snapshots.
    return {key: getattr(model, key) for key in keys if key not in {"file_path", "password_hash"}}


def hydrate(model, values):
    if values is None:
        return None
    result = {}
    for column in inspect(model).columns:
        if column.key not in values:
            continue
        value = values[column.key]
        if value is not None:
            python_type = column.type.python_type
            if python_type is uuid.UUID:
                value = uuid.UUID(value)
            elif python_type is datetime:
                value = datetime.fromisoformat(value)
        result[column.key] = value
    return model(**result)


async def frozen_payload(db, cycle):
    if not cycle.closed_at:
        return None
    if not cycle.snapshot_id:
        raise HTTPException(409, "This legacy closed review has no complete frozen export. Start a new review to create an assured report.")
    snapshot = await db.get(Snapshot, cycle.snapshot_id)
    payload = json.loads(snapshot.data_json) if snapshot else None
    if not isinstance(payload, dict) or payload.get("schema_version") != 2:
        raise HTTPException(
            409,
            "This legacy closed review has no complete frozen export. Its original snapshot is retained; start a new review to create an assured report.",
        )
    if payload.get("cycle", {}).get("id") != str(cycle.id):
        raise HTTPException(409, "The frozen review scope could not be verified.")
    return payload


async def evidence_download_path(db, cycle, evidence_file):
    """Closed-review downloads use the same verified bytes as the handover package."""
    payload = await frozen_payload(db, cycle)
    if payload is None:
        path = Path(evidence_file.file_path)
        if not path.is_file():
            raise HTTPException(404, "File not found on disk")
        return path
    entry = next((entry for entry in payload["files"]
                  if entry["kind"] == "evidence" and entry["id"] == str(evidence_file.id)), None)
    if entry is None:
        raise HTTPException(409, "This evidence file is not part of the frozen review.")
    root = (Path(settings.upload_dir) / "review-snapshots" / str(cycle.snapshot_id)).resolve()
    path = (root / entry["path"]).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(409, "Frozen evidence is missing. Restore the completed review backup.")
    with path.open("rb") as handle:
        if file_digest(handle) != entry["sha256"]:
            raise HTTPException(409, "Frozen evidence failed its integrity check. Download stopped.")
    return path


async def assessment_rows(db, cycle, *, use_snapshot=True):
    payload = await frozen_payload(db, cycle) if use_snapshot else None
    if payload is not None:
        return [
            AssessmentRow(
                item=hydrate(ReviewItem, row["item"]),
                requirement=hydrate(Requirement, row["requirement"]),
                document=hydrate(Document, row["document"]),
                status=row["status"],
                **{
                    key: hydrate(User, row.get(key))
                    for key in ["owner", "assigned", "responsible", "reviewer"]
                },
                files=[hydrate(ReviewItemEvidenceFile, entry) for entry in row["files"]],
                comments=[hydrate(ReviewItemComment, entry) for entry in row.get("comments", [])],
                source=row.get("source", {}),
                status_comment=row.get("status_comment", ""),
            )
            for row in payload["rows"]
        ]
    latest = select(
        RequirementStatus,
        func.row_number()
        .over(
            partition_by=RequirementStatus.requirement_id,
            order_by=(RequirementStatus.changed_at.desc(), RequirementStatus.id.desc()),
        )
        .label("rn"),
    ).subquery()
    result = await db.execute(
        select(
            ReviewItem,
            Requirement,
            Document,
            latest.c.status,
            latest.c.assigned_to,
            latest.c.comment,
        )
        .join(Requirement, Requirement.id == ReviewItem.requirement_id)
        .outerjoin(Document, Document.id == Requirement.document_id)
        .outerjoin(latest, and_(latest.c.requirement_id == Requirement.id, latest.c.rn == 1))
        .where(
            ReviewItem.review_cycle_id == cycle.id,
            Requirement.organization_id == cycle.organization_id,
        )
        .order_by(Requirement.document_id, Requirement.sort_order, Requirement.reference_id)
    )
    rows = result.all()
    user_ids = {
        uid
        for item, req, doc, status, owner, comment in rows
        for uid in [owner, item.assigned_reviewer_id, item.responsible_user_id, item.reviewer_id]
        if uid
    }
    users = (
        {
            u.id: u
            for u in (
                await db.execute(
                    select(User).where(
                        User.id.in_(user_ids), User.organization_id == cycle.organization_id
                    )
                )
            ).scalars()
        }
        if user_ids
        else {}
    )
    ids = [row[0].id for row in rows]
    files = {i: [] for i in ids}
    comments = {i: [] for i in ids}
    if ids:
        for entry in (
            await db.execute(
                select(ReviewItemEvidenceFile)
                .where(ReviewItemEvidenceFile.review_item_id.in_(ids))
                .order_by(ReviewItemEvidenceFile.uploaded_at, ReviewItemEvidenceFile.id)
            )
        ).scalars():
            files[entry.review_item_id].append(entry)
        for entry in (
            await db.execute(
                select(ReviewItemComment)
                .where(ReviewItemComment.review_item_id.in_(ids))
                .order_by(ReviewItemComment.created_at, ReviewItemComment.id)
            )
        ).scalars():
            comments[entry.review_item_id].append(entry)
    version_ids = {
        r.requirement_set_version_id for _, r, *_ in rows if r.requirement_set_version_id
    }
    versions = (
        {
            v.id: v
            for v in (
                await db.execute(
                    select(RequirementSetVersion).where(RequirementSetVersion.id.in_(version_ids))
                )
            ).scalars()
        }
        if version_ids
        else {}
    )
    extraction_ids = {r.source_extraction_id for _, r, *_ in rows if r.source_extraction_id}
    extracts = (
        {
            e.id: e
            for e in (
                await db.execute(
                    select(ExtractedRequirement).where(ExtractedRequirement.id.in_(extraction_ids))
                )
            ).scalars()
        }
        if extraction_ids
        else {}
    )
    output = []
    for item, req, doc, status, owner, comment in rows:
        version = versions.get(req.requirement_set_version_id)
        extracted = extracts.get(req.source_extraction_id)
        output.append(
            AssessmentRow(
                item,
                req,
                doc,
                item.assessment_status or "not_started",
                users.get(owner),
                users.get(item.assigned_reviewer_id),
                users.get(item.responsible_user_id),
                users.get(item.reviewer_id),
                files[item.id],
                comments[item.id],
                {
                    "baseline_version": version.version_number if version else None,
                    "page": extracted.page_number if extracted else None,
                    "excerpt": extracted.source_excerpt if extracted else None,
                },
                current_rationale(item, comment),
            )
        )
    return output


def assessment_gap_reasons(row):
    """Completion blockers, shared by the review screen and every gap export."""
    kind = row.requirement.requirement_type
    if kind not in {"mandatory", "recommended", "not_applicable"}:
        return []
    reasons = []
    rationale = plain_text(current_rationale(row.item, row.status_comment))
    is_na = row.status == "not_applicable" or kind == "not_applicable"
    if is_na:
        if not rationale:
            reasons.append("Record the reason this requirement does not apply")
    else:
        if row.status != "evidenced":
            reasons.append("Evidence is not complete")
    if row.item.review_status not in {"confirmed", "updated"}:
        reasons.append(
            "Resolve escalation"
            if row.item.review_status == "escalated"
            else "Record the review decision"
        )
    return reasons


def readiness(rows):
    blockers = []
    applicable = 0
    ready = 0
    excluded = 0
    informational = 0
    for row in rows:
        reasons = []
        kind = row.requirement.requirement_type
        if kind not in {"mandatory", "recommended", "not_applicable"}:
            informational += 1
            continue
        is_na = row.status == "not_applicable" or kind == "not_applicable"
        if is_na:
            excluded += 1
        else:
            applicable += 1
        reasons = assessment_gap_reasons(row)
        if reasons:
            blockers.append(
                {
                    "item_id": str(row.item.id),
                    "reference_id": row.requirement.reference_id,
                    "reasons": reasons,
                }
            )
        elif not is_na:
            ready += 1
    if not rows:
        blockers.append(
            {
                "item_id": None,
                "reference_id": "Review scope",
                "reasons": ["Add requirements to this review"],
            }
        )
    return {
        "can_close": not blockers,
        "total": len(rows),
        "applicable": applicable,
        "ready": ready,
        "not_applicable": excluded,
        "informational": informational,
        "blocker_count": len(blockers),
        "blockers": blockers,
    }


async def freeze_review(db, cycle, user, rows):
    snapshot_id = uuid.uuid4()
    folder = Path(settings.upload_dir) / "review-snapshots" / str(snapshot_id)
    folder.mkdir(parents=True, exist_ok=False)
    manifest = []
    copied = set()

    def copy_file(path, name, kind, identity):
        if identity in copied:
            return
        source = Path(path)
        if not source.is_file():
            raise HTTPException(
                409, f"Missing {kind} file: {name}. Restore it before completing the review."
            )
        relative = f"{kind}/{identity}/{Path(name).name}"
        target = folder / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        with target.open("rb") as handle:
            digest = file_digest(handle)
        manifest.append(
            {
                "path": relative,
                "sha256": digest,
                "size": target.stat().st_size,
                "id": identity,
                "kind": kind,
                "filename": name,
            }
        )
        copied.add(identity)

    try:
        for row in rows:
            if row.document and row.document.has_source:
                copy_file(
                    row.document.file_path, row.document.filename, "sources", str(row.document.id)
                )
            for entry in row.files:
                copy_file(entry.file_path, entry.filename, "evidence", str(entry.id))
        jurisdiction = await db.get(Jurisdiction, cycle.jurisdiction_id)
        payload = {
            "schema_version": 2,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "cycle": serialise(cycle),
            "jurisdiction": serialise(jurisdiction),
            "closed_by": serialise(user),
            "readiness": readiness(rows),
            "files": manifest,
            "rows": [
                {
                    "item": serialise(row.item),
                    "requirement": serialise(row.requirement),
                    "document": serialise(row.document),
                    "status": row.status,
                    "status_comment": row.status_comment,
                    **{
                        key: serialise(getattr(row, key))
                        for key in ["owner", "assigned", "responsible", "reviewer"]
                    },
                    "files": [serialise(x) for x in row.files],
                    "comments": [serialise(x) for x in row.comments],
                    "source": row.source,
                }
                for row in rows
            ],
        }
        encoded = json.dumps(payload, default=str, sort_keys=True)
        snapshot = Snapshot(
            id=snapshot_id,
            organization_id=cycle.organization_id,
            name=f"Completed review: {cycle.name}",
            description="Frozen scope, decisions, source metadata and evidence manifest",
            snapshot_type="review_cycle",
            data_json=encoded,
            total_requirements=len(rows),
            evidenced_requirements=sum(r.status == "evidenced" for r in rows),
            created_by=user.id,
        )
        db.add(snapshot)
        await db.flush()
        return snapshot, folder
    except BaseException:
        shutil.rmtree(folder)
        raise
