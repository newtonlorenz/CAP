import asyncio
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse

from app.api.deps import require_installation_operator
from app.config import settings
from app.database import async_session, engine
from app.models.user import User
from app.schemas.backups import (
    BackupListResponse,
    BackupMetadataResponse,
    BackupRestoreRequest,
    BackupRestoreResponse,
)
from app.services.audit import log_action
from app.services.file_utils import save_upload_file
from app.services.backups import (
    BackupConflictError,
    BackupDependencyError,
    BackupError,
    BackupNotFoundError,
    BackupOperationError,
    BackupValidationError,
    create_backup,
    delete_backup,
    get_backup,
    get_backup_archive_path,
    import_backup_archive,
    list_backups,
    restore_backup,
)

router = APIRouter(prefix="/api/v1/admin/backups", tags=["backups"])


def _to_response(metadata: dict) -> BackupMetadataResponse:
    return BackupMetadataResponse(
        id=metadata["id"],
        archive_filename=metadata["archive_filename"],
        created_at=metadata["created_at"],
        reason=metadata["reason"],
        source_backup_id=metadata.get("source_backup_id"),
        created_by_user_id=metadata.get("created_by_user_id"),
        created_by_user_name=metadata.get("created_by_user_name"),
        size_bytes=metadata["size_bytes"],
        sha256=metadata["sha256"],
        format_version=metadata["format_version"],
    )


def _to_http_error(exc: BackupError) -> HTTPException:
    if isinstance(exc, BackupNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, BackupConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, BackupValidationError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, (BackupOperationError, BackupDependencyError)):
        return HTTPException(status_code=500, detail=str(exc))
    return HTTPException(status_code=500, detail="Backup operation failed")


async def _audit_best_effort(
    *,
    current_user: User,
    action: str,
    entity_type: str,
    entity_id: str,
    old_value: Optional[dict] = None,
    new_value: Optional[dict] = None,
) -> None:
    try:
        async with async_session() as db:
            await log_action(
                db,
                current_user,
                action,
                entity_type,
                entity_id,
                old_value=old_value,
                new_value=new_value,
            )
            await db.commit()
    except Exception:
        return


@router.get("", response_model=BackupListResponse)
async def list_admin_backups(
    current_user: User = Depends(require_installation_operator),
):
    try:
        backups = await asyncio.to_thread(list_backups)
    except BackupError as exc:
        raise _to_http_error(exc) from exc
    items = [_to_response(item) for item in backups]
    return BackupListResponse(items=items, total=len(items))


@router.post("", response_model=BackupMetadataResponse, status_code=201)
async def create_admin_backup(
    current_user: User = Depends(require_installation_operator),
):
    try:
        metadata = await asyncio.to_thread(
            create_backup,
            reason="manual",
            created_by_user_id=str(current_user.id),
            created_by_user_name=current_user.full_name,
        )
    except BackupError as exc:
        raise _to_http_error(exc) from exc

    await _audit_best_effort(
        current_user=current_user,
        action="create",
        entity_type="system_backup",
        entity_id=metadata["id"],
        new_value={
            "reason": metadata["reason"],
            "size_bytes": metadata["size_bytes"],
            "sha256": metadata["sha256"],
            "archive_filename": metadata["archive_filename"],
        },
    )
    return _to_response(metadata)


@router.post("/import", response_model=BackupMetadataResponse, status_code=201)
async def import_admin_backup(
    file: UploadFile = File(...),
    current_user: User = Depends(require_installation_operator),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    with tempfile.TemporaryDirectory(prefix="backup-import-upload-") as temp_dir:
        upload_path = Path(temp_dir) / "upload.capbak"
        try:
            await save_upload_file(
                file,
                str(upload_path),
                settings.backup_upload_max_mb * 1024 * 1024,
            )
            metadata = await asyncio.to_thread(import_backup_archive, upload_path)
        except BackupError as exc:
            raise _to_http_error(exc) from exc
        finally:
            await file.close()

    await _audit_best_effort(
        current_user=current_user,
        action="import",
        entity_type="system_backup",
        entity_id=metadata["id"],
        new_value={
            "reason": metadata["reason"],
            "size_bytes": metadata["size_bytes"],
            "sha256": metadata["sha256"],
            "archive_filename": metadata["archive_filename"],
        },
    )
    return _to_response(metadata)


@router.get("/{backup_id}/download")
async def download_admin_backup(
    backup_id: str,
    current_user: User = Depends(require_installation_operator),
):
    try:
        metadata = await asyncio.to_thread(get_backup, backup_id)
        archive_path = await asyncio.to_thread(get_backup_archive_path, backup_id)
    except BackupError as exc:
        raise _to_http_error(exc) from exc
    return FileResponse(
        str(archive_path),
        filename=metadata["archive_filename"],
        media_type="application/octet-stream",
    )


@router.delete("/{backup_id}", status_code=204)
async def delete_admin_backup(
    backup_id: str,
    current_user: User = Depends(require_installation_operator),
):
    try:
        metadata = await asyncio.to_thread(get_backup, backup_id)
        await asyncio.to_thread(delete_backup, backup_id)
    except BackupError as exc:
        raise _to_http_error(exc) from exc

    await _audit_best_effort(
        current_user=current_user,
        action="delete",
        entity_type="system_backup",
        entity_id=backup_id,
        old_value={
            "reason": metadata["reason"],
            "size_bytes": metadata["size_bytes"],
            "sha256": metadata["sha256"],
            "archive_filename": metadata["archive_filename"],
        },
    )
    return Response(status_code=204)


@router.post("/{backup_id}/restore", response_model=BackupRestoreResponse)
async def restore_admin_backup(
    backup_id: str,
    body: BackupRestoreRequest,
    current_user: User = Depends(require_installation_operator),
):
    await _audit_best_effort(
        current_user=current_user,
        action="restore_start",
        entity_type="system_backup",
        entity_id=backup_id,
        new_value={"reason": body.reason},
    )

    try:
        restore_result = await asyncio.to_thread(
            restore_backup,
            backup_id,
            reason=body.reason,
            requested_by_user_id=str(current_user.id),
            requested_by_user_name=current_user.full_name,
        )
    except BackupError as exc:
        await _audit_best_effort(
            current_user=current_user,
            action="restore_failed",
            entity_type="system_backup",
            entity_id=backup_id,
            new_value={"reason": body.reason, "error": str(exc)},
        )
        raise _to_http_error(exc) from exc
    finally:
        await engine.dispose()

    await _audit_best_effort(
        current_user=current_user,
        action="restore_complete",
        entity_type="system_backup",
        entity_id=backup_id,
        new_value={
            "reason": body.reason,
            "pre_restore_backup_id": restore_result["pre_restore_backup_id"],
            "completed_at": restore_result["completed_at"].isoformat(),
        },
    )

    return BackupRestoreResponse(
        restored_backup_id=restore_result["restored_backup_id"],
        pre_restore_backup_id=restore_result["pre_restore_backup_id"],
        completed_at=restore_result["completed_at"],
        reason=restore_result.get("reason"),
    )
