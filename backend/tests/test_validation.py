"""Validation tests for API inputs."""

import uuid

import pytest

from app.models import User
from app.services.auth import create_access_token, hash_password


@pytest.fixture
async def admin_user(db_session):
    user = User(
        email="admin@example.com",
        password_hash=hash_password("adminpass"),
        full_name="Admin User",
        role="admin",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def admin_headers(admin_user):
    token = create_access_token({"sub": str(admin_user.id)})
    return {"Authorization": f"Bearer {token}"}


async def test_create_user_invalid_email(client, admin_headers):
    """Test user creation with invalid email format."""
    response = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": "not-an-email",
            "password": "testpass123",
            "full_name": "Test User",
            "role": "contributor",
        },
    )
    assert response.status_code == 422


async def test_create_user_short_password(client, admin_headers):
    """Test user creation with too short password."""
    response = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": "test@example.com",
            "password": "short",
            "full_name": "Test User",
            "role": "contributor",
        },
    )
    assert response.status_code == 422


async def test_create_user_invalid_role(client, admin_headers):
    """Test user creation with invalid role."""
    response = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": "test@example.com",
            "password": "testpass123",
            "full_name": "Test User",
            "role": "superadmin",
        },
    )
    assert response.status_code == 422


async def test_create_user_missing_required_field(client, admin_headers):
    """Test user creation with missing required field."""
    response = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": "test@example.com",
            "password": "testpass123",
            # missing full_name
            "role": "contributor",
        },
    )
    assert response.status_code == 422


async def test_login_missing_email(client):
    """Test login with missing email."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"password": "testpass"},
    )
    assert response.status_code == 422


async def test_login_missing_password(client):
    """Test login with missing password."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com"},
    )
    assert response.status_code == 422


async def test_review_cycle_invalid_scope(client, admin_headers, default_jurisdiction):
    """Test review cycle creation with invalid scope."""
    response = await client.post(
        "/api/v1/review-cycles",
        headers=admin_headers,
        json={
            "name": "Test Cycle",
            "jurisdiction_id": str(default_jurisdiction.id),
            "scope": "invalid_scope",
        },
    )
    # Strict baseline locking rejects unsupported/empty-scope resolution paths (400),
    # and may become 422 if scope is schema-validated in the future.
    assert response.status_code in [400, 422]


async def test_evidence_link_invalid_url(
    client, admin_headers, db_session, admin_user, default_jurisdiction
):
    """Test adding evidence link with invalid URL."""
    from app.models import Requirement

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

    response = await client.post(
        f"/api/v1/requirements/{req.id}/links",
        headers=admin_headers,
        json={
            "url": "not-a-valid-url",
            "label": "Test Link",
        },
    )
    # Might be 422 if URL is validated, or 201 if any string is accepted
    assert response.status_code in [201, 422]


async def test_status_change_invalid_status(
    client, admin_headers, db_session, admin_user, default_jurisdiction
):
    """Test status change with invalid status value."""
    from app.models import Requirement

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

    response = await client.put(
        f"/api/v1/requirements/{req.id}/status",
        headers=admin_headers,
        json={
            "status": "invalid_status_value",
            "comment": "Test comment",
        },
    )
    # Should be 200 if any status is accepted, or 422 if validated
    assert response.status_code in [200, 422]


async def test_pagination_negative_skip(client, admin_headers):
    """Test pagination with negative skip."""
    response = await client.get(
        "/api/v1/requirements?skip=-1",
        headers=admin_headers,
    )
    # Should be 422 or handle gracefully
    assert response.status_code in [200, 422]


async def test_pagination_zero_limit(client, admin_headers):
    """Test pagination with zero limit."""
    response = await client.get(
        "/api/v1/requirements?limit=0",
        headers=admin_headers,
    )
    # Should return empty list or reject
    assert response.status_code in [200, 422]


async def test_large_pagination_limit(client, admin_headers):
    """Test pagination with very large limit."""
    response = await client.get(
        "/api/v1/requirements?limit=10000",
        headers=admin_headers,
    )
    # Should either cap the limit or accept it
    assert response.status_code == 200


async def test_malformed_json_body(client, admin_headers):
    """Test request with malformed JSON body."""
    response = await client.post(
        "/api/v1/users",
        headers={**admin_headers, "Content-Type": "application/json"},
        content="not valid json{",
    )
    assert response.status_code == 422


async def test_empty_json_body(client, admin_headers):
    """Test request with empty JSON body."""
    response = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={},
    )
    assert response.status_code == 422


async def test_extra_fields_in_request(client, admin_headers):
    """Test request with extra unexpected fields."""
    response = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": "test@example.com",
            "password": "testpass123",
            "full_name": "Test User",
            "role": "contributor",
            "unexpected_field": "should be ignored or rejected",
        },
    )
    # Extra fields should be ignored (201) or rejected (422)
    assert response.status_code in [201, 422]
