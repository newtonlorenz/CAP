"""Attach immutable documentation handovers to the existing internal package workflow."""
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_current_user, require_role
from app.api.program import _get_submission_package_for_user, _require_package_access
from app.database import get_db
from app.models.documentation_integrations import DocumentationSnapshot
from app.models.program import SubmissionPackageArtifact
from app.models.user import User
from app.schemas.program import SubmissionPackageArtifactResponse
from app.services.audit import log_action
from app.services.documentation_export import build_documentation_archive, frozen_evidence
from app.services.documentation_packages import validate_artifact_source
from app.services.documentation_snapshots import validate_snapshot_sources

router = APIRouter(prefix="/api/v1/documentation", tags=["documentation packages"])


class AttachSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str | None = Field(None, min_length=1, max_length=255)
    required: bool = True


@router.post("/snapshots/{snapshot_id}/packages/{package_id}", response_model=SubmissionPackageArtifactResponse, status_code=201)
async def attach_snapshot(snapshot_id: uuid.UUID, package_id: uuid.UUID, body: AttachSnapshot = Body(default=AttachSnapshot()),
    db: AsyncSession = Depends(get_db), user: User = Depends(require_role("manager", "admin"))):
    snapshot = await db.get(DocumentationSnapshot, snapshot_id)
    if snapshot is None:
        raise HTTPException(404, "Snapshot not found")
    # Take the register/source locks before the package lock, matching export order.
    data = await validate_snapshot_sources(db, snapshot, user, "export")
    await _require_package_access(db, user, package_id, "edit")
    package = await _get_submission_package_for_user(db, user, package_id, lock=True)
    if package.status != "draft" or package.locked_at:
        raise HTTPException(409, "Documentation sources can only be attached to a draft package")
    if data.get("project_id") != str(package.project_id):
        raise HTTPException(422, "Freeze documentation for this package's project before attaching it")
    duplicate = await db.scalar(select(SubmissionPackageArtifact.id).where(
        SubmissionPackageArtifact.submission_package_id == package.id,
        SubmissionPackageArtifact.documentation_snapshot_id == snapshot.id))
    if duplicate:
        raise HTTPException(409, "This documentation snapshot is already attached")
    artifact = SubmissionPackageArtifact(id=uuid.uuid4(), submission_package_id=package.id,
        documentation_snapshot_id=snapshot.id, artifact_type="documentation_register_snapshot",
        name=body.name or f"{data['register']['name']} · revision {snapshot.register_revision}"[:255],
        required=body.required, included=True)
    artifact.link_url = f"/api/v1/documentation/package-artifacts/{artifact.id}/download"
    db.add(artifact)
    await db.flush()
    await log_action(db, user, "attach_documentation_snapshot", "submission_package_artifact", str(artifact.id),
        new_value={"documentation_snapshot_id": str(snapshot.id), "register_revision": snapshot.register_revision})
    await db.commit()
    await db.refresh(artifact)
    return artifact


@router.get("/package-artifacts/{artifact_id}/download")
async def download_artifact(artifact_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    artifact = await db.get(SubmissionPackageArtifact, artifact_id)
    if artifact is None or artifact.documentation_snapshot_id is None:
        raise HTTPException(404, "Artifact not found")
    await _require_package_access(db, user, artifact.submission_package_id, "export")
    snapshot, data = await validate_artifact_source(db, artifact, user, "export")
    evidence = frozen_evidence(data.get("frozen_evidence", []), user.organization_id)
    stream = await run_in_threadpool(build_documentation_archive, data, evidence)
    try:
        await log_action(db, user, "export", "submission_package_artifact", str(artifact.id),
            new_value={"documentation_snapshot_id": str(snapshot.id)})
        await db.commit()
    except BaseException:
        stream.close()
        raise
    def chunks():
        while chunk := stream.read(1024 * 1024):
            yield chunk
    return StreamingResponse(chunks(), media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="documentation-{snapshot.id}.zip"'},
        background=BackgroundTask(stream.close))
