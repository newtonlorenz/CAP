import io

from app.models.user import User
from app.services.auth import create_access_token, hash_password


async def test_upload_document(client, db_session, default_jurisdiction):
    user = User(
        email="user@test.com",
        password_hash=hash_password("pass"),
        full_name="Test User",
        role="manager",
    )
    db_session.add(user)
    await db_session.commit()

    token = create_access_token({"sub": str(user.id), "role": "manager"})
    pdf_content = b"%PDF-1.4 fake pdf content"
    response = await client.post(
        "/api/v1/documents",
        files={"file": ("test.pdf", io.BytesIO(pdf_content), "application/pdf")},
        data={
            "document_type": "standard",
            "jurisdiction_id": str(default_jurisdiction.id),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "uploaded"
    assert response.json()["filename"] == "test.pdf"


async def test_contributor_cannot_upload_document(client, db_session, default_jurisdiction):
    user = User(
        email="contributor@test.com",
        password_hash=hash_password("pass"),
        full_name="Contributor",
        role="contributor",
    )
    db_session.add(user)
    await db_session.commit()

    token = create_access_token({"sub": str(user.id), "role": "contributor"})
    pdf_content = b"%PDF-1.4 fake pdf content"
    response = await client.post(
        "/api/v1/documents",
        files={"file": ("test.pdf", io.BytesIO(pdf_content), "application/pdf")},
        data={
            "document_type": "standard",
            "jurisdiction_id": str(default_jurisdiction.id),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


async def test_upload_non_pdf_rejected(client, db_session, default_jurisdiction):
    user = User(
        email="user@test.com",
        password_hash=hash_password("pass"),
        full_name="Test User",
        role="manager",
    )
    db_session.add(user)
    await db_session.commit()

    token = create_access_token({"sub": str(user.id), "role": "manager"})
    response = await client.post(
        "/api/v1/documents",
        files={"file": ("test.txt", io.BytesIO(b"not a pdf"), "text/plain")},
        data={
            "document_type": "standard",
            "jurisdiction_id": str(default_jurisdiction.id),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


async def test_list_documents(client, db_session):
    user = User(
        email="user@test.com",
        password_hash=hash_password("pass"),
        full_name="Test User",
        role="contributor",
    )
    db_session.add(user)
    await db_session.commit()

    token = create_access_token({"sub": str(user.id), "role": "contributor"})
    response = await client.get(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert "items" in response.json()
    assert "total" in response.json()


async def test_list_documents_unauthorized(client):
    response = await client.get("/api/v1/documents")
    assert response.status_code == 401
