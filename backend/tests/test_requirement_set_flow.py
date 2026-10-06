import pytest

from app.models import Document, ExtractedRequirement, ExtractionRun, User
from app.services.auth import create_access_token, hash_password


@pytest.fixture
async def manager_user(db_session):
    user = User(
        email="manager@example.com",
        password_hash=hash_password("testpass"),
        full_name="Manager User",
        role="manager",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def manager_headers(manager_user):
    token = create_access_token({"sub": str(manager_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def contributor_user(db_session):
    user = User(
        email="contributor@example.com",
        password_hash=hash_password("testpass"),
        full_name="Contributor User",
        role="contributor",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def contributor_headers(contributor_user):
    token = create_access_token({"sub": str(contributor_user.id)})
    return {"Authorization": f"Bearer {token}"}


async def test_manager_can_create_manual_requirement_set(
    client, manager_headers, default_jurisdiction
):
    response = await client.post(
        "/api/v1/requirements/sets",
        json={
            "jurisdiction_id": str(default_jurisdiction.id),
            "name": "Manual Set",
            "document_type": "annex_b",
            "testing_frequency": "one_off",
        },
        headers=manager_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "draft"
    assert data["filename"] is None
    assert data["has_source"] is False
    assert data["name"] == "Manual Set"


async def test_contributor_cannot_create_manual_requirement_set(
    client, contributor_headers, default_jurisdiction
):
    response = await client.post(
        "/api/v1/requirements/sets",
        json={
            "jurisdiction_id": str(default_jurisdiction.id),
            "name": "Manual Set",
            "document_type": "annex_b",
            "testing_frequency": "one_off",
        },
        headers=contributor_headers,
    )
    assert response.status_code == 403


async def test_manual_set_submit_and_approve_without_extraction(
    client, manager_headers, contributor_headers, default_jurisdiction
):
    # Create draft requirement set
    response = await client.post(
        "/api/v1/requirements/sets",
        json={
            "jurisdiction_id": str(default_jurisdiction.id),
            "name": "Manual Set",
            "document_type": "annex_b",
            "testing_frequency": "one_off",
        },
        headers=manager_headers,
    )
    assert response.status_code == 201
    set_id = response.json()["id"]

    # Contributor cannot create requirements in the set
    response = await client.post(
        "/api/v1/requirements",
        json={
            "document_id": set_id,
            "reference_id": "1",
            "title": "Req 1",
            "text": "Do the thing",
            "requirement_type": "mandatory",
        },
        headers=contributor_headers,
    )
    assert response.status_code == 403

    # Manager can create a requirement
    response = await client.post(
        "/api/v1/requirements",
        json={
            "document_id": set_id,
            "reference_id": "1",
            "title": "Req 1",
            "text": "Do the thing",
            "requirement_type": "mandatory",
        },
        headers=manager_headers,
    )
    assert response.status_code == 201
    assert response.json()["reference_id"] == "1"

    # Submit for approval
    response = await client.post(f"/api/v1/documents/{set_id}/submit", headers=manager_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "pending_approval"

    # Approve without extraction
    response = await client.post(f"/api/v1/documents/{set_id}/approve", headers=manager_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "approved"


async def test_cannot_approve_empty_manual_set(client, manager_headers, default_jurisdiction):
    response = await client.post(
        "/api/v1/requirements/sets",
        json={
            "jurisdiction_id": str(default_jurisdiction.id),
            "name": "Empty Manual Set",
            "document_type": "annex_b",
            "testing_frequency": "one_off",
        },
        headers=manager_headers,
    )
    assert response.status_code == 201
    set_id = response.json()["id"]

    response = await client.post(f"/api/v1/documents/{set_id}/submit", headers=manager_headers)
    assert response.status_code == 422
    assert "empty" in response.text.lower()


async def test_draft_sets_excluded_from_dashboard_reports_and_review_cycles(
    client, manager_headers, default_jurisdiction
):
    # Create draft set + requirement
    response = await client.post(
        "/api/v1/requirements/sets",
        json={
            "jurisdiction_id": str(default_jurisdiction.id),
            "name": "Draft Set",
            "document_type": "annex_b",
            "testing_frequency": "one_off",
        },
        headers=manager_headers,
    )
    assert response.status_code == 201
    set_id = response.json()["id"]

    response = await client.post(
        "/api/v1/requirements",
        json={
            "document_id": set_id,
            "reference_id": "D-1",
            "title": "Draft Req",
            "text": "Draft requirement",
            "requirement_type": "mandatory",
        },
        headers=manager_headers,
    )
    assert response.status_code == 201

    # Dashboard should exclude draft requirement sets
    response = await client.get(
        f"/api/v1/dashboard?jurisdiction_id={default_jurisdiction.id}",
        headers=manager_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["kpis"]["overall"]["total"] == 0

    # Reports should exclude draft requirement sets by default
    response = await client.get(
        f"/api/v1/reports/gap-analysis?jurisdiction_id={default_jurisdiction.id}",
        headers=manager_headers,
    )
    assert response.status_code == 200
    assert "D-1" not in response.text

    # Review cycle "scope=documents" should reject non-approved sets
    response = await client.post(
        "/api/v1/review-cycles",
        json={
            "name": "Cycle",
            "jurisdiction_id": str(default_jurisdiction.id),
            "scope": "documents",
            "document_ids": [set_id],
        },
        headers=manager_headers,
    )
    assert response.status_code == 400

    # Review cycle "scope=all" now requires at least one approved, versioned baseline.
    response = await client.post(
        "/api/v1/review-cycles",
        json={"name": "All Cycle", "jurisdiction_id": str(default_jurisdiction.id), "scope": "all"},
        headers=manager_headers,
    )
    assert response.status_code == 400

    # Approve the set, then it should show up in dashboard + reports
    response = await client.post(f"/api/v1/documents/{set_id}/submit", headers=manager_headers)
    assert response.status_code == 200
    response = await client.post(f"/api/v1/documents/{set_id}/approve", headers=manager_headers)
    assert response.status_code == 200

    response = await client.get(
        f"/api/v1/dashboard?jurisdiction_id={default_jurisdiction.id}",
        headers=manager_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["kpis"]["overall"]["total"] == 1

    response = await client.get(
        f"/api/v1/reports/gap-analysis?jurisdiction_id={default_jurisdiction.id}",
        headers=manager_headers,
    )
    assert response.status_code == 200
    assert "D-1" in response.text


async def test_rejected_extraction_submission_has_editable_draft_requirements(
    client, manager_headers, default_jurisdiction, db_session, manager_user
):
    document = Document(
        organization_id=manager_user.organization_id,
        jurisdiction_id=default_jurisdiction.id,
        filename="extracted.pdf",
        name="Extracted Draft",
        document_type="annex_b",
        version=None,
        status="extracted",
        file_path="/tmp/extracted.pdf",
        uploaded_by=manager_user.id,
        testing_frequency="one_off",
    )
    db_session.add(document)
    await db_session.flush()

    extraction_run = ExtractionRun(
        document_id=document.id,
        status="completed",
        total_pages=1,
        current_page=1,
        requirements_found=1,
        ai_provider="deterministic",
        ai_model="annex_b_v2_guide",
    )
    db_session.add(extraction_run)
    await db_session.flush()
    document.current_extraction_id = extraction_run.id

    extracted_requirement = ExtractedRequirement(
        document_id=document.id,
        extraction_run_id=extraction_run.id,
        reference_id="E-1",
        title="Extracted Requirement",
        text="Requirement imported from extraction",
        original_text="Requirement imported from extraction",
        requirement_type="mandatory",
        parent_id=None,
        page_number=1,
        confidence_score=1.0,
        status="pending",
        sort_order=0,
    )
    db_session.add(extracted_requirement)
    await db_session.commit()

    submit_response = await client.post(
        f"/api/v1/documents/{document.id}/submit",
        headers=manager_headers,
    )
    assert submit_response.status_code == 200
    reject_response = await client.post(
        f"/api/v1/documents/{document.id}/reject",
        params={"comment": "Needs revision"},
        headers=manager_headers,
    )
    assert reject_response.status_code == 200

    versions_response = await client.get(
        f"/api/v1/requirements/sets/{document.id}/versions",
        headers=manager_headers,
    )
    assert versions_response.status_code == 200
    versions = versions_response.json()["items"]
    draft_version = next((version for version in versions if version["status"] == "draft"), None)
    assert draft_version is not None

    draft_requirements_response = await client.get(
        (
            "/api/v1/requirements"
            f"?requirement_set_version_id={draft_version['id']}&active_only=true&limit=100"
        ),
        headers=manager_headers,
    )
    assert draft_requirements_response.status_code == 200
    draft_data = draft_requirements_response.json()
    assert draft_data["total"] == 1
    draft_requirement = draft_data["items"][0]
    assert draft_requirement["reference_id"] == "E-1"
    assert draft_requirement["requirement_set_version_id"] == draft_version["id"]

    update_response = await client.put(
        f"/api/v1/requirements/{draft_requirement['id']}",
        json={"text": "Updated in extracted draft"},
        headers=manager_headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["text"] == "Updated in extracted draft"


async def test_prepare_edit_populates_requirements_for_fresh_extracted_set(
    client, manager_headers, default_jurisdiction, db_session, manager_user
):
    document = Document(
        organization_id=manager_user.organization_id,
        jurisdiction_id=default_jurisdiction.id,
        filename="fresh-extracted.pdf",
        name="Fresh Extracted",
        document_type="annex_b",
        version=None,
        status="extracted",
        file_path="/tmp/fresh-extracted.pdf",
        uploaded_by=manager_user.id,
        testing_frequency="one_off",
    )
    db_session.add(document)
    await db_session.flush()

    extraction_run = ExtractionRun(
        document_id=document.id,
        status="completed",
        total_pages=1,
        current_page=1,
        requirements_found=1,
        ai_provider="deterministic",
        ai_model="annex_b_v2_guide",
    )
    db_session.add(extraction_run)
    await db_session.flush()
    document.current_extraction_id = extraction_run.id

    extracted_requirement = ExtractedRequirement(
        document_id=document.id,
        extraction_run_id=extraction_run.id,
        reference_id="FRESH-1",
        title="Fresh Extracted Requirement",
        text="Fresh requirement imported from extraction",
        original_text="Fresh requirement imported from extraction",
        requirement_type="mandatory",
        parent_id=None,
        page_number=1,
        confidence_score=1.0,
        status="pending",
        sort_order=0,
    )
    db_session.add(extracted_requirement)
    await db_session.commit()

    prepare_response = await client.post(
        f"/api/v1/documents/{document.id}/prepare-edit",
        headers=manager_headers,
    )
    assert prepare_response.status_code == 200
    assert prepare_response.json()["requirements_count"] == 1

    requirements_response = await client.get(
        f"/api/v1/requirements?document_id={document.id}&active_only=true&limit=100",
        headers=manager_headers,
    )
    assert requirements_response.status_code == 200
    requirements_data = requirements_response.json()
    assert requirements_data["total"] == 1
    item = requirements_data["items"][0]
    assert item["reference_id"] == "FRESH-1"

    update_response = await client.put(
        f"/api/v1/requirements/{item['id']}",
        json={"text": "Fresh requirement updated in edit mode"},
        headers=manager_headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["text"] == "Fresh requirement updated in edit mode"


async def test_create_requirement_derives_parent_from_reference_when_parent_omitted(
    client, manager_headers, default_jurisdiction
):
    response = await client.post(
        "/api/v1/requirements/sets",
        json={
            "jurisdiction_id": str(default_jurisdiction.id),
            "name": "Derived Parent Set",
            "document_type": "annex_b",
            "testing_frequency": "one_off",
        },
        headers=manager_headers,
    )
    assert response.status_code == 201
    document_id = response.json()["id"]

    top_level = await client.post(
        "/api/v1/requirements",
        json={
            "document_id": document_id,
            "reference_id": "3.2",
            "text": "Top level section",
            "requirement_type": "informational",
        },
        headers=manager_headers,
    )
    assert top_level.status_code == 201
    top_level_payload = top_level.json()
    assert top_level_payload["parent_id"] is None

    section = await client.post(
        "/api/v1/requirements",
        json={
            "document_id": document_id,
            "reference_id": "3.2.5",
            "text": "Child section",
            "requirement_type": "informational",
        },
        headers=manager_headers,
    )
    assert section.status_code == 201
    section_payload = section.json()
    assert section_payload["parent_id"] == top_level_payload["id"]

    requirement = await client.post(
        "/api/v1/requirements",
        json={
            "document_id": document_id,
            "reference_id": "3.2.5.3",
            "text": "Nested requirement",
            "requirement_type": "mandatory",
        },
        headers=manager_headers,
    )
    assert requirement.status_code == 201
    assert requirement.json()["parent_id"] == section_payload["id"]

    separate_root = await client.post(
        "/api/v1/requirements",
        json={
            "document_id": document_id,
            "reference_id": "5",
            "text": "Another root",
            "requirement_type": "mandatory",
        },
        headers=manager_headers,
    )
    assert separate_root.status_code == 201
    assert separate_root.json()["parent_id"] is None


async def test_update_requirement_reference_reassigns_parent_from_reference(
    client, manager_headers, default_jurisdiction
):
    response = await client.post(
        "/api/v1/requirements/sets",
        json={
            "jurisdiction_id": str(default_jurisdiction.id),
            "name": "Requirement Reparent Set",
            "document_type": "annex_b",
            "testing_frequency": "one_off",
        },
        headers=manager_headers,
    )
    assert response.status_code == 201
    document_id = response.json()["id"]

    parent_three = await client.post(
        "/api/v1/requirements",
        json={
            "document_id": document_id,
            "reference_id": "3",
            "text": "Section 3",
            "requirement_type": "informational",
        },
        headers=manager_headers,
    )
    assert parent_three.status_code == 201
    parent_three_payload = parent_three.json()

    left_parent = await client.post(
        "/api/v1/requirements",
        json={
            "document_id": document_id,
            "reference_id": "3.2",
            "text": "Left branch",
            "requirement_type": "informational",
        },
        headers=manager_headers,
    )
    assert left_parent.status_code == 201
    assert left_parent.json()["parent_id"] == parent_three_payload["id"]

    right_parent = await client.post(
        "/api/v1/requirements",
        json={
            "document_id": document_id,
            "reference_id": "3.4",
            "text": "Right branch",
            "requirement_type": "informational",
        },
        headers=manager_headers,
    )
    assert right_parent.status_code == 201
    right_parent_payload = right_parent.json()
    assert right_parent_payload["parent_id"] == parent_three_payload["id"]

    moving_requirement = await client.post(
        "/api/v1/requirements",
        json={
            "document_id": document_id,
            "reference_id": "3.2.5",
            "text": "Move me",
            "requirement_type": "mandatory",
        },
        headers=manager_headers,
    )
    assert moving_requirement.status_code == 201
    moving_requirement_payload = moving_requirement.json()

    update_response = await client.put(
        f"/api/v1/requirements/{moving_requirement_payload['id']}",
        json={"reference_id": "3.4.1"},
        headers=manager_headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["reference_id"] == "3.4.1"
    assert update_response.json()["parent_id"] == right_parent_payload["id"]


async def test_sync_parent_from_reference_repairs_requirement_hierarchy(
    client, manager_headers, default_jurisdiction
):
    response = await client.post(
        "/api/v1/requirements/sets",
        json={
            "jurisdiction_id": str(default_jurisdiction.id),
            "name": "Requirement Sync Set",
            "document_type": "annex_b",
            "testing_frequency": "one_off",
        },
        headers=manager_headers,
    )
    assert response.status_code == 201
    document_id = response.json()["id"]

    wrong_parent = await client.post(
        "/api/v1/requirements",
        json={
            "document_id": document_id,
            "reference_id": "3.2",
            "text": "Wrong parent",
            "requirement_type": "informational",
        },
        headers=manager_headers,
    )
    assert wrong_parent.status_code == 201
    wrong_parent_payload = wrong_parent.json()

    correct_parent = await client.post(
        "/api/v1/requirements",
        json={
            "document_id": document_id,
            "reference_id": "3.2.5",
            "text": "Correct parent",
            "requirement_type": "informational",
        },
        headers=manager_headers,
    )
    assert correct_parent.status_code == 201
    correct_parent_payload = correct_parent.json()

    child = await client.post(
        "/api/v1/requirements",
        json={
            "document_id": document_id,
            "reference_id": "3.2.5.3",
            "text": "Wrongly parented child",
            "requirement_type": "mandatory",
            "parent_id": wrong_parent_payload["id"],
        },
        headers=manager_headers,
    )
    assert child.status_code == 201
    child_payload = child.json()
    assert child_payload["parent_id"] == wrong_parent_payload["id"]

    sync_response = await client.put(
        f"/api/v1/requirements/{child_payload['id']}",
        json={"sync_parent_from_reference": True},
        headers=manager_headers,
    )
    assert sync_response.status_code == 200
    assert sync_response.json()["reference_id"] == "3.2.5.3"
    assert sync_response.json()["parent_id"] == correct_parent_payload["id"]


async def test_update_extraction_reference_reassigns_parent_from_reference(
    client, manager_headers, default_jurisdiction, db_session, manager_user
):
    document = Document(
        organization_id=manager_user.organization_id,
        jurisdiction_id=default_jurisdiction.id,
        filename="hierarchy-source.pdf",
        name="Hierarchy Source",
        document_type="annex_b",
        version=None,
        status="extracted",
        file_path="/tmp/hierarchy-source.pdf",
        uploaded_by=manager_user.id,
        testing_frequency="one_off",
    )
    db_session.add(document)
    await db_session.flush()

    extraction_run = ExtractionRun(
        document_id=document.id,
        status="completed",
        total_pages=1,
        current_page=1,
        requirements_found=4,
        ai_provider="deterministic",
        ai_model="annex_b_v2_guide",
    )
    db_session.add(extraction_run)
    await db_session.flush()
    document.current_extraction_id = extraction_run.id

    parent_three = ExtractedRequirement(
        document_id=document.id,
        extraction_run_id=extraction_run.id,
        reference_id="3",
        title="Section 3",
        text="Section 3",
        original_text="Section 3",
        requirement_type="informational",
        parent_id=None,
        page_number=1,
        confidence_score=1.0,
        status="pending",
        sort_order=0,
    )
    db_session.add(parent_three)
    await db_session.flush()

    left_parent = ExtractedRequirement(
        document_id=document.id,
        extraction_run_id=extraction_run.id,
        reference_id="3.2",
        title="Left branch",
        text="Left branch",
        original_text="Left branch",
        requirement_type="informational",
        parent_id=parent_three.id,
        page_number=1,
        confidence_score=1.0,
        status="pending",
        sort_order=1,
    )
    right_parent = ExtractedRequirement(
        document_id=document.id,
        extraction_run_id=extraction_run.id,
        reference_id="3.4",
        title="Right branch",
        text="Right branch",
        original_text="Right branch",
        requirement_type="informational",
        parent_id=parent_three.id,
        page_number=1,
        confidence_score=1.0,
        status="pending",
        sort_order=2,
    )
    db_session.add_all([left_parent, right_parent])
    await db_session.flush()

    moving_extraction = ExtractedRequirement(
        document_id=document.id,
        extraction_run_id=extraction_run.id,
        reference_id="3.2.5",
        title="Move me",
        text="Move me",
        original_text="Move me",
        requirement_type="mandatory",
        parent_id=left_parent.id,
        page_number=1,
        confidence_score=1.0,
        status="pending",
        sort_order=3,
    )
    db_session.add(moving_extraction)
    await db_session.commit()
    await db_session.refresh(right_parent)
    await db_session.refresh(moving_extraction)

    response = await client.put(
        f"/api/v1/documents/{document.id}/extractions/{moving_extraction.id}",
        json={"reference_id": "3.4.1"},
        headers=manager_headers,
    )
    assert response.status_code == 200
    assert response.json()["reference_id"] == "3.4.1"
    assert response.json()["parent_id"] == str(right_parent.id)


async def test_sync_parent_from_reference_repairs_extracted_requirement_hierarchy(
    client, manager_headers, default_jurisdiction, db_session, manager_user
):
    document = Document(
        organization_id=manager_user.organization_id,
        jurisdiction_id=default_jurisdiction.id,
        filename="hierarchy-repair.pdf",
        name="Hierarchy Repair",
        document_type="annex_b",
        version=None,
        status="extracted",
        file_path="/tmp/hierarchy-repair.pdf",
        uploaded_by=manager_user.id,
        testing_frequency="one_off",
    )
    db_session.add(document)
    await db_session.flush()

    extraction_run = ExtractionRun(
        document_id=document.id,
        status="completed",
        total_pages=1,
        current_page=1,
        requirements_found=3,
        ai_provider="deterministic",
        ai_model="annex_b_v2_guide",
    )
    db_session.add(extraction_run)
    await db_session.flush()
    document.current_extraction_id = extraction_run.id

    wrong_parent = ExtractedRequirement(
        document_id=document.id,
        extraction_run_id=extraction_run.id,
        reference_id="3.2",
        title="Wrong parent",
        text="Wrong parent",
        original_text="Wrong parent",
        requirement_type="informational",
        parent_id=None,
        page_number=1,
        confidence_score=1.0,
        status="pending",
        sort_order=0,
    )
    db_session.add(wrong_parent)
    await db_session.flush()

    correct_parent = ExtractedRequirement(
        document_id=document.id,
        extraction_run_id=extraction_run.id,
        reference_id="3.2.5",
        title="Correct parent",
        text="Correct parent",
        original_text="Correct parent",
        requirement_type="informational",
        parent_id=wrong_parent.id,
        page_number=1,
        confidence_score=1.0,
        status="pending",
        sort_order=1,
    )
    db_session.add(correct_parent)
    await db_session.flush()

    child = ExtractedRequirement(
        document_id=document.id,
        extraction_run_id=extraction_run.id,
        reference_id="3.2.5.3",
        title="Mismatched child",
        text="Mismatched child",
        original_text="Mismatched child",
        requirement_type="mandatory",
        parent_id=wrong_parent.id,
        page_number=1,
        confidence_score=1.0,
        status="pending",
        sort_order=2,
    )
    db_session.add(child)
    await db_session.commit()
    await db_session.refresh(correct_parent)
    await db_session.refresh(child)

    response = await client.put(
        f"/api/v1/documents/{document.id}/extractions/{child.id}",
        json={"sync_parent_from_reference": True},
        headers=manager_headers,
    )
    assert response.status_code == 200
    assert response.json()["reference_id"] == "3.2.5.3"
    assert response.json()["parent_id"] == str(correct_parent.id)
