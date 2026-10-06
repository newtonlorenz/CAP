"""Legacy extraction mutations must stay on the editable current run."""

import pytest
from sqlalchemy import func, select

from app.models.document import Document
from app.models.extraction import ExtractionRun
from app.models.requirement import ExtractedRequirement, ExtractionFeedback
from app.models.user import User
from app.services.auth import create_access_token, hash_password


@pytest.fixture
async def extraction_case(db_session, default_jurisdiction):
    user = User(
        email="mutation-guard-manager@example.com",
        password_hash=hash_password("testpass"),
        full_name="Mutation Guard Manager",
        role="manager",
    )
    db_session.add(user)
    await db_session.flush()
    document = Document(
        jurisdiction_id=default_jurisdiction.id,
        filename="source.pdf",
        file_path="/tmp/source.pdf",
        document_type="standard",
        status="extracted",
        uploaded_by=user.id,
    )
    db_session.add(document)
    await db_session.flush()
    old_run = ExtractionRun(
        document_id=document.id, status="completed", ai_provider="local", ai_model="test"
    )
    current_run = ExtractionRun(
        document_id=document.id, status="completed", ai_provider="local", ai_model="test"
    )
    db_session.add_all([old_run, current_run])
    await db_session.flush()
    document.current_extraction_id = current_run.id
    old_rows = [
        ExtractedRequirement(
            document_id=document.id,
            extraction_run_id=old_run.id,
            reference_id=f"OLD-{index}",
            text=f"Old source {index}",
            original_text=f"Old source {index}",
            requirement_type="mandatory",
            page_number=1,
            confidence_score=0.8,
            needs_review=True,
            sort_order=index,
        )
        for index in (1, 2)
    ]
    current_row = ExtractedRequirement(
        document_id=document.id,
        extraction_run_id=current_run.id,
        reference_id="CURRENT-1",
        text="Current source",
        original_text="Current source",
        requirement_type="mandatory",
        page_number=1,
        confidence_score=0.8,
        needs_review=True,
        sort_order=1,
    )
    db_session.add_all([*old_rows, current_row])
    await db_session.commit()
    token = create_access_token({"sub": str(user.id), "role": user.role})
    return document, old_run, current_run, old_rows, current_row, {
        "Authorization": f"Bearer {token}"
    }


def _requests(document, old_run, old_rows, current_row):
    base = f"/api/v1/documents/{document.id}/extractions"
    old = old_rows[0]
    return [
        ("put", f"{base}/{old.id}", {"text": "Changed"}),
        ("post", f"{base}/{old.id}/feedback", {"action": "accept"}),
        ("post", f"{base}/reorder", {
            "run_id": str(old_run.id), "ordered_ids": [str(row.id) for row in reversed(old_rows)]
        }),
        ("post", f"{base}/feedback-batch", {
            "run_id": str(old_run.id), "action": {"type": "accept"}
        }),
        ("post", f"{base}/reconcile-batch", {
            "operations": [{"action": "edit", "extraction_id": str(old.id), "text": "Changed"}],
            "republish": True,
        }),
        ("post", f"{base}/reconcile-batch", {
            "operations": [{"action": "split", "extraction_id": str(old.id),
                            "split_items": [{"reference_id": "SPLIT", "text": "Changed"}]}]
        }),
        ("post", f"{base}/reconcile-batch", {
            "operations": [{"action": "merge", "source_ids": [str(old.id), str(current_row.id)]}]
        }),
        ("post", f"{base}/reconcile-batch", {
            "operations": [{"action": "reject", "source_ids": [str(old.id)]}]
        }),
    ]


@pytest.mark.parametrize("request_index", range(8))
async def test_stale_run_mutations_are_rejected_without_side_effects(
    client, db_session, extraction_case, request_index
):
    document, old_run, _, old_rows, current_row, headers = extraction_case
    method, path, payload = _requests(document, old_run, old_rows, current_row)[request_index]
    response = await client.request(method, path, json=payload, headers=headers)
    assert response.status_code == 409, response.text

    await db_session.refresh(document)
    for row in [*old_rows, current_row]:
        await db_session.refresh(row)
        assert row.text == ("Current source" if row.id == current_row.id else
                            f"Old source {row.sort_order}")
        assert row.status != "rejected"
        assert row.needs_review
    assert document.status == "extracted"
    assert (await db_session.scalar(select(func.count(ExtractionFeedback.id)))) == 0
    assert (await db_session.scalar(select(func.count(ExtractedRequirement.id)))) == 3


@pytest.mark.parametrize("request_index", range(8))
async def test_approved_document_blocks_all_legacy_mutations(
    client, db_session, extraction_case, request_index
):
    document, old_run, _, old_rows, current_row, headers = extraction_case
    document.status = "approved"
    await db_session.commit()
    method, path, payload = _requests(document, old_run, old_rows, current_row)[request_index]
    response = await client.request(method, path, json=payload, headers=headers)
    assert response.status_code == 409, response.text
    await db_session.refresh(document)
    assert document.status == "approved"


async def test_batch_feedback_without_run_id_only_changes_current_run(
    client, db_session, extraction_case
):
    document, _, _, old_rows, current_row, headers = extraction_case
    response = await client.post(
        f"/api/v1/documents/{document.id}/extractions/feedback-batch",
        json={"action": {"type": "accept"}},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["matched_count"] == 1
    assert response.json()["affected_ids"] == [str(current_row.id)]
    await db_session.refresh(current_row)
    assert not current_row.needs_review
    for row in old_rows:
        await db_session.refresh(row)
        assert row.needs_review


@pytest.mark.parametrize("run_state", ["missing", "pending"])
async def test_mutation_requires_a_completed_current_run(
    client, db_session, extraction_case, run_state
):
    document, _, current_run, _, current_row, headers = extraction_case
    if run_state == "missing":
        document.current_extraction_id = None
    else:
        current_run.status = "pending"
    await db_session.commit()
    response = await client.put(
        f"/api/v1/documents/{document.id}/extractions/{current_row.id}",
        json={"text": "Changed"}, headers=headers,
    )
    assert response.status_code == 409, response.text
    await db_session.refresh(current_row)
    assert current_row.text == "Current source"


async def test_current_run_remains_editable(client, db_session, extraction_case):
    document, _, _, _, current_row, headers = extraction_case
    response = await client.put(
        f"/api/v1/documents/{document.id}/extractions/{current_row.id}",
        json={"text": "Corrected"}, headers=headers,
    )
    assert response.status_code == 200, response.text
    await db_session.refresh(current_row)
    assert current_row.text == "Corrected"
    assert current_row.original_text == "Current source"


@pytest.mark.parametrize("status", ["approved", "pending_approval"])
@pytest.mark.parametrize("republish_payload", [
    {"republish": True},
    {"operations": [{"action": "republish"}]},
])
async def test_batch_republish_cannot_reopen_locked_document(
    client, db_session, extraction_case, status, republish_payload
):
    document, _, _, _, _, headers = extraction_case
    document.status = status
    await db_session.commit()
    response = await client.post(
        f"/api/v1/documents/{document.id}/extractions/reconcile-batch",
        json=republish_payload, headers=headers,
    )
    assert response.status_code == 409, response.text
    await db_session.refresh(document)
    assert document.status == status


async def test_mixed_run_batch_is_atomic(client, db_session, extraction_case):
    document, _, _, old_rows, current_row, headers = extraction_case
    response = await client.post(
        f"/api/v1/documents/{document.id}/extractions/reconcile-batch",
        json={
            "operations": [
                {"action": "edit", "extraction_id": str(current_row.id), "text": "Changed"},
                {"action": "reject", "source_ids": [str(old_rows[0].id)]},
            ],
            "republish": True,
        },
        headers=headers,
    )
    assert response.status_code == 409, response.text
    await db_session.refresh(current_row)
    await db_session.refresh(old_rows[0])
    assert current_row.text == "Current source"
    assert old_rows[0].status != "rejected"
