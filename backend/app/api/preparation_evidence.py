"""Organisation-owned reusable evidence, independent of any requirement baseline."""

import uuid
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_current_user, require_role
from app.api.tenant import apply_org_scope, get_org_owned_or_404
from app.config import settings
from app.database import get_db
from app.models.preparation import PreparationEvidence
from app.models.user import User
from app.schemas.preparation_evidence import (
    EvidenceArchive,
    EvidenceCreate,
    EvidenceDetails,
    EvidenceResponse,
)
from app.services.access import access_details, initialize_access, require_access
from app.services.audit import log_action
from app.services.file_utils import save_upload_file
from app.services.preparation_files import (
    ALLOWED_EXTENSIONS,
    clean_filename,
    evidence_root,
    file_digest,
    verify_evidence_file,
)

router = APIRouter(prefix="/api/v1/preparation/evidence", tags=["preparation evidence"])
editor = require_role("contributor", "manager", "admin")


async def evidence_response(db, item, user):
    policy = await access_details(db, "preparation_evidence", item.id, user)
    return EvidenceResponse.model_validate(item).model_copy(
        update={
            "access": {
                "visibility": policy["visibility"],
                "permissions": policy["effective_permissions"],
                "revision": policy["revision"],
            }
        }
    )


@router.get("", response_model=dict)
async def list_evidence(
    include_archived: bool = False,
    q: str = Query("", max_length=255),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = apply_org_scope(select(PreparationEvidence), PreparationEvidence, user)
    if not include_archived:
        query = query.where(PreparationEvidence.archived.is_(False))
    if q.strip():
        query = query.where(PreparationEvidence.title.icontains(q.strip(), autoescape=True))
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = (
        await db.scalars(
            query.order_by(PreparationEvidence.created_at.desc(), PreparationEvidence.id)
            .offset(skip)
            .limit(limit)
        )
    ).all()
    return {"items": [await evidence_response(db, row, user) for row in rows], "total": total}


@router.post("", response_model=EvidenceResponse, status_code=201)
async def create_evidence(
    body: EvidenceCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(editor),
):
    values = body.model_dump(exclude={"link_url", "visibility"})
    item = PreparationEvidence(
        id=uuid.uuid4(),
        organization_id=user.organization_id,
        created_by=user.id,
        link_url=str(body.link_url) if body.link_url else None,
        **values,
    )
    db.add(item)
    await db.flush()
    await initialize_access(db, "preparation_evidence", item.id, user, visibility=body.visibility)
    await log_action(
        db,
        user,
        "create",
        "preparation_evidence",
        str(item.id),
        new_value={"title": item.title, "kind": item.kind},
    )
    await db.commit()
    await db.refresh(item)
    return await evidence_response(db, item, user)


@router.post("/upload", response_model=EvidenceResponse, status_code=201)
async def upload_evidence(
    file: UploadFile = File(...),
    visibility: Literal["organisation", "restricted", "secret"] = Form("secret"),
    title: str = Form(..., min_length=1, max_length=255),
    body: str | None = Form(None, max_length=50000),
    valid_from: date | None = Form(None),
    valid_until: date | None = Form(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(editor),
):
    try:
        metadata = EvidenceDetails(
            title=title, body=body, valid_from=valid_from, valid_until=valid_until
        )
    except ValidationError:
        raise HTTPException(422, "Provide a title and a valid evidence date range") from None
    filename = clean_filename(file.filename)
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            400, f"Unsupported evidence format. Use: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
    item_id = uuid.uuid4()
    path = evidence_root() / f"{item_id}{suffix}"
    try:
        size = await save_upload_file(
            file, str(path), settings.max_evidence_upload_mb * 1024 * 1024
        )
        if not size:
            raise HTTPException(400, "Evidence file is empty")
        item = PreparationEvidence(
            id=item_id,
            organization_id=user.organization_id,
            created_by=user.id,
            kind="file",
            filename=filename,
            file_path=str(path.relative_to(Path(settings.upload_dir).resolve())),
            size_bytes=size,
            sha256=await run_in_threadpool(file_digest, path),
            **metadata.model_dump(),
        )
        db.add(item)
        await db.flush()
        await initialize_access(db, "preparation_evidence", item.id, user, visibility=visibility)
        await log_action(
            db,
            user,
            "upload",
            "preparation_evidence",
            str(item_id),
            new_value={"title": item.title, "sha256": item.sha256, "size_bytes": size},
        )
        await db.commit()
    except BaseException:
        await db.rollback()
        path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    await db.refresh(item)
    return await evidence_response(db, item, user)


@router.patch("/{evidence_id}", response_model=EvidenceResponse)
async def archive_evidence(
    evidence_id: uuid.UUID,
    body: EvidenceArchive,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(editor),
):
    item = await require_access(db, PreparationEvidence, evidence_id, user, "edit")
    old = item.archived
    item.archived = body.archived
    await log_action(
        db,
        user,
        "update",
        "preparation_evidence",
        str(item.id),
        old_value={"archived": old},
        new_value={"archived": item.archived},
    )
    await db.commit()
    await db.refresh(item)
    return await evidence_response(db, item, user)


@router.get("/{evidence_id}", response_model=EvidenceResponse)
async def read_evidence(
    evidence_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = await get_org_owned_or_404(
        db, PreparationEvidence, evidence_id, user, detail="Evidence not found"
    )
    return await evidence_response(db, item, user)


@router.get("/{evidence_id}/download")
async def download_evidence(
    evidence_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = await require_access(db, PreparationEvidence, evidence_id, user, "export")
    path = await run_in_threadpool(verify_evidence_file, item)
    return FileResponse(
        path,
        filename=item.filename or "evidence",
        media_type="application/octet-stream",
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"},
    )
