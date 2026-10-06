from datetime import datetime, timezone

from app.models.document import Document
from app.models.extraction import ExtractionRun
from app.models.requirement import ExtractedRequirement
from app.models.user import User
from app.services.auth import create_access_token, hash_password


async def _create_manager(db_session, email: str = "manager.review@test.com"):
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


async def test_list_extractions_filters_needs_review(client, db_session, default_jurisdiction):
    manager, headers = await _create_manager(db_session, "manager.filter@test.com")

    document = Document(
        jurisdiction_id=default_jurisdiction.id,
        filename="test.pdf",
        document_type="standard",
        status="extracted",
        file_path="/tmp/test.pdf",
        uploaded_by=manager.id,
    )
    db_session.add(document)
    await db_session.flush()

    run = ExtractionRun(
        document_id=document.id,
        status="completed",
        current_page=4, total_pages=4,
        ai_provider="openai",
        ai_model="gpt-5-mini",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    await db_session.flush()

    flagged = ExtractedRequirement(
        document_id=document.id,
        extraction_run_id=run.id,
        reference_id="3.2.1",
        text="The system shall retain records.",
        original_text="The system shall retain records.",
        requirement_type="mandatory",
        page_number=3,
        confidence_score=0.6,
        needs_review=True,
        review_reason="anchor_mismatch",
        parser_strategy="ai_chunked",
        sort_order=1,
    )
    clean = ExtractedRequirement(
        document_id=document.id,
        extraction_run_id=run.id,
        reference_id="3.2.2",
        text="The system shall log access.",
        original_text="The system shall log access.",
        requirement_type="mandatory",
        page_number=3,
        confidence_score=0.9,
        needs_review=False,
        parser_strategy="rule_based",
        sort_order=2,
    )
    db_session.add_all([flagged, clean])
    await db_session.commit()

    response = await client.get(
        f"/api/v1/documents/{document.id}/extractions?run_id={run.id}&needs_review=true",
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["reference_id"] == "3.2.1"


async def test_feedback_accept_clears_needs_review(client, db_session, default_jurisdiction):
    manager, headers = await _create_manager(db_session, "manager.feedback@test.com")

    document = Document(
        jurisdiction_id=default_jurisdiction.id,
        filename="test.pdf",
        document_type="standard",
        status="extracted",
        file_path="/tmp/test.pdf",
        uploaded_by=manager.id,
    )
    db_session.add(document)
    await db_session.flush()

    run = ExtractionRun(
        document_id=document.id,
        status="completed",
        current_page=4, total_pages=4,
        ai_provider="openai",
        ai_model="gpt-5-mini",
    )
    db_session.add(run)
    await db_session.flush()
    document.current_extraction_id = run.id

    extraction = ExtractedRequirement(
        document_id=document.id,
        extraction_run_id=run.id,
        reference_id="3.2.1",
        text="The system shall retain records.",
        original_text="The system shall retain records.",
        requirement_type="mandatory",
        page_number=3,
        confidence_score=0.6,
        needs_review=True,
        review_reason="anchor_mismatch",
        parser_strategy="ai_chunked",
        sort_order=1,
    )
    db_session.add(extraction)
    await db_session.commit()
    await db_session.refresh(extraction)

    feedback_response = await client.post(
        f"/api/v1/documents/{document.id}/extractions/{extraction.id}/feedback",
        headers=headers,
        json={"action": "accept"},
    )
    assert feedback_response.status_code == 200
    assert feedback_response.json()["action"] == "accept"

    filtered = await client.get(
        f"/api/v1/documents/{document.id}/extractions?run_id={run.id}&needs_review=true",
        headers=headers,
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 0


async def test_submit_blocked_when_unresolved_review_items(
    client, db_session, default_jurisdiction
):
    manager, headers = await _create_manager(db_session, "manager.submit@test.com")

    document = Document(
        jurisdiction_id=default_jurisdiction.id,
        filename="test.pdf",
        document_type="standard",
        status="extracted",
        file_path="/tmp/test.pdf",
        uploaded_by=manager.id,
    )
    db_session.add(document)
    await db_session.flush()

    run = ExtractionRun(
        document_id=document.id,
        status="completed",
        current_page=4, total_pages=4,
        ai_provider="openai",
        ai_model="gpt-5-mini",
    )
    db_session.add(run)
    await db_session.flush()

    document.current_extraction_id = run.id

    extraction = ExtractedRequirement(
        document_id=document.id,
        extraction_run_id=run.id,
        reference_id="3.2.1",
        text="The system shall retain records.",
        original_text="The system shall retain records.",
        requirement_type="mandatory",
        page_number=3,
        confidence_score=0.6,
        needs_review=True,
        review_reason="anchor_mismatch",
        parser_strategy="ai_chunked",
        sort_order=1,
    )
    db_session.add(extraction)
    await db_session.commit()

    submit_response = await client.post(
        f"/api/v1/documents/{document.id}/submit",
        headers=headers,
    )
    assert submit_response.status_code == 400
    assert "Resolve all flagged extraction review items" in submit_response.json()["detail"]
