from datetime import datetime, timezone

from app.models.document import Document
from app.models.extraction import ExtractionRun, ExtractionRunDiagnostic
from app.models.user import User
from app.services.auth import create_access_token, hash_password


async def _create_manager(db_session, email: str = "manager.diagnostics@test.com"):
    user = User(
        email=email,
        password_hash=hash_password("pass"),
        full_name="Manager",
        role="manager",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    token = create_access_token({"sub": str(user.id), "role": user.role})
    return user, {"Authorization": f"Bearer {token}"}


async def test_get_extraction_diagnostics(client, db_session, default_jurisdiction):
    manager, headers = await _create_manager(db_session, "manager.diag.success@test.com")

    document = Document(
        jurisdiction_id=default_jurisdiction.id,
        filename="diag.pdf",
        document_type="standard",
        status="extracted",
        file_path="/tmp/diag.pdf",
        uploaded_by=manager.id,
    )
    db_session.add(document)
    await db_session.flush()

    run = ExtractionRun(
        document_id=document.id,
        status="completed",
        ai_provider="openai",
        ai_model="gpt-4o",
        parseability_score=0.71,
        fallback_trigger_reason="Low parseability ratio 0.22",
        strategy_counts={"rule": 21, "table": 8, "vision": 3},
        diagnostics_available=True,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    await db_session.flush()

    diagnostics = ExtractionRunDiagnostic(
        extraction_run_id=run.id,
        document_id=document.id,
        parseability_score=0.71,
        fallback_trigger_reason="Low parseability ratio 0.22",
        strategy_counts={"rule": 21, "table": 8, "vision": 3},
        decision_payload={"low_parseability_pages": [8, 26], "ocr_applied": False},
        page_metrics=[{"page_number": 8, "parseability_score": 0.42}],
        canonical_blocks=[{"page_number": 8, "line_count": 44}],
    )
    db_session.add(diagnostics)
    await db_session.commit()

    response = await client.get(
        f"/api/v1/documents/{document.id}/extraction-runs/{run.id}/diagnostics",
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["document_id"] == str(document.id)
    assert payload["extraction_run_id"] == str(run.id)
    assert payload["parseability_score"] == 0.71
    assert payload["strategy_counts"]["vision"] == 3
    assert payload["page_metrics"][0]["page_number"] == 8


async def test_get_extraction_diagnostics_not_found(client, db_session, default_jurisdiction):
    manager, headers = await _create_manager(db_session, "manager.diag.missing@test.com")

    document = Document(
        jurisdiction_id=default_jurisdiction.id,
        filename="diag-missing.pdf",
        document_type="standard",
        status="extracted",
        file_path="/tmp/diag-missing.pdf",
        uploaded_by=manager.id,
    )
    db_session.add(document)
    await db_session.flush()

    run = ExtractionRun(
        document_id=document.id,
        status="completed",
        ai_provider="openai",
        ai_model="gpt-4o",
    )
    db_session.add(run)
    await db_session.commit()

    response = await client.get(
        f"/api/v1/documents/{document.id}/extraction-runs/{run.id}/diagnostics",
        headers=headers,
    )
    assert response.status_code == 404
