"""Submission packages retain typed documentation snapshots and their source audience."""

import json

from fastapi import HTTPException
from sqlalchemy import select

from app.models.documentation_integrations import DocumentationSnapshot
from app.models.program import SubmissionPackageArtifact


async def validate_artifact_source(db, artifact, user, action="view"):
    if artifact.documentation_snapshot_id is None:
        return None
    snapshot = await db.get(DocumentationSnapshot, artifact.documentation_snapshot_id)
    if snapshot is None:
        raise HTTPException(404, "Artifact source not found")
    from app.services.documentation_snapshots import validate_snapshot_sources

    data = await validate_snapshot_sources(db, snapshot, user, action)
    return snapshot, data


async def require_documentation_package_sources(db, package_id, user, action="view"):
    query = select(SubmissionPackageArtifact).where(
        SubmissionPackageArtifact.submission_package_id == package_id,
        SubmissionPackageArtifact.documentation_snapshot_id.is_not(None),
    )
    # Bundle manifests describe excluded artifacts too; each emitted source must
    # retain its current audience regardless of the inclusion checkbox.
    if action != "export":
        query = query.where(SubmissionPackageArtifact.included.is_(True))
    artifacts = (await db.scalars(query)).all()
    for artifact in artifacts:
        await validate_artifact_source(db, artifact, user, action)


async def index_snapshot_sources(db, snapshot, data):
    """Persist original identities alongside the immutable JSON, in the same transaction."""
    import uuid
    from app.models.documentation import DocumentationSnapshotSource

    identities = set()
    if data.get("project_id"):
        identities.add(("project_id", str(data["project_id"])))
    for evidence_id in set(json.loads(snapshot.evidence_ids_json)) | set(
        data.get("referenced_evidence_ids", [])
    ):
        identities.add(("evidence_id", str(evidence_id)))
    for row in data.get("expectations", []):
        identities.add(("expectation_id", str(row["id"])))
        if row.get("project_id"):
            identities.add(("project_id", str(row["project_id"])))
    for row in data.get("auditor_requests", []):
        identities.add(("request_id", str(row["id"])))
        identities.add(("project_id", str(row["project_id"])))
        identities.add(("case_id", str(row["case_id"])))
    for source in data.get("process_sources", []):
        for key in ("application_id", "review_cycle_id", "review_item_id", "case_id", "project_id"):
            if source.get(key):
                identities.add((key, str(source[key])))
        identities.update(("case_id", str(value)) for value in source.get("reused_case_ids", []))
        identities.update(
            ("evidence_id", str(value)) for value in source.get("shared_evidence_ids", [])
        )
        identities.update(
            ("review_file_id", str(value)) for value in source.get("review_file_ids", [])
        )
    for key, value in sorted(identities):
        db.add(DocumentationSnapshotSource(snapshot_id=snapshot.id, **{key: uuid.UUID(value)}))
    await db.flush()
