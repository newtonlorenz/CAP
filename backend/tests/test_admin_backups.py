import hashlib
import io
import json
import os
import sqlite3
import tarfile

import pytest
from sqlalchemy import text

from app.config import settings
from app.models.document import Document
from app.models.extraction import ExtractionRun
from app.models.user import User
from app.services import backups as backup_service
from app.services.auth import create_access_token, hash_password


def _sha256_bytes(data: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(data)
    return digest.hexdigest()


async def _sqlite_db_path(db_session) -> str:
    result = await db_session.execute(text("PRAGMA database_list"))
    for row in result.all():
        if row[1] == "main":
            return str(row[2])
    raise RuntimeError("Could not resolve sqlite database path")


@pytest.fixture
async def admin_user(db_session, monkeypatch):
    user = User(
        email="backup-admin@example.com",
        password_hash=hash_password("adminpass123"),
        full_name="Backup Admin",
        role="admin",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    from app.config import settings
    monkeypatch.setattr(settings, "installation_operator_ids", [str(user.id)])
    return user


@pytest.fixture
async def contributor_user(db_session):
    user = User(
        email="backup-contributor@example.com",
        password_hash=hash_password("contribpass123"),
        full_name="Backup Contributor",
        role="contributor",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def admin_headers(admin_user):
    token = create_access_token({"sub": str(admin_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def contributor_headers(contributor_user):
    token = create_access_token({"sub": str(contributor_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def backup_env(monkeypatch, db_session, tmp_path):
    upload_dir = tmp_path / "uploads"
    backup_dir = upload_dir / ".system_backups"
    upload_dir.mkdir(parents=True, exist_ok=True)
    backup_dir.mkdir(parents=True, exist_ok=True)
    db_path = await _sqlite_db_path(db_session)

    monkeypatch.setattr(settings, "upload_dir", str(upload_dir))
    monkeypatch.setattr(settings, "backup_dir", str(backup_dir))
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setattr(settings, "backup_retention_count", 20)
    monkeypatch.setattr(settings, "backup_upload_max_mb", 2048)
    return {"upload_dir": upload_dir, "backup_dir": backup_dir, "db_path": db_path}


async def _create_backup(client, headers) -> dict:
    response = await client.post("/api/v1/admin/backups", headers=headers)
    assert response.status_code == 201
    return response.json()


async def _create_backup_bytes(client, headers, backup_env) -> tuple[dict, bytes]:
    created = await _create_backup(client, headers)
    archive_path = backup_env["backup_dir"] / created["archive_filename"]
    return created, archive_path.read_bytes()


async def _import_backup(
    client, headers, archive_bytes: bytes, filename: str = "import.capbak"
) -> dict:
    response = await client.post(
        "/api/v1/admin/backups/import",
        headers=headers,
        files={"file": (filename, archive_bytes, "application/octet-stream")},
    )
    assert response.status_code == 201
    return response.json()


async def test_backup_endpoints_require_admin(client, contributor_headers, backup_env):
    list_response = await client.get("/api/v1/admin/backups", headers=contributor_headers)
    assert list_response.status_code == 403

    create_response = await client.post("/api/v1/admin/backups", headers=contributor_headers)
    assert create_response.status_code == 403

    import_response = await client.post(
        "/api/v1/admin/backups/import",
        headers=contributor_headers,
        files={"file": ("backup.capbak", b"fake-backup", "application/octet-stream")},
    )
    assert import_response.status_code == 403

    download_response = await client.get(
        "/api/v1/admin/backups/nonexistent/download",
        headers=contributor_headers,
    )
    assert download_response.status_code == 403

    delete_response = await client.delete(
        "/api/v1/admin/backups/nonexistent",
        headers=contributor_headers,
    )
    assert delete_response.status_code == 403

    restore_response = await client.post(
        "/api/v1/admin/backups/nonexistent/restore",
        headers=contributor_headers,
        json={"confirmation": "RESTORE"},
    )
    assert restore_response.status_code == 403


async def test_tenant_admin_without_operator_grant_cannot_use_any_backup_endpoint(
    client, db_session, admin_headers, backup_env
):
    tenant_admin = User(
        email="tenant-backup-admin@example.com",
        password_hash=hash_password("password123"),
        full_name="Tenant Admin",
        role="admin",
    )
    db_session.add(tenant_admin)
    await db_session.commit()
    await db_session.refresh(tenant_admin)
    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(tenant_admin.id)})}"}
    for method, path, kwargs in [
        ("get", "/api/v1/admin/backups", {}),
        ("post", "/api/v1/admin/backups", {}),
        ("post", "/api/v1/admin/backups/import", {"files": {"file": ("x", b"x")}}),
        ("get", "/api/v1/admin/backups/missing/download", {}),
        ("delete", "/api/v1/admin/backups/missing", {}),
        ("post", "/api/v1/admin/backups/missing/restore", {"json": {"confirmation": "RESTORE"}}),
    ]:
        response = await getattr(client, method)(path, headers=headers, **kwargs)
        assert response.status_code == 403, (method, path, response.text)


def _replace_archive_member(archive: bytes, name: str, replacement: bytes) -> bytes:
    output = io.BytesIO()
    with (
        tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as original,
        tarfile.open(fileobj=output, mode="w:gz") as rebuilt,
    ):
        for member in original:
            content = replacement if member.name == name else original.extractfile(member).read()
            info = tarfile.TarInfo(member.name)
            info.size = len(content)
            rebuilt.addfile(info, io.BytesIO(content))
    return output.getvalue()


def _nested_archive(*entries: tuple[str, bytes]) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as tar:
        for name, content in entries:
            info = tarfile.TarInfo(name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return output.getvalue()


def _archive_with_uploads(archive: bytes, uploads: bytes) -> bytes:
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        manifest = json.loads(tar.extractfile("manifest.json").read())
    manifest["uploads"]["sha256"] = _sha256_bytes(uploads)
    manifest["uploads"]["size_bytes"] = len(uploads)
    updated = _replace_archive_member(
        archive, "manifest.json", json.dumps(manifest).encode("utf-8")
    )
    return _replace_archive_member(updated, "uploads.tar.gz", uploads)


@pytest.mark.parametrize("name", [".system_backups/overwrite.capbak", "../outside.txt", "/tmp/outside.txt"])
async def test_import_rejects_nested_upload_paths_before_persisting(
    client, admin_headers, backup_env, name
):
    created, archive = await _create_backup_bytes(client, admin_headers, backup_env)
    await client.delete(f"/api/v1/admin/backups/{created['id']}", headers=admin_headers)
    malicious = _archive_with_uploads(archive, _nested_archive((name, b"intrusion")))
    response = await client.post(
        "/api/v1/admin/backups/import",
        headers=admin_headers,
        files={"file": ("bad.capbak", malicious, "application/octet-stream")},
    )
    assert response.status_code == 400
    assert list(backup_env["backup_dir"].glob("*.capbak")) == []


async def test_import_rejects_nested_expansion_limit_before_persisting(
    client, admin_headers, backup_env, monkeypatch
):
    created, archive = await _create_backup_bytes(client, admin_headers, backup_env)
    await client.delete(f"/api/v1/admin/backups/{created['id']}", headers=admin_headers)
    malicious = _archive_with_uploads(archive, _nested_archive(("large.bin", b"0" * (1024 * 1024 + 1))))
    monkeypatch.setattr(settings, "backup_expanded_max_mb", 1)
    response = await client.post(
        "/api/v1/admin/backups/import",
        headers=admin_headers,
        files={"file": ("bad.capbak", malicious, "application/octet-stream")},
    )
    assert response.status_code == 400
    assert list(backup_env["backup_dir"].glob("*.capbak")) == []


async def test_import_rejects_combined_outer_and_nested_expansion(
    client, admin_headers, backup_env, monkeypatch
):
    created, archive = await _create_backup_bytes(client, admin_headers, backup_env)
    await client.delete(f"/api/v1/admin/backups/{created['id']}", headers=admin_headers)

    db_dump = b"x" * (700 * 1024)
    uploads = _nested_archive(("large.bin", b"y" * (700 * 1024)))
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        manifest = json.loads(tar.extractfile("manifest.json").read())
    manifest["database"].update(sha256=_sha256_bytes(db_dump), size_bytes=len(db_dump))
    manifest["uploads"].update(sha256=_sha256_bytes(uploads), size_bytes=len(uploads))
    archive = _replace_archive_member(archive, "database.sql", db_dump)
    archive = _replace_archive_member(archive, "uploads.tar.gz", uploads)
    archive = _replace_archive_member(
        archive, "manifest.json", json.dumps(manifest).encode("utf-8")
    )

    limit = 1024 * 1024
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as outer:
        outer_total = sum(member.size for member in outer)
    with tarfile.open(fileobj=io.BytesIO(uploads), mode="r:gz") as nested:
        nested_total = sum(member.size for member in nested)
    assert outer_total < limit
    assert nested_total < limit
    assert outer_total + nested_total > limit

    monkeypatch.setattr(settings, "backup_expanded_max_mb", 1)
    response = await client.post(
        "/api/v1/admin/backups/import",
        headers=admin_headers,
        files={"file": ("oversized.capbak", archive, "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "size" in response.json()["detail"].lower()
    assert list(backup_env["backup_dir"].glob("*.capbak")) == []


async def test_import_rejects_nested_member_count_before_persisting(
    client, admin_headers, backup_env, monkeypatch
):
    created, archive = await _create_backup_bytes(client, admin_headers, backup_env)
    await client.delete(f"/api/v1/admin/backups/{created['id']}", headers=admin_headers)
    uploads = _nested_archive(*[(f"file-{index}.txt", b"x") for index in range(4)])
    monkeypatch.setattr(settings, "backup_max_members", 3)
    response = await client.post(
        "/api/v1/admin/backups/import",
        headers=admin_headers,
        files={"file": ("bad.capbak", _archive_with_uploads(archive, uploads), "application/octet-stream")},
    )
    assert response.status_code == 400
    assert list(backup_env["backup_dir"].glob("*.capbak")) == []


async def test_import_rejects_large_nested_tar_header_before_persisting(
    client, admin_headers, backup_env
):
    created, archive = await _create_backup_bytes(client, admin_headers, backup_env)
    await client.delete(f"/api/v1/admin/backups/{created['id']}", headers=admin_headers)
    nested_output = io.BytesIO()
    with tarfile.open(fileobj=nested_output, mode="w:gz", format=tarfile.PAX_FORMAT) as tar:
        member = tarfile.TarInfo("small.txt")
        member.size = 1
        member.pax_headers = {"comment": "a" * (1024 * 1024 + 1)}
        tar.addfile(member, io.BytesIO(b"x"))
    malicious = _archive_with_uploads(archive, nested_output.getvalue())
    response = await client.post(
        "/api/v1/admin/backups/import",
        headers=admin_headers,
        files={"file": ("bad.capbak", malicious, "application/octet-stream")},
    )
    assert response.status_code == 400
    assert list(backup_env["backup_dir"].glob("*.capbak")) == []


async def test_local_backup_larger_than_import_limit_can_restore(
    client, admin_headers, backup_env, monkeypatch
):
    monkeypatch.setattr(settings, "backup_upload_max_mb", 1)
    state_file = backup_env["upload_dir"] / "large.bin"
    expected = os.urandom(1024 * 1024 + 1)
    state_file.write_bytes(expected)
    created = await _create_backup(client, admin_headers)
    assert created["size_bytes"] > 1024 * 1024
    state_file.write_bytes(b"changed")
    response = await client.post(
        f"/api/v1/admin/backups/{created['id']}/restore",
        headers=admin_headers,
        json={"confirmation": "RESTORE"},
    )
    assert response.status_code == 200
    assert state_file.read_bytes() == expected


async def test_restore_rejects_archive_changed_after_creation_without_mutation(
    client, admin_headers, backup_env
):
    created = await _create_backup(client, admin_headers)
    archive_path = backup_env["backup_dir"] / created["archive_filename"]
    archive_path.write_bytes(archive_path.read_bytes() + b"unexpected")
    state_file = backup_env["upload_dir"] / "current.txt"
    state_file.write_text("current", encoding="utf-8")
    response = await client.post(
        f"/api/v1/admin/backups/{created['id']}/restore",
        headers=admin_headers,
        json={"confirmation": "RESTORE"},
    )
    assert response.status_code == 400
    assert state_file.read_text(encoding="utf-8") == "current"
    assert len(list(backup_env["backup_dir"].glob("*.capbak"))) == 1


async def test_admin_can_create_list_download_delete_backups(client, admin_headers, backup_env):
    upload_dir = backup_env["upload_dir"]
    (upload_dir / "sample.txt").write_text("sample-upload", encoding="utf-8")

    created = await _create_backup(client, admin_headers)
    backup_id = created["id"]

    list_response = await client.get("/api/v1/admin/backups", headers=admin_headers)
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == backup_id

    download_response = await client.get(
        f"/api/v1/admin/backups/{backup_id}/download",
        headers=admin_headers,
    )
    assert download_response.status_code == 200
    assert download_response.headers["content-type"] == "application/octet-stream"
    assert download_response.content

    delete_response = await client.delete(
        f"/api/v1/admin/backups/{backup_id}",
        headers=admin_headers,
    )
    assert delete_response.status_code == 204

    list_after_delete = await client.get("/api/v1/admin/backups", headers=admin_headers)
    assert list_after_delete.status_code == 200
    assert list_after_delete.json()["total"] == 0


async def test_admin_can_import_backup_and_download_it(client, admin_headers, backup_env):
    created, archive_bytes = await _create_backup_bytes(client, admin_headers, backup_env)
    delete_response = await client.delete(
        f"/api/v1/admin/backups/{created['id']}",
        headers=admin_headers,
    )
    assert delete_response.status_code == 204

    imported = await _import_backup(
        client, admin_headers, archive_bytes, created["archive_filename"]
    )
    assert imported["id"] == created["id"]
    assert imported["archive_filename"] == created["archive_filename"]

    archive_path = backup_env["backup_dir"] / imported["archive_filename"]
    sidecar_path = backup_env["backup_dir"] / f"{imported['id']}.json"
    assert archive_path.exists()
    assert sidecar_path.exists()

    list_response = await client.get("/api/v1/admin/backups", headers=admin_headers)
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["id"] == created["id"]

    download_response = await client.get(
        f"/api/v1/admin/backups/{created['id']}/download",
        headers=admin_headers,
    )
    assert download_response.status_code == 200
    assert download_response.content == archive_bytes


async def test_backup_manifest_checksums_and_upload_backup_exclusion(
    client, admin_headers, backup_env
):
    upload_dir = backup_env["upload_dir"]
    backup_dir = backup_env["backup_dir"]

    (upload_dir / "regular.txt").write_text("keep-me", encoding="utf-8")
    (backup_dir / "should-not-export.txt").write_text("exclude-me", encoding="utf-8")

    created = await _create_backup(client, admin_headers)
    archive_path = backup_dir / created["archive_filename"]
    assert archive_path.exists()

    with tarfile.open(archive_path, "r:gz") as outer_tar:
        manifest_file = outer_tar.extractfile("manifest.json")
        db_file = outer_tar.extractfile("database.sql")
        uploads_file = outer_tar.extractfile("uploads.tar.gz")
        assert manifest_file is not None
        assert db_file is not None
        assert uploads_file is not None

        manifest_data = json.loads(manifest_file.read().decode("utf-8"))
        db_bytes = db_file.read()
        uploads_bytes = uploads_file.read()

    assert manifest_data["format_version"] == 1
    assert manifest_data["database"]["sha256"] == _sha256_bytes(db_bytes)
    assert manifest_data["uploads"]["sha256"] == _sha256_bytes(uploads_bytes)

    with tarfile.open(fileobj=io.BytesIO(uploads_bytes), mode="r:gz") as uploads_tar:
        names = uploads_tar.getnames()
    assert "regular.txt" in names
    assert "should-not-export.txt" not in names


async def test_restore_reverts_database_and_uploads_and_creates_pre_restore_backup(
    client,
    db_session,
    default_jurisdiction,
    admin_user,
    admin_headers,
    backup_env,
):
    upload_dir = backup_env["upload_dir"]
    db_path = backup_env["db_path"]
    tracked_file = upload_dir / "state.txt"
    tracked_file.write_text("before-backup", encoding="utf-8")

    created = await _create_backup(client, admin_headers)
    backup_id = created["id"]

    tracked_file.write_text("after-backup", encoding="utf-8")
    db_session.add(
        User(
            email="post-backup-user@example.com",
            password_hash=hash_password("password123"),
            full_name="Post Backup User",
            role="contributor",
            organization_id=admin_user.organization_id,
        )
    )
    await db_session.commit()

    restore_response = await client.post(
        f"/api/v1/admin/backups/{backup_id}/restore",
        headers=admin_headers,
        json={"confirmation": "RESTORE", "reason": "restore test"},
    )
    assert restore_response.status_code == 200
    restore_payload = restore_response.json()
    assert restore_payload["restored_backup_id"] == backup_id
    assert restore_payload["pre_restore_backup_id"]

    assert tracked_file.read_text(encoding="utf-8") == "before-backup"

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM users WHERE email = ?",
            ("post-backup-user@example.com",),
        ).fetchone()
    assert row is not None
    assert int(row[0]) == 0

    list_response = await client.get("/api/v1/admin/backups", headers=admin_headers)
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["total"] == 2
    reasons = {item["reason"] for item in list_payload["items"]}
    assert "pre_restore" in reasons
    assert "manual" in reasons


async def test_imported_backup_can_restore_database_and_uploads(
    client,
    db_session,
    default_jurisdiction,
    admin_user,
    admin_headers,
    backup_env,
):
    tracked_file = backup_env["upload_dir"] / "state.txt"
    tracked_file.write_text("before-import", encoding="utf-8")

    created, archive_bytes = await _create_backup_bytes(client, admin_headers, backup_env)
    delete_response = await client.delete(
        f"/api/v1/admin/backups/{created['id']}",
        headers=admin_headers,
    )
    assert delete_response.status_code == 204

    tracked_file.write_text("after-import", encoding="utf-8")
    db_session.add(
        User(
            email="post-import-user@example.com",
            password_hash=hash_password("password123"),
            full_name="Post Import User",
            role="contributor",
            organization_id=admin_user.organization_id,
        )
    )
    await db_session.commit()

    imported = await _import_backup(
        client, admin_headers, archive_bytes, created["archive_filename"]
    )

    restore_response = await client.post(
        f"/api/v1/admin/backups/{imported['id']}/restore",
        headers=admin_headers,
        json={"confirmation": "RESTORE", "reason": "import restore test"},
    )
    assert restore_response.status_code == 200
    restore_payload = restore_response.json()
    assert restore_payload["restored_backup_id"] == imported["id"]
    assert restore_payload["pre_restore_backup_id"]

    assert tracked_file.read_text(encoding="utf-8") == "before-import"

    with sqlite3.connect(backup_env["db_path"]) as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM users WHERE email = ?",
            ("post-import-user@example.com",),
        ).fetchone()
    assert row is not None
    assert int(row[0]) == 0

    list_response = await client.get("/api/v1/admin/backups", headers=admin_headers)
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 2


async def test_restore_returns_conflict_when_extraction_is_active(
    client,
    db_session,
    default_jurisdiction,
    admin_user,
    admin_headers,
    backup_env,
):
    created = await _create_backup(client, admin_headers)
    backup_id = created["id"]

    document = Document(
        jurisdiction_id=default_jurisdiction.id,
        organization_id=admin_user.organization_id,
        filename="active.pdf",
        name="Active Extraction Doc",
        document_type="standard",
        version="1",
        status="extracting",
        file_path=str(backup_env["upload_dir"] / "active.pdf"),
        uploaded_by=admin_user.id,
    )
    db_session.add(document)
    await db_session.flush()

    db_session.add(
        ExtractionRun(
            document_id=document.id,
            status="running",
            ai_provider="none",
            ai_model="none",
        )
    )
    await db_session.commit()

    restore_response = await client.post(
        f"/api/v1/admin/backups/{backup_id}/restore",
        headers=admin_headers,
        json={"confirmation": "RESTORE"},
    )
    assert restore_response.status_code == 409
    assert "active" in restore_response.json()["detail"].lower()


async def test_restore_rejects_corrupted_archive(client, admin_headers, backup_env):
    created = await _create_backup(client, admin_headers)
    backup_id = created["id"]
    archive_path = backup_env["backup_dir"] / created["archive_filename"]
    archive_path.write_bytes(b"not-a-valid-backup")

    restore_response = await client.post(
        f"/api/v1/admin/backups/{backup_id}/restore",
        headers=admin_headers,
        json={"confirmation": "RESTORE"},
    )
    assert restore_response.status_code == 400


async def test_restore_rejects_different_database_engine_before_mutation(
    client, admin_headers, backup_env, monkeypatch
):
    created = await _create_backup(client, admin_headers)
    tracked_file = backup_env["upload_dir"] / "state.txt"
    tracked_file.write_text("retain-current-state", encoding="utf-8")
    backup_count = len(list(backup_env["backup_dir"].glob("*.capbak")))
    monkeypatch.setattr(backup_service, "_database_engine", lambda: "postgresql")

    response = await client.post(
        f"/api/v1/admin/backups/{created['id']}/restore",
        headers=admin_headers,
        json={"confirmation": "RESTORE"},
    )

    assert response.status_code == 400
    assert "engine" in response.json()["detail"].lower()
    assert tracked_file.read_text(encoding="utf-8") == "retain-current-state"
    assert len(list(backup_env["backup_dir"].glob("*.capbak"))) == backup_count


async def test_import_rejects_corrupted_archive_without_partial_files(
    client, admin_headers, backup_env
):
    response = await client.post(
        "/api/v1/admin/backups/import",
        headers=admin_headers,
        files={"file": ("broken.capbak", b"not-a-valid-backup", "application/octet-stream")},
    )
    assert response.status_code == 400
    assert list(backup_env["backup_dir"].glob("*.capbak")) == []
    assert list(backup_env["backup_dir"].glob("*.json")) == []


async def test_import_rejects_duplicate_backup_ids(client, admin_headers, backup_env):
    created, archive_bytes = await _create_backup_bytes(client, admin_headers, backup_env)

    response = await client.post(
        "/api/v1/admin/backups/import",
        headers=admin_headers,
        files={
            "file": (created["archive_filename"], archive_bytes, "application/octet-stream"),
        },
    )
    assert response.status_code == 409
    assert created["id"] in response.json()["detail"]


async def test_import_rejects_uploads_over_configured_limit(
    client, admin_headers, backup_env, monkeypatch
):
    monkeypatch.setattr(settings, "backup_upload_max_mb", 1)

    response = await client.post(
        "/api/v1/admin/backups/import",
        headers=admin_headers,
        files={
            "file": ("too-large.capbak", b"x" * (1024 * 1024 + 1), "application/octet-stream"),
        },
    )
    assert response.status_code == 413
    assert list(backup_env["backup_dir"].glob("*.capbak")) == []


async def test_backup_retention_keeps_latest_n(client, admin_headers, backup_env, monkeypatch):
    monkeypatch.setattr(settings, "backup_retention_count", 2)
    for idx in range(3):
        (backup_env["upload_dir"] / f"file-{idx}.txt").write_text(str(idx), encoding="utf-8")
        response = await client.post("/api/v1/admin/backups", headers=admin_headers)
        assert response.status_code == 201

    list_response = await client.get("/api/v1/admin/backups", headers=admin_headers)
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["total"] == 2


def test_run_command_uses_explicit_postgres_tools_directory(monkeypatch, tmp_path):
    pg_dump_path = tmp_path / "pg_dump"
    pg_dump_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    pg_dump_path.chmod(0o755)
    monkeypatch.setattr(settings, "postgres_bin_dir", str(tmp_path))
    monkeypatch.setattr(backup_service.shutil, "which", lambda command: None)

    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return backup_service.subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(backup_service.subprocess, "run", fake_run)

    backup_service._run_command(["pg_dump", "--version"])

    assert captured["command"] == [str(pg_dump_path), "--version"]


def test_run_command_wraps_unresolved_commands_as_dependency_error(monkeypatch):
    def fake_resolve(command_name: str) -> str:
        raise FileNotFoundError(command_name)

    monkeypatch.setattr(backup_service, "_resolve_command", fake_resolve)

    with pytest.raises(backup_service.BackupDependencyError, match="pg_dump"):
        backup_service._run_command(["pg_dump", "--version"])


@pytest.mark.parametrize("operation", ["dump", "restore", "query"])
def test_missing_postgres_tools_never_discover_containers(monkeypatch, tmp_path, operation):
    url = backup_service.make_url("postgresql+asyncpg://fixture@127.0.0.1:25489/cap_e2e")
    monkeypatch.setattr(settings, "postgres_bin_dir", "")
    monkeypatch.setattr(backup_service.shutil, "which", lambda command: None)
    calls = []
    monkeypatch.setattr(backup_service.subprocess, "run", lambda *args, **kwargs: calls.append(args))
    with pytest.raises(backup_service.BackupDependencyError):
        if operation == "dump":
            backup_service._dump_postgres_database_to_file(url, tmp_path / "database.sql")
        elif operation == "restore":
            backup_service._restore_postgres_database_from_dump(url, tmp_path / "database.sql")
        else:
            backup_service._query_active_postgres_extractions(url, "select 0")
    assert calls == []


def test_invalid_explicit_postgres_directory_does_not_fall_back(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "postgres_bin_dir", str(tmp_path))
    monkeypatch.setattr(backup_service.shutil, "which", lambda command: "/unexpected/pg_dump")
    with pytest.raises(FileNotFoundError):
        backup_service._resolve_command("pg_dump")


def test_pg17_dump_restores_to_pg16_without_changing_copy_data(monkeypatch, tmp_path):
    dump_path = tmp_path / "database.sql"
    original = (
        "-- PostgreSQL database dump\nSET transaction_timeout = 0;\n"
        + "-- header padding\n" * 32
        + "COPY public.notes (body) FROM stdin;\nSET transaction_timeout = 0;\n\\.\n"
    )
    dump_path.write_text(original, encoding="utf-8")
    executed = []

    def fake_run(command, **_kwargs):
        if "SHOW server_version_num;" in command:
            return backup_service.subprocess.CompletedProcess(command, 0, "160015\n", "")
        executed.append((command, (tmp_path / "database-compatible.sql").read_text()))
        return backup_service.subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(backup_service, "_run_command", fake_run)
    url = backup_service.make_url("postgresql+asyncpg://fixture@127.0.0.1:25489/cap_e2e")
    backup_service._restore_postgres_database_from_dump(url, dump_path)

    assert len(executed) == 1
    assert executed[0][1].count("SET transaction_timeout = 0;") == 1
    assert dump_path.read_text(encoding="utf-8") == original
    assert not (tmp_path / "database-compatible.sql").exists()
