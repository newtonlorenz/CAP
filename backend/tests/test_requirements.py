import uuid

import pytest

from app.models import Requirement, User
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
async def test_requirement(db_session, test_user, default_jurisdiction):
    doc_id = uuid.uuid4()
    req = Requirement(
        jurisdiction_id=default_jurisdiction.id,
        document_id=doc_id,
        reference_id="REQ-001",
        text="The system shall implement security controls",
        requirement_type="mandatory",
        active=True,
        version=1,
        sort_order=0,
    )
    db_session.add(req)
    await db_session.commit()
    await db_session.refresh(req)
    return req


@pytest.fixture
def auth_headers(test_user):
    token = create_access_token({"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {token}"}


async def test_list_requirements(client, test_requirement, auth_headers):
    response = await client.get("/api/v1/requirements", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert len(data["items"]) == 1
    assert data["items"][0]["reference_id"] == "REQ-001"


async def test_list_requirements_unauthorized(client):
    response = await client.get("/api/v1/requirements")
    assert response.status_code == 401


async def test_get_requirement_detail(client, test_requirement, auth_headers):
    response = await client.get(f"/api/v1/requirements/{test_requirement.id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["reference_id"] == "REQ-001"
    assert data["text"] == "The system shall implement security controls"
    assert "status_history" in data
    assert "priority" not in data
    assert "review_frequency" not in data


async def test_update_requirement_status(client, test_requirement, auth_headers):
    response = await client.put(
        f"/api/v1/requirements/{test_requirement.id}/status",
        headers=auth_headers,
        json={"status": "in_progress", "comment": "Starting work on this requirement"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["current_status"] == "in_progress"


async def test_update_status_requires_comment(client, test_requirement, auth_headers):
    response = await client.put(
        f"/api/v1/requirements/{test_requirement.id}/status",
        headers=auth_headers,
        json={"status": "in_progress", "comment": ""},
    )
    assert response.status_code == 422


async def test_search_requirements(client, test_requirement, auth_headers):
    response = await client.get("/api/v1/requirements?search=security", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1

    response = await client.get("/api/v1/requirements?search=nonexistent", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 0
