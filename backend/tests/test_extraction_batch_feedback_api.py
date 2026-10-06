from datetime import datetime, timezone

from sqlalchemy import select

from app.models.document import Document
from app.models.extraction import ExtractionRun
from app.models.requirement import ExtractedRequirement
from app.models.user import User
from app.services.auth import create_access_token, hash_password


async def _create_user(db_session, *, email: str, role: str) -> tuple[User, dict[str, str]]:
    user = User(
        email=email,
        password_hash=hash_password("testpass"),
        full_name=f"{role.title()} User",
        role=role,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    token = create_access_token({"sub": str(user.id), "role": user.role})
    return user, {"Authorization": f"Bearer {token}"}


async def _seed_feedback_batch_document(
    db_session,
    *,
    user: User,
    jurisdiction_id,
):
    document = Document(
        organization_id=user.organization_id,
        jurisdiction_id=jurisdiction_id,
        filename="feedback-batch.pdf",
        name="Feedback batch import",
        document_type="standard",
        status="extracted",
        file_path="/tmp/feedback-batch.pdf",
        uploaded_by=user.id,
    )
    db_session.add(document)
    await db_session.flush()

    run = ExtractionRun(
        document_id=document.id,
        status="completed",
        ai_provider="openai",
        ai_model="gpt-5-mini",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    await db_session.flush()
    document.current_extraction_id = run.id

    rows = [
        ExtractedRequirement(
            document_id=document.id,
            extraction_run_id=run.id,
            reference_id="3.2.1",
            title="Rule A",
            text="Clause A",
            original_text="Clause A",
            requirement_type="mandatory",
            page_number=1,
            confidence_score=0.62,
            status="pending",
            needs_review=True,
            review_reason="anchor_mismatch",
            sort_order=1,
        ),
        ExtractedRequirement(
            document_id=document.id,
            extraction_run_id=run.id,
            reference_id="3.2.2",
            title="Rule B",
            text="Clause B",
            original_text="Clause B",
            requirement_type="mandatory",
            page_number=1,
            confidence_score=0.41,
            status="pending",
            needs_review=True,
            review_reason="low_confidence",
            sort_order=2,
        ),
        ExtractedRequirement(
            document_id=document.id,
            extraction_run_id=run.id,
            reference_id="7.1",
            title="Rule C",
            text="Clause C",
            original_text="Clause C",
            requirement_type="conditional",
            page_number=2,
            confidence_score=0.82,
            status="pending",
            needs_review=True,
            review_reason="low_confidence",
            sort_order=3,
        ),
        ExtractedRequirement(
            document_id=document.id,
            extraction_run_id=run.id,
            reference_id="9",
            title="Rule D",
            text="Clause D",
            original_text="Clause D",
            requirement_type="mandatory",
            page_number=3,
            confidence_score=0.91,
            status="accepted",
            needs_review=False,
            review_reason=None,
            sort_order=4,
        ),
        ExtractedRequirement(
            document_id=document.id,
            extraction_run_id=run.id,
            reference_id="3.9.1",
            title="Rule E",
            text="Clause E",
            original_text="Clause E",
            requirement_type="mandatory",
            page_number=3,
            confidence_score=0.70,
            status="rejected",
            needs_review=False,
            review_reason="rejected_by_reviewer",
            sort_order=5,
        ),
        ExtractedRequirement(
            document_id=document.id,
            extraction_run_id=None,
            reference_id="3.8",
            title="Rule F",
            text="Clause F",
            original_text="Clause F",
            requirement_type="mandatory",
            page_number=4,
            confidence_score=0.55,
            status="pending",
            needs_review=True,
            review_reason="low_confidence",
            sort_order=6,
        ),
        ExtractedRequirement(
            document_id=document.id,
            extraction_run_id=run.id,
            reference_id="5.1",
            title="Rule G",
            text="Clause G",
            original_text="Clause G",
            requirement_type="mandatory",
            page_number=5,
            confidence_score=0.58,
            status="pending",
            needs_review=True,
            review_reason="low_confidence",
            sort_order=7,
        ),
    ]
    db_session.add_all(rows)
    await db_session.commit()

    for row in rows:
        await db_session.refresh(row)

    return document, run, rows


async def test_feedback_batch_preview_returns_filtered_distributions(
    client,
    db_session,
    default_jurisdiction,
):
    admin_user, headers = await _create_user(
        db_session,
        email="batch-preview-admin@example.com",
        role="admin",
    )
    document, run, rows = await _seed_feedback_batch_document(
        db_session,
        user=admin_user,
        jurisdiction_id=default_jurisdiction.id,
    )
    anchor_row = rows[0]

    response = await client.post(
        f"/api/v1/documents/{document.id}/extractions/feedback-batch",
        headers=headers,
        json={
            "run_id": str(run.id),
            "preview_only": True,
            "filter": {
                "needs_review_only": True,
                "confidence_min": 0.5,
                "confidence_max": 0.8,
                "requirement_types": ["mandatory"],
                "section_prefixes": ["3"],
                "review_reasons": ["anchor_mismatch"],
            },
            "action": {"type": "accept"},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["preview_only"] is True
    assert payload["matched_count"] == 1
    assert payload["affected_count"] == 0
    assert payload["affected_ids"] == []
    assert payload["failures"] == []
    assert payload["distributions"]["by_review_reason"] == [{"key": "anchor_mismatch", "total": 1}]
    assert payload["distributions"]["by_section_prefix"] == [{"key": "3", "total": 1}]

    row_result = await db_session.execute(
        select(ExtractedRequirement).where(ExtractedRequirement.id == anchor_row.id)
    )
    row = row_result.scalar_one()
    assert row.needs_review is True
    assert row.review_reason == "anchor_mismatch"


async def test_feedback_batch_accept_clears_review_fields(
    client,
    db_session,
    default_jurisdiction,
):
    manager_user, headers = await _create_user(
        db_session,
        email="batch-accept-manager@example.com",
        role="manager",
    )
    document, run, rows = await _seed_feedback_batch_document(
        db_session,
        user=manager_user,
        jurisdiction_id=default_jurisdiction.id,
    )
    target = rows[0]

    response = await client.post(
        f"/api/v1/documents/{document.id}/extractions/feedback-batch",
        headers=headers,
        json={
            "run_id": str(run.id),
            "preview_only": False,
            "filter": {
                "section_prefixes": ["3"],
                "review_reasons": ["anchor_mismatch"],
            },
            "action": {"type": "accept"},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["matched_count"] == 1
    assert payload["affected_count"] == 1
    assert payload["affected_ids"] == [str(target.id)]

    await db_session.refresh(target)
    assert target.needs_review is False
    assert target.review_reason is None


async def test_feedback_batch_reject_sets_rejected_state(
    client,
    db_session,
    default_jurisdiction,
):
    manager_user, headers = await _create_user(
        db_session,
        email="batch-reject-manager@example.com",
        role="manager",
    )
    document, run, rows = await _seed_feedback_batch_document(
        db_session,
        user=manager_user,
        jurisdiction_id=default_jurisdiction.id,
    )
    target = rows[2]

    response = await client.post(
        f"/api/v1/documents/{document.id}/extractions/feedback-batch",
        headers=headers,
        json={
            "run_id": str(run.id),
            "filter": {
                "section_prefixes": ["7"],
                "review_reasons": ["low_confidence"],
            },
            "action": {"type": "reject"},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["affected_count"] == 1
    assert payload["affected_ids"] == [str(target.id)]

    await db_session.refresh(target)
    assert target.status == "rejected"
    assert target.needs_review is False
    assert target.review_reason == "rejected_by_reviewer"


async def test_feedback_batch_edit_updates_fields_and_clears_review_flags(
    client,
    db_session,
    default_jurisdiction,
):
    approver_user, headers = await _create_user(
        db_session,
        email="batch-edit-approver@example.com",
        role="approver",
    )
    document, run, rows = await _seed_feedback_batch_document(
        db_session,
        user=approver_user,
        jurisdiction_id=default_jurisdiction.id,
    )
    target = rows[6]

    response = await client.post(
        f"/api/v1/documents/{document.id}/extractions/feedback-batch",
        headers=headers,
        json={
            "run_id": str(run.id),
            "filter": {
                "section_prefixes": ["5"],
                "review_reasons": ["low_confidence"],
            },
            "action": {
                "type": "edit",
                "edit": {
                    "requirement_type": "informational",
                    "status": "accepted",
                },
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["affected_count"] == 1
    assert payload["affected_ids"] == [str(target.id)]

    await db_session.refresh(target)
    assert target.requirement_type == "informational"
    assert target.status == "accepted"
    assert target.needs_review is False
    assert target.review_reason is None


async def test_feedback_batch_excludes_runless_rows(
    client,
    db_session,
    default_jurisdiction,
):
    admin_user, headers = await _create_user(
        db_session,
        email="batch-partial-admin@example.com",
        role="admin",
    )
    document, _, rows = await _seed_feedback_batch_document(
        db_session,
        user=admin_user,
        jurisdiction_id=default_jurisdiction.id,
    )
    runless_target = rows[5]
    run_target = rows[1]

    response = await client.post(
        f"/api/v1/documents/{document.id}/extractions/feedback-batch",
        headers=headers,
        json={
            "preview_only": False,
            "filter": {
                "section_prefixes": ["3"],
                "review_reasons": ["low_confidence"],
            },
            "action": {"type": "accept"},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["matched_count"] == 1
    assert payload["affected_count"] == 1
    assert payload["affected_ids"] == [str(run_target.id)]
    assert payload["failures"] == []

    await db_session.refresh(run_target)
    assert run_target.needs_review is False
    assert run_target.review_reason is None
    await db_session.refresh(runless_target)
    assert runless_target.needs_review is True
    assert runless_target.review_reason == "low_confidence"


async def test_feedback_batch_role_boundary_enforced(
    client,
    db_session,
    default_jurisdiction,
):
    admin_user, admin_headers = await _create_user(
        db_session,
        email="batch-role-admin@example.com",
        role="admin",
    )
    contributor_user, contributor_headers = await _create_user(
        db_session,
        email="batch-role-contributor@example.com",
        role="contributor",
    )
    assert contributor_user.role == "contributor"

    document, run, _ = await _seed_feedback_batch_document(
        db_session,
        user=admin_user,
        jurisdiction_id=default_jurisdiction.id,
    )

    denied = await client.post(
        f"/api/v1/documents/{document.id}/extractions/feedback-batch",
        headers=contributor_headers,
        json={
            "run_id": str(run.id),
            "preview_only": True,
            "action": {"type": "accept"},
        },
    )
    assert denied.status_code == 403

    allowed = await client.post(
        f"/api/v1/documents/{document.id}/extractions/feedback-batch",
        headers=admin_headers,
        json={
            "run_id": str(run.id),
            "preview_only": True,
            "action": {"type": "accept"},
        },
    )
    assert allowed.status_code == 200
