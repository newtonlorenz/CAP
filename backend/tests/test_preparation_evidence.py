"""Evidence library isolation, file integrity and portable preparation exports."""

import hashlib
import io
import json
import secrets
import shutil
import uuid
import zipfile
from pathlib import Path

import pytest

from app.models.organization import Organization
from app.models.preparation import PreparationEvidence
from app.models.user import User
from app.services.auth import create_access_token, hash_password
from app.services.preparation_files import checked_evidence_path

BASE = "/api/v1/preparation"


@pytest.fixture
async def preparation_users(db_session):
    orgs = [
        Organization(code=f"preparation-{index}", name=f"Example organisation {index}")
        for index in range(2)
    ]
    db_session.add_all(orgs)
    await db_session.flush()
    users = {}
    password_hash = hash_password(secrets.token_urlsafe(24))
    for key, org, role in [
        ("admin", orgs[0], "admin"),
        ("contributor", orgs[0], "contributor"),
        ("viewer", orgs[0], "viewer"),
        ("outsider", orgs[1], "admin"),
        ("legacy", None, "admin"),
    ]:
        user = User(
            email=f"{key}-prep@example.com",
            full_name=key,
            password_hash=password_hash,
            role=role,
            organization_id=org.id if org else None,
        )
        db_session.add(user)
        await db_session.flush()
        users[key] = {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}
    await db_session.commit()
    return users


async def upload(
    client, headers, *, filename="policy.txt", content=b"Example control evidence", **metadata
):
    return await client.post(
        f"{BASE}/evidence/upload",
        data={"title": "Shared policy", "visibility": "organisation", **metadata},
        files={"file": (filename, content, "text/plain")},
        headers=headers,
    )


async def test_evidence_library_isolated_and_readers_cannot_mutate(client, preparation_users):
    users = preparation_users
    created = await client.post(
        f"{BASE}/evidence",
        json={"title": "Approval record", "kind": "note", "body": "Reviewed by the control owner", "visibility": "organisation"},
        headers=users["contributor"],
    )
    assert created.status_code == 201, created.text
    evidence_id = created.json()["id"]
    for role in ("outsider", "legacy"):
        assert (
            await client.get(f"{BASE}/evidence/{evidence_id}", headers=users[role])
        ).status_code == 404
        listing = await client.get(f"{BASE}/evidence", headers=users[role])
        assert listing.json()["items"] == []
        assert (
            await client.patch(
                f"{BASE}/evidence/{evidence_id}", json={"archived": True}, headers=users[role]
            )
        ).status_code == 404
        assert (
            await client.get(f"{BASE}/evidence/{evidence_id}/download", headers=users[role])
        ).status_code == 404
    assert (await client.get(f"{BASE}/evidence", headers=users["viewer"])).json()["total"] == 1
    assert (
        await client.post(
            f"{BASE}/evidence",
            json={"title": "Not permitted", "kind": "note", "body": "No"},
            headers=users["viewer"],
        )
    ).status_code == 403
    assert (
        await client.patch(
            f"{BASE}/evidence/{evidence_id}", json={"archived": True}, headers=users["contributor"]
        )
    ).status_code == 200
    assert (await client.get(f"{BASE}/evidence", headers=users["admin"])).json()["total"] == 0
    assert (
        await client.get(f"{BASE}/evidence?include_archived=true", headers=users["admin"])
    ).json()["total"] == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"title": "   ", "kind": "note", "body": "text"},
        {"title": "Empty", "kind": "note", "body": "   "},
        {"title": "Invalid", "kind": "link", "link_url": "javascript:alert(1)"},
        {"title": "Credentials", "kind": "link", "link_url": "https://name:password@example.com"},
        {
            "title": "Dates",
            "kind": "note",
            "body": "text",
            "valid_from": "2027-02-01",
            "valid_until": "2027-01-01",
        },
    ],
)
async def test_evidence_rejects_invalid_metadata(client, preparation_users, payload):
    response = await client.post(
        f"{BASE}/evidence", json=payload, headers=preparation_users["admin"]
    )
    assert response.status_code == 422


async def test_uploaded_bytes_are_verified_and_storage_path_private(
    client, preparation_users, db_session, monkeypatch, tmp_path
):
    created = await upload(client, preparation_users["contributor"], filename="../../policy.txt")
    assert created.status_code == 201, created.text
    data = created.json()
    assert data["filename"] == "policy.txt"
    assert "file_path" not in data
    assert data["sha256"] == hashlib.sha256(b"Example control evidence").hexdigest()
    download = await client.get(
        f"{BASE}/evidence/{data['id']}/download", headers=preparation_users["viewer"]
    )
    assert download.status_code == 200
    assert download.content == b"Example control evidence"
    assert download.headers["content-disposition"].startswith("attachment;")
    assert download.headers["x-content-type-options"] == "nosniff"
    item = await db_session.get(PreparationEvidence, uuid.UUID(data["id"]))
    from app.config import settings

    # A restored uploads volume may be mounted at another operator-selected path.
    assert not Path(item.file_path).is_absolute()
    restored_root = tmp_path / "restored-uploads"
    shutil.copytree(settings.upload_dir, restored_root)
    monkeypatch.setattr(settings, "upload_dir", str(restored_root))
    restored = await client.get(
        f"{BASE}/evidence/{data['id']}/download", headers=preparation_users["admin"]
    )
    assert restored.content == b"Example control evidence"
    checked_evidence_path(item).write_bytes(b"Changed outside CAP")
    assert (
        await client.get(
            f"{BASE}/evidence/{data['id']}/download", headers=preparation_users["admin"]
        )
    ).status_code == 409


async def test_upload_limits_empty_files_and_invalid_dates_leave_no_files(
    client, preparation_users, monkeypatch
):
    from app.config import settings

    headers = preparation_users["admin"]
    assert (await upload(client, headers, content=b"")).status_code == 400
    assert (
        await upload(client, headers, valid_from="2027-02-01", valid_until="2027-01-01")
    ).status_code == 422
    assert (await upload(client, headers, filename="script.exe")).status_code == 400
    monkeypatch.setattr(settings, "max_evidence_upload_mb", 1)
    assert (await upload(client, headers, content=b"x" * (1024 * 1024 + 1))).status_code == 413
    assert list(Path(settings.upload_dir).rglob("*.*")) == []
    assert (await client.get(f"{BASE}/evidence", headers=headers)).json()["total"] == 0


async def make_case(client, headers, jurisdiction_id):
    template = await client.post(
        f"{BASE}/templates",
        headers=headers,
        json={
            "name": "Application preparation",
            "kind": "licence_application",
            "fields": [
                {
                    "key": "entity",
                    "label": "Applicant",
                    "type": "text",
                    "section": "Organisation",
                    "required": True,
                }
            ],
        },
    )
    assert template.status_code == 201, template.text
    response = await client.post(
        f"{BASE}/cases",
        headers=headers,
        json={
            "template_id": template.json()["id"],
            "jurisdiction_id": str(jurisdiction_id),
            "name": "Example application",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_export_contains_scoped_responses_evidence_checksums_and_no_approval_claim(
    client, preparation_users, default_jurisdiction
):
    headers = preparation_users["admin"]
    case = await make_case(client, headers, default_jurisdiction.id)
    evidence = (await upload(client, headers)).json()
    saved = await client.put(
        f"{BASE}/cases/{case['id']}/responses/entity",
        headers=headers,
        json={
            "expected_revision": case["revision"],
            "value": "=Example entity",
            "evidence_ids": [evidence["id"]],
        },
    )
    assert saved.status_code == 200, saved.text
    exported = await client.get(f"{BASE}/cases/{case['id']}/export", headers=headers)
    assert exported.status_code == 200, exported.text
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        record = json.loads(archive.read("preparation.json"))
        assert record["case"]["responses"][0]["value"] == "=Example entity"
        assert record["case"]["readiness"]["ready"] is False
        assert "not a regulator submission" in record["purpose"]
        assert "'=Example entity" in archive.read("responses.csv").decode("utf-8-sig")
        assert "file_path" not in json.dumps(record)
        manifest = json.loads(archive.read("manifest.json"))
        for item in manifest["files"]:
            data = archive.read(item["path"])
            assert hashlib.sha256(data).hexdigest() == item["sha256"]
            assert len(data) == item["size_bytes"]
        attached = [name for name in archive.namelist() if name.startswith("evidence/")]
        assert len(attached) == 1
        assert archive.read(attached[0]) == b"Example control evidence"
    assert (
        await client.get(f"{BASE}/cases/{case['id']}/export", headers=preparation_users["outsider"])
    ).status_code == 404
    after = (await client.get(f"{BASE}/cases/{case['id']}", headers=headers)).json()
    assert after["revision"] == saved.json()["revision"]
    assert after["responses"][0]["accepted_at"] is None
