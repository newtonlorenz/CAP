"""Country and certification metadata must not select executable policies."""

import importlib.util
import io
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException

from app.config import settings
from app.services.pdf_parser import PdfParser
from app.services.ai_provider import ProviderConfig


@pytest.fixture
async def admin_headers(db_session):
    from app.models.user import User
    from app.services.auth import create_access_token

    user = User(email="generic@example.test", full_name="Generic fixture",
                role="admin", password_hash="unused")
    db_session.add(user)
    await db_session.commit()
    return {"Authorization": "Bearer " + create_access_token({"sub": str(user.id)})}


@pytest.mark.parametrize("engine", ["native", "opendataloader"])
async def test_custom_jurisdiction_and_category_can_extract_locally(
    client,
    admin_headers,
    db_session,
    monkeypatch,
    engine,
):
    from app.models.jurisdiction import Jurisdiction
    from app.tasks.extraction import extract_requirements_task

    jurisdiction = Jurisdiction(code="operator-area", name="Operator jurisdiction", active=True)
    db_session.add(jurisdiction)
    await db_session.commit()
    monkeypatch.setattr(settings, "ai_provider_setting", "none")
    monkeypatch.setattr(settings, "pdf_structure_engine", engine)
    monkeypatch.setattr("app.services.structured_pdf.structured_pdf_available", lambda: True)
    queued = []
    monkeypatch.setattr(extract_requirements_task, "delay", lambda *args: queued.append(args))
    upload = await client.post(
        "/api/v1/documents",
        headers=admin_headers,
        files={
            "file": ("source.pdf", io.BytesIO(b"%PDF-1.4\nsynthetic fixture"), "application/pdf")
        },
        data={"document_type": "Custom certification", "jurisdiction_id": str(jurisdiction.id)},
    )
    assert upload.status_code == 201, upload.text
    result = await client.post(
        f"/api/v1/documents/{upload.json()['id']}/extract", headers=admin_headers
    )
    assert result.status_code == 200, result.text
    assert result.json()["document_type"] == "Custom certification"
    assert result.json()["current_extraction"]["ai_provider"] == "local"
    assert result.json()["current_extraction"]["pipeline_version"] == (
        "opendataloader_v1" if engine == "opendataloader" else "born_digital_v4"
    )
    assert len(queued) == 1


async def test_native_parser_does_not_treat_a_legacy_category_as_a_template():
    source = "1.1 Audit records\nThe service shall retain access logs."
    parser = PdfParser()
    custom = await parser.parse_requirements(
        source, "Custom certification", 1, provider_config=ProviderConfig()
    )
    legacy = await parser.parse_requirements(source, "annex_a", 1, provider_config=ProviderConfig())
    assert custom
    assert custom == legacy
    assert all(item["text"] in source for item in custom)


@pytest.mark.parametrize("category", [" ", "x" * 51])
async def test_upload_rejects_invalid_category_before_saving(
    client,
    admin_headers,
    default_jurisdiction,
    category,
):
    result = await client.post(
        "/api/v1/documents",
        headers=admin_headers,
        files={"file": ("source.pdf", io.BytesIO(b"%PDF-1.4\nfixture"), "application/pdf")},
        data={"document_type": category, "jurisdiction_id": str(default_jurisdiction.id)},
    )
    assert result.status_code == 422
    assert not list(Path(settings.upload_dir).glob("*"))


def test_generic_metadata_migration_preserves_legacy_assertions_and_pack_records():
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/g20260926_generic_parser_metadata.py"
    )
    spec = importlib.util.spec_from_file_location("generic_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE components (id INTEGER PRIMARY KEY, public_cloud_iso27001 BOOLEAN)"
            )
        )
        conn.execute(sa.text("INSERT INTO components VALUES (1, true), (2, false)"))
        conn.execute(
            sa.text(
                "CREATE TABLE market_packs (id INTEGER PRIMARY KEY, parser_mode VARCHAR(30), CONSTRAINT ck_market_packs_parser_mode CHECK (parser_mode IN ('dk_hybrid', 'generic_ai')))"
            )
        )
        conn.execute(sa.text("INSERT INTO market_packs VALUES (1, 'dk_hybrid')"))
        migration.op = Operations(MigrationContext.configure(conn))
        migration.upgrade()
        assert conn.execute(sa.text("SELECT * FROM components ORDER BY id")).all() == [
            (1, 1, "ISO/IEC 27001"),
            (2, 0, None),
        ]
        assert conn.execute(sa.text("SELECT * FROM market_packs")).all() == [(1, "dk_hybrid")]
        conn.execute(sa.text("INSERT INTO market_packs VALUES (2, 'operator_parser')"))


@pytest.mark.parametrize(
    "configured, asserted, allowed",
    [
        ("", "Example standard", False),
        ("Example standard", "Other standard", False),
        ("Example standard", "Example standard", True),
    ],
)
def test_cloud_location_exemption_requires_explicit_matching_policy(
    monkeypatch, configured, asserted, allowed
):
    from app.api.change_management import _validate_component_payload

    monkeypatch.setattr(settings, "cloud_location_exemption_standard", configured)
    payload = dict(
        confidentiality_code=1,
        integrity_code=1,
        availability_code=1,
        accountability_code=1,
        is_hardware=True,
        hosting_model="public_cloud",
        public_cloud_certification=asserted,
        public_cloud_independent=True,
        public_cloud_redundancy=True,
    )
    if allowed:
        assert _validate_component_payload(payload) == 1
    else:
        with pytest.raises(HTTPException, match="geographic_location"):
            _validate_component_payload(payload)
