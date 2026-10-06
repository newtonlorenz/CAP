"""Edge case tests for API endpoints."""

import uuid
from datetime import datetime, timezone

import pytest

from app.models import Document, Requirement, User
from app.models.extraction import ExtractionRun
from app.models.requirement import ExtractedRequirement
from app.services.auth import create_access_token, hash_password


@pytest.fixture
async def test_user(db_session):
    user = User(
        email="test@example.com",
        password_hash=hash_password("testpass"),
        full_name="Test User",
        role="admin",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(test_user):
    token = create_access_token({"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {token}"}


async def test_requirement_not_found(client, auth_headers):
    """Test getting a non-existent requirement."""
    fake_id = uuid.uuid4()
    response = await client.get(f"/api/v1/requirements/{fake_id}", headers=auth_headers)
    assert response.status_code == 404


async def test_invalid_uuid_format(client, auth_headers):
    """Test with invalid UUID format."""
    response = await client.get("/api/v1/requirements/not-a-uuid", headers=auth_headers)
    assert response.status_code == 422


async def test_expired_token(client):
    """Test with an invalid/malformed token."""
    headers = {"Authorization": "Bearer invalid-token"}
    response = await client.get("/api/v1/requirements", headers=headers)
    assert response.status_code == 401


async def test_missing_authorization_header(client):
    """Test without authorization header."""
    response = await client.get("/api/v1/requirements")
    assert response.status_code == 401


async def test_empty_list_response(client, auth_headers):
    """Test that empty lists return proper structure."""
    response = await client.get("/api/v1/requirements", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["items"] == []
    assert data["total"] == 0


async def test_pagination_defaults(
    client, auth_headers, db_session, test_user, default_jurisdiction
):
    """Test that pagination uses correct defaults."""
    # Create 25 requirements
    doc_id = uuid.uuid4()
    for i in range(25):
        req = Requirement(
            jurisdiction_id=default_jurisdiction.id,
            document_id=doc_id,
            reference_id=f"REQ-{i:03d}",
            text=f"Requirement {i}",
            requirement_type="mandatory",
            active=True,
            version=1,
            sort_order=i,
        )
        db_session.add(req)
    await db_session.commit()

    # Default limit is 20
    response = await client.get("/api/v1/requirements", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) <= 20
    assert data["total"] == 25


async def test_pagination_with_skip(
    client, auth_headers, db_session, test_user, default_jurisdiction
):
    """Test pagination with skip parameter."""
    doc_id = uuid.uuid4()
    for i in range(10):
        req = Requirement(
            jurisdiction_id=default_jurisdiction.id,
            document_id=doc_id,
            reference_id=f"REQ-{i:03d}",
            text=f"Requirement {i}",
            requirement_type="mandatory",
            active=True,
            version=1,
            sort_order=i,
        )
        db_session.add(req)
    await db_session.commit()

    response = await client.get("/api/v1/requirements?skip=5&limit=10", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    # Should return remaining 5 items
    assert data["total"] == 10


async def test_status_change_creates_history(
    client, auth_headers, db_session, test_user, default_jurisdiction
):
    """Test that status changes create history entries."""
    doc_id = uuid.uuid4()
    req = Requirement(
        jurisdiction_id=default_jurisdiction.id,
        document_id=doc_id,
        reference_id="REQ-001",
        text="Test requirement",
        requirement_type="mandatory",
        active=True,
        version=1,
        sort_order=0,
    )
    db_session.add(req)
    await db_session.commit()
    await db_session.refresh(req)

    # Change status multiple times
    statuses = ["in_progress", "blocked", "in_progress", "evidenced"]
    for status in statuses:
        response = await client.put(
            f"/api/v1/requirements/{req.id}/status",
            headers=auth_headers,
            json={"status": status, "comment": f"Changing to {status}"},
        )
        assert response.status_code == 200

    # Get requirement and check history
    response = await client.get(f"/api/v1/requirements/{req.id}", headers=auth_headers)
    data = response.json()
    assert len(data["status_history"]) == 4
    # Verify all statuses are present in history
    history_statuses = [h["status"] for h in data["status_history"]]
    for status in statuses:
        assert status in history_statuses


async def test_document_status_workflow(
    client, auth_headers, db_session, test_user, default_jurisdiction
):
    """Test document status transitions."""
    # Document must be in 'extracted' status before it can be submitted
    doc = Document(
        jurisdiction_id=default_jurisdiction.id,
        filename="test.pdf",
        document_type="annex_b",
        status="extracted",  # Documents must be extracted before submission
        file_path="/uploads/test.pdf",
        uploaded_by=test_user.id,
        name="Test Document",
        testing_frequency="quarterly",
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)

    run = ExtractionRun(
        document_id=doc.id,
        status="completed",
        total_pages=1,
        current_page=1,
        requirements_found=1,
        ai_provider="none",
        ai_model="none",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    doc.current_extraction_id = run.id
    await db_session.commit()

    extracted = ExtractedRequirement(
        document_id=doc.id,
        extraction_run_id=run.id,
        reference_id="REQ-001",
        title="Test Requirement",
        text="Test requirement text",
        original_text="Test requirement text",
        requirement_type="mandatory",
        parent_id=None,
        page_number=1,
        confidence_score=0.99,
        status="accepted",
        sort_order=0,
    )
    db_session.add(extracted)
    await db_session.commit()

    # Submit for approval
    response = await client.post(f"/api/v1/documents/{doc.id}/submit", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending_approval"

    # Approve
    response = await client.post(
        f"/api/v1/documents/{doc.id}/approve",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"


async def test_inactive_user_cannot_authenticate(client, db_session):
    """Test that inactive users cannot get tokens."""
    user = User(
        email="inactive@example.com",
        password_hash=hash_password("testpass"),
        full_name="Inactive User",
        role="contributor",
        active=False,
    )
    db_session.add(user)
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "inactive@example.com", "password": "testpass"},
    )
    assert response.status_code == 401


async def test_search_case_insensitive(
    client, auth_headers, db_session, test_user, default_jurisdiction
):
    """Test that search is case-insensitive."""
    doc_id = uuid.uuid4()
    req = Requirement(
        jurisdiction_id=default_jurisdiction.id,
        document_id=doc_id,
        reference_id="REQ-001",
        text="Security controls must be implemented",
        requirement_type="mandatory",
        active=True,
        version=1,
        sort_order=0,
    )
    db_session.add(req)
    await db_session.commit()

    # Search with different cases
    for search_term in ["security", "SECURITY", "Security", "sEcUrItY"]:
        response = await client.get(
            f"/api/v1/requirements?search={search_term}", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1, f"Failed for search term: {search_term}"
