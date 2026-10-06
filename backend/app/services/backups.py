from __future__ import annotations

import contextlib
import datetime as dt
import fcntl
import gzip
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
import uuid
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.engine import make_url

from app.config import settings

BACKUP_EXTENSION = ".capbak"
MANIFEST_FILENAME = "manifest.json"
DATABASE_DUMP_FILENAME = "database.sql"
UPLOADS_ARCHIVE_FILENAME = "uploads.tar.gz"
BACKUP_FORMAT_VERSION = 1
LOCK_FILENAME = ".backup.lock"
RESTORE_FLAG_FILENAME = ".restore_in_progress"
BACKUP_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
MAX_TAR_HEADER_READ = 1024 * 1024


class _BoundedTarReader:
    """Bound raw tar reads, including PAX headers omitted from member sizes."""

    def __init__(self, stream):
        self.stream = stream
        self.limit = (
            settings.backup_expanded_max_mb * 1024 * 1024
            + settings.backup_max_members * 1024
            + MAX_TAR_HEADER_READ
        )

    def read(self, size=-1):
        if size < 0 or size > MAX_TAR_HEADER_READ:
            raise BackupValidationError("Backup tar header exceeds the size limit")
        data = self.stream.read(size)
        if self.stream.tell() > self.limit:
            raise BackupValidationError("Expanded backup exceeds the configured size limit")
        return data

    def seek(self, offset, whence=0):
        if whence == 0:
            target = offset
        elif whence == 1:
            target = self.stream.tell() + offset
        else:
            raise BackupValidationError("Backup tar cannot seek relative to its end")
        if target > self.limit:
            raise BackupValidationError("Expanded backup exceeds the configured size limit")
        position = self.stream.seek(offset, whence)
        return position

    def tell(self):
        return self.stream.tell()


@contextlib.contextmanager
def _open_limited_tar(path: Path):
    with (
        gzip.open(path, "rb") as gzip_stream,
        tarfile.open(fileobj=_BoundedTarReader(gzip_stream), mode="r:") as tar,
    ):
        yield tar


class BackupError(Exception):
    pass


class BackupNotFoundError(BackupError):
    pass


class BackupValidationError(BackupError):
    pass


class BackupOperationError(BackupError):
    pass


class BackupDependencyError(BackupError):
    pass


class BackupConflictError(BackupError):
    pass


def list_backups() -> list[dict[str, Any]]:
    backup_dir = _ensure_backup_dir()
    with _operation_lock(backup_dir):
        return _load_backups_locked(backup_dir)


def get_backup(backup_id: str) -> dict[str, Any]:
    backup_dir = _ensure_backup_dir()
    with _operation_lock(backup_dir):
        return _load_backup_locked(backup_dir, backup_id)


def get_backup_archive_path(backup_id: str) -> Path:
    backup_dir = _ensure_backup_dir()
    with _operation_lock(backup_dir):
        metadata = _load_backup_locked(backup_dir, backup_id)
        archive_path = backup_dir / metadata["archive_filename"]
        if not archive_path.exists():
            raise BackupNotFoundError("Backup archive file is missing")
        return archive_path


def delete_backup(backup_id: str) -> None:
    backup_dir = _ensure_backup_dir()
    with _operation_lock(backup_dir):
        metadata = _load_backup_locked(backup_dir, backup_id)
        archive_path = backup_dir / metadata["archive_filename"]
        sidecar_path = _sidecar_path(backup_dir, backup_id)
        if archive_path.exists():
            archive_path.unlink()
        if sidecar_path.exists():
            sidecar_path.unlink()


def create_backup(
    *,
    reason: str,
    created_by_user_id: Optional[str],
    created_by_user_name: Optional[str],
    source_backup_id: Optional[str] = None,
    protected_ids: Optional[set[str]] = None,
) -> dict[str, Any]:
    backup_dir = _ensure_backup_dir()
    with _operation_lock(backup_dir):
        return _create_backup_locked(
            backup_dir=backup_dir,
            reason=reason,
            created_by_user_id=created_by_user_id,
            created_by_user_name=created_by_user_name,
            source_backup_id=source_backup_id,
            protected_ids=protected_ids,
        )


def import_backup_archive(source_path: Path) -> dict[str, Any]:
    backup_dir = _ensure_backup_dir()
    with _operation_lock(backup_dir):
        return _import_backup_archive_locked(backup_dir=backup_dir, source_path=source_path)


def restore_backup(
    backup_id: str,
    *,
    reason: Optional[str],
    requested_by_user_id: Optional[str],
    requested_by_user_name: Optional[str],
) -> dict[str, Any]:
    backup_dir = _ensure_backup_dir()
    upload_dir = _ensure_upload_dir()

    with _operation_lock(backup_dir):
        metadata = _load_backup_locked(backup_dir, backup_id)
        archive_path = backup_dir / metadata["archive_filename"]
        if not archive_path.exists():
            raise BackupNotFoundError("Backup archive file is missing")
        if _file_sha256(archive_path) != (metadata["sha256"], metadata["size_bytes"]):
            raise BackupValidationError("Backup archive does not match stored metadata")

        work_dir = Path(tempfile.mkdtemp(prefix=f"restore-{backup_id}-", dir=str(backup_dir)))
        try:
            manifest, db_dump_path, uploads_snapshot_path = _extract_and_validate_backup(
                archive_path,
                work_dir,
            )
            if manifest["database"]["engine"] != _database_engine():
                raise BackupValidationError(
                    "Backup database engine does not match this installation"
                )
            pre_restore_metadata = _create_backup_locked(
                backup_dir=backup_dir,
                reason="pre_restore",
                created_by_user_id=requested_by_user_id,
                created_by_user_name=requested_by_user_name,
                source_backup_id=backup_id,
                protected_ids={backup_id},
            )

            restore_started_at = _utcnow().isoformat()
            _set_restore_in_progress_locked(
                backup_dir,
                {
                    "backup_id": backup_id,
                    "started_at": restore_started_at,
                },
            )
            try:
                _precheck_no_active_extractions()

                rollback_uploads_snapshot = work_dir / "rollback-uploads.tar.gz"
                _archive_uploads(
                    output_path=rollback_uploads_snapshot,
                    upload_dir=upload_dir,
                    backup_dir=backup_dir,
                )

                try:
                    _restore_uploads_from_archive(
                        upload_snapshot_path=uploads_snapshot_path,
                        upload_dir=upload_dir,
                        backup_dir=backup_dir,
                    )
                    _restore_database_from_dump(db_dump_path)
                except Exception as restore_exc:
                    try:
                        _restore_uploads_from_archive(
                            upload_snapshot_path=rollback_uploads_snapshot,
                            upload_dir=upload_dir,
                            backup_dir=backup_dir,
                        )
                    except Exception as rollback_exc:
                        raise BackupOperationError(
                            f"Restore failed and upload rollback also failed: {rollback_exc}"
                        ) from restore_exc
                    raise
            finally:
                _set_restore_in_progress_locked(backup_dir, None)

            completed_at = _utcnow()
            return {
                "restored_backup_id": backup_id,
                "pre_restore_backup_id": pre_restore_metadata["id"],
                "completed_at": completed_at,
                "reason": reason,
                "manifest_format_version": manifest["format_version"],
            }
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)


def is_restore_in_progress() -> bool:
    backup_dir = Path(settings.backup_dir)
    return (backup_dir / RESTORE_FLAG_FILENAME).exists()


def _create_backup_locked(
    *,
    backup_dir: Path,
    reason: str,
    created_by_user_id: Optional[str],
    created_by_user_name: Optional[str],
    source_backup_id: Optional[str],
    protected_ids: Optional[set[str]],
) -> dict[str, Any]:
    backup_id = _generate_backup_id()
    upload_dir = _ensure_upload_dir()

    work_dir = Path(tempfile.mkdtemp(prefix=f"backup-{backup_id}-", dir=str(backup_dir)))
    try:
        db_dump_path = work_dir / DATABASE_DUMP_FILENAME
        uploads_snapshot_path = work_dir / UPLOADS_ARCHIVE_FILENAME
        manifest_path = work_dir / MANIFEST_FILENAME
        archive_tmp_path = work_dir / f"{backup_id}{BACKUP_EXTENSION}"

        db_engine = _database_engine()
        _dump_database_to_file(db_dump_path)
        _archive_uploads(
            output_path=uploads_snapshot_path,
            upload_dir=upload_dir,
            backup_dir=backup_dir,
        )

        db_sha256, db_size = _file_sha256(db_dump_path)
        uploads_sha256, uploads_size = _file_sha256(uploads_snapshot_path)
        created_at = _utcnow()

        manifest = {
            "format_version": BACKUP_FORMAT_VERSION,
            "backup_id": backup_id,
            "created_at": created_at.isoformat(),
            "reason": reason,
            "source_backup_id": source_backup_id,
            "created_by": {
                "user_id": created_by_user_id,
                "user_name": created_by_user_name,
            },
            "database": {
                "filename": DATABASE_DUMP_FILENAME,
                "engine": db_engine,
                "sha256": db_sha256,
                "size_bytes": db_size,
            },
            "uploads": {
                "filename": UPLOADS_ARCHIVE_FILENAME,
                "sha256": uploads_sha256,
                "size_bytes": uploads_size,
            },
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

        with tarfile.open(archive_tmp_path, "w:gz") as tar:
            tar.add(manifest_path, arcname=MANIFEST_FILENAME)
            tar.add(db_dump_path, arcname=DATABASE_DUMP_FILENAME)
            tar.add(uploads_snapshot_path, arcname=UPLOADS_ARCHIVE_FILENAME)

        archive_sha256, archive_size = _file_sha256(archive_tmp_path)
        archive_filename = f"{backup_id}{BACKUP_EXTENSION}"
        final_archive_path = backup_dir / archive_filename
        os.replace(archive_tmp_path, final_archive_path)

        metadata = {
            "id": backup_id,
            "archive_filename": archive_filename,
            "created_at": created_at.isoformat(),
            "reason": reason,
            "source_backup_id": source_backup_id,
            "created_by_user_id": created_by_user_id,
            "created_by_user_name": created_by_user_name,
            "size_bytes": archive_size,
            "sha256": archive_sha256,
            "format_version": BACKUP_FORMAT_VERSION,
        }
        sidecar_tmp_path = work_dir / f"{backup_id}.json"
        sidecar_tmp_path.write_text(
            json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8"
        )
        os.replace(sidecar_tmp_path, _sidecar_path(backup_dir, backup_id))

        protected = set(protected_ids or set())
        protected.add(backup_id)
        _enforce_retention_locked(backup_dir, protected_ids=protected)
        return metadata
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def restore_into_empty_installation(source_path: Path) -> dict[str, Any]:
    """Restore an archive before migrations or application workers start.

    This is deliberately limited to an empty PostgreSQL database and uploads
    volume. A failed attempt must be retried with fresh isolated storage.
    """
    if _database_engine() != "postgresql":
        raise BackupValidationError("Offline restore requires PostgreSQL")

    backup_dir = _ensure_backup_dir()
    upload_dir = _ensure_upload_dir()
    with _operation_lock(backup_dir):
        if any(child.resolve() != backup_dir.resolve() for child in upload_dir.iterdir()):
            raise BackupConflictError("Offline restore requires an empty uploads volume")

        url = make_url(settings.database_url)
        args, env = _postgres_connection_args(url)
        result = _run_command(
            ["psql", *args, "--tuples-only", "--no-align", "--command",
             "SELECT COUNT(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
             "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f');"],
            env=env,
            capture_output=True,
        )
        if int((result.stdout or "").strip()) != 0:
            raise BackupConflictError("Offline restore requires an empty database")

        work_dir = Path(tempfile.mkdtemp(prefix="offline-restore-", dir=str(backup_dir)))
        try:
            manifest, db_dump_path, uploads_snapshot_path = _extract_and_validate_backup(
                source_path, work_dir
            )
            if manifest["database"]["engine"] != "postgresql":
                raise BackupValidationError("Backup database engine must be PostgreSQL")
            _set_restore_in_progress_locked(
                backup_dir, {"backup_id": manifest["backup_id"], "started_at": _utcnow().isoformat()}
            )
            try:
                _restore_uploads_from_archive(
                    upload_snapshot_path=uploads_snapshot_path,
                    upload_dir=upload_dir,
                    backup_dir=backup_dir,
                )
                _restore_database_from_dump(db_dump_path)
            finally:
                _set_restore_in_progress_locked(backup_dir, None)
            return manifest
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)


def _import_backup_archive_locked(*, backup_dir: Path, source_path: Path) -> dict[str, Any]:
    source_path = Path(source_path)
    if not source_path.exists():
        raise BackupNotFoundError("Uploaded backup archive is missing")
    if source_path.stat().st_size > settings.backup_upload_max_mb * 1024 * 1024:
        raise BackupValidationError("Backup archive exceeds the configured upload limit")

    work_dir = Path(tempfile.mkdtemp(prefix="backup-import-", dir=str(backup_dir)))
    try:
        archive_tmp_path = work_dir / f"import{BACKUP_EXTENSION}"
        shutil.copy2(source_path, archive_tmp_path)

        manifest, _, _ = _extract_and_validate_backup(
            archive_tmp_path,
            work_dir / "validate",
            enforce_upload_limit=True,
        )
        metadata = _build_imported_backup_metadata(manifest=manifest, archive_path=archive_tmp_path)

        backup_id = metadata["id"]
        sidecar_path = _sidecar_path(backup_dir, backup_id)
        final_archive_path = backup_dir / metadata["archive_filename"]
        if sidecar_path.exists() or final_archive_path.exists():
            raise BackupConflictError(f"Backup '{backup_id}' already exists")

        os.replace(archive_tmp_path, final_archive_path)

        sidecar_tmp_path = work_dir / f"{backup_id}.json"
        sidecar_tmp_path.write_text(
            json.dumps(metadata, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(sidecar_tmp_path, sidecar_path)

        _enforce_retention_locked(backup_dir, protected_ids={backup_id})
        return metadata
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _extract_and_validate_backup(
    archive_path: Path,
    work_dir: Path,
    *,
    enforce_upload_limit: bool = False,
) -> tuple[dict[str, Any], Path, Path]:
    manifest_path = work_dir / MANIFEST_FILENAME
    db_dump_path = work_dir / DATABASE_DUMP_FILENAME
    uploads_snapshot_path = work_dir / UPLOADS_ARCHIVE_FILENAME

    if enforce_upload_limit and archive_path.stat().st_size > settings.backup_upload_max_mb * 1024 * 1024:
        raise BackupValidationError("Backup archive exceeds the configured upload limit")

    try:
        with _open_limited_tar(archive_path) as tar:
            members = _validated_tar_members(tar)
            remaining_budget = settings.backup_expanded_max_mb * 1024 * 1024 - sum(
                member.size for member in members
            )
            member_names = {member.name for member in members}
            required = {MANIFEST_FILENAME, DATABASE_DUMP_FILENAME, UPLOADS_ARCHIVE_FILENAME}
            if member_names != required or any(not member.isfile() for member in members):
                raise BackupValidationError("Backup archive must contain exactly the required files")
            if tar.getmember(MANIFEST_FILENAME).size > 1024 * 1024:
                raise BackupValidationError("Backup manifest exceeds the size limit")

            _extract_tar_member(tar, MANIFEST_FILENAME, manifest_path)
            _extract_tar_member(tar, DATABASE_DUMP_FILENAME, db_dump_path)
            _extract_tar_member(tar, UPLOADS_ARCHIVE_FILENAME, uploads_snapshot_path)
    except BackupValidationError:
        raise
    except (OSError, EOFError, tarfile.TarError) as exc:
        raise BackupValidationError("Backup archive is not a valid gzip tar archive") from exc

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        raise BackupValidationError("Backup manifest is invalid") from exc

    if not isinstance(manifest, dict):
        raise BackupValidationError("Backup manifest is invalid")

    if manifest.get("format_version") != BACKUP_FORMAT_VERSION:
        raise BackupValidationError(
            f"Unsupported backup format version: {manifest.get('format_version')}"
        )

    db_section = manifest.get("database") or {}
    uploads_section = manifest.get("uploads") or {}
    if not isinstance(db_section, dict) or not isinstance(uploads_section, dict):
        raise BackupValidationError("Backup manifest sections are invalid")
    if db_section.get("engine") not in {"postgresql", "sqlite"}:
        raise BackupValidationError("Backup database engine is missing or unsupported")
    expected_db_sha = db_section.get("sha256")
    expected_uploads_sha = uploads_section.get("sha256")
    if not expected_db_sha or not expected_uploads_sha:
        raise BackupValidationError("Manifest checksum information is incomplete")

    actual_db_sha, _ = _file_sha256(db_dump_path)
    actual_uploads_sha, _ = _file_sha256(uploads_snapshot_path)
    if expected_db_sha != actual_db_sha:
        raise BackupValidationError("Database checksum mismatch")
    if expected_uploads_sha != actual_uploads_sha:
        raise BackupValidationError("Uploads snapshot checksum mismatch")

    # Validate the nested archive before import persists it or restore takes a
    # pre-restore snapshot. A malicious uploads path must not reach backups.
    try:
        with _open_limited_tar(uploads_snapshot_path) as uploads_tar:
            _validated_upload_members(uploads_tar, remaining_budget=remaining_budget)
    except BackupValidationError:
        raise
    except (OSError, EOFError, tarfile.TarError) as exc:
        raise BackupValidationError("Uploads snapshot is not a valid gzip tar archive") from exc

    return manifest, db_dump_path, uploads_snapshot_path


def _build_imported_backup_metadata(
    *,
    manifest: dict[str, Any],
    archive_path: Path,
) -> dict[str, Any]:
    created_by = manifest.get("created_by") or {}
    created_at = str(manifest.get("created_at") or "").strip() or _utcnow().isoformat()
    archive_sha256, archive_size = _file_sha256(archive_path)

    return _normalize_backup_metadata(
        {
            "id": manifest.get("backup_id"),
            "archive_filename": f"{manifest.get('backup_id')}{BACKUP_EXTENSION}",
            "created_at": created_at,
            "reason": manifest.get("reason"),
            "source_backup_id": manifest.get("source_backup_id"),
            "created_by_user_id": created_by.get("user_id"),
            "created_by_user_name": created_by.get("user_name"),
            "size_bytes": archive_size,
            "sha256": archive_sha256,
            "format_version": manifest.get("format_version"),
        }
    )


def _extract_tar_member(tar: tarfile.TarFile, name: str, destination: Path) -> None:
    try:
        member = tar.getmember(name)
        file_obj = tar.extractfile(member)
        if file_obj is None:
            raise BackupValidationError(f"Could not extract '{name}' from archive")
        if not member.isfile() or member.size > settings.backup_expanded_max_mb * 1024 * 1024:
            raise BackupValidationError("Invalid or oversized backup member")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as handle:
            _copy_member_with_limit(file_obj, handle, member.size)
    except BackupValidationError:
        raise
    except (KeyError, OSError, tarfile.TarError) as exc:
        raise BackupValidationError(f"Could not extract '{name}' from archive") from exc


def _archive_uploads(*, output_path: Path, upload_dir: Path, backup_dir: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    upload_dir.mkdir(parents=True, exist_ok=True)
    backup_dir_resolved = backup_dir.resolve()

    with tarfile.open(output_path, "w:gz") as tar:
        for root, dirs, files in os.walk(upload_dir):
            root_path = Path(root)
            kept_dirs: list[str] = []
            for dir_name in dirs:
                directory = root_path / dir_name
                candidate = directory.resolve()
                if _is_within(candidate, backup_dir_resolved):
                    continue
                if directory.is_symlink():
                    raise BackupValidationError("Uploads contain a symbolic link")
                kept_dirs.append(dir_name)
            dirs[:] = kept_dirs

            for file_name in sorted(files):
                file_path = root_path / file_name
                if _is_within(file_path.resolve(), backup_dir_resolved):
                    continue
                if file_path.is_symlink():
                    raise BackupValidationError("Uploads contain a symbolic link")
                arcname = file_path.relative_to(upload_dir)
                tar.add(file_path, arcname=str(arcname), recursive=False)


def _restore_uploads_from_archive(
    *, upload_snapshot_path: Path, upload_dir: Path, backup_dir: Path
) -> None:
    extract_dir = Path(tempfile.mkdtemp(prefix="uploads-restore-"))
    try:
        with _open_limited_tar(upload_snapshot_path) as tar:
            _safe_extract_tar(tar, extract_dir)

        _clear_upload_dir(upload_dir, backup_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)

        for child in extract_dir.iterdir():
            destination = upload_dir / child.name
            if child.is_dir():
                shutil.copytree(child, destination, dirs_exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(child, destination)
    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)


def _validated_tar_members(tar, *, remaining_budget: Optional[int] = None):
    total = 0
    members = []
    seen = set()
    size_limit = (
        settings.backup_expanded_max_mb * 1024 * 1024
        if remaining_budget is None
        else remaining_budget
    )
    for member in tar:
        total += member.size
        if (
            total > size_limit
            or len(members) >= settings.backup_max_members
        ):
            raise BackupValidationError(
                "Expanded backup exceeds the configured size or file-count limit"
            )
        if (
            member.size < 0
            or member.size > settings.backup_expanded_max_mb * 1024 * 1024
            or not (member.isfile() or member.isdir())
            or member.name in seen
        ):
            raise BackupValidationError(
                "Backup contains duplicate paths, links or unsupported entries"
            )
        seen.add(member.name)
        members.append(member)
    return members


def _safe_extract_tar(tar: tarfile.TarFile, target_dir: Path) -> None:
    target_dir_resolved = target_dir.resolve()
    for member in _validated_upload_members(tar):
        member_target = (target_dir / member.name).resolve()
        if not _is_within(member_target, target_dir_resolved):
            raise BackupValidationError(f"Invalid archive path: {member.name}")
        if member.isdir():
            member_target.mkdir(parents=True, exist_ok=True)
        else:
            member_target.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            if source is None:
                raise BackupValidationError("Could not extract uploads member")
            with member_target.open("wb") as destination:
                _copy_member_with_limit(source, destination, member.size)


def _validated_upload_members(
    tar: tarfile.TarFile, *, remaining_budget: Optional[int] = None
) -> list[tarfile.TarInfo]:
    members = _validated_tar_members(tar, remaining_budget=remaining_budget)
    upload_dir = Path(settings.upload_dir).resolve()
    backup_dir = Path(settings.backup_dir or upload_dir / ".system_backups").resolve()
    reserved = backup_dir.relative_to(upload_dir).parts if _is_within(backup_dir, upload_dir) else ()
    canonical: dict[tuple[str, ...], tarfile.TarInfo] = {}
    for member in members:
        path = Path(member.name)
        if (
            path.is_absolute()
            or not path.parts
            or any(part in {"", ".", ".."} for part in path.parts)
            or (reserved and path.parts[:len(reserved)] == reserved)
        ):
            raise BackupValidationError(f"Invalid uploads archive path: {member.name}")
        if path.parts in canonical:
            raise BackupValidationError("Uploads archive contains duplicate paths")
        canonical[path.parts] = member
    for parts in canonical:
        if any(not canonical[parts[:index]].isdir() for index in range(1, len(parts)) if parts[:index] in canonical):
            raise BackupValidationError("Uploads archive contains a file used as a directory")
    return members


def _copy_member_with_limit(source, destination, declared_size: int) -> None:
    remaining = declared_size
    while remaining:
        chunk = source.read(min(1024 * 1024, remaining))
        if not chunk:
            raise BackupValidationError("Backup member is truncated")
        destination.write(chunk)
        remaining -= len(chunk)


def _clear_upload_dir(upload_dir: Path, backup_dir: Path) -> None:
    upload_dir.mkdir(parents=True, exist_ok=True)
    backup_dir_resolved = backup_dir.resolve()
    for child in upload_dir.iterdir():
        child_resolved = child.resolve()
        if child_resolved == backup_dir_resolved:
            continue
        if _is_within(child_resolved, backup_dir_resolved):
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink(missing_ok=True)


def _dump_database_to_file(output_path: Path) -> None:
    engine = _database_engine()
    if engine == "postgresql":
        url = make_url(settings.database_url)
        _dump_postgres_database_to_file(url, output_path)
        return

    if engine == "sqlite":
        db_path = _sqlite_database_path()
        with (
            sqlite3.connect(db_path) as connection,
            output_path.open("w", encoding="utf-8") as handle,
        ):
            for line in connection.iterdump():
                handle.write(f"{line}\n")
        return

    raise BackupValidationError("Unsupported database engine")


def _restore_database_from_dump(dump_path: Path) -> None:
    engine = _database_engine()
    if engine == "postgresql":
        url = make_url(settings.database_url)
        _restore_postgres_database_from_dump(url, dump_path)
        return

    if engine == "sqlite":
        db_path = _sqlite_database_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_path.unlink(missing_ok=True)
        script = dump_path.read_text(encoding="utf-8")
        with sqlite3.connect(db_path) as connection:
            connection.executescript(script)
            connection.commit()
        return

    raise BackupValidationError("Unsupported database engine")


def _precheck_no_active_extractions() -> None:
    engine = _database_engine()
    if engine == "postgresql":
        query = "SELECT COUNT(*) FROM extraction_runs WHERE status IN ('pending', 'running');"
        url = make_url(settings.database_url)
        active_count = _query_active_postgres_extractions(url, query)
    elif engine == "sqlite":
        db_path = _sqlite_database_path()
        with sqlite3.connect(db_path) as connection:
            try:
                cursor = connection.execute(
                    "SELECT COUNT(*) FROM extraction_runs WHERE status IN ('pending', 'running');"
                )
                active_count = int(cursor.fetchone()[0])
            except sqlite3.OperationalError:
                active_count = 0
    else:
        raise BackupValidationError("Unsupported database engine")

    if active_count > 0:
        raise BackupConflictError("Cannot restore while extraction runs are active")


def _run_command(
    command: list[str],
    *,
    env: Optional[dict[str, str]] = None,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    try:
        resolved_command = _resolve_command(command[0])
        resolved_args = [resolved_command, *command[1:]]
        return subprocess.run(
            resolved_args,
            check=True,
            text=True,
            env=env,
            capture_output=capture_output,
        )
    except FileNotFoundError as exc:
        raise BackupDependencyError(f"Required command '{command[0]}' is not installed") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        detail = stderr or stdout or "unknown command error"
        raise BackupOperationError(f"Command failed ({command[0]}): {detail}") from exc


def _dump_postgres_database_to_file(url, output_path: Path) -> None:
    args, env = _postgres_connection_args(url)
    command = [
        "pg_dump",
        *args,
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-privileges",
        "--format=plain",
        "--encoding=UTF8",
        "--file",
        str(output_path),
    ]
    _run_command(command, env=env)


def _restore_postgres_database_from_dump(url, dump_path: Path) -> None:
    args, env = _postgres_connection_args(url)
    version_result = _run_command(
        ["psql", *args, "--tuples-only", "--no-align", "--command", "SHOW server_version_num;"],
        env=env,
        capture_output=True,
    )
    server_version = int((version_result.stdout or "").strip())
    compatible_path = dump_path
    if server_version < 170000:
        # pg_dump 17 writes this session setting even for PostgreSQL 16. It is
        # unsupported there, but removing the exact header line changes no data.
        compatible_path = dump_path.with_name("database-compatible.sql")
        with dump_path.open("r", encoding="utf-8") as source, compatible_path.open(
            "w", encoding="utf-8"
        ) as target:
            for line_number, line in enumerate(source):
                if line_number < 32 and line == "SET transaction_timeout = 0;\n":
                    continue
                target.write(line)
    command = [
        "psql",
        *args,
        "--set",
        "ON_ERROR_STOP=1",
        "--single-transaction",
        "--file",
        str(compatible_path),
    ]
    try:
        _run_command(command, env=env)
    finally:
        if compatible_path != dump_path:
            compatible_path.unlink(missing_ok=True)


def _query_active_postgres_extractions(url, query: str) -> int:
    args, env = _postgres_connection_args(url)
    command = [
        "psql",
        *args,
        "--tuples-only",
        "--no-align",
        "--command",
        query,
    ]
    result = _run_command(command, env=env, capture_output=True)
    value = (result.stdout or "").strip() or "0"
    return int(value)


def _resolve_command(command_name: str) -> str:
    """Use the configured client directory or PATH; never discover host containers."""
    if settings.postgres_bin_dir:
        candidate = Path(settings.postgres_bin_dir) / command_name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
        raise FileNotFoundError(command_name)
    resolved = shutil.which(command_name)
    if not resolved:
        raise FileNotFoundError(command_name)
    return resolved


def _sqlite_database_path() -> Path:
    url = make_url(settings.database_url)
    database = url.database
    if not database or database == ":memory:":
        raise BackupValidationError(
            "SQLite in-memory databases are not supported for backup restore"
        )
    if database.startswith("file:"):
        raise BackupValidationError("SQLite URI database URLs are not supported for backup restore")
    db_path = Path(database)
    if not db_path.is_absolute():
        db_path = (Path.cwd() / db_path).resolve()
    return db_path


def _postgres_connection_args(url) -> tuple[list[str], dict[str, str]]:
    args: list[str] = []
    if url.host:
        args.extend(["--host", str(url.host)])
    if url.port:
        args.extend(["--port", str(url.port)])
    if url.username:
        args.extend(["--username", str(url.username)])
    args.extend(["--dbname", str(url.database or "postgres")])

    env = os.environ.copy()
    if url.password:
        env["PGPASSWORD"] = str(url.password)
    return args, env


def _database_engine() -> str:
    drivername = make_url(settings.database_url).drivername
    if drivername.startswith("postgresql"):
        return "postgresql"
    if drivername.startswith("sqlite"):
        return "sqlite"
    return drivername


def _load_backups_locked(backup_dir: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for sidecar in backup_dir.glob("*.json"):
        if sidecar.name == RESTORE_FLAG_FILENAME:
            continue
        with contextlib.suppress(json.JSONDecodeError, OSError, BackupValidationError):
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
            normalized = _normalize_backup_metadata(payload)
            archive_path = backup_dir / normalized["archive_filename"]
            if not archive_path.exists():
                continue
            items.append(normalized)

    items.sort(key=_sort_key, reverse=True)
    return items


def _load_backup_locked(backup_dir: Path, backup_id: str) -> dict[str, Any]:
    path = _sidecar_path(backup_dir, backup_id)
    if not path.exists():
        raise BackupNotFoundError("Backup not found")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BackupValidationError("Backup metadata is corrupted") from exc
    return _normalize_backup_metadata(payload)


def _normalize_backup_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    backup_id = _validate_backup_id(payload.get("id"))
    archive_filename = str(payload.get("archive_filename") or "").strip()
    if not archive_filename:
        archive_filename = f"{backup_id}{BACKUP_EXTENSION}"
    if archive_filename != f"{backup_id}{BACKUP_EXTENSION}":
        raise BackupValidationError("Backup archive filename is invalid")
    created_at = str(payload.get("created_at") or "").strip()
    if not created_at:
        created_at = _utcnow().isoformat()
    _validate_created_at(created_at)
    return {
        "id": backup_id,
        "archive_filename": archive_filename,
        "created_at": created_at,
        "reason": str(payload.get("reason") or "manual"),
        "source_backup_id": payload.get("source_backup_id"),
        "created_by_user_id": payload.get("created_by_user_id"),
        "created_by_user_name": payload.get("created_by_user_name"),
        "size_bytes": int(payload.get("size_bytes") or 0),
        "sha256": str(payload.get("sha256") or ""),
        "format_version": int(payload.get("format_version") or BACKUP_FORMAT_VERSION),
    }


def _enforce_retention_locked(backup_dir: Path, *, protected_ids: set[str]) -> None:
    retention_count = max(1, int(settings.backup_retention_count))
    backups = _load_backups_locked(backup_dir)
    if len(backups) <= retention_count:
        return

    deleted = 0
    for metadata in backups[retention_count:]:
        backup_id = metadata["id"]
        if backup_id in protected_ids:
            continue
        archive_path = backup_dir / metadata["archive_filename"]
        sidecar_path = _sidecar_path(backup_dir, backup_id)
        if archive_path.exists():
            archive_path.unlink()
        if sidecar_path.exists():
            sidecar_path.unlink()
        deleted += 1
        if len(backups) - deleted <= retention_count:
            break


def _file_sha256(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            total += len(chunk)
    return digest.hexdigest(), total


def _sort_key(item: dict[str, Any]) -> dt.datetime:
    created_at = str(item.get("created_at") or "")
    if created_at.endswith("Z"):
        created_at = created_at.replace("Z", "+00:00")
    with contextlib.suppress(ValueError):
        return dt.datetime.fromisoformat(created_at)
    return dt.datetime.min.replace(tzinfo=dt.timezone.utc)


def _set_restore_in_progress_locked(backup_dir: Path, payload: Optional[dict[str, Any]]) -> None:
    flag_path = backup_dir / RESTORE_FLAG_FILENAME
    if payload is None:
        flag_path.unlink(missing_ok=True)
        return
    tmp_path = backup_dir / f"{RESTORE_FLAG_FILENAME}.tmp"
    tmp_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    os.replace(tmp_path, flag_path)


@contextlib.contextmanager
def _operation_lock(backup_dir: Path):
    lock_path = backup_dir / LOCK_FILENAME
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _generate_backup_id() -> str:
    timestamp = _utcnow().strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid.uuid4().hex[:8]
    return f"{timestamp}-{suffix}"


def _ensure_backup_dir() -> Path:
    backup_dir = Path(settings.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir.resolve()


def _ensure_upload_dir() -> Path:
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir.resolve()


def _sidecar_path(backup_dir: Path, backup_id: str) -> Path:
    return backup_dir / f"{backup_id}.json"


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _validate_backup_id(value: Any) -> str:
    backup_id = str(value or "").strip()
    if not backup_id:
        raise BackupValidationError("Backup metadata missing id")
    if not BACKUP_ID_PATTERN.fullmatch(backup_id):
        raise BackupValidationError("Backup id is invalid")
    return backup_id


def _validate_created_at(value: str) -> None:
    normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
    try:
        dt.datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise BackupValidationError("Backup created_at is invalid") from exc
