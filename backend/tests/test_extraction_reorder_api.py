from datetime import datetime, timezone

from app.models.document import Document
from app.models.extraction import ExtractionRun
from app.models.requirement import ExtractedRequirement
from app.models.user import User
from app.services.auth import create_access_token, hash_password


async def _create_user(db_session, *, email: str, role: str):
    user = User(
        email=email,
        password_hash=hash_password("pass"),
        full_name=f"{role.title()} User",
        role=role,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    token = create_access_token({"sub": str(user.id), "role": user.role})
    return user, {"Authorization": f"Bearer {token}"}


async def _seed_document_with_extractions(db_session, *, owner: User, jurisdiction_id):
    document = Document(
        organization_id=owner.organization_id,
        jurisdiction_id=jurisdiction_id,
        filename="reorder-test.pdf",
        document_type="standard",
        status="extracted",
        file_path="/tmp/reorder-test.pdf",
        uploaded_by=owner.id,
    )
    db_session.add(document)
    await db_session.flush()

    run_primary = ExtractionRun(
        document_id=document.id,
        status="completed",
        ai_provider="openai",
        ai_model="gpt-5-mini",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    run_secondary = ExtractionRun(
        document_id=document.id,
        status="completed",
        ai_provider="openai",
        ai_model="gpt-5-mini",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db_session.add_all([run_primary, run_secondary])
    await db_session.flush()
    document.current_extraction_id = run_primary.id

    run_primary_rows = [
        ExtractedRequirement(
            document_id=document.id,
            extraction_run_id=run_primary.id,
            reference_id="1",
            title="Requirement 1",
            text="Requirement 1",
            original_text="Requirement 1",
            requirement_type="mandatory",
            page_number=1,
            confidence_score=0.9,
            status="pending",
            needs_review=False,
            parser_strategy="ai_chunked",
            sort_order=1,
        ),
        ExtractedRequirement(
            document_id=document.id,
            extraction_run_id=run_primary.id,
            reference_id="2",
            title="Requirement 2",
            text="Requirement 2",
            original_text="Requirement 2",
            requirement_type="mandatory",
            page_number=1,
            confidence_score=0.9,
            status="pending",
            needs_review=False,
            parser_strategy="ai_chunked",
            sort_order=2,
        ),
        ExtractedRequirement(
            document_id=document.id,
            extraction_run_id=run_primary.id,
            reference_id="3",
            title="Requirement 3",
            text="Requirement 3",
            original_text="Requirement 3",
            requirement_type="mandatory",
            page_number=2,
            confidence_score=0.9,
            status="pending",
            needs_review=False,
            parser_strategy="ai_chunked",
            sort_order=3,
        ),
    ]
    run_secondary_row = ExtractedRequirement(
        document_id=document.id,
        extraction_run_id=run_secondary.id,
        reference_id="9",
        title="Secondary run requirement",
        text="Secondary run requirement",
        original_text="Secondary run requirement",
        requirement_type="mandatory",
        page_number=5,
        confidence_score=0.9,
        status="pending",
        needs_review=False,
        parser_strategy="ai_chunked",
        sort_order=1,
    )
    db_session.add_all([*run_primary_rows, run_secondary_row])
    await db_session.commit()

    for row in run_primary_rows:
        await db_session.refresh(row)
    await db_session.refresh(run_secondary_row)

    return document, run_primary, run_secondary, run_primary_rows, run_secondary_row


async def test_reorder_extractions_persists_requested_order(
    client, db_session, default_jurisdiction
):
    manager, headers = await _create_user(
        db_session,
        email="manager.reorder.ok@example.com",
        role="manager",
    )
    document, run_primary, _, run_rows, _ = await _seed_document_with_extractions(
        db_session,
        owner=manager,
        jurisdiction_id=default_jurisdiction.id,
    )

    requested_order = [run_rows[2].id, run_rows[0].id, run_rows[1].id]
    response = await client.post(
        f"/api/v1/documents/{document.id}/extractions/reorder",
        headers=headers,
        json={
            "run_id": str(run_primary.id),
            "ordered_ids": [str(extraction_id) for extraction_id in requested_order],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["updated_count"] == 3
    assert payload["ordered_ids"] == [str(extraction_id) for extraction_id in requested_order]

    list_response = await client.get(
        f"/api/v1/documents/{document.id}/extractions?run_id={run_primary.id}&limit=100",
        headers=headers,
    )
    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert [item["id"] for item in items] == [
        str(extraction_id) for extraction_id in requested_order
    ]
    assert [item["sort_order"] for item in items] == [0, 1, 2]


async def test_reorder_extractions_rejects_duplicate_ids(client, db_session, default_jurisdiction):
    manager, headers = await _create_user(
        db_session,
        email="manager.reorder.duplicate@example.com",
        role="manager",
    )
    document, run_primary, _, run_rows, _ = await _seed_document_with_extractions(
        db_session,
        owner=manager,
        jurisdiction_id=default_jurisdiction.id,
    )

    response = await client.post(
        f"/api/v1/documents/{document.id}/extractions/reorder",
        headers=headers,
        json={
            "run_id": str(run_primary.id),
            "ordered_ids": [
                str(run_rows[0].id),
                str(run_rows[0].id),
                str(run_rows[1].id),
            ],
        },
    )
    assert response.status_code == 400
    assert "duplicates" in response.json()["detail"]


async def test_reorder_extractions_rejects_missing_or_extra_ids(
    client, db_session, default_jurisdiction
):
    manager, headers = await _create_user(
        db_session,
        email="manager.reorder.mismatch@example.com",
        role="manager",
    )
    document, run_primary, run_secondary, run_rows, run_secondary_row = (
        await _seed_document_with_extractions(
            db_session,
            owner=manager,
            jurisdiction_id=default_jurisdiction.id,
        )
    )

    missing_response = await client.post(
        f"/api/v1/documents/{document.id}/extractions/reorder",
        headers=headers,
        json={
            "run_id": str(run_primary.id),
            "ordered_ids": [str(run_rows[0].id), str(run_rows[1].id)],
        },
    )
    assert missing_response.status_code == 400
    assert "exactly all extraction IDs" in missing_response.json()["detail"]

    outside_run_response = await client.post(
        f"/api/v1/documents/{document.id}/extractions/reorder",
        headers=headers,
        json={
            "run_id": str(run_primary.id),
            "ordered_ids": [
                str(run_rows[0].id),
                str(run_rows[1].id),
                str(run_secondary_row.id),
            ],
        },
    )
    assert outside_run_response.status_code == 400
    detail = outside_run_response.json()["detail"]
    assert detail["message"].startswith("ordered_ids must include exactly all extraction IDs")
    assert str(run_rows[2].id) in detail["missing_ids"]
    assert str(run_secondary_row.id) in detail["extra_ids"]

    # Ensure wrong run scope is rejected too.
    wrong_run_response = await client.post(
        f"/api/v1/documents/{document.id}/extractions/reorder",
        headers=headers,
        json={
            "run_id": str(run_secondary.id),
            "ordered_ids": [str(run_rows[0].id)],
        },
    )
    assert wrong_run_response.status_code == 409


async def test_reorder_extractions_role_boundary(client, db_session, default_jurisdiction):
    manager, manager_headers = await _create_user(
        db_session,
        email="manager.reorder.role@example.com",
        role="manager",
    )
    _, contributor_headers = await _create_user(
        db_session,
        email="contributor.reorder.role@example.com",
        role="contributor",
    )
    document, run_primary, _, run_rows, _ = await _seed_document_with_extractions(
        db_session,
        owner=manager,
        jurisdiction_id=default_jurisdiction.id,
    )

    denied = await client.post(
        f"/api/v1/documents/{document.id}/extractions/reorder",
        headers=contributor_headers,
        json={
            "run_id": str(run_primary.id),
            "ordered_ids": [str(row.id) for row in run_rows],
        },
    )
    assert denied.status_code == 403

    allowed = await client.post(
        f"/api/v1/documents/{document.id}/extractions/reorder",
        headers=manager_headers,
        json={
            "run_id": str(run_primary.id),
            "ordered_ids": [str(row.id) for row in run_rows],
        },
    )
    assert allowed.status_code == 200
