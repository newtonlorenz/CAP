import json

import pytest

from app.models.document import Document
from app.models.extraction import ExtractionRun
from app.models.user import User
from app.services.auth import create_access_token, hash_password


@pytest.mark.asyncio
async def test_extraction_events_stream(client, db_session, monkeypatch, default_jurisdiction):
    user = User(
        email="user@test.com",
        password_hash=hash_password("pass"),
        full_name="Test User",
        role="contributor",
    )
    db_session.add(user)
    await db_session.commit()

    document = Document(
        jurisdiction_id=default_jurisdiction.id,
        filename="test.pdf",
        document_type="standard",
        status="extracting",
        file_path="/tmp/test.pdf",
        uploaded_by=user.id,
    )
    db_session.add(document)
    await db_session.commit()

    run = ExtractionRun(
        document_id=document.id,
        status="running",
        ai_provider="openai",
        ai_model="gpt-4o",
    )
    db_session.add(run)
    await db_session.commit()

    document.current_extraction_id = run.id
    await db_session.commit()

    token = create_access_token({"sub": str(user.id), "role": "contributor"})

    async def fake_stream(run_id: str):
        yield json.dumps({"stage": "test", "message": "ok"})

    monkeypatch.setattr("app.api.documents.stream_events", fake_stream)

    url = f"/api/v1/documents/{document.id}/extraction-runs/{run.id}/events/stream"
    async with client.stream("GET", url, headers={"Authorization": f"Bearer {token}"}) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = await response.aread()
        assert b"data:" in body
