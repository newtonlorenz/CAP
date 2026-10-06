"""Quality jobs preserve reviewed content, survive outages and reject stale results."""

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models import Document, ExtractedRequirement, ExtractionRun, User
from app.models.requirement_quality import RequirementQualityFinding, RequirementQualityRun
from app.services.quality_jobs import row_snapshot, source_sha
from app.tasks.requirement_quality import check_quality


@pytest.mark.parametrize(
    "scenario,applied,status",
    [
        ("fresh", True, "completed"),
        ("uncertain", False, "completed"),
        ("edited", False, "completed"),
        ("recheck", False, "completed"),
        ("approved", False, "completed"),
        ("stale", False, "completed"),
        ("stale_parent", False, "completed"),
        ("stale_proposed_parent", False, "completed"),
        ("missing_parent", False, "completed"),
        ("new_parent", False, "completed"),
        ("cancel", False, "cancelled"),
        ("settings", False, "skipped"),
        ("outage", False, "partial"),
    ],
)
async def test_quality_delivery_respects_review_and_freshness(
    scenario,
    applied,
    status,
    db_session,
    setup_database,
    default_jurisdiction,
    tmp_path,
    monkeypatch,
):
    from app.services import installation_settings, requirement_quality

    source = tmp_path / "source.pdf"
    source.write_bytes(b"fixture source fingerprint")
    user = User(
        email="quality@example.com",
        password_hash="fixture",
        full_name="Quality Manager",
        role="manager",
    )
    db_session.add(user)
    await db_session.flush()
    doc = Document(
        filename="source.pdf",
        file_path=str(source),
        document_type="standard",
        jurisdiction_id=default_jurisdiction.id,
        uploaded_by=user.id,
        status="extracted",
    )
    db_session.add(doc)
    await db_session.flush()
    extraction = ExtractionRun(
        document_id=doc.id, status="completed", ai_provider="local", ai_model="local"
    )
    db_session.add(extraction)
    await db_session.flush()
    doc.current_extraction_id = extraction.id
    row = ExtractedRequirement(
        document_id=doc.id,
        extraction_run_id=extraction.id,
        reference_id="1",
        text="Operator must keep records.",
        original_text="Operator must keep records.",
        page_number=1,
        requirement_type="recommended",
        quality_auto_editable=True,
    )
    db_session.add(row)
    await db_session.flush()
    parent = None
    snapshot_rows = [row_snapshot(row)]
    if scenario in {"stale_parent", "stale_proposed_parent", "missing_parent", "new_parent"}:
        parent = ExtractedRequirement(
            document_id=doc.id,
            extraction_run_id=extraction.id,
            reference_id="PARENT",
            text="Original parent scope",
            original_text="Original parent scope",
            page_number=1,
            quality_auto_editable=True,
        )
        db_session.add(parent)
        await db_session.flush()
        if scenario in {"stale_parent", "missing_parent"}:
            row.parent_id = parent.id
        snapshot_rows = [row_snapshot(row)]
        if scenario != "new_parent":
            snapshot_rows.append(row_snapshot(parent))
    run = RequirementQualityRun(
        document_id=doc.id,
        extraction_run_id=extraction.id,
        requested_by=user.id,
        mode="recheck" if scenario == "recheck" else "import",
        model="jev-1.13.0",
        settings_revision=1,
        source_sha256=source_sha(source),
        snapshot={"rows": snapshot_rows, "pages": [{"page_number": 1, "text": row.text}]},
    )
    db_session.add(run)
    await db_session.flush()
    run_id, row_id = run.id, row.id
    if scenario == "edited":
        row.quality_auto_editable = False
    elif scenario == "approved":
        doc.status = "approved"
    await db_session.commit()
    runtime = SimpleNamespace(
        jev_enabled=True,
        jev_model="jev-1.13.0",
        typesafe_api_key="fixture",
        jev_settings_revision=1,
    )

    async def resolve(_db):
        return runtime

    monkeypatch.setattr(installation_settings, "resolve_installation_settings", resolve)

    async def evaluate(rows, pages, config, **kwargs):
        if scenario == "outage":
            raise RuntimeError("secret provider error")
        if scenario in {
            "stale",
            "cancel",
            "stale_parent",
            "stale_proposed_parent",
            "missing_parent",
        }:
            async with setup_database() as other:
                if scenario == "stale":
                    changed = await other.get(ExtractedRequirement, row_id)
                    changed.text = "Human edited the obligation."
                elif scenario in {"stale_parent", "stale_proposed_parent", "missing_parent"}:
                    changed = await other.get(ExtractedRequirement, parent.id)
                    if scenario == "missing_parent":
                        changed.status = "rejected"
                    else:
                        changed.text = "Human changed the parent scope."
                        changed.quality_auto_editable = False
                else:
                    changed = await other.get(RequirementQualityRun, run_id)
                    changed.status = "cancelled"
                await other.commit()
        if scenario == "settings":
            runtime.jev_settings_revision = 2
        return {
            "status": "completed",
            "findings": [
                {
                    "requirement_id": str(row_id),
                    "kind": "classification",
                    "source_page": 1,
                    "source_excerpt": row.text,
                    "before": {"requirement_type": "recommended"},
                    "after": {
                        "requirement_type": "mandatory",
                        **(
                            {"parent_id": str(parent.id)}
                            if scenario in {"stale_proposed_parent", "new_parent"}
                            else {}
                        ),
                    },
                    "answers": {},
                    "auto_eligible": scenario != "uncertain",
                }
            ],
            "coverage": {"checked": 1, "total": 1},
            "usage": {},
            "warnings": [],
        }

    monkeypatch.setattr(requirement_quality, "evaluate_requirements", evaluate)
    await check_quality(run_id, setup_database)
    # A duplicate delivery must neither repeat application nor duplicate findings.
    await check_quality(run_id, setup_database)
    await db_session.refresh(run)
    await db_session.refresh(row)
    findings = list(
        (
            await db_session.scalars(
                select(RequirementQualityFinding).where(RequirementQualityFinding.run_id == run_id)
            )
        ).all()
    )
    assert run.status == status
    assert row.requirement_type == ("mandatory" if applied else "recommended")
    assert row.original_text == "Operator must keep records."
    assert len(findings) == (0 if scenario in {"cancel", "settings", "outage"} else 1)
    assert any(f.applied for f in findings) == applied
    if applied:
        assert row.needs_review and row.status == "pending"
    if scenario in {
        "uncertain",
        "stale_parent",
        "stale_proposed_parent",
        "missing_parent",
        "new_parent",
    }:
        assert row.needs_review and row.status == "pending"
    if parent:
        await db_session.refresh(parent)
        assert row.parent_id == (
            parent.id if scenario in {"stale_parent", "missing_parent"} else None
        )
        if scenario in {"stale_parent", "stale_proposed_parent"}:
            assert parent.text == "Human changed the parent scope."
    if scenario == "stale":
        assert row.text == "Human edited the obligation."
    if scenario == "outage":
        assert "secret" not in str(run.warnings)


async def test_quality_api_is_document_scoped_and_requires_jev_confirmation(
    client, db_session, default_jurisdiction, tmp_path, monkeypatch
):
    from app.models import Organization
    from app.services import installation_settings
    from app.services.auth import create_access_token

    source = tmp_path / "source.pdf"
    source.write_bytes(b"quality API source")
    outsider_org = Organization(name="Other organisation", code="quality-other")
    db_session.add(outsider_org)
    user = User(
        email="quality-api@example.com",
        password_hash="fixture",
        full_name="Quality Manager",
        role="manager",
    )
    db_session.add(user)
    await db_session.flush()
    doc = Document(
        filename="source.pdf",
        file_path=str(source),
        document_type="standard",
        jurisdiction_id=default_jurisdiction.id,
        uploaded_by=user.id,
        status="extracted",
    )
    other = Document(
        filename="other.pdf",
        file_path=str(source),
        document_type="standard",
        jurisdiction_id=default_jurisdiction.id,
        uploaded_by=user.id,
        organization_id=outsider_org.id,
    )
    db_session.add_all([doc, other])
    await db_session.flush()
    extraction = ExtractionRun(
        document_id=doc.id, status="completed", ai_provider="local", ai_model="local"
    )
    db_session.add(extraction)
    await db_session.flush()
    doc.current_extraction_id = extraction.id
    run = RequirementQualityRun(
        document_id=doc.id,
        extraction_run_id=extraction.id,
        requested_by=user.id,
        mode="recheck",
        model="jev-1.13.0",
        settings_revision=1,
        source_sha256=source_sha(source),
        snapshot={},
    )
    db_session.add(run)
    await db_session.commit()
    headers = {
        "Authorization": f"Bearer {create_access_token({'sub': str(user.id), 'role': user.role})}"
    }

    async def resolve(db):
        return SimpleNamespace(
            jev_enabled=True,
            jev_model="jev-1.13.0",
            typesafe_api_key="fixture",
            jev_settings_revision=1,
        )

    monkeypatch.setattr(installation_settings, "resolve_installation_settings", resolve)
    base = f"/api/v1/documents/{doc.id}/quality-runs"
    denied = await client.post(base, headers=headers, json={"jev_settings_revision": 1})
    assert denied.status_code == 400
    stale = await client.post(
        base, headers=headers, json={"allow_external_ai": True, "jev_settings_revision": 0}
    )
    assert stale.status_code == 409
    crossed = await client.get(
        f"/api/v1/documents/{other.id}/quality-runs/{run.id}", headers=headers
    )
    assert crossed.status_code == 404
    listed = await client.get(base, headers=headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [str(run.id)]
    cancelled = await client.post(f"{base}/{run.id}/cancel", headers=headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"


async def test_recheck_selected_approved_version_preserves_approved_requirements(
    client, db_session, setup_database, default_jurisdiction, tmp_path, monkeypatch
):
    from app.api import requirement_quality as quality_api
    from app.models import Requirement, RequirementSetVersion
    from app.services import installation_settings, requirement_quality
    from app.services.auth import create_access_token

    source = tmp_path / "source.pdf"
    source.write_bytes(b"approved source")
    user = User(
        email="quality-version@example.com",
        password_hash="fixture",
        full_name="Quality Manager",
        role="manager",
    )
    db_session.add(user)
    await db_session.flush()
    document = Document(
        filename="source.pdf",
        file_path=str(source),
        document_type="standard",
        jurisdiction_id=default_jurisdiction.id,
        uploaded_by=user.id,
        status="approved",
    )
    db_session.add(document)
    await db_session.flush()
    version = RequirementSetVersion(
        document_id=document.id,
        version_number=1,
        status="approved",
        is_current=False,
        created_by=user.id,
    )
    db_session.add(version)
    await db_session.flush()
    requirement = Requirement(
        document_id=document.id,
        requirement_set_version_id=version.id,
        jurisdiction_id=default_jurisdiction.id,
        reference_id="1",
        text="Reviewed wording",
        requirement_type="recommended",
    )
    db_session.add(requirement)
    await db_session.commit()

    async def resolve(db):
        return SimpleNamespace(
            jev_enabled=True,
            jev_model="jev-1.13.0",
            typesafe_api_key="fixture",
            jev_settings_revision=1,
        )

    async def defer(db, run_id):
        return True

    monkeypatch.setattr(installation_settings, "resolve_installation_settings", resolve)
    monkeypatch.setattr(quality_api, "dispatch_quality_run", defer)
    token = create_access_token({"sub": str(user.id), "role": user.role})
    response = await client.post(
        f"/api/v1/documents/{document.id}/quality-runs",
        headers={"Authorization": f"Bearer {token}"},
        json={"version_id": str(version.id), "allow_external_ai": True, "jev_settings_revision": 1},
    )
    assert response.status_code == 200
    assert response.json()["version_id"] == str(version.id)
    run_id = uuid.UUID(response.json()["id"])
    async with setup_database() as db:
        run = await db.get(RequirementQualityRun, run_id)
        run.snapshot = {**run.snapshot, "pages": [{"page_number": 1, "text": "Source wording"}]}
        await db.commit()

    async def evaluate(rows, pages, config, **kwargs):
        assert rows[0]["id"] == str(requirement.id)
        return {
            "status": "completed",
            "findings": [
                {
                    "requirement_id": str(requirement.id),
                    "kind": "accuracy",
                    "source_page": 1,
                    "source_excerpt": "Source wording",
                    "after": {"text": "Source wording", "requirement_type": "mandatory"},
                    "auto_eligible": True,
                }
            ],
            "coverage": {"checked": 1},
            "usage": {},
            "warnings": [],
        }

    monkeypatch.setattr(requirement_quality, "evaluate_requirements", evaluate)
    await check_quality(run_id, setup_database)
    await db_session.refresh(requirement)
    await db_session.refresh(version)
    assert requirement.text == "Reviewed wording" and requirement.requirement_type == "recommended"
    assert version.status == "approved"
    detail = await client.get(
        f"/api/v1/documents/{document.id}/quality-runs/{run_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail.json()["findings"][0]["applied"] is False


@pytest.mark.parametrize(
    "unavailable", ["missing_key", "disabled", "stale_revision", "unconfirmed"]
)
async def test_optional_jev_configuration_never_blocks_local_baseline_except_consent(
    unavailable, client, db_session, default_jurisdiction, tmp_path, monkeypatch
):
    from app.config import settings
    from app.services import extraction_jobs, installation_settings
    from app.services.auth import create_access_token

    monkeypatch.setattr(settings, "pdf_structure_engine", "native")
    source = tmp_path / "source.pdf"
    source.write_bytes(b"source available for baseline dispatch")
    user = User(
        email="quality-fallback@example.com",
        password_hash="fixture",
        full_name="Quality Manager",
        role="manager",
    )
    db_session.add(user)
    await db_session.flush()
    document = Document(
        filename="source.pdf",
        file_path=str(source),
        document_type="standard",
        jurisdiction_id=default_jurisdiction.id,
        uploaded_by=user.id,
        status="uploaded",
    )
    db_session.add(document)
    await db_session.commit()

    async def resolve(db):
        return SimpleNamespace(
            ai_provider="none",
            ai_model="local",
            jev_enabled=unavailable != "disabled",
            jev_model="jev-1.13.0",
            typesafe_api_key="" if unavailable == "missing_key" else "fixture",
            jev_settings_revision=2 if unavailable == "stale_revision" else 1,
        )

    dispatched = []

    async def dispatch(db, run_id):
        dispatched.append(run_id)
        return True

    monkeypatch.setattr(installation_settings, "resolve_installation_settings", resolve)
    monkeypatch.setattr(extraction_jobs, "dispatch_run", dispatch)
    token = create_access_token({"sub": str(user.id), "role": user.role})
    response = await client.post(
        f"/api/v1/documents/{document.id}/extract",
        headers={"Authorization": f"Bearer {token}"},
        params={
            "use_jev": True,
            "allow_external_ai": unavailable != "unconfirmed",
            "jev_settings_revision": 1,
        },
    )
    await db_session.refresh(document)
    if unavailable == "unconfirmed":
        assert response.status_code == 400
        assert document.status == "uploaded" and not dispatched
        return
    assert response.status_code == 200
    assert document.status == "pending_extraction"
    assert dispatched == [document.current_extraction_id]
    quality = await db_session.scalar(
        select(RequirementQualityRun).where(RequirementQualityRun.document_id == document.id)
    )
    assert quality.status == "skipped" and quality.warnings
    assert quality.extraction_run_id == document.current_extraction_id


@pytest.mark.parametrize("cancelled", [False, True])
async def test_completed_baseline_queues_original_source_pages_without_reviving_cancelled_check(
    cancelled, db_session, default_jurisdiction, monkeypatch
):
    from app.services import quality_jobs

    user = User(
        email="quality-queue@example.com",
        password_hash="fixture",
        full_name="Quality Manager",
        role="manager",
    )
    db_session.add(user)
    await db_session.flush()
    doc = Document(
        filename="source.pdf",
        file_path="source.pdf",
        document_type="standard",
        jurisdiction_id=default_jurisdiction.id,
        uploaded_by=user.id,
        status="extracted",
    )
    db_session.add(doc)
    await db_session.flush()
    extraction = ExtractionRun(
        document_id=doc.id, status="completed", ai_provider="local", ai_model="local"
    )
    db_session.add(extraction)
    await db_session.flush()
    doc.current_extraction_id = extraction.id
    row = ExtractedRequirement(
        document_id=doc.id,
        extraction_run_id=extraction.id,
        reference_id="1",
        text="Baseline wording",
        original_text="Baseline wording",
        page_number=1,
        quality_auto_editable=True,
    )
    quality = RequirementQualityRun(
        document_id=doc.id,
        extraction_run_id=extraction.id,
        requested_by=user.id,
        mode="import",
        status="cancelled" if cancelled else "waiting_extraction",
        model="jev-1.13.0",
        settings_revision=1,
        source_sha256="fixture",
        snapshot={},
    )
    db_session.add_all([row, quality])
    await db_session.commit()
    dispatched = []

    async def dispatch(db, run_id):
        dispatched.append(run_id)
        return True

    monkeypatch.setattr(quality_jobs, "dispatch_quality_run", dispatch)
    pages = [{"page_number": 1, "text": "Original source wording and exception."}]
    await quality_jobs.complete_import_quality(db_session, extraction, pages)
    await db_session.refresh(quality)
    assert quality.status == ("cancelled" if cancelled else "pending")
    assert dispatched == ([] if cancelled else [quality.id])
    if not cancelled:
        assert quality.snapshot["pages"] == pages
        assert quality.snapshot["rows"][0]["text"] == "Baseline wording"
