import os
import csv
import io
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text
from typing import Optional

from app.models import (
    Organization,
    Requirement,
    ReviewCycle,
    ReviewItem,
    ReviewItemComment,
    ReviewItemEvidenceFile,
    User,
)
from app.models.program import CertificationProject
from app.schemas.program import ProjectMigrationChangedDecision
from app.services.review_migration import (
    ReviewMigrationDecisionError,
    compare_baseline_requirements,
    resolve_project_changed_decisions,
    should_carry_forward_requirement,
)
from app.services.auth import create_access_token, hash_password


@pytest.fixture
async def baseline_admin_user(db_session):
    user = User(
        email="baseline-admin@example.com",
        password_hash=hash_password("testpass"),
        full_name="Baseline Admin",
        role="admin",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def baseline_admin_headers(baseline_admin_user):
    token = create_access_token({"sub": str(baseline_admin_user.id)})
    return {"Authorization": f"Bearer {token}"}


def _cycle_items_by_reference(cycle_detail: dict) -> dict[str, dict]:
    return {item["requirement"]["reference_id"]: item for item in cycle_detail["items"]}


def test_project_changed_decisions_distinguish_duplicate_references_across_sets():
    first_id, second_id = uuid.uuid4(), uuid.uuid4()
    changed = [
        {"new_requirement_id": str(first_id), "reference_id": "R-1"},
        {"new_requirement_id": str(second_id), "reference_id": "R-1"},
    ]
    decisions = [ProjectMigrationChangedDecision(new_requirement_id=first_id, action="carry_forward")]
    resolved = resolve_project_changed_decisions(changed, decisions)
    assert set(resolved) == {first_id}
    assert resolved[first_id] == "carry_forward"
    with pytest.raises(ReviewMigrationDecisionError) as ambiguous:
        resolve_project_changed_decisions(
            changed, [ProjectMigrationChangedDecision(reference_id="R-1", action="carry_forward")]
        )
    assert "one changed requirement" in str(ambiguous.value)


def test_migration_comparison_tracks_renames_changes_additions_and_removals():
    document_id = uuid.uuid4()
    cycle_id = uuid.uuid4()
    old_changed = Requirement(id=uuid.uuid4(), document_id=document_id, reference_id="R-1", text="Old", requirement_type="mandatory")
    old_removed = Requirement(id=uuid.uuid4(), document_id=document_id, reference_id="R-2", text="Removed", requirement_type="mandatory")
    old_matched = Requirement(id=uuid.uuid4(), document_id=document_id, reference_id="R-3", text="Same", requirement_type="mandatory")
    previous = {
        (document_id, requirement.reference_id): (
            ReviewItem(id=uuid.uuid4(), review_cycle_id=cycle_id, requirement_id=requirement.id),
            requirement,
        )
        for requirement in (old_changed, old_removed, old_matched)
    }
    target_changed = Requirement(
        id=uuid.uuid4(), document_id=document_id, reference_id="R-1A", text="New",
        requirement_type="mandatory", source_requirement_id=old_changed.id,
    )
    target_added = Requirement(id=uuid.uuid4(), document_id=document_id, reference_id="R-4", text="Added", requirement_type="mandatory")
    target_matched = Requirement(id=uuid.uuid4(), document_id=document_id, reference_id="R-3", text="Same", requirement_type="mandatory")
    comparison = compare_baseline_requirements(
        (target_changed, target_added, target_matched), previous, {document_id: "Set A"}
    )

    assert [item.reference_id for item in comparison.changed] == ["R-1A"]
    assert comparison.changed[0].old_requirement_id == old_changed.id
    assert [item.reference_id for item in comparison.added] == ["R-4"]
    assert [item.reference_id for item in comparison.matched] == ["R-3"]
    assert [item.reference_id for item in comparison.removed] == ["R-2"]
    assert should_carry_forward_requirement(target_changed, old_changed, {}) is False
    assert should_carry_forward_requirement(target_changed, old_changed, {target_changed.id: "carry_forward"}) is True
    assert should_carry_forward_requirement(target_matched, old_matched, {}) is True
    reclassified = Requirement(
        id=uuid.uuid4(), document_id=document_id, reference_id="R-3",
        text="Same", requirement_type="recommended",
    )
    assert [item.reference_id for item in compare_baseline_requirements(
        (reclassified,), {(document_id, "R-3"): previous[(document_id, "R-3")]}, {}
    ).changed] == ["R-3"]
    assert should_carry_forward_requirement(reclassified, old_matched, {}) is False


async def _assign_and_set_requirement_status(
    client,
    headers,
    requirement_id: str,
    assigned_to: str,
    assign_comment: str,
    status: str,
    status_comment: str,
):
    assign_resp = await client.put(
        f"/api/v1/requirements/{requirement_id}/assign",
        json={"assigned_to": assigned_to, "comment": assign_comment},
        headers=headers,
    )
    assert assign_resp.status_code == 200

    status_resp = await client.put(
        f"/api/v1/requirements/{requirement_id}/status",
        json={"status": status, "comment": status_comment},
        headers=headers,
    )
    assert status_resp.status_code == 200
    return status_resp.json()


async def _create_review_item_comment(
    client,
    headers,
    cycle_id: str,
    item_id: str,
    body: str,
):
    response = await client.post(
        f"/api/v1/review-cycles/{cycle_id}/items/{item_id}/comments",
        json={"body": body},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


async def _age_review_item_comment(
    db_session,
    comment_id: str,
    *,
    minutes_old: int = 16,
) -> dict[str, str]:
    result = await db_session.execute(
        select(ReviewItemComment).where(ReviewItemComment.id == uuid.UUID(comment_id))
    )
    comment = result.scalar_one()
    aged_timestamp = (datetime.now(timezone.utc) - timedelta(minutes=minutes_old)).replace(
        microsecond=0
    )
    comment.created_at = aged_timestamp
    comment.updated_at = aged_timestamp
    await db_session.commit()
    return {
        "created_at": aged_timestamp.replace(tzinfo=None).isoformat(),
        "updated_at": aged_timestamp.replace(tzinfo=None).isoformat(),
    }


async def _upload_review_item_file(
    client,
    headers,
    cycle_id: str,
    item_id: str,
    *,
    filename: str,
    content: bytes,
    content_type: str,
    description: Optional[str] = None,
):
    response = await client.post(
        f"/api/v1/review-cycles/{cycle_id}/items/{item_id}/files",
        headers=headers,
        data={"description": description} if description is not None else None,
        files={"file": (filename, content, content_type)},
    )
    assert response.status_code == 201
    return response.json()


async def _set_review_item_jira_fields(db_session, item_id: str) -> dict[str, Optional[str]]:
    result = await db_session.execute(select(ReviewItem).where(ReviewItem.id == uuid.UUID(item_id)))
    item = result.scalar_one()
    jira_updated_at = datetime(2025, 1, 2, 12, 30, tzinfo=timezone.utc)
    jira_synced_at = datetime(2025, 1, 3, 9, 15, tzinfo=timezone.utc)
    item.jira_issue_key = "OPS-42"
    item.jira_issue_url = "https://jira.example.com/browse/OPS-42"
    item.jira_status = "In Progress"
    item.jira_summary = "Follow up migrated review evidence"
    item.jira_assignee = "Baseline Admin"
    item.jira_priority = "High"
    item.jira_updated_at = jira_updated_at
    item.jira_synced_at = jira_synced_at
    item.jira_sync_error = "Previous sync warning"
    await db_session.commit()
    return {
        "jira_issue_key": item.jira_issue_key,
        "jira_issue_url": item.jira_issue_url,
        "jira_status": item.jira_status,
        "jira_summary": item.jira_summary,
        "jira_assignee": item.jira_assignee,
        "jira_priority": item.jira_priority,
        "jira_updated_at": jira_updated_at.replace(tzinfo=None).isoformat(),
        "jira_synced_at": jira_synced_at.replace(tzinfo=None).isoformat(),
        "jira_sync_error": item.jira_sync_error,
    }


async def _create_and_approve_manual_set(
    client,
    headers,
    jurisdiction_id: str,
    name: str,
    requirements=None,
) -> tuple[str, str]:
    set_resp = await client.post(
        "/api/v1/requirements/sets",
        json={
            "jurisdiction_id": jurisdiction_id,
            "name": name,
            "document_type": "annex_b",
            "testing_frequency": "monthly",
        },
        headers=headers,
    )
    assert set_resp.status_code == 201
    document_id = set_resp.json()["id"]

    requirement_payloads = requirements or [
        {
            "reference_id": "R-1",
            "title": "Requirement 1",
            "text": "Maintain controls",
            "requirement_type": "mandatory",
        }
    ]
    for index, requirement in enumerate(requirement_payloads, start=1):
        req_resp = await client.post(
            "/api/v1/requirements",
            json={
                "document_id": document_id,
                "reference_id": requirement["reference_id"],
                "title": requirement.get("title") or f"Requirement {index}",
                "text": requirement["text"],
                "requirement_type": requirement.get("requirement_type", "mandatory"),
            },
            headers=headers,
        )
        assert req_resp.status_code == 201

    versions_resp = await client.get(
        f"/api/v1/requirements/sets/{document_id}/versions",
        headers=headers,
    )
    assert versions_resp.status_code == 200
    draft_version_id = versions_resp.json()["items"][0]["id"]

    submit_resp = await client.post(
        f"/api/v1/requirements/sets/{document_id}/versions/{draft_version_id}/submit",
        json={},
        headers=headers,
    )
    assert submit_resp.status_code == 200

    approve_resp = await client.post(
        f"/api/v1/requirements/sets/{document_id}/versions/{draft_version_id}/approve",
        json={},
        headers=headers,
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["is_current"] is True
    return document_id, draft_version_id


async def test_locked_version_rejects_edit_and_clone_creates_editable_draft(
    client,
    baseline_admin_headers,
    default_jurisdiction,
):
    document_id, approved_version_id = await _create_and_approve_manual_set(
        client,
        baseline_admin_headers,
        str(default_jurisdiction.id),
        "Baseline set",
    )

    requirements_resp = await client.get(
        f"/api/v1/requirements?document_id={document_id}&limit=100",
        headers=baseline_admin_headers,
    )
    assert requirements_resp.status_code == 200
    requirement_id = requirements_resp.json()["items"][0]["id"]

    locked_update_resp = await client.put(
        f"/api/v1/requirements/{requirement_id}",
        json={"text": "Updated locked requirement"},
        headers=baseline_admin_headers,
    )
    assert locked_update_resp.status_code == 409

    clone_resp = await client.post(
        f"/api/v1/requirements/sets/{document_id}/versions/clone",
        json={"source_version_id": approved_version_id},
        headers=baseline_admin_headers,
    )
    assert clone_resp.status_code == 201
    assert clone_resp.json()["status"] == "draft"

    draft_requirements_resp = await client.get(
        f"/api/v1/requirements?document_id={document_id}&limit=100",
        headers=baseline_admin_headers,
    )
    assert draft_requirements_resp.status_code == 200
    draft_requirement_id = draft_requirements_resp.json()["items"][0]["id"]

    editable_update_resp = await client.put(
        f"/api/v1/requirements/{draft_requirement_id}",
        json={"text": "Updated draft requirement"},
        headers=baseline_admin_headers,
    )
    assert editable_update_resp.status_code == 200
    assert editable_update_resp.json()["text"] == "Updated draft requirement"


async def test_project_can_start_without_baseline_but_cannot_start_assessment(
    client,
    baseline_admin_headers,
    default_jurisdiction,
):
    response = await client.post(
        "/api/v1/certification-projects",
        json={
            "jurisdiction_id": str(default_jurisdiction.id),
            "name": "Project without baseline",
            "stage": "intake",
            "status": "active",
        },
        headers=baseline_admin_headers,
    )
    assert response.status_code == 201, response.text
    project = response.json()
    assert project["baseline_versions"] == []
    assert project["requirement_set_ids"] == []
    assessment = await client.post(
        f"/api/v1/certification-projects/{project['id']}/submission-cycle",
        headers=baseline_admin_headers,
    )
    assert assessment.status_code == 409
    assert "baseline" in str(assessment.json()["detail"]).lower()


async def test_project_baseline_update_rejects_empty_selection(
    client,
    baseline_admin_headers,
    default_jurisdiction,
):
    document_id, _ = await _create_and_approve_manual_set(
        client,
        baseline_admin_headers,
        str(default_jurisdiction.id),
        "Baseline set for update",
    )
    project_resp = await client.post(
        "/api/v1/certification-projects",
        json={
            "jurisdiction_id": str(default_jurisdiction.id),
            "name": "Baseline update project",
            "stage": "intake",
            "status": "active",
            "requirement_set_ids": [document_id],
        },
        headers=baseline_admin_headers,
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    update_resp = await client.put(
        f"/api/v1/certification-projects/{project_id}/baseline",
        json={"requirement_set_ids": []},
        headers=baseline_admin_headers,
    )
    assert update_resp.status_code == 400


async def test_submission_cycle_rejects_legacy_project_without_baseline(
    client,
    db_session,
    baseline_admin_user,
    baseline_admin_headers,
    default_jurisdiction,
):
    legacy_project = CertificationProject(
        organization_id=baseline_admin_user.organization_id,
        source_document_id=None,
        jurisdiction_id=default_jurisdiction.id,
        name="Legacy empty baseline project",
        description=None,
        stage="intake",
        status="active",
        owner_id=None,
        created_by=baseline_admin_user.id,
    )
    db_session.add(legacy_project)
    await db_session.commit()
    await db_session.refresh(legacy_project)

    response = await client.post(
        f"/api/v1/certification-projects/{legacy_project.id}/submission-cycle",
        headers=baseline_admin_headers,
    )
    assert response.status_code == 409


async def test_review_cycle_creation_requires_resolvable_baselines(
    client,
    baseline_admin_headers,
    default_jurisdiction,
):
    response = await client.post(
        "/api/v1/review-cycles",
        json={
            "name": "No baseline cycle",
            "jurisdiction_id": str(default_jurisdiction.id),
            "scope": "all",
        },
        headers=baseline_admin_headers,
    )
    assert response.status_code == 400


async def test_project_baseline_pins_submission_cycle_items(
    client,
    baseline_admin_headers,
    default_jurisdiction,
):
    document_id, _ = await _create_and_approve_manual_set(
        client,
        baseline_admin_headers,
        str(default_jurisdiction.id),
        "Project baseline set",
    )

    project_resp = await client.post(
        "/api/v1/certification-projects",
        json={
            "jurisdiction_id": str(default_jurisdiction.id),
            "name": "Baseline Project",
            "stage": "intake",
            "status": "active",
            "requirement_set_ids": [document_id],
        },
        headers=baseline_admin_headers,
    )
    assert project_resp.status_code == 201
    project = project_resp.json()
    assert project["requirement_set_ids"] == [document_id]
    assert len(project["baseline_versions"]) == 1

    ensure_cycle_resp = await client.post(
        f"/api/v1/certification-projects/{project['id']}/submission-cycle",
        headers=baseline_admin_headers,
    )
    assert ensure_cycle_resp.status_code == 200
    ensure_payload = ensure_cycle_resp.json()
    assert ensure_payload["created"] is True
    assert ensure_payload["review_items_created"] == 1

    cycle_detail_resp = await client.get(
        f"/api/v1/review-cycles/{ensure_payload['review_cycle_id']}",
        headers=baseline_admin_headers,
    )
    assert cycle_detail_resp.status_code == 200
    cycle_detail = cycle_detail_resp.json()
    assert len(cycle_detail["baseline_versions"]) == 1
    assert len(cycle_detail["items"]) == 1


async def test_baseline_migration_preview_and_execute_carry_forward(
    client,
    db_session,
    monkeypatch,
    baseline_admin_user,
    baseline_admin_headers,
    default_jurisdiction,
):
    document_id, approved_v1_id = await _create_and_approve_manual_set(
        client,
        baseline_admin_headers,
        str(default_jurisdiction.id),
        "Migration set",
        requirements=[
            {
                "reference_id": "R-1",
                "title": "Requirement 1",
                "text": "Maintain controls",
                "requirement_type": "mandatory",
            },
            {
                "reference_id": "R-2",
                "title": "Requirement 2",
                "text": "Maintain logs",
                "requirement_type": "mandatory",
            },
        ],
    )

    project_resp = await client.post(
        "/api/v1/certification-projects",
        json={
            "jurisdiction_id": str(default_jurisdiction.id),
            "name": "Migration Project",
            "stage": "intake",
            "status": "active",
            "requirement_set_ids": [document_id],
        },
        headers=baseline_admin_headers,
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    cycle_resp = await client.post(
        f"/api/v1/certification-projects/{project_id}/submission-cycle",
        headers=baseline_admin_headers,
    )
    assert cycle_resp.status_code == 200
    cycle_id = cycle_resp.json()["review_cycle_id"]
    # SQLite does not create the PostgreSQL-only partial index from the migration.
    # Install its equivalent here so the successor insert checks the same ordering.
    await db_session.execute(text(
        "CREATE UNIQUE INDEX test_active_submission_per_project "
        "ON review_cycles(certification_project_id) "
        "WHERE cycle_type = 'submission' AND status <> 'archived' "
        "AND certification_project_id IS NOT NULL"
    ))
    await db_session.commit()

    cycle_detail_resp = await client.get(
        f"/api/v1/review-cycles/{cycle_id}",
        headers=baseline_admin_headers,
    )
    assert cycle_detail_resp.status_code == 200
    cycle_detail = cycle_detail_resp.json()
    original_items = _cycle_items_by_reference(cycle_detail)
    original_changed_item = original_items["R-1"]
    original_unchanged_item = original_items["R-2"]

    await _assign_and_set_requirement_status(
        client,
        baseline_admin_headers,
        original_changed_item["requirement"]["id"],
        str(baseline_admin_user.id),
        "Assign changed requirement",
        "in_progress",
        "Changed requirement in progress",
    )
    await _assign_and_set_requirement_status(
        client,
        baseline_admin_headers,
        original_unchanged_item["requirement"]["id"],
        str(baseline_admin_user.id),
        "Assign unchanged requirement",
        "evidenced",
        "Unchanged requirement evidenced",
    )

    changed_comment = await _create_review_item_comment(
        client,
        baseline_admin_headers,
        cycle_id,
        original_changed_item["id"],
        "Changed carried comment",
    )
    changed_comment_timestamps = await _age_review_item_comment(
        db_session,
        changed_comment["id"],
    )
    changed_file = await _upload_review_item_file(
        client,
        baseline_admin_headers,
        cycle_id,
        original_changed_item["id"],
        filename="changed-proof.png",
        content=b"changed proof bytes",
        content_type="image/png",
        description="Changed screenshot",
    )
    changed_jira_fields = await _set_review_item_jira_fields(
        db_session,
        original_changed_item["id"],
    )

    update_item_resp = await client.put(
        f"/api/v1/review-cycles/{cycle_id}/items/{original_changed_item['id']}",
        json={"review_status": "updated", "requirement_status": "in_progress",
              "review_evidence": "Carried evidence"},
        headers=baseline_admin_headers,
    )
    assert update_item_resp.status_code == 200

    unchanged_comment = await _create_review_item_comment(
        client,
        baseline_admin_headers,
        cycle_id,
        original_unchanged_item["id"],
        "Unchanged carried comment",
    )
    unchanged_file = await _upload_review_item_file(
        client,
        baseline_admin_headers,
        cycle_id,
        original_unchanged_item["id"],
        filename="unchanged-proof.txt",
        content=b"unchanged proof bytes",
        content_type="text/plain",
        description="Unchanged attachment",
    )
    linked_file = await db_session.get(ReviewItemEvidenceFile, uuid.UUID(unchanged_file["id"]))
    linked_file.comment_id = uuid.UUID(unchanged_comment["id"])
    await db_session.commit()
    unchanged_update_item_resp = await client.put(
        f"/api/v1/review-cycles/{cycle_id}/items/{original_unchanged_item['id']}",
        json={"review_status": "confirmed", "requirement_status": "evidenced",
              "review_evidence": "Unchanged evidence"},
        headers=baseline_admin_headers,
    )
    assert unchanged_update_item_resp.status_code == 200

    clone_resp = await client.post(
        f"/api/v1/requirements/sets/{document_id}/versions/clone",
        json={"source_version_id": approved_v1_id},
        headers=baseline_admin_headers,
    )
    assert clone_resp.status_code == 201
    draft_v2_id = clone_resp.json()["id"]

    draft_requirements_resp = await client.get(
        f"/api/v1/requirements?document_id={document_id}&limit=100",
        headers=baseline_admin_headers,
    )
    assert draft_requirements_resp.status_code == 200
    draft_requirements = {
        item["reference_id"]: item for item in draft_requirements_resp.json()["items"]
    }

    change_reference_resp = await client.put(
        f"/api/v1/requirements/{draft_requirements['R-1']['id']}",
        json={"reference_id": "R-1A", "text": "Maintain controls (updated)"},
        headers=baseline_admin_headers,
    )
    assert change_reference_resp.status_code == 200

    submit_v2_resp = await client.post(
        f"/api/v1/requirements/sets/{document_id}/versions/{draft_v2_id}/submit",
        json={},
        headers=baseline_admin_headers,
    )
    assert submit_v2_resp.status_code == 200
    approve_v2_resp = await client.post(
        f"/api/v1/requirements/sets/{document_id}/versions/{draft_v2_id}/approve",
        json={},
        headers=baseline_admin_headers,
    )
    assert approve_v2_resp.status_code == 200

    preview_resp = await client.post(
        f"/api/v1/certification-projects/{project_id}/baseline-migrations/preview",
        json={"from_cycle_id": cycle_id, "requirement_set_ids": [document_id]},
        headers=baseline_admin_headers,
    )
    assert preview_resp.status_code == 200
    preview = preview_resp.json()
    assert preview["from_cycle_id"] == cycle_id
    assert len(preview["changed"]) >= 1

    async def no_current_approved_version(_db, _document_id):
        return None

    with monkeypatch.context() as patch:
        patch.setattr(
            "app.api.program.get_current_approved_version_for_document",
            no_current_approved_version,
        )
        stale_execute_resp = await client.post(
            f"/api/v1/certification-projects/{project_id}/baseline-migrations/execute",
            json={"migration_id": preview["migration_id"]},
            headers=baseline_admin_headers,
        )
    assert stale_execute_resp.status_code == 409
    assert "changed after preview" in stale_execute_resp.json()["detail"]

    other_org = Organization(code=f"other-{uuid.uuid4().hex[:10]}", name="Other organization")
    db_session.add(other_org)
    await db_session.flush()
    other_admin = User(
        email=f"other-{uuid.uuid4().hex[:10]}@example.com",
        password_hash=hash_password("testpass"),
        full_name="Other Admin",
        role="admin",
        organization_id=other_org.id,
    )
    db_session.add(other_admin)
    await db_session.commit()
    other_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': str(other_admin.id)})}"
    }
    cross_org_execute_resp = await client.post(
        f"/api/v1/certification-projects/{project_id}/baseline-migrations/execute",
        json={"migration_id": preview["migration_id"]},
        headers=other_headers,
    )
    assert cross_org_execute_resp.status_code == 404

    invalid_decision_resp = await client.post(
        f"/api/v1/certification-projects/{project_id}/baseline-migrations/execute",
        json={
            "migration_id": preview["migration_id"],
            "changed_decisions": [{"new_requirement_id": str(uuid.uuid4()), "action": "carry_forward"}],
        },
        headers=baseline_admin_headers,
    )
    assert invalid_decision_resp.status_code == 400
    assert invalid_decision_resp.json()["detail"] == "Changed requirement ID is not in the preview"

    execute_resp = await client.post(
        f"/api/v1/certification-projects/{project_id}/baseline-migrations/execute",
        json={
            "migration_id": preview["migration_id"],
            "changed_decisions": [{"new_requirement_id": preview["changed"][0]["new_requirement_id"], "action": "carry_forward"}],
        },
        headers=baseline_admin_headers,
    )
    assert execute_resp.status_code == 200
    execute = execute_resp.json()
    assert execute["created"] is True
    assert execute["from_cycle_id"] == cycle_id

    migrated_cycle_resp = await client.get(
        f"/api/v1/review-cycles/{execute['to_cycle_id']}",
        headers=baseline_admin_headers,
    )
    assert migrated_cycle_resp.status_code == 200
    migrated_cycle = migrated_cycle_resp.json()
    assert migrated_cycle["predecessor_cycle_id"] == cycle_id
    migrated_items = _cycle_items_by_reference(migrated_cycle)
    changed_migrated_item = migrated_items["R-1A"]
    unchanged_migrated_item = migrated_items["R-2"]

    assert changed_migrated_item["review_status"] == "pending"
    assert changed_migrated_item["review_evidence"] == "Carried evidence"
    assert changed_migrated_item["requirement_current_status"] == "not_started"
    assert changed_migrated_item["jira_issue_key"] == changed_jira_fields["jira_issue_key"]
    assert changed_migrated_item["jira_issue_url"] == changed_jira_fields["jira_issue_url"]
    assert changed_migrated_item["jira_status"] == changed_jira_fields["jira_status"]
    assert changed_migrated_item["jira_summary"] == changed_jira_fields["jira_summary"]
    assert changed_migrated_item["jira_assignee"] == changed_jira_fields["jira_assignee"]
    assert changed_migrated_item["jira_priority"] == changed_jira_fields["jira_priority"]
    assert changed_migrated_item["jira_updated_at"] == changed_jira_fields["jira_updated_at"]
    assert changed_migrated_item["jira_synced_at"] == changed_jira_fields["jira_synced_at"]
    assert changed_migrated_item["jira_sync_error"] == changed_jira_fields["jira_sync_error"]
    assert len(changed_migrated_item["comments"]) == 1
    assert changed_migrated_item["comments"][0]["body"] == "Changed carried comment"
    assert (
        changed_migrated_item["comments"][0]["created_at"]
        == changed_comment_timestamps["created_at"]
    )
    assert (
        changed_migrated_item["comments"][0]["updated_at"]
        == changed_comment_timestamps["updated_at"]
    )
    assert changed_migrated_item["comments"][0]["can_edit"] is False
    assert len(changed_migrated_item["evidence_files"]) == 1
    assert changed_migrated_item["evidence_files"][0]["filename"] == "changed-proof.png"
    assert changed_migrated_item["evidence_files"][0]["description"] == "Changed screenshot"
    assert changed_migrated_item["evidence_files"][0]["uploaded_at"] == changed_file["uploaded_at"]

    assert unchanged_migrated_item["review_status"] == "confirmed"
    assert unchanged_migrated_item["review_evidence"] == "Unchanged evidence"
    assert unchanged_migrated_item["requirement_current_status"] == "evidenced"
    assert len(unchanged_migrated_item["comments"]) == 1
    assert unchanged_migrated_item["comments"][0]["body"] == unchanged_comment["body"]
    assert len(unchanged_migrated_item["evidence_files"]) == 1
    assert unchanged_migrated_item["evidence_files"][0]["filename"] == "unchanged-proof.txt"
    assert unchanged_migrated_item["evidence_files"][0]["comment_id"] == unchanged_migrated_item["comments"][0]["id"]
    assert unchanged_migrated_item["comments"][0]["id"] != unchanged_comment["id"]
    assert unchanged_migrated_item["evidence_files"][0]["description"] == "Unchanged attachment"
    assert (
        unchanged_migrated_item["evidence_files"][0]["uploaded_at"] == unchanged_file["uploaded_at"]
    )

    changed_requirement_resp = await client.get(
        f"/api/v1/requirements/{changed_migrated_item['requirement']['id']}",
        headers=baseline_admin_headers,
    )
    assert changed_requirement_resp.status_code == 200
    changed_requirement = changed_requirement_resp.json()
    assert changed_requirement["current_status"] is None
    assert changed_requirement["status_history"] == []
    assert migrated_cycle["readiness"]["can_close"] is False

    gap_response = await client.get(
        f"/api/v1/reports/gap-analysis?review_cycle_id={execute['to_cycle_id']}&format=csv",
        headers=baseline_admin_headers,
    )
    assert gap_response.status_code == 200
    gap_rows = {row["Reference ID"]: row for row in csv.DictReader(io.StringIO(gap_response.text))}
    assert gap_rows["R-1A"]["Requirement Status"] == "not_started"
    assert gap_rows["R-1A"]["Review Complete"] == "No"
    assert "Record the review decision" in gap_rows["R-1A"]["Gap Reasons / Next Actions"]

    unchanged_requirement_resp = await client.get(
        f"/api/v1/requirements/{unchanged_migrated_item['requirement']['id']}",
        headers=baseline_admin_headers,
    )
    assert unchanged_requirement_resp.status_code == 200
    unchanged_requirement = unchanged_requirement_resp.json()
    assert unchanged_requirement["current_status"] == "evidenced"
    assert unchanged_requirement["assigned_to"] == str(baseline_admin_user.id)
    assert len(unchanged_requirement["status_history"]) == 1
    assert (
        unchanged_requirement["status_history"][0]["comment"] == "Unchanged evidence"
    )

    changed_download_resp = await client.get(
        f"/api/v1/review-cycles/{execute['to_cycle_id']}/items/{changed_migrated_item['id']}/files/{changed_migrated_item['evidence_files'][0]['id']}/download",
        headers=baseline_admin_headers,
    )
    assert changed_download_resp.status_code == 200
    assert changed_download_resp.content == b"changed proof bytes"

    delete_predecessor_resp = await client.delete(
        f"/api/v1/review-cycles/{cycle_id}",
        headers=baseline_admin_headers,
    )
    assert delete_predecessor_resp.status_code == 204

    changed_download_after_delete_resp = await client.get(
        f"/api/v1/review-cycles/{execute['to_cycle_id']}/items/{changed_migrated_item['id']}/files/{changed_migrated_item['evidence_files'][0]['id']}/download",
        headers=baseline_admin_headers,
    )
    assert changed_download_after_delete_resp.status_code == 200
    assert changed_download_after_delete_resp.content == b"changed proof bytes"


async def test_review_cycle_migration_releases_active_submission_index(
    client, db_session, baseline_admin_headers, default_jurisdiction,
):
    document_id, approved_v1_id = await _create_and_approve_manual_set(
        client, baseline_admin_headers, str(default_jurisdiction.id), "Indexed submission migration"
    )
    project = await client.post(
        "/api/v1/certification-projects",
        json={"jurisdiction_id": str(default_jurisdiction.id), "name": "Indexed submission",
              "requirement_set_ids": [document_id]},
        headers=baseline_admin_headers,
    )
    assert project.status_code == 201, project.text
    cycle = await client.post(
        f"/api/v1/certification-projects/{project.json()['id']}/submission-cycle",
        headers=baseline_admin_headers,
    )
    assert cycle.status_code == 200, cycle.text
    cycle_id = cycle.json()["review_cycle_id"]
    await db_session.execute(text(
        "CREATE UNIQUE INDEX test_active_submission_per_project "
        "ON review_cycles(certification_project_id) "
        "WHERE cycle_type = 'submission' AND status <> 'archived' "
        "AND certification_project_id IS NOT NULL"
    ))
    await db_session.commit()

    cloned = await client.post(
        f"/api/v1/requirements/sets/{document_id}/versions/clone",
        json={"source_version_id": approved_v1_id}, headers=baseline_admin_headers,
    )
    assert cloned.status_code == 201, cloned.text
    draft_id = cloned.json()["id"]
    listed = await client.get(
        f"/api/v1/requirements?document_id={document_id}&limit=100",
        headers=baseline_admin_headers,
    )
    draft_requirement_id = listed.json()["items"][0]["id"]
    assert (await client.put(
        f"/api/v1/requirements/{draft_requirement_id}",
        json={"text": "Updated wording"}, headers=baseline_admin_headers,
    )).status_code == 200
    assert (await client.post(
        f"/api/v1/requirements/sets/{document_id}/versions/{draft_id}/submit",
        json={}, headers=baseline_admin_headers,
    )).status_code == 200
    assert (await client.post(
        f"/api/v1/requirements/sets/{document_id}/versions/{draft_id}/approve",
        json={}, headers=baseline_admin_headers,
    )).status_code == 200

    preview = await client.post(
        f"/api/v1/review-cycles/{cycle_id}/baseline-migrations/preview",
        headers=baseline_admin_headers,
    )
    assert preview.status_code == 200, preview.text
    executed = await client.post(
        f"/api/v1/review-cycles/{cycle_id}/baseline-migrations/execute",
        json={"target_version_ids": preview.json()["target_version_ids"], "changed_decisions": []},
        headers=baseline_admin_headers,
    )
    assert executed.status_code == 200, executed.text
    predecessor = await client.get(f"/api/v1/review-cycles/{cycle_id}", headers=baseline_admin_headers)
    assert predecessor.json()["status"] == "archived"
    successor = await client.get(
        f"/api/v1/review-cycles/{executed.json()['to_cycle_id']}", headers=baseline_admin_headers,
    )
    assert successor.json()["status"] == "active"


async def test_review_cycle_latest_migration_preview_and_execute(
    client,
    db_session,
    baseline_admin_user,
    baseline_admin_headers,
    default_jurisdiction,
):
    document_id, approved_v1_id = await _create_and_approve_manual_set(
        client,
        baseline_admin_headers,
        str(default_jurisdiction.id),
        "Operational migration set",
    )

    cycle_resp = await client.post(
        "/api/v1/review-cycles",
        json={
            "name": "Operational migration cycle",
            "jurisdiction_id": str(default_jurisdiction.id),
            "scope": "documents",
            "document_ids": [document_id],
        },
        headers=baseline_admin_headers,
    )
    assert cycle_resp.status_code == 201
    cycle_id = cycle_resp.json()["id"]

    initial_cycle_detail_resp = await client.get(
        f"/api/v1/review-cycles/{cycle_id}",
        headers=baseline_admin_headers,
    )
    assert initial_cycle_detail_resp.status_code == 200
    initial_cycle = initial_cycle_detail_resp.json()
    initial_items = _cycle_items_by_reference(initial_cycle)
    assert initial_cycle["baseline_versions"][0]["version_number"] == 1
    assert initial_cycle["baseline_versions"][0]["is_latest"] is True
    assert (
        initial_cycle["baseline_versions"][0]["latest_requirement_set_version_id"] == approved_v1_id
    )
    assert initial_cycle["baseline_versions"][0]["latest_version_number"] == 1
    original_item = initial_items["R-1"]

    await _assign_and_set_requirement_status(
        client,
        baseline_admin_headers,
        original_item["requirement"]["id"],
        str(baseline_admin_user.id),
        "Assign operational requirement",
        "in_progress",
        "Operational requirement in progress",
    )
    carried_comment = await _create_review_item_comment(
        client,
        baseline_admin_headers,
        cycle_id,
        original_item["id"],
        "Operational carried comment",
    )
    carried_comment_timestamps = await _age_review_item_comment(
        db_session,
        carried_comment["id"],
    )
    carried_file = await _upload_review_item_file(
        client,
        baseline_admin_headers,
        cycle_id,
        original_item["id"],
        filename="operational-evidence.txt",
        content=b"operational evidence bytes",
        content_type="text/plain",
        description="Operational attachment",
    )
    jira_fields = await _set_review_item_jira_fields(
        db_session,
        original_item["id"],
    )

    initial_cycle_list_resp = await client.get(
        f"/api/v1/review-cycles?jurisdiction_id={default_jurisdiction.id}&limit=100",
        headers=baseline_admin_headers,
    )
    assert initial_cycle_list_resp.status_code == 200
    initial_cycle_list_item = next(
        item for item in initial_cycle_list_resp.json()["items"] if item["id"] == cycle_id
    )
    assert initial_cycle_list_item["baseline_versions"][0]["is_latest"] is True
    assert (
        initial_cycle_list_item["baseline_versions"][0]["latest_requirement_set_version_id"]
        == approved_v1_id
    )
    assert initial_cycle_list_item["baseline_versions"][0]["latest_version_number"] == 1

    update_item_resp = await client.put(
        f"/api/v1/review-cycles/{cycle_id}/items/{original_item['id']}",
        json={"review_status": "updated", "review_evidence": "Carry forward me", "requirement_status": "in_progress"},
        headers=baseline_admin_headers,
    )
    assert update_item_resp.status_code == 200

    clone_resp = await client.post(
        f"/api/v1/requirements/sets/{document_id}/versions/clone",
        json={"source_version_id": approved_v1_id},
        headers=baseline_admin_headers,
    )
    assert clone_resp.status_code == 201
    draft_v2_id = clone_resp.json()["id"]

    draft_requirements_resp = await client.get(
        f"/api/v1/requirements?document_id={document_id}&limit=100",
        headers=baseline_admin_headers,
    )
    assert draft_requirements_resp.status_code == 200
    draft_requirement_id = draft_requirements_resp.json()["items"][0]["id"]

    update_requirement_resp = await client.put(
        f"/api/v1/requirements/{draft_requirement_id}",
        json={"text": "Maintain controls with updated wording"},
        headers=baseline_admin_headers,
    )
    assert update_requirement_resp.status_code == 200

    submit_v2_resp = await client.post(
        f"/api/v1/requirements/sets/{document_id}/versions/{draft_v2_id}/submit",
        json={},
        headers=baseline_admin_headers,
    )
    assert submit_v2_resp.status_code == 200
    approve_v2_resp = await client.post(
        f"/api/v1/requirements/sets/{document_id}/versions/{draft_v2_id}/approve",
        json={},
        headers=baseline_admin_headers,
    )
    assert approve_v2_resp.status_code == 200
    approved_v2_id = approve_v2_resp.json()["id"]

    stale_cycle_detail_resp = await client.get(
        f"/api/v1/review-cycles/{cycle_id}",
        headers=baseline_admin_headers,
    )
    assert stale_cycle_detail_resp.status_code == 200
    stale_cycle = stale_cycle_detail_resp.json()
    assert stale_cycle["baseline_versions"][0]["version_number"] == 1
    assert stale_cycle["baseline_versions"][0]["is_latest"] is False
    assert (
        stale_cycle["baseline_versions"][0]["latest_requirement_set_version_id"] == approved_v2_id
    )
    assert stale_cycle["baseline_versions"][0]["latest_version_number"] == 2

    stale_cycle_list_resp = await client.get(
        f"/api/v1/review-cycles?jurisdiction_id={default_jurisdiction.id}&limit=100",
        headers=baseline_admin_headers,
    )
    assert stale_cycle_list_resp.status_code == 200
    stale_cycle_list_item = next(
        item for item in stale_cycle_list_resp.json()["items"] if item["id"] == cycle_id
    )
    assert stale_cycle_list_item["baseline_versions"][0]["is_latest"] is False
    assert (
        stale_cycle_list_item["baseline_versions"][0]["latest_requirement_set_version_id"]
        == approved_v2_id
    )
    assert stale_cycle_list_item["baseline_versions"][0]["latest_version_number"] == 2

    preview_resp = await client.post(
        f"/api/v1/review-cycles/{cycle_id}/baseline-migrations/preview",
        headers=baseline_admin_headers,
    )
    assert preview_resp.status_code == 200
    preview = preview_resp.json()
    assert preview["source_cycle_id"] == cycle_id
    assert preview["target_version_ids"] == [approved_v2_id]
    assert len(preview["changed"]) == 1
    assert preview["changed"][0]["reference_id"] == "R-1"

    execute_resp = await client.post(
        f"/api/v1/review-cycles/{cycle_id}/baseline-migrations/execute",
        json={
            "target_version_ids": preview["target_version_ids"],
            "changed_decisions": [
                {
                    "new_requirement_id": preview["changed"][0]["new_requirement_id"],
                    "action": "carry_forward",
                }
            ],
        },
        headers=baseline_admin_headers,
    )
    assert execute_resp.status_code == 200
    execute = execute_resp.json()
    assert execute["created"] is True
    assert execute["from_cycle_id"] == cycle_id

    archived_cycle_resp = await client.get(
        f"/api/v1/review-cycles/{cycle_id}",
        headers=baseline_admin_headers,
    )
    assert archived_cycle_resp.status_code == 200
    assert archived_cycle_resp.json()["status"] == "archived"
    archived_preview_resp = await client.post(
        f"/api/v1/review-cycles/{cycle_id}/baseline-migrations/preview",
        headers=baseline_admin_headers,
    )
    assert archived_preview_resp.status_code == 409

    migrated_cycle_resp = await client.get(
        f"/api/v1/review-cycles/{execute['to_cycle_id']}",
        headers=baseline_admin_headers,
    )
    assert migrated_cycle_resp.status_code == 200
    migrated_cycle = migrated_cycle_resp.json()
    assert migrated_cycle["predecessor_cycle_id"] == cycle_id
    assert migrated_cycle["baseline_versions"][0]["version_number"] == 2
    assert migrated_cycle["baseline_versions"][0]["is_latest"] is True
    migrated_item = migrated_cycle["items"][0]
    assert migrated_item["review_status"] == "pending"
    migrated_stored_item = await db_session.get(ReviewItem, uuid.UUID(migrated_item["id"]))
    assert migrated_stored_item.assessment_status == "not_started"
    assert migrated_stored_item.assessment_rationale is None
    assert migrated_stored_item.reviewer_id is None
    assert migrated_stored_item.reviewed_at is None
    assert migrated_item["review_evidence"] == "Carry forward me"
    assert migrated_item["requirement_current_status"] == "not_started"
    assert migrated_item["jira_issue_key"] == jira_fields["jira_issue_key"]
    assert migrated_item["jira_issue_url"] == jira_fields["jira_issue_url"]
    assert migrated_item["jira_status"] == jira_fields["jira_status"]
    assert migrated_item["jira_summary"] == jira_fields["jira_summary"]
    assert migrated_item["jira_assignee"] == jira_fields["jira_assignee"]
    assert migrated_item["jira_priority"] == jira_fields["jira_priority"]
    assert migrated_item["jira_updated_at"] == jira_fields["jira_updated_at"]
    assert migrated_item["jira_synced_at"] == jira_fields["jira_synced_at"]
    assert migrated_item["jira_sync_error"] == jira_fields["jira_sync_error"]
    assert migrated_cycle["progress"]["pending"] == 1
    assert len(migrated_item["comments"]) == 1
    assert migrated_item["comments"][0]["body"] == "Operational carried comment"
    assert migrated_item["comments"][0]["created_at"] == carried_comment_timestamps["created_at"]
    assert migrated_item["comments"][0]["updated_at"] == carried_comment_timestamps["updated_at"]
    assert migrated_item["comments"][0]["can_edit"] is False
    assert len(migrated_item["evidence_files"]) == 1
    assert migrated_item["evidence_files"][0]["filename"] == "operational-evidence.txt"
    assert migrated_item["evidence_files"][0]["description"] == "Operational attachment"
    assert migrated_item["evidence_files"][0]["uploaded_at"] == carried_file["uploaded_at"]

    migrated_requirement_resp = await client.get(
        f"/api/v1/requirements/{migrated_item['requirement']['id']}",
        headers=baseline_admin_headers,
    )
    assert migrated_requirement_resp.status_code == 200
    migrated_requirement = migrated_requirement_resp.json()
    assert migrated_requirement["current_status"] is None
    assert migrated_requirement["status_history"] == []
    assert migrated_cycle["readiness"]["can_close"] is False

    migrated_download_resp = await client.get(
        f"/api/v1/review-cycles/{execute['to_cycle_id']}/items/{migrated_item['id']}/files/{migrated_item['evidence_files'][0]['id']}/download",
        headers=baseline_admin_headers,
    )
    assert migrated_download_resp.status_code == 200
    assert migrated_download_resp.content == b"operational evidence bytes"


async def test_review_cycle_latest_migration_reset_pending_starts_changed_requirement_fresh(
    client,
    db_session,
    baseline_admin_user,
    baseline_admin_headers,
    default_jurisdiction,
):
    document_id, approved_v1_id = await _create_and_approve_manual_set(
        client,
        baseline_admin_headers,
        str(default_jurisdiction.id),
        "Reset migration set",
    )

    cycle_resp = await client.post(
        "/api/v1/review-cycles",
        json={
            "name": "Reset migration cycle",
            "jurisdiction_id": str(default_jurisdiction.id),
            "scope": "documents",
            "document_ids": [document_id],
        },
        headers=baseline_admin_headers,
    )
    assert cycle_resp.status_code == 201
    cycle_id = cycle_resp.json()["id"]

    cycle_detail_resp = await client.get(
        f"/api/v1/review-cycles/{cycle_id}",
        headers=baseline_admin_headers,
    )
    assert cycle_detail_resp.status_code == 200
    original_item = _cycle_items_by_reference(cycle_detail_resp.json())["R-1"]

    await _assign_and_set_requirement_status(
        client,
        baseline_admin_headers,
        original_item["requirement"]["id"],
        str(baseline_admin_user.id),
        "Assign reset requirement",
        "in_progress",
        "Reset requirement in progress",
    )

    update_item_resp = await client.put(
        f"/api/v1/review-cycles/{cycle_id}/items/{original_item['id']}",
        json={"review_status": "updated", "review_evidence": "Do not carry forward"},
        headers=baseline_admin_headers,
    )
    assert update_item_resp.status_code == 200
    await _create_review_item_comment(
        client,
        baseline_admin_headers,
        cycle_id,
        original_item["id"],
        "Reset me",
    )
    await _upload_review_item_file(
        client,
        baseline_admin_headers,
        cycle_id,
        original_item["id"],
        filename="reset-proof.txt",
        content=b"reset me",
        content_type="text/plain",
        description="Reset attachment",
    )
    await _set_review_item_jira_fields(
        db_session,
        original_item["id"],
    )

    clone_resp = await client.post(
        f"/api/v1/requirements/sets/{document_id}/versions/clone",
        json={"source_version_id": approved_v1_id},
        headers=baseline_admin_headers,
    )
    assert clone_resp.status_code == 201
    draft_v2_id = clone_resp.json()["id"]

    draft_requirements_resp = await client.get(
        f"/api/v1/requirements?document_id={document_id}&limit=100",
        headers=baseline_admin_headers,
    )
    assert draft_requirements_resp.status_code == 200
    draft_requirement_id = draft_requirements_resp.json()["items"][0]["id"]

    update_requirement_resp = await client.put(
        f"/api/v1/requirements/{draft_requirement_id}",
        json={"text": "Maintain controls with reset wording"},
        headers=baseline_admin_headers,
    )
    assert update_requirement_resp.status_code == 200

    submit_v2_resp = await client.post(
        f"/api/v1/requirements/sets/{document_id}/versions/{draft_v2_id}/submit",
        json={},
        headers=baseline_admin_headers,
    )
    assert submit_v2_resp.status_code == 200
    approve_v2_resp = await client.post(
        f"/api/v1/requirements/sets/{document_id}/versions/{draft_v2_id}/approve",
        json={},
        headers=baseline_admin_headers,
    )
    assert approve_v2_resp.status_code == 200

    preview_resp = await client.post(
        f"/api/v1/review-cycles/{cycle_id}/baseline-migrations/preview",
        headers=baseline_admin_headers,
    )
    assert preview_resp.status_code == 200
    preview = preview_resp.json()
    assert len(preview["changed"]) == 1

    execute_resp = await client.post(
        f"/api/v1/review-cycles/{cycle_id}/baseline-migrations/execute",
        json={
            "target_version_ids": preview["target_version_ids"],
            "changed_decisions": [
                {
                    "new_requirement_id": preview["changed"][0]["new_requirement_id"],
                    "action": "reset_pending",
                }
            ],
        },
        headers=baseline_admin_headers,
    )
    assert execute_resp.status_code == 200
    execute = execute_resp.json()

    migrated_cycle_resp = await client.get(
        f"/api/v1/review-cycles/{execute['to_cycle_id']}",
        headers=baseline_admin_headers,
    )
    assert migrated_cycle_resp.status_code == 200
    migrated_cycle = migrated_cycle_resp.json()
    migrated_item = migrated_cycle["items"][0]
    assert migrated_item["review_status"] == "pending"
    assert migrated_item["review_evidence"] is None
    assert migrated_item["requirement_current_status"] == "not_started"
    assert migrated_item["comments"] == []
    assert migrated_item["evidence_files"] == []
    assert migrated_item["jira_issue_key"] is None
    assert migrated_item["jira_issue_url"] is None
    assert migrated_item["jira_status"] is None
    assert migrated_item["jira_summary"] is None
    assert migrated_item["jira_assignee"] is None
    assert migrated_item["jira_priority"] is None
    assert migrated_item["jira_updated_at"] is None
    assert migrated_item["jira_synced_at"] is None
    assert migrated_item["jira_sync_error"] is None

    migrated_requirement_resp = await client.get(
        f"/api/v1/requirements/{migrated_item['requirement']['id']}",
        headers=baseline_admin_headers,
    )
    assert migrated_requirement_resp.status_code == 200
    migrated_requirement = migrated_requirement_resp.json()
    assert migrated_requirement["current_status"] is None
    assert migrated_requirement["status_history"] == []


async def test_review_cycle_latest_migration_fails_when_source_evidence_file_is_missing(
    client,
    db_session,
    baseline_admin_headers,
    default_jurisdiction,
):
    document_id, approved_v1_id = await _create_and_approve_manual_set(
        client,
        baseline_admin_headers,
        str(default_jurisdiction.id),
        "Missing evidence migration set",
    )

    cycle_resp = await client.post(
        "/api/v1/review-cycles",
        json={
            "name": "Missing evidence migration cycle",
            "jurisdiction_id": str(default_jurisdiction.id),
            "scope": "documents",
            "document_ids": [document_id],
        },
        headers=baseline_admin_headers,
    )
    assert cycle_resp.status_code == 201
    cycle_id = cycle_resp.json()["id"]

    cycle_detail_resp = await client.get(
        f"/api/v1/review-cycles/{cycle_id}",
        headers=baseline_admin_headers,
    )
    assert cycle_detail_resp.status_code == 200
    original_item = _cycle_items_by_reference(cycle_detail_resp.json())["R-1"]

    upload_resp = await _upload_review_item_file(
        client,
        baseline_admin_headers,
        cycle_id,
        original_item["id"],
        filename="missing-proof.txt",
        content=b"missing evidence bytes",
        content_type="text/plain",
        description="Missing attachment",
    )

    clone_resp = await client.post(
        f"/api/v1/requirements/sets/{document_id}/versions/clone",
        json={"source_version_id": approved_v1_id},
        headers=baseline_admin_headers,
    )
    assert clone_resp.status_code == 201
    draft_v2_id = clone_resp.json()["id"]

    draft_requirements_resp = await client.get(
        f"/api/v1/requirements?document_id={document_id}&limit=100",
        headers=baseline_admin_headers,
    )
    assert draft_requirements_resp.status_code == 200
    draft_requirement_id = draft_requirements_resp.json()["items"][0]["id"]

    update_requirement_resp = await client.put(
        f"/api/v1/requirements/{draft_requirement_id}",
        json={"text": "Maintain controls but require migration"},
        headers=baseline_admin_headers,
    )
    assert update_requirement_resp.status_code == 200

    submit_v2_resp = await client.post(
        f"/api/v1/requirements/sets/{document_id}/versions/{draft_v2_id}/submit",
        json={},
        headers=baseline_admin_headers,
    )
    assert submit_v2_resp.status_code == 200
    approve_v2_resp = await client.post(
        f"/api/v1/requirements/sets/{document_id}/versions/{draft_v2_id}/approve",
        json={},
        headers=baseline_admin_headers,
    )
    assert approve_v2_resp.status_code == 200

    file_result = await db_session.execute(
        select(ReviewItemEvidenceFile).where(
            ReviewItemEvidenceFile.id == uuid.UUID(upload_resp["id"])
        )
    )
    evidence_file = file_result.scalar_one()
    os.remove(evidence_file.file_path)

    preview_resp = await client.post(
        f"/api/v1/review-cycles/{cycle_id}/baseline-migrations/preview",
        headers=baseline_admin_headers,
    )
    assert preview_resp.status_code == 200
    preview = preview_resp.json()
    assert len(preview["changed"]) == 1

    execute_resp = await client.post(
        f"/api/v1/review-cycles/{cycle_id}/baseline-migrations/execute",
        json={
            "target_version_ids": preview["target_version_ids"],
            "changed_decisions": [
                {
                    "new_requirement_id": preview["changed"][0]["new_requirement_id"],
                    "action": "carry_forward",
                }
            ],
        },
        headers=baseline_admin_headers,
    )
    assert execute_resp.status_code == 409
    assert "source file is missing" in execute_resp.json()["detail"]

    original_cycle_resp = await client.get(
        f"/api/v1/review-cycles/{cycle_id}",
        headers=baseline_admin_headers,
    )
    assert original_cycle_resp.status_code == 200
    assert original_cycle_resp.json()["status"] == "active"

    successor_result = await db_session.execute(
        select(ReviewCycle).where(ReviewCycle.predecessor_cycle_id == uuid.UUID(cycle_id))
    )
    assert successor_result.scalars().all() == []

    evidence_rows_result = await db_session.execute(
        select(ReviewItemEvidenceFile).where(
            ReviewItemEvidenceFile.review_item_id == uuid.UUID(original_item["id"])
        )
    )
    assert len(evidence_rows_result.scalars().all()) == 1
