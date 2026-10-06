import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.api.documents import _get_document_for_user
from app.database import get_db
from app.models.document import Document
from app.models.requirement_quality import RequirementQualityFinding, RequirementQualityRun
from app.models.user import User
from app.schemas.requirement_quality import (
    QualityFindingResponse,
    QualityRunCreate,
    QualityRunResponse,
)
from app.services.extraction_jobs import utcnow
from app.services.quality_jobs import create_quality_run, dispatch_quality_run, quality_config

router = APIRouter(prefix="/api/v1/documents", tags=["source quality"])


async def selected_run(db, user, document_id, run_id):
    await _get_document_for_user(db, user, document_id)
    run = await db.get(RequirementQualityRun, run_id)
    if not run or run.document_id != document_id:
        raise HTTPException(404, "Source quality run not found")
    return run


async def response(db, run):
    value = QualityRunResponse.model_validate(run).model_dump()
    findings = list(
        (
            await db.scalars(
                select(RequirementQualityFinding).where(RequirementQualityFinding.run_id == run.id)
            )
        ).all()
    )
    value["findings"] = []
    for finding in findings:
        item = QualityFindingResponse.model_validate(finding).model_dump()
        item["answers"] = {
            key: answer for key, answer in item["answers"].items() if not key.startswith("_")
        }
        value["findings"].append(item)
    return value


@router.post("/{document_id}/quality-runs", response_model=QualityRunResponse)
async def create(
    document_id: uuid.UUID,
    body: QualityRunCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("manager", "admin")),
):
    doc = await _get_document_for_user(db, user, document_id)
    doc = await db.scalar(select(Document).where(Document.id == doc.id).with_for_update())
    config, revision = await quality_config(db, body.allow_external_ai, body.jev_settings_revision)
    run = await create_quality_run(
        db,
        doc,
        user,
        config,
        revision,
        extraction_run_id=body.extraction_run_id,
        version_id=body.version_id,
    )
    await db.commit()
    await dispatch_quality_run(db, run.id)
    await db.refresh(run)
    return await response(db, run)


@router.get("/{document_id}/quality-runs")
async def list_runs(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _get_document_for_user(db, user, document_id)
    runs = list(
        (
            await db.scalars(
                select(RequirementQualityRun)
                .where(RequirementQualityRun.document_id == document_id)
                .order_by(RequirementQualityRun.created_at.desc())
                .limit(100)
            )
        ).all()
    )
    return {"items": [QualityRunResponse.model_validate(run) for run in runs]}


@router.get("/{document_id}/quality-runs/{run_id}", response_model=QualityRunResponse)
async def detail(
    document_id: uuid.UUID,
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await response(db, await selected_run(db, user, document_id, run_id))


@router.post("/{document_id}/quality-runs/{run_id}/cancel", response_model=QualityRunResponse)
async def cancel(
    document_id: uuid.UUID,
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("manager", "admin")),
):
    doc = await _get_document_for_user(db, user, document_id)
    await db.refresh(doc, with_for_update=True)
    run = await selected_run(db, user, document_id, run_id)
    await db.refresh(run, with_for_update=True)
    if run.status in {"waiting_extraction", "pending", "running"}:
        run.status = "cancelled"
        run.completed_at = utcnow()
        run.owner_token = None
        from app.services.audit import log_action

        await log_action(
            db,
            user,
            "cancel",
            "requirement_quality_run",
            str(run.id),
            new_value={"status": "cancelled"},
        )
        await db.commit()
    return await response(db, run)
