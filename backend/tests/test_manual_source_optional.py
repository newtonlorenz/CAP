import importlib.util
import io
import uuid
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, select, text

from app.config import settings
from app.models import Document
from app.models.user import User
from app.services.auth import create_access_token, hash_password


@pytest.fixture
async def manager_headers(db_session):
    user = User(
        email="manual-source-manager@example.com",
        password_hash=hash_password("testpass"),
        full_name="Manual Source Manager",
        role="manager",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    token = create_access_token({"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


async def _create_manual_set(client, headers, jurisdiction_id):
    response = await client.post(
        "/api/v1/requirements/sets",
        json={
            "jurisdiction_id": str(jurisdiction_id),
            "name": "Manual source-free set",
            "document_type": "annex_b",
            "testing_frequency": "one_off",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_manual_set_has_no_pdf_and_remains_listable(
    client, manager_headers, default_jurisdiction, db_session
):
    created = await _create_manual_set(client, manager_headers, default_jurisdiction.id)
    assert created["filename"] is None
    assert created["has_source"] is False

    document = await db_session.scalar(
        select(Document).where(Document.id == uuid.UUID(created["id"]))
    )
    assert document.file_path is None
    assert not Path(settings.upload_dir).exists()

    detail = await client.get(f"/api/v1/documents/{created['id']}", headers=manager_headers)
    assert detail.status_code == 200
    assert detail.json()["filename"] is None
    assert detail.json()["has_source"] is False

    listing = await client.get(
        "/api/v1/requirements/sets?include_empty_sets=true", headers=manager_headers
    )
    assert listing.status_code == 200, listing.text
    listed = next(item for item in listing.json()["items"] if item["document_id"] == created["id"])
    assert listed["filename"] is None
    assert listed["has_source"] is False

    source = await client.get(f"/api/v1/documents/{created['id']}/source", headers=manager_headers)
    assert source.status_code == 404
    assert "no source PDF" in source.text

    extraction = await client.post(f"/api/v1/documents/{created['id']}/extract", headers=manager_headers)
    assert extraction.status_code == 409
    assert "no source PDF" in extraction.text


async def test_legacy_manual_placeholder_is_not_exposed_as_a_source(
    client, manager_headers, default_jurisdiction, db_session, tmp_path
):
    created = await _create_manual_set(client, manager_headers, default_jurisdiction.id)
    placeholder = tmp_path / f"manual_{uuid.uuid4()}.pdf"
    placeholder.write_bytes(b"%PDF-1.4\nlegacy placeholder")
    document = await db_session.scalar(
        select(Document).where(Document.id == uuid.UUID(created["id"]))
    )
    document.filename = "manual-placeholder.pdf"
    document.file_path = str(placeholder)
    await db_session.commit()

    detail = await client.get(f"/api/v1/documents/{created['id']}", headers=manager_headers)
    assert detail.status_code == 200
    assert detail.json()["filename"] == "manual-placeholder.pdf"
    assert detail.json()["has_source"] is False
    listing = await client.get(
        "/api/v1/requirements/sets?include_empty_sets=true", headers=manager_headers
    )
    assert listing.status_code == 200
    listed = next(item for item in listing.json()["items"] if item["document_id"] == created["id"])
    assert listed["has_source"] is False
    source = await client.get(f"/api/v1/documents/{created['id']}/source", headers=manager_headers)
    assert source.status_code == 404
    extraction = await client.post(f"/api/v1/documents/{created['id']}/extract", headers=manager_headers)
    assert extraction.status_code == 409


@pytest.mark.parametrize("filename", ["manual.pdf", "manual-placeholder.pdf"])
async def test_real_upload_named_manual_pdf_remains_a_source(
    client, manager_headers, default_jurisdiction, filename
):
    pdf = b"%PDF-1.4\nreal uploaded source"
    upload = await client.post(
        "/api/v1/documents",
        files={"file": (filename, io.BytesIO(pdf), "application/pdf")},
        data={"document_type": "annex_a", "jurisdiction_id": str(default_jurisdiction.id)},
        headers=manager_headers,
    )
    assert upload.status_code == 201, upload.text
    assert upload.json()["has_source"] is True
    listing = await client.get(
        "/api/v1/requirements/sets?include_empty_sets=true", headers=manager_headers
    )
    assert listing.status_code == 200
    listed = next(item for item in listing.json()["items"] if item["document_id"] == upload.json()["id"])
    assert listed["has_source"] is True
    source = await client.get(
        f"/api/v1/documents/{upload.json()['id']}/source", headers=manager_headers
    )
    assert source.status_code == 200
    assert source.content == pdf


@pytest.mark.parametrize(
    ("engine", "document_type", "expected_pipeline"),
    [
        ("opendataloader", "standard", "opendataloader_v1"),
        ("native", "standard", "born_digital_v4"),
        ("opendataloader", "operator category", "opendataloader_v1"),
    ],
)
async def test_uploaded_pdf_keeps_source_and_snapshots_pipeline(
    client, manager_headers, default_jurisdiction, monkeypatch,
    engine, document_type, expected_pipeline,
):
    from app.tasks.extraction import extract_requirements_task

    queued = []
    monkeypatch.setattr(extract_requirements_task, "delay", lambda *args: queued.append(args))
    monkeypatch.setattr(settings, "ai_provider_setting", "none")
    monkeypatch.setattr(settings, "pdf_structure_engine", engine)
    monkeypatch.setattr("app.services.structured_pdf.structured_pdf_available", lambda: True)
    pdf = b"%PDF-1.4\nsynthetic fixture"
    upload = await client.post(
        "/api/v1/documents",
        files={"file": ("real-source.pdf", io.BytesIO(pdf), "application/pdf")},
        data={"document_type": document_type, "jurisdiction_id": str(default_jurisdiction.id)},
        headers=manager_headers,
    )
    assert upload.status_code == 201, upload.text
    document_id = upload.json()["id"]
    assert upload.json()["filename"] == "real-source.pdf"
    assert upload.json()["has_source"] is True

    source = await client.get(f"/api/v1/documents/{document_id}/source", headers=manager_headers)
    assert source.status_code == 200
    assert source.content == pdf

    response = await client.post(f"/api/v1/documents/{document_id}/extract", headers=manager_headers)
    assert response.status_code == 200, response.text
    assert response.json()["current_extraction"]["pipeline_version"] == expected_pipeline
    if expected_pipeline == "opendataloader_v1":
        assert response.json()["current_extraction"]["ai_provider"] == "local"
        assert response.json()["current_extraction"]["ai_model"] == "opendataloader_2.5.11"
    assert len(queued) == 1


async def test_missing_uploaded_pdf_returns_404_without_queue(
    client, manager_headers, default_jurisdiction, db_session, monkeypatch
):
    from app.tasks.extraction import extract_requirements_task

    queued = []
    monkeypatch.setattr(extract_requirements_task, "delay", lambda *args: queued.append(args))
    upload = await client.post(
        "/api/v1/documents",
        files={"file": ("source.pdf", io.BytesIO(b"%PDF-1.4\nfixture"), "application/pdf")},
        data={"document_type": "annex_a", "jurisdiction_id": str(default_jurisdiction.id)},
        headers=manager_headers,
    )
    assert upload.status_code == 201
    document_id = upload.json()["id"]
    document = await db_session.scalar(select(Document).where(Document.id == uuid.UUID(document_id)))
    Path(document.file_path).unlink()

    source = await client.get(f"/api/v1/documents/{document_id}/source", headers=manager_headers)
    extraction = await client.post(f"/api/v1/documents/{document_id}/extract", headers=manager_headers)
    assert source.status_code == 404
    assert extraction.status_code == 404
    assert queued == []


@pytest.mark.parametrize("available", [True, False])
async def test_structured_scp_is_local_even_when_cloud_provider_is_configured(
    client, manager_headers, default_jurisdiction, monkeypatch, available
):
    from app.tasks.extraction import extract_requirements_task

    queued = []
    monkeypatch.setattr(extract_requirements_task, "delay", lambda *args: queued.append(args))
    monkeypatch.setattr(settings, "pdf_structure_engine", "opendataloader")
    monkeypatch.setattr(settings, "ai_provider_setting", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "synthetic-test-key")
    monkeypatch.setattr("app.services.structured_pdf.structured_pdf_available", lambda: available)
    upload = await client.post(
        "/api/v1/documents",
        files={"file": ("scp.pdf", io.BytesIO(b"%PDF-1.4\nfixture"), "application/pdf")},
        data={"document_type": "standard", "jurisdiction_id": str(default_jurisdiction.id)},
        headers=manager_headers,
    )
    assert upload.status_code == 201
    response = await client.post(
        f"/api/v1/documents/{upload.json()['id']}/extract", headers=manager_headers
    )
    if available:
        assert response.status_code == 200, response.text
        run = response.json()["current_extraction"]
        assert (run["ai_provider"], run["ai_model"], run["pipeline_version"]) == (
            "local", "opendataloader_2.5.11", "opendataloader_v1"
        )
        assert len(queued) == 1
    else:
        assert response.status_code == 503
        assert "OpenDataLoader" in response.text
        assert queued == []


def test_nullable_source_migration_round_trip_is_safe(tmp_path, monkeypatch):
    migration_path = (
        Path(__file__).parents[1]
        / "alembic/versions/s20260924_source_optional_manual_sets.py"
    )
    spec = importlib.util.spec_from_file_location("source_optional_migration", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE documents (id INTEGER PRIMARY KEY, filename VARCHAR(500) NOT NULL, "
            "file_path VARCHAR(500) NOT NULL)"
        ))
        connection.execute(text(
            "INSERT INTO documents (id, filename, file_path) VALUES (1, 'source.pdf', 'source.pdf')"
        ))
        operations = Operations(MigrationContext.configure(connection))
        monkeypatch.setattr(migration, "op", operations)

        migration.upgrade()
        assert all(
            column["nullable"]
            for column in inspect(connection).get_columns("documents")
            if column["name"] in {"filename", "file_path"}
        )
        connection.execute(text("INSERT INTO documents (id, filename, file_path) VALUES (2, NULL, NULL)"))
        with pytest.raises(RuntimeError, match="source-free requirement sets"):
            migration.downgrade()
        connection.execute(text("DELETE FROM documents WHERE id = 2"))
        migration.downgrade()
        assert all(
            not column["nullable"]
            for column in inspect(connection).get_columns("documents")
            if column["name"] in {"filename", "file_path"}
        )
    engine.dispose()
