import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.tenant import get_org_owned_or_404
from app.config import settings
from app.database import get_db
from app.models.evidence import EvidenceFile, EvidenceLink, EvidenceNote
from app.models.requirement import Requirement
from app.models.user import User
from app.schemas.evidence import (
    EvidenceResponse,
    FileResponse,
    LinkCreate,
    LinkResponse,
    NoteCreate,
    NoteResponse,
)
from app.services.audit import log_action
from app.services.file_utils import save_upload_file

router = APIRouter(prefix="/api/v1/requirements", tags=["evidence"])


async def _get_requirement(
    requirement_id: uuid.UUID,
    db: AsyncSession,
    current_user: User,
) -> Requirement:
    return await get_org_owned_or_404(
        db,
        Requirement,
        requirement_id,
        current_user,
        detail="Requirement not found",
    )


@router.get("/{requirement_id}/evidence", response_model=EvidenceResponse)
async def get_evidence(
    requirement_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_requirement(requirement_id, db, current_user)

    notes_result = await db.execute(
        select(EvidenceNote)
        .where(EvidenceNote.requirement_id == requirement_id)
        .order_by(EvidenceNote.created_at.desc())
    )
    notes = notes_result.scalars().all()

    files_result = await db.execute(
        select(EvidenceFile)
        .where(EvidenceFile.requirement_id == requirement_id)
        .order_by(EvidenceFile.uploaded_at.desc())
    )
    files = files_result.scalars().all()

    links_result = await db.execute(
        select(EvidenceLink)
        .where(EvidenceLink.requirement_id == requirement_id)
        .order_by(EvidenceLink.added_at.desc())
    )
    links = links_result.scalars().all()

    return EvidenceResponse(
        notes=[NoteResponse.model_validate(n) for n in notes],
        files=[FileResponse.model_validate(f) for f in files],
        links=[LinkResponse.model_validate(link) for link in links],
    )


@router.post("/{requirement_id}/notes", response_model=NoteResponse, status_code=201)
async def add_note(
    requirement_id: uuid.UUID,
    body: NoteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_requirement(requirement_id, db, current_user)

    note = EvidenceNote(
        requirement_id=requirement_id,
        note_text=body.note_text,
        created_by=current_user.id,
    )
    db.add(note)

    await log_action(
        db,
        current_user,
        "create",
        "evidence_note",
        str(note.id),
        new_value={"requirement_id": str(requirement_id), "note_text": body.note_text[:100]},
    )
    await db.commit()
    await db.refresh(note)
    return note


@router.delete("/{requirement_id}/notes/{note_id}", status_code=204)
async def delete_note(
    requirement_id: uuid.UUID,
    note_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_requirement(requirement_id, db, current_user)
    result = await db.execute(
        select(EvidenceNote).where(
            EvidenceNote.id == note_id,
            EvidenceNote.requirement_id == requirement_id,
        )
    )
    note = result.scalar_one_or_none()
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")

    await log_action(
        db,
        current_user,
        "delete",
        "evidence_note",
        str(note.id),
        old_value={"requirement_id": str(requirement_id), "note_text": note.note_text[:100]},
    )
    await db.delete(note)
    await db.commit()


@router.post("/{requirement_id}/files", response_model=FileResponse, status_code=201)
async def upload_file(
    requirement_id: uuid.UUID,
    file: UploadFile = File(...),
    description: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_requirement(requirement_id, db, current_user)
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    # Sanitize filename
    safe_filename = "".join(c for c in file.filename if c.isalnum() or c in "._- ")
    unique_filename = f"{uuid.uuid4()}_{safe_filename}"

    evidence_dir = os.path.join(settings.upload_dir, "evidence")
    os.makedirs(evidence_dir, exist_ok=True)
    file_path = os.path.join(evidence_dir, unique_filename)
    max_bytes = settings.max_evidence_upload_mb * 1024 * 1024
    await save_upload_file(file, file_path, max_bytes)

    evidence_file = EvidenceFile(
        requirement_id=requirement_id,
        filename=file.filename,
        file_path=file_path,
        description=description,
        uploaded_by=current_user.id,
    )
    db.add(evidence_file)

    await log_action(
        db,
        current_user,
        "create",
        "evidence_file",
        str(evidence_file.id),
        new_value={"requirement_id": str(requirement_id), "filename": file.filename},
    )
    await db.commit()
    await db.refresh(evidence_file)
    return evidence_file


@router.delete("/{requirement_id}/files/{file_id}", status_code=204)
async def delete_file(
    requirement_id: uuid.UUID,
    file_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_requirement(requirement_id, db, current_user)
    result = await db.execute(
        select(EvidenceFile).where(
            EvidenceFile.id == file_id,
            EvidenceFile.requirement_id == requirement_id,
        )
    )
    evidence_file = result.scalar_one_or_none()
    if evidence_file is None:
        raise HTTPException(status_code=404, detail="File not found")

    # Remove physical file
    if os.path.exists(evidence_file.file_path):
        os.remove(evidence_file.file_path)

    await log_action(
        db,
        current_user,
        "delete",
        "evidence_file",
        str(evidence_file.id),
        old_value={"requirement_id": str(requirement_id), "filename": evidence_file.filename},
    )
    await db.delete(evidence_file)
    await db.commit()


@router.post("/{requirement_id}/links", response_model=LinkResponse, status_code=201)
async def add_link(
    requirement_id: uuid.UUID,
    body: LinkCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_requirement(requirement_id, db, current_user)

    link = EvidenceLink(
        requirement_id=requirement_id,
        url=body.url,
        label=body.label,
        added_by=current_user.id,
    )
    db.add(link)

    await log_action(
        db,
        current_user,
        "create",
        "evidence_link",
        str(link.id),
        new_value={"requirement_id": str(requirement_id), "url": body.url, "label": body.label},
    )
    await db.commit()
    await db.refresh(link)
    return link


@router.delete("/{requirement_id}/links/{link_id}", status_code=204)
async def delete_link(
    requirement_id: uuid.UUID,
    link_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_requirement(requirement_id, db, current_user)
    result = await db.execute(
        select(EvidenceLink).where(
            EvidenceLink.id == link_id,
            EvidenceLink.requirement_id == requirement_id,
        )
    )
    link = result.scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=404, detail="Link not found")

    await log_action(
        db,
        current_user,
        "delete",
        "evidence_link",
        str(link.id),
        old_value={"requirement_id": str(requirement_id), "url": link.url, "label": link.label},
    )
    await db.delete(link)
    await db.commit()
