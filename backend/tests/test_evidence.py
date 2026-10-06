import uuid

import pytest

from app.models import EvidenceLink, EvidenceNote, Requirement, User
from app.services.auth import create_access_token, hash_password


@pytest.fixture
async def test_user(db_session):
    user = User(
        email="test@example.com",
        password_hash=hash_password("testpass"),
        full_name="Test User",
        role="contributor",
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
        text="Test requirement",
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


async def test_add_note(client, test_requirement, auth_headers):
    response = await client.post(
        f"/api/v1/requirements/{test_requirement.id}/notes",
        headers=auth_headers,
        json={"note_text": "This is a test note"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["note_text"] == "This is a test note"
    assert "id" in data
    assert "created_at" in data


async def test_add_link(client, test_requirement, auth_headers):
    response = await client.post(
        f"/api/v1/requirements/{test_requirement.id}/links",
        headers=auth_headers,
        json={"url": "https://example.com/docs", "label": "Reference Documentation"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["url"] == "https://example.com/docs"
    assert data["label"] == "Reference Documentation"


async def test_get_evidence(client, test_requirement, auth_headers, db_session):
    # Add some evidence first
    note = EvidenceNote(
        requirement_id=test_requirement.id,
        note_text="Test note",
        created_by=uuid.uuid4(),
    )
    link = EvidenceLink(
        requirement_id=test_requirement.id,
        url="https://example.com",
        label="Test Link",
        added_by=uuid.uuid4(),
    )
    db_session.add(note)
    db_session.add(link)
    await db_session.commit()

    response = await client.get(
        f"/api/v1/requirements/{test_requirement.id}/evidence",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "notes" in data
    assert "links" in data
    assert "files" in data
    assert len(data["notes"]) == 1
    assert len(data["links"]) == 1


async def test_delete_note(client, test_requirement, auth_headers, db_session, test_user):
    # Add a note first
    note = EvidenceNote(
        requirement_id=test_requirement.id,
        note_text="Note to delete",
        created_by=test_user.id,
    )
    db_session.add(note)
    await db_session.commit()
    await db_session.refresh(note)

    response = await client.delete(
        f"/api/v1/requirements/{test_requirement.id}/notes/{note.id}",
        headers=auth_headers,
    )
    assert response.status_code == 204


async def test_add_note_invalid_requirement(client, auth_headers):
    fake_id = uuid.uuid4()
    response = await client.post(
        f"/api/v1/requirements/{fake_id}/notes",
        headers=auth_headers,
        json={"note_text": "This should fail"},
    )
    assert response.status_code == 404
