import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app.models.document import Document
from app.models.program import RequirementSetVersion
from app.models import (
    BaselineMigration,
    CertificationProject,
    MaintenanceEvent,
    MaintenancePlan,
    Requirement,
    ReviewCycle,
    ReviewCycleRequirementBaseline,
    ReviewItem,
    ReviewItemComment,
    ReviewItemEvidenceFile,
    SubmissionPackage,
    User,
)
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
async def contributor_user(db_session):
    user = User(
        email="contrib@example.com",
        password_hash=hash_password("contribpass"),
        full_name="Contributor User",
        role="contributor",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def assigned_reviewer_user(db_session):
    user = User(
        email="reviewer@example.com",
        password_hash=hash_password("reviewerpass"),
        full_name="Assigned Reviewer",
        role="assigned_reviewer",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def responsible_user(db_session):
    user = User(
        email="responsible@example.com",
        password_hash=hash_password("responsiblepass"),
        full_name="Responsible User",
        role="contributor",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def test_requirement(db_session, admin_user, default_jurisdiction):
    document = Document(
        organization_id=admin_user.organization_id,
        jurisdiction_id=default_jurisdiction.id,
        filename="reviews-set.pdf",
        name="Reviews set",
        document_type="scp",
        version="1",
        status="approved",
        file_path="/tmp/reviews-set.pdf",
        uploaded_by=admin_user.id,
        approved_by=admin_user.id,
    )
    db_session.add(document)
    await db_session.flush()

    version = RequirementSetVersion(
        organization_id=admin_user.organization_id,
        document_id=document.id,
        version_number=1,
        status="approved",
        is_current=True,
        created_by=admin_user.id,
        approved_by=admin_user.id,
        approved_at=datetime.now(timezone.utc),
        locked_at=datetime.now(timezone.utc),
    )
    db_session.add(version)
    await db_session.flush()

    req = Requirement(
        jurisdiction_id=default_jurisdiction.id,
        document_id=document.id,
        requirement_set_version_id=version.id,
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
def admin_headers(admin_user):
    token = create_access_token({"sub": str(admin_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def contributor_headers(contributor_user):
    token = create_access_token({"sub": str(contributor_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def assigned_reviewer_headers(assigned_reviewer_user):
    token = create_access_token({"sub": str(assigned_reviewer_user.id)})
    return {"Authorization": f"Bearer {token}"}


async def test_create_review_cycle(client, admin_headers, test_requirement, default_jurisdiction):
    deadline = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
    response = await client.post(
        "/api/v1/review-cycles",
        headers=admin_headers,
        json={
            "name": "Q1 2024 Review",
            "description": "Quarterly compliance review",
            "jurisdiction_id": str(default_jurisdiction.id),
            "scope": "all",
            "deadline": deadline,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Q1 2024 Review"
    assert data["status"] == "active"


async def test_create_review_cycle_with_defaults(
    client,
    admin_headers,
    test_requirement,
    assigned_reviewer_user,
    responsible_user,
    default_jurisdiction,
    db_session,
):
    response = await client.post(
        "/api/v1/review-cycles",
        headers=admin_headers,
        json={
            "name": "Defaults Cycle",
            "jurisdiction_id": str(default_jurisdiction.id),
            "scope": "all",
            "default_assigned_reviewer_id": str(assigned_reviewer_user.id),
            "default_responsible_user_id": str(responsible_user.id),
        },
    )
    assert response.status_code == 201
    result = await db_session.execute(select(ReviewItem))
    item = result.scalar_one()
    assert item.assigned_reviewer_id == assigned_reviewer_user.id
    assert item.responsible_user_id == responsible_user.id


async def test_assign_responsible_by_assigned_reviewer(
    client,
    assigned_reviewer_headers,
    assigned_reviewer_user,
    responsible_user,
    db_session,
    test_requirement,
    default_jurisdiction,
):
    cycle = ReviewCycle(
        name="Assignment Cycle",
        scope="all",
        jurisdiction_id=default_jurisdiction.id,
        created_by=assigned_reviewer_user.id,
    )
    db_session.add(cycle)
    await db_session.commit()
    await db_session.refresh(cycle)

    item = ReviewItem(
        review_cycle_id=cycle.id,
        requirement_id=test_requirement.id,
        review_status="pending",
        assigned_reviewer_id=assigned_reviewer_user.id,
    )
    db_session.add(item)
    await db_session.commit()

    response = await client.put(
        f"/api/v1/review-cycles/{cycle.id}/items/{item.id}/assign",
        headers=assigned_reviewer_headers,
        json={"responsible_user_id": str(responsible_user.id)},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["responsible_user_id"] == str(responsible_user.id)


async def test_assigned_reviewer_cannot_change_assigned_reviewer(
    client,
    assigned_reviewer_headers,
    assigned_reviewer_user,
    responsible_user,
    db_session,
    test_requirement,
    default_jurisdiction,
):
    cycle = ReviewCycle(
        name="Assignment Cycle 2",
        scope="all",
        jurisdiction_id=default_jurisdiction.id,
        created_by=assigned_reviewer_user.id,
    )
    db_session.add(cycle)
    await db_session.commit()
    await db_session.refresh(cycle)

    item = ReviewItem(
        review_cycle_id=cycle.id,
        requirement_id=test_requirement.id,
        review_status="pending",
        assigned_reviewer_id=assigned_reviewer_user.id,
    )
    db_session.add(item)
    await db_session.commit()

    response = await client.put(
        f"/api/v1/review-cycles/{cycle.id}/items/{item.id}/assign",
        headers=assigned_reviewer_headers,
        json={"assigned_reviewer_id": str(responsible_user.id)},
    )
    assert response.status_code == 403


async def test_create_review_cycle_contributor_forbidden(
    client, contributor_headers, default_jurisdiction
):
    response = await client.post(
        "/api/v1/review-cycles",
        headers=contributor_headers,
        json={
            "name": "Test Review",
            "jurisdiction_id": str(default_jurisdiction.id),
            "scope": "all",
        },
    )
    assert response.status_code == 403


async def test_list_review_cycles(
    client, admin_headers, db_session, admin_user, default_jurisdiction
):
    # Create a review cycle
    cycle = ReviewCycle(
        name="Test Cycle",
        scope="all",
        jurisdiction_id=default_jurisdiction.id,
        created_by=admin_user.id,
    )
    db_session.add(cycle)
    await db_session.commit()

    response = await client.get("/api/v1/review-cycles", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) == 1


async def test_get_review_cycle_detail(
    client, admin_headers, db_session, admin_user, default_jurisdiction
):
    cycle = ReviewCycle(
        name="Test Cycle",
        scope="all",
        jurisdiction_id=default_jurisdiction.id,
        created_by=admin_user.id,
    )
    db_session.add(cycle)
    await db_session.commit()
    await db_session.refresh(cycle)

    response = await client.get(f"/api/v1/review-cycles/{cycle.id}", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Cycle"


async def test_review_cycle_detail_progress_excludes_not_applicable_status_and_restores(
    client,
    admin_headers,
    db_session,
    admin_user,
    test_requirement,
    default_jurisdiction,
):
    cycle = ReviewCycle(
        name="Scoped Progress Cycle",
        scope="all",
        jurisdiction_id=default_jurisdiction.id,
        created_by=admin_user.id,
    )
    db_session.add(cycle)
    await db_session.commit()
    await db_session.refresh(cycle)

    item = ReviewItem(
        review_cycle_id=cycle.id,
        requirement_id=test_requirement.id,
        review_status="pending",
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    not_applicable_response = await client.put(
        f"/api/v1/review-cycles/{cycle.id}/items/{item.id}",
        headers=admin_headers,
        json={"review_status": "pending", "requirement_status": "not_applicable", "review_evidence": "Product outside the agreed review scope"},
    )
    assert not_applicable_response.status_code == 200

    excluded_detail = await client.get(f"/api/v1/review-cycles/{cycle.id}", headers=admin_headers)
    assert excluded_detail.status_code == 200
    excluded_data = excluded_detail.json()
    assert excluded_data["items"][0]["requirement_current_status"] == "not_applicable"
    assert excluded_data["progress"] == {"total": 0, "completed": 0, "pending": 0}

    restored_response = await client.put(
        f"/api/v1/review-cycles/{cycle.id}/items/{item.id}",
        headers=admin_headers,
        json={"review_status": "pending", "requirement_status": "in_progress"},
    )
    assert restored_response.status_code == 200

    restored_detail = await client.get(f"/api/v1/review-cycles/{cycle.id}", headers=admin_headers)
    assert restored_detail.status_code == 200
    restored_data = restored_detail.json()
    assert restored_data["items"][0]["requirement_current_status"] == "in_progress"
    assert restored_data["progress"] == {"total": 1, "completed": 0, "pending": 1}


async def test_close_review_cycle(
    client, admin_headers, db_session, admin_user, default_jurisdiction
):
    cycle = ReviewCycle(
        name="Cycle to Close",
        scope="all",
        jurisdiction_id=default_jurisdiction.id,
        created_by=admin_user.id,
    )
    db_session.add(cycle)
    await db_session.commit()
    await db_session.refresh(cycle)

    response = await client.post(f"/api/v1/review-cycles/{cycle.id}/close", headers=admin_headers)
    assert response.status_code == 409
    assert "Add requirements" in response.text


async def test_close_review_cycle_snapshot_is_scoped_to_cycle_items(
    client, admin_headers, db_session, admin_user, default_jurisdiction
):
    requirement_in_cycle = Requirement(
        jurisdiction_id=default_jurisdiction.id,
        document_id=None,
        reference_id="REQ-IN",
        text="Requirement included in submission cycle",
        requirement_type="mandatory",
        active=True,
        version=1,
        sort_order=1,
    )
    requirement_outside_cycle = Requirement(
        jurisdiction_id=default_jurisdiction.id,
        document_id=None,
        reference_id="REQ-OUT",
        text="Requirement outside submission cycle",
        requirement_type="mandatory",
        active=True,
        version=1,
        sort_order=2,
    )
    db_session.add_all([requirement_in_cycle, requirement_outside_cycle])
    await db_session.flush()

    cycle = ReviewCycle(
        name="Cycle Scoped Snapshot",
        scope="all",
        jurisdiction_id=default_jurisdiction.id,
        created_by=admin_user.id,
    )
    db_session.add(cycle)
    await db_session.flush()

    db_session.add(
        ReviewItem(
            review_cycle_id=cycle.id,
            requirement_id=requirement_in_cycle.id,
            review_status="confirmed",
            assessment_status="evidenced",
            review_evidence="E-001 documented control test",
            reviewer_id=admin_user.id,
            reviewed_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()

    close_response = await client.post(
        f"/api/v1/review-cycles/{cycle.id}/close", headers=admin_headers
    )
    assert close_response.status_code == 200
    snapshot_id = close_response.json()["snapshot_id"]
    assert snapshot_id

    snapshot_response = await client.get(f"/api/v1/snapshots/{snapshot_id}", headers=admin_headers)
    assert snapshot_response.status_code == 200
    snapshot_data = snapshot_response.json()
    records = json.loads(snapshot_data["data_json"])
    reference_ids = {row["requirement"]["reference_id"] for row in records["rows"]}

    assert snapshot_data["total_requirements"] == 1
    assert reference_ids == {"REQ-IN"}


async def test_archive_review_cycle(
    client, admin_headers, db_session, admin_user, default_jurisdiction
):
    cycle = ReviewCycle(
        name="Cycle to Archive",
        scope="all",
        jurisdiction_id=default_jurisdiction.id,
        created_by=admin_user.id,
    )
    db_session.add(cycle)
    await db_session.commit()
    await db_session.refresh(cycle)

    response = await client.post(f"/api/v1/review-cycles/{cycle.id}/archive", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "archived"


async def test_restore_review_cycle_restores_active_status(
    client, admin_headers, db_session, admin_user, default_jurisdiction
):
    cycle = ReviewCycle(
        name="Cycle to Restore Active",
        scope="all",
        jurisdiction_id=default_jurisdiction.id,
        created_by=admin_user.id,
    )
    db_session.add(cycle)
    await db_session.commit()
    await db_session.refresh(cycle)

    archive_response = await client.post(
        f"/api/v1/review-cycles/{cycle.id}/archive",
        headers=admin_headers,
    )
    assert archive_response.status_code == 200
    assert archive_response.json()["status"] == "archived"

    restore_response = await client.post(
        f"/api/v1/review-cycles/{cycle.id}/restore",
        headers=admin_headers,
    )
    assert restore_response.status_code == 200
    restore_data = restore_response.json()
    assert restore_data["status"] == "active"
    assert restore_data["closed_at"] is None
    assert restore_data["snapshot_id"] is None


async def test_restore_review_cycle_restores_closed_status(
    client, admin_headers, db_session, admin_user, default_jurisdiction
):
    cycle = ReviewCycle(
        name="Cycle to Restore Closed",
        scope="all",
        jurisdiction_id=default_jurisdiction.id,
        created_by=admin_user.id,
    )
    db_session.add(cycle)
    await db_session.commit()
    await db_session.refresh(cycle)

    requirement = Requirement(jurisdiction_id=default_jurisdiction.id, reference_id="C-1", text="Record retention", requirement_type="mandatory")
    db_session.add(requirement)
    await db_session.flush()
    db_session.add(ReviewItem(review_cycle_id=cycle.id, requirement_id=requirement.id, assessment_status="evidenced", review_status="confirmed", review_evidence="E-001 control test", reviewer_id=admin_user.id, reviewed_at=datetime.now(timezone.utc)))
    await db_session.commit()

    close_response = await client.post(
        f"/api/v1/review-cycles/{cycle.id}/close",
        headers=admin_headers,
    )
    assert close_response.status_code == 200
    closed_data = close_response.json()
    assert closed_data["status"] == "closed"
    assert closed_data["closed_at"] is not None
    assert closed_data["snapshot_id"] is not None

    archive_response = await client.post(
        f"/api/v1/review-cycles/{cycle.id}/archive",
        headers=admin_headers,
    )
    assert archive_response.status_code == 200
    assert archive_response.json()["status"] == "archived"

    restore_response = await client.post(
        f"/api/v1/review-cycles/{cycle.id}/restore",
        headers=admin_headers,
    )
    assert restore_response.status_code == 200
    restore_data = restore_response.json()
    assert restore_data["status"] == "closed"
    assert restore_data["closed_at"] == closed_data["closed_at"]
    assert restore_data["snapshot_id"] == closed_data["snapshot_id"]


async def test_restore_review_cycle_requires_archived_status(
    client, admin_headers, db_session, admin_user, default_jurisdiction
):
    cycle = ReviewCycle(
        name="Cycle Not Archived",
        scope="all",
        jurisdiction_id=default_jurisdiction.id,
        created_by=admin_user.id,
    )
    db_session.add(cycle)
    await db_session.commit()
    await db_session.refresh(cycle)

    response = await client.post(f"/api/v1/review-cycles/{cycle.id}/restore", headers=admin_headers)
    assert response.status_code == 400
    assert response.json()["detail"] == "Review cycle is not archived"


async def test_delete_review_cycle(
    client, admin_headers, db_session, admin_user, test_requirement, default_jurisdiction
):
    cycle = ReviewCycle(
        name="Cycle to Delete",
        scope="all",
        jurisdiction_id=default_jurisdiction.id,
        created_by=admin_user.id,
    )
    db_session.add(cycle)
    await db_session.commit()
    await db_session.refresh(cycle)

    item = ReviewItem(
        review_cycle_id=cycle.id,
        requirement_id=test_requirement.id,
        review_status="pending",
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    comment = ReviewItemComment(
        review_item_id=item.id,
        author_id=admin_user.id,
        body="test comment",
    )
    db_session.add(comment)
    await db_session.commit()

    evidence_path = f"/tmp/{uuid.uuid4()}_review_evidence.txt"
    with open(evidence_path, "w", encoding="utf-8") as handle:
        handle.write("evidence")
    evidence = ReviewItemEvidenceFile(
        review_item_id=item.id,
        filename="review_evidence.txt",
        file_path=evidence_path,
        uploaded_by=admin_user.id,
    )
    db_session.add(evidence)
    await db_session.commit()

    response = await client.delete(f"/api/v1/review-cycles/{cycle.id}", headers=admin_headers)
    assert response.status_code == 204

    cycle_result = await db_session.execute(select(ReviewCycle).where(ReviewCycle.id == cycle.id))
    assert cycle_result.scalar_one_or_none() is None

    item_result = await db_session.execute(select(ReviewItem).where(ReviewItem.id == item.id))
    assert item_result.scalar_one_or_none() is None

    comment_result = await db_session.execute(
        select(ReviewItemComment).where(ReviewItemComment.review_item_id == item.id)
    )
    assert comment_result.scalar_one_or_none() is None

    evidence_result = await db_session.execute(
        select(ReviewItemEvidenceFile).where(ReviewItemEvidenceFile.review_item_id == item.id)
    )
    assert evidence_result.scalar_one_or_none() is None
    assert not os.path.exists(evidence_path)


async def test_delete_review_cycle_with_linked_records(
    client, admin_headers, db_session, admin_user, test_requirement, default_jurisdiction
):
    project = CertificationProject(
        jurisdiction_id=default_jurisdiction.id,
        name="Delete linked review project",
        stage="intake",
        status="active",
        created_by=admin_user.id,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    cycle = ReviewCycle(
        name="Cycle linked for delete",
        scope="all",
        jurisdiction_id=default_jurisdiction.id,
        certification_project_id=project.id,
        created_by=admin_user.id,
    )
    db_session.add(cycle)
    await db_session.commit()
    await db_session.refresh(cycle)

    successor = ReviewCycle(
        name="Successor cycle",
        scope="all",
        jurisdiction_id=default_jurisdiction.id,
        predecessor_cycle_id=cycle.id,
        created_by=admin_user.id,
    )
    db_session.add(successor)

    baseline = ReviewCycleRequirementBaseline(
        review_cycle_id=cycle.id,
        document_id=test_requirement.document_id,
        requirement_set_version_id=test_requirement.requirement_set_version_id,
    )
    db_session.add(baseline)

    package = SubmissionPackage(
        project_id=project.id,
        review_cycle_id=cycle.id,
        version="v1",
        created_by=admin_user.id,
    )
    db_session.add(package)

    migration = BaselineMigration(
        project_id=project.id,
        from_cycle_id=cycle.id,
        to_cycle_id=cycle.id,
        created_by=admin_user.id,
    )
    db_session.add(migration)

    maintenance_plan = MaintenancePlan(
        jurisdiction_id=default_jurisdiction.id,
        name="Linked maintenance plan",
        cadence_days=30,
    )
    db_session.add(maintenance_plan)
    await db_session.flush()

    maintenance_event = MaintenanceEvent(
        maintenance_plan_id=maintenance_plan.id,
        review_cycle_id=cycle.id,
        event_type="reminder",
    )
    db_session.add(maintenance_event)
    await db_session.commit()
    await db_session.refresh(successor)
    await db_session.refresh(package)
    await db_session.refresh(migration)
    await db_session.refresh(maintenance_event)

    response = await client.delete(f"/api/v1/review-cycles/{cycle.id}", headers=admin_headers)
    assert response.status_code == 204

    cycle_result = await db_session.execute(select(ReviewCycle).where(ReviewCycle.id == cycle.id))
    assert cycle_result.scalar_one_or_none() is None

    await db_session.refresh(successor)
    assert successor.predecessor_cycle_id is None

    baseline_result = await db_session.execute(
        select(ReviewCycleRequirementBaseline).where(
            ReviewCycleRequirementBaseline.review_cycle_id == cycle.id
        )
    )
    assert baseline_result.scalar_one_or_none() is None

    await db_session.refresh(package)
    assert package.review_cycle_id is None

    await db_session.refresh(migration)
    assert migration.from_cycle_id is None
    assert migration.to_cycle_id is None

    await db_session.refresh(maintenance_event)
    assert maintenance_event.review_cycle_id is None


async def test_archive_review_cycle_contributor_forbidden(
    client, contributor_headers, db_session, admin_user, default_jurisdiction
):
    cycle = ReviewCycle(
        name="Contributor Archive Forbidden",
        scope="all",
        jurisdiction_id=default_jurisdiction.id,
        created_by=admin_user.id,
    )
    db_session.add(cycle)
    await db_session.commit()

    response = await client.post(
        f"/api/v1/review-cycles/{cycle.id}/archive", headers=contributor_headers
    )
    assert response.status_code == 403


async def test_restore_review_cycle_contributor_forbidden(
    client, contributor_headers, db_session, admin_user, default_jurisdiction
):
    cycle = ReviewCycle(
        name="Contributor Restore Forbidden",
        scope="all",
        jurisdiction_id=default_jurisdiction.id,
        status="archived",
        created_by=admin_user.id,
    )
    db_session.add(cycle)
    await db_session.commit()

    response = await client.post(
        f"/api/v1/review-cycles/{cycle.id}/restore",
        headers=contributor_headers,
    )
    assert response.status_code == 403


async def test_delete_review_cycle_contributor_forbidden(
    client, contributor_headers, db_session, admin_user, default_jurisdiction
):
    cycle = ReviewCycle(
        name="Contributor Delete Forbidden",
        scope="all",
        jurisdiction_id=default_jurisdiction.id,
        created_by=admin_user.id,
    )
    db_session.add(cycle)
    await db_session.commit()

    response = await client.delete(f"/api/v1/review-cycles/{cycle.id}", headers=contributor_headers)
    assert response.status_code == 403


async def test_create_snapshot(client, admin_headers, test_requirement):
    response = await client.post(
        "/api/v1/snapshots",
        headers=admin_headers,
        json={
            "name": "Q1 2024 Snapshot",
            "description": "Compliance snapshot for Q1",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Q1 2024 Snapshot"
    assert data["total_requirements"] >= 0


async def test_informational_items_get_system_comment(
    client, admin_headers, db_session, admin_user, default_jurisdiction, test_requirement
):
    req = Requirement(
        jurisdiction_id=default_jurisdiction.id,
        document_id=test_requirement.document_id,
        requirement_set_version_id=test_requirement.requirement_set_version_id,
        reference_id="REQ-INFO-1",
        text="Informational requirement",
        requirement_type="informational",
        active=True,
        version=1,
        sort_order=0,
    )
    db_session.add(req)
    await db_session.commit()

    response = await client.post(
        "/api/v1/review-cycles",
        headers=admin_headers,
        json={
            "name": "Info Review",
            "jurisdiction_id": str(default_jurisdiction.id),
            "scope": "all",
        },
    )
    assert response.status_code == 201
    cycle_id = response.json()["id"]

    detail = await client.get(f"/api/v1/review-cycles/{cycle_id}", headers=admin_headers)
    assert detail.status_code == 200
    data = detail.json()
    info_item = next(
        item for item in data["items"] if item["requirement"]["requirement_type"] == "informational"
    )
    assert info_item["comments"]
    assert info_item["comments"][0]["author_name"] == "System"
    assert info_item["comments"][0]["created_at"]


async def test_review_item_comment_create_and_edit_window(
    client,
    admin_headers,
    admin_user,
    db_session,
    test_requirement,
    default_jurisdiction,
):
    response = await client.post(
        "/api/v1/review-cycles",
        headers=admin_headers,
        json={
            "name": "Comment Cycle",
            "jurisdiction_id": str(default_jurisdiction.id),
            "scope": "all",
        },
    )
    assert response.status_code == 201
    cycle_id = response.json()["id"]

    result = await db_session.execute(
        select(ReviewItem).where(ReviewItem.review_cycle_id == uuid.UUID(cycle_id))
    )
    item = result.scalar_one()

    create_response = await client.post(
        f"/api/v1/review-cycles/{cycle_id}/items/{item.id}/comments",
        headers=admin_headers,
        json={"body": "Initial comment"},
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["author_name"] == admin_user.full_name
    assert created["created_at"]
    assert created["can_edit"] is True

    comment_id = created["id"]
    edit_response = await client.put(
        f"/api/v1/review-cycles/{cycle_id}/items/{item.id}/comments/{comment_id}",
        headers=admin_headers,
        json={"body": "Updated comment"},
    )
    assert edit_response.status_code == 200
    edited = edit_response.json()
    assert edited["body"] == "Updated comment"

    result = await db_session.execute(
        select(ReviewItemComment).where(ReviewItemComment.id == uuid.UUID(comment_id))
    )
    comment = result.scalar_one()
    comment.created_at = datetime.now(timezone.utc) - timedelta(minutes=16)
    await db_session.commit()

    expired_response = await client.put(
        f"/api/v1/review-cycles/{cycle_id}/items/{item.id}/comments/{comment_id}",
        headers=admin_headers,
        json={"body": "Too late"},
    )
    assert expired_response.status_code == 403


async def test_comment_mentions_email_recipients_with_item_link(
    client, admin_headers, admin_user, assigned_reviewer_user, responsible_user,
    db_session, test_requirement, default_jurisdiction, monkeypatch,
):
    from app.config import settings
    from app.models.organization import Organization

    monkeypatch.setattr(settings, "email_mode", "disabled")
    monkeypatch.setattr(settings, "frontend_base_url", "https://cap.example.com/cap/")
    monkeypatch.setattr(settings, "installation_operator_ids", [str(admin_user.id)])
    saved = await client.put(
        "/api/v1/admin/installation-settings/email", headers=admin_headers,
        json={
            "revision": 0, "mode": "smtp", "smtp_host": "smtp.saved.test",
            "smtp_port": 465, "smtp_user": "", "smtp_from": "noreply@example.com",
            "smtp_security": "ssl",
        },
    )
    assert saved.status_code == 200
    smtp = MagicMock()
    monkeypatch.setattr("app.services.email.smtplib.SMTP_SSL", smtp)
    monkeypatch.setattr("app.services.email.smtplib.SMTP", smtp)
    send = smtp.return_value.__enter__.return_value.send_message

    # Full names emitted by the UI may include accents and punctuation.
    responsible_user.full_name = "José O'Neill"
    org = Organization(name="Other organisation", code="other")
    db_session.add(org)
    await db_session.flush()
    db_session.add_all([
        User(email="inactive@example.com", full_name="Inactive User", active=False,
             password_hash=admin_user.password_hash),
        User(email="outside@example.com", full_name="Outside User", organization_id=org.id,
             password_hash=admin_user.password_hash),
        User(email="prefix@example.com", full_name="José", password_hash=admin_user.password_hash),
    ])
    cycle = ReviewCycle(
        name="Mention Cycle", scope="all", jurisdiction_id=default_jurisdiction.id,
        created_by=admin_user.id,
    )
    db_session.add(cycle)
    await db_session.flush()
    item = ReviewItem(review_cycle_id=cycle.id, requirement_id=test_requirement.id)
    db_session.add(item)
    await db_session.commit()

    endpoint = f"/api/v1/review-cycles/{cycle.id}/items/{item.id}/comments"
    body = (
        "@José O'Neill please check this. Again @responsible@example.com.\n"
        "@Admin User @Inactive User @Outside User\n"
        "reviewer@example.com https://example.com/@reviewer @reviewer-extra"
    )
    created = await client.post(endpoint, headers=admin_headers, json={"body": body})
    assert created.status_code == 201
    assert send.call_count == 1
    email = send.call_args.args[0]
    assert str(email["To"]) == responsible_user.email
    assert str(email["Subject"]) == "You were mentioned in review cycle: Mention Cycle"
    assert "Admin User mentioned you" in email.get_content()
    assert body in email.get_content()
    link = f"https://cap.example.com/cap/review-cycles/{cycle.id}?mode=focus&item={item.id}"
    assert link in email.get_content()
    assert smtp.call_args.args == ("smtp.saved.test", 465)

    comment_url = f"{endpoint}/{created.json()['id']}"
    # Changing a name to another alias for the same person must not resend.
    edited = await client.put(comment_url, headers=admin_headers, json={
        "body": "@responsible thanks. @Assigned Reviewer please check this next.",
    })
    assert edited.status_code == 200
    assert send.call_count == 2
    email = send.call_args.args[0]
    assert str(email["To"]) == assigned_reviewer_user.email
    assert link in email.get_content()
    assert "@Assigned Reviewer please check this next." in email.get_content()

    edited = await client.put(comment_url, headers=admin_headers, json={
        "body": "@responsible @reviewer@example.com just a wording correction.",
    })
    assert edited.status_code == 200
    assert send.call_count == 2

    preference_response = await client.patch(
        "/api/v1/auth/notification-settings",
        headers={"Authorization": f"Bearer {create_access_token({'sub': str(assigned_reviewer_user.id)})}"},
        json={"review_mentions": False, "review_reminders": True},
    )
    assert preference_response.status_code == 200
    opted_out = await client.post(endpoint, headers=admin_headers, json={
        "body": "@Assigned Reviewer please check this new comment.",
    })
    assert opted_out.status_code == 201
    assert send.call_count == 2

    restored = await client.patch(
        "/api/v1/auth/notification-settings",
        headers={"Authorization": f"Bearer {create_access_token({'sub': str(assigned_reviewer_user.id)})}"},
        json={"review_mentions": True, "review_reminders": True},
    )
    assert restored.status_code == 200
    disabled = await client.put(
        "/api/v1/admin/installation-settings/email", headers=admin_headers,
        json={"revision": 1, "mode": "disabled"},
    )
    assert disabled.status_code == 200
    created = await client.post(endpoint, headers=admin_headers, json={
        "body": "@Assigned Reviewer email is disabled, but save the comment.",
    })
    assert created.status_code == 201
    assert send.call_count == 2


async def test_review_item_evidence_files_upload_download_delete(
    client,
    admin_headers,
    admin_user,
    db_session,
    test_requirement,
    default_jurisdiction,
):
    response = await client.post(
        "/api/v1/review-cycles",
        headers=admin_headers,
        json={
            "name": "File Cycle",
            "jurisdiction_id": str(default_jurisdiction.id),
            "scope": "all",
        },
    )
    assert response.status_code == 201
    cycle_id = response.json()["id"]

    result = await db_session.execute(
        select(ReviewItem).where(ReviewItem.review_cycle_id == uuid.UUID(cycle_id))
    )
    item = result.scalar_one()

    upload_response = await client.post(
        f"/api/v1/review-cycles/{cycle_id}/items/{item.id}/files",
        headers=admin_headers,
        files={"file": ("evidence.txt", b"evidence content", "text/plain")},
    )
    assert upload_response.status_code == 201
    file_data = upload_response.json()
    assert file_data["filename"] == "evidence.txt"

    download_response = await client.get(
        f"/api/v1/review-cycles/{cycle_id}/items/{item.id}/files/{file_data['id']}/download",
        headers=admin_headers,
    )
    assert download_response.status_code == 200
    assert download_response.content == b"evidence content"

    delete_response = await client.delete(
        f"/api/v1/review-cycles/{cycle_id}/items/{item.id}/files/{file_data['id']}",
        headers=admin_headers,
    )
    assert delete_response.status_code == 204

    result = await db_session.execute(
        select(ReviewItemEvidenceFile).where(
            ReviewItemEvidenceFile.id == uuid.UUID(file_data["id"])
        )
    )
    assert result.scalar_one_or_none() is None


async def test_review_item_evidence_file_preview_only_allows_images(
    client,
    admin_headers,
    admin_user,
    db_session,
    test_requirement,
    default_jurisdiction,
):
    response = await client.post(
        "/api/v1/review-cycles",
        headers=admin_headers,
        json={
            "name": "Preview Cycle",
            "jurisdiction_id": str(default_jurisdiction.id),
            "scope": "all",
        },
    )
    assert response.status_code == 201
    cycle_id = response.json()["id"]

    result = await db_session.execute(
        select(ReviewItem).where(ReviewItem.review_cycle_id == uuid.UUID(cycle_id))
    )
    item = result.scalar_one()

    png_bytes = b"\x89PNG\r\n\x1a\npng-data"
    upload_response = await client.post(
        f"/api/v1/review-cycles/{cycle_id}/items/{item.id}/files",
        headers=admin_headers,
        files={"file": ("evidence.png", png_bytes, "image/png")},
    )
    assert upload_response.status_code == 201
    image_file = upload_response.json()

    preview_response = await client.get(
        f"/api/v1/review-cycles/{cycle_id}/items/{item.id}/files/{image_file['id']}/preview",
        headers=admin_headers,
    )
    assert preview_response.status_code == 200
    assert preview_response.content == png_bytes
    assert preview_response.headers["content-type"].startswith("image/png")
    assert "content-disposition" not in preview_response.headers

    text_upload_response = await client.post(
        f"/api/v1/review-cycles/{cycle_id}/items/{item.id}/files",
        headers=admin_headers,
        files={"file": ("evidence.txt", b"plain text", "text/plain")},
    )
    assert text_upload_response.status_code == 201
    text_file = text_upload_response.json()

    text_preview_response = await client.get(
        f"/api/v1/review-cycles/{cycle_id}/items/{item.id}/files/{text_file['id']}/preview",
        headers=admin_headers,
    )
    assert text_preview_response.status_code == 400
    assert text_preview_response.json()["detail"] == "Evidence file is not previewable"


async def test_review_item_evidence_file_preview_respects_assigned_reviewer_scope(
    client,
    admin_headers,
    assigned_reviewer_headers,
    assigned_reviewer_user,
    admin_user,
    db_session,
    test_requirement,
    default_jurisdiction,
):
    cycle = ReviewCycle(
        name="Assigned Preview Cycle",
        scope="all",
        jurisdiction_id=default_jurisdiction.id,
        created_by=admin_user.id,
    )
    db_session.add(cycle)
    await db_session.commit()
    await db_session.refresh(cycle)

    allowed_item = ReviewItem(
        review_cycle_id=cycle.id,
        requirement_id=test_requirement.id,
        review_status="pending",
        assigned_reviewer_id=assigned_reviewer_user.id,
    )
    blocked_item = ReviewItem(
        review_cycle_id=cycle.id,
        requirement_id=test_requirement.id,
        review_status="pending",
        assigned_reviewer_id=admin_user.id,
    )
    db_session.add_all([allowed_item, blocked_item])
    await db_session.commit()
    await db_session.refresh(allowed_item)
    await db_session.refresh(blocked_item)

    png_bytes = b"\x89PNG\r\n\x1a\npng-data"
    allowed_upload = await client.post(
        f"/api/v1/review-cycles/{cycle.id}/items/{allowed_item.id}/files",
        headers=admin_headers,
        files={"file": ("allowed.png", png_bytes, "image/png")},
    )
    assert allowed_upload.status_code == 201
    allowed_file_id = allowed_upload.json()["id"]

    blocked_upload = await client.post(
        f"/api/v1/review-cycles/{cycle.id}/items/{blocked_item.id}/files",
        headers=admin_headers,
        files={"file": ("blocked.png", png_bytes, "image/png")},
    )
    assert blocked_upload.status_code == 201
    blocked_file_id = blocked_upload.json()["id"]

    allowed_preview = await client.get(
        f"/api/v1/review-cycles/{cycle.id}/items/{allowed_item.id}/files/{allowed_file_id}/preview",
        headers=assigned_reviewer_headers,
    )
    assert allowed_preview.status_code == 200

    blocked_preview = await client.get(
        f"/api/v1/review-cycles/{cycle.id}/items/{blocked_item.id}/files/{blocked_file_id}/preview",
        headers=assigned_reviewer_headers,
    )
    assert blocked_preview.status_code == 403
    assert (
        blocked_preview.json()["detail"]
        == "You can only preview files for review items assigned to you"
    )


async def test_update_review_item_does_not_clear_evidence(
    client,
    admin_headers,
    admin_user,
    db_session,
    test_requirement,
    default_jurisdiction,
):
    response = await client.post(
        "/api/v1/review-cycles",
        headers=admin_headers,
        json={
            "name": "Evidence Cycle",
            "jurisdiction_id": str(default_jurisdiction.id),
            "scope": "all",
        },
    )
    assert response.status_code == 201
    cycle_id = response.json()["id"]

    result = await db_session.execute(
        select(ReviewItem).where(ReviewItem.review_cycle_id == uuid.UUID(cycle_id))
    )
    item = result.scalar_one()
    item.review_evidence = "Keep me"
    await db_session.commit()

    update_response = await client.put(
        f"/api/v1/review-cycles/{cycle_id}/items/{item.id}",
        headers=admin_headers,
        json={"review_status": "confirmed"},
    )
    assert update_response.status_code == 200

    await db_session.refresh(item)
    assert item.review_evidence == "Keep me"


async def test_reminders_include_responsible_users(
    client,
    admin_headers,
    admin_user,
    assigned_reviewer_user,
    responsible_user,
    db_session,
    test_requirement,
    default_jurisdiction,
    monkeypatch,
):
    from app.config import settings
    import app.api.reviews as reviews_api

    monkeypatch.setattr(settings, "email_mode", "disabled")
    monkeypatch.setattr(settings, "installation_operator_ids", [str(admin_user.id)])
    saved = await client.put(
        "/api/v1/admin/installation-settings/email",
        headers=admin_headers,
        json={
            "revision": 0, "mode": "smtp", "smtp_host": "smtp.saved.test",
            "smtp_port": 465, "smtp_user": "saved-user",
            "smtp_from": "noreply@example.com", "smtp_security": "ssl",
            "password": "saved-test-password",
        },
    )
    assert saved.status_code == 200

    sent_to: list[list[str]] = []

    def fake_send_email(to_emails, subject, body, *, config):
        assert config.smtp_host == "smtp.saved.test"
        assert config.smtp_password == "saved-test-password"
        assert config.smtp_use_ssl and not config.smtp_use_tls
        sent_to.append(list(to_emails))

    monkeypatch.setattr(reviews_api, "send_email", fake_send_email)

    cycle = ReviewCycle(
        name="Reminder Cycle",
        scope="all",
        jurisdiction_id=default_jurisdiction.id,
        created_by=admin_user.id,
    )
    db_session.add(cycle)
    await db_session.commit()
    await db_session.refresh(cycle)

    item = ReviewItem(
        review_cycle_id=cycle.id,
        requirement_id=test_requirement.id,
        review_status="pending",
        assigned_reviewer_id=assigned_reviewer_user.id,
        responsible_user_id=responsible_user.id,
    )
    db_session.add(item)
    await db_session.commit()

    response = await client.post(
        f"/api/v1/review-cycles/{cycle.id}/remind-assigned",
        headers=admin_headers,
        json={"review_statuses": ["pending"]},
    )
    assert response.status_code == 200
    recipients = {email for group in sent_to for email in group}
    assert assigned_reviewer_user.email in recipients
    assert responsible_user.email in recipients

    preferences = await client.patch(
        "/api/v1/auth/notification-settings",
        headers={"Authorization": f"Bearer {create_access_token({'sub': str(assigned_reviewer_user.id)})}"},
        json={"review_mentions": True, "review_reminders": False},
    )
    assert preferences.status_code == 200
    sent_to.clear()
    response = await client.post(
        f"/api/v1/review-cycles/{cycle.id}/remind-assigned",
        headers=admin_headers,
        json={"review_statuses": ["pending"]},
    )
    assert response.status_code == 200
    assert sent_to == [[responsible_user.email]]
