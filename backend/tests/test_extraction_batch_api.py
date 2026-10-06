from datetime import datetime, timezone

import pytest

from app.models.document import Document
from app.models.extraction import ExtractionRun
from app.models.requirement import ExtractedRequirement
from app.models.user import User
from app.services.auth import create_access_token, hash_password


@pytest.fixture
async def extraction_admin_user(db_session):
    user = User(
        email="extract-batch-admin@example.com",
        password_hash=hash_password("testpass"),
        full_name="Extract Batch Admin",
        role="admin",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def extraction_auth_headers(extraction_admin_user):
    token = create_access_token({"sub": str(extraction_admin_user.id)})
    return {"Authorization": f"Bearer {token}"}


async def test_reconcile_batch_supports_edit_split_merge_and_reject(
    client,
    db_session,
    default_jurisdiction,
    extraction_admin_user,
    extraction_auth_headers,
):
    document = Document(
        organization_id=extraction_admin_user.organization_id,
        jurisdiction_id=default_jurisdiction.id,
        filename="batch.pdf",
        name="Batch import",
        document_type="annex_b",
        status="extracted",
        file_path="/tmp/batch.pdf",
        uploaded_by=extraction_admin_user.id,
    )
    db_session.add(document)
    await db_session.flush()

    run = ExtractionRun(
        document_id=document.id,
        status="completed",
        ai_provider="none",
        ai_model="none",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    await db_session.flush()
    document.current_extraction_id = run.id

    ext1 = ExtractedRequirement(
        document_id=document.id,
        extraction_run_id=run.id,
        reference_id="A1",
        title="Rule A1",
        text="Original clause A1",
        original_text="Original clause A1",
        requirement_type="mandatory",
        page_number=1,
        confidence_score=0.9,
        status="pending",
        sort_order=1,
    )
    ext2 = ExtractedRequirement(
        document_id=document.id,
        extraction_run_id=run.id,
        reference_id="A2",
        title="Rule A2",
        text="Original clause A2",
        original_text="Original clause A2",
        requirement_type="mandatory",
        page_number=1,
        confidence_score=0.9,
        status="pending",
        sort_order=2,
    )
    db_session.add_all([ext1, ext2])
    await db_session.commit()
    await db_session.refresh(ext1)
    await db_session.refresh(ext2)

    response = await client.post(
        f"/api/v1/documents/{document.id}/extractions/reconcile-batch",
        json={
            "operations": [
                {
                    "action": "edit",
                    "extraction_id": str(ext1.id),
                    "reference_id": "A1-edited",
                    "text": "Edited text for A1",
                },
                {
                    "action": "split",
                    "extraction_id": str(ext2.id),
                    "split_items": [
                        {
                            "reference_id": "A2-1",
                            "text": "Split chunk 1",
                            "requirement_type": "mandatory",
                        },
                        {
                            "reference_id": "A2-2",
                            "text": "Split chunk 2",
                            "requirement_type": "mandatory",
                        },
                    ],
                },
                {
                    "action": "merge",
                    "source_ids": [str(ext1.id), str(ext2.id)],
                    "reference_id": "A-MERGED",
                },
                {
                    "action": "reject",
                    "source_ids": [str(ext1.id)],
                },
                {
                    "action": "comment",
                    "comment": "Reviewed and reconciled",
                },
            ],
            "republish": True,
        },
        headers=extraction_auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["processed"] == 5
    assert data["comments_added"] == 1

    list_response = await client.get(
        f"/api/v1/documents/{document.id}/extractions?limit=200",
        headers=extraction_auth_headers,
    )
    assert list_response.status_code == 200
    rows = list_response.json()["items"]
    assert len(rows) >= 4


async def test_reconcile_batch_remains_compatible_after_feedback_batch_usage(
    client,
    db_session,
    default_jurisdiction,
    extraction_admin_user,
    extraction_auth_headers,
):
    document = Document(
        organization_id=extraction_admin_user.organization_id,
        jurisdiction_id=default_jurisdiction.id,
        filename="compat.pdf",
        name="Compat import",
        document_type="annex_b",
        status="extracted",
        file_path="/tmp/compat.pdf",
        uploaded_by=extraction_admin_user.id,
    )
    db_session.add(document)
    await db_session.flush()

    run = ExtractionRun(
        document_id=document.id,
        status="completed",
        ai_provider="none",
        ai_model="none",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    await db_session.flush()
    document.current_extraction_id = run.id

    extraction = ExtractedRequirement(
        document_id=document.id,
        extraction_run_id=run.id,
        reference_id="C-1",
        title="Compat Rule",
        text="Compat clause",
        original_text="Compat clause",
        requirement_type="mandatory",
        page_number=1,
        confidence_score=0.77,
        status="pending",
        needs_review=True,
        review_reason="low_confidence",
        sort_order=1,
    )
    db_session.add(extraction)
    await db_session.commit()
    await db_session.refresh(extraction)

    preview_response = await client.post(
        f"/api/v1/documents/{document.id}/extractions/feedback-batch",
        json={
            "run_id": str(run.id),
            "preview_only": True,
            "action": {"type": "accept"},
        },
        headers=extraction_auth_headers,
    )
    assert preview_response.status_code == 200
    assert preview_response.json()["matched_count"] == 1

    reconcile_response = await client.post(
        f"/api/v1/documents/{document.id}/extractions/reconcile-batch",
        json={
            "operations": [
                {
                    "action": "reject",
                    "source_ids": [str(extraction.id)],
                }
            ],
            "republish": False,
        },
        headers=extraction_auth_headers,
    )
    assert reconcile_response.status_code == 200
    payload = reconcile_response.json()
    assert payload["processed"] == 1
    assert payload["errors"] == []
