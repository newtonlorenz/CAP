import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.audit import AuditLog
from app.models.document import Document
from app.models.organization import Organization
from app.models.program import EvidenceItem
from app.models.requirement import Requirement, RequirementStatus
from app.models.user import User
from app.services.auth import create_access_token, hash_password


@pytest.fixture
async def program_admin_user(db_session):
    user = User(
        email="program-admin@example.com",
        password_hash=hash_password("testpass"),
        full_name="Program Admin",
        role="admin",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def program_auth_headers(program_admin_user):
    token = create_access_token({"sub": str(program_admin_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def program_contributor_headers(db_session):
    user = User(
        email="program-contributor@example.com",
        password_hash=hash_password("testpass"),
        full_name="Program Contributor",
        role="contributor",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    token = create_access_token({"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


async def _create_and_approve_requirement_set(
    client,
    headers,
    jurisdiction_id: str,
    *,
    name: str,
    testing_frequency: str = "monthly",
) -> str:
    set_resp = await client.post(
        "/api/v1/requirements/sets",
        json={
            "jurisdiction_id": jurisdiction_id,
            "name": name,
            "document_type": "scp",
            "testing_frequency": testing_frequency,
        },
        headers=headers,
    )
    assert set_resp.status_code == 201
    document_id = set_resp.json()["id"]

    requirement_resp = await client.post(
        "/api/v1/requirements",
        json={
            "document_id": document_id,
            "reference_id": "R-1",
            "title": "Requirement 1",
            "text": "Maintain controls",
            "requirement_type": "mandatory",
        },
        headers=headers,
    )
    assert requirement_resp.status_code == 201

    versions_resp = await client.get(
        f"/api/v1/requirements/sets/{document_id}/versions",
        headers=headers,
    )
    assert versions_resp.status_code == 200
    version_id = versions_resp.json()["items"][0]["id"]

    submit_resp = await client.post(
        f"/api/v1/requirements/sets/{document_id}/versions/{version_id}/submit",
        json={},
        headers=headers,
    )
    assert submit_resp.status_code == 200

    approve_resp = await client.post(
        f"/api/v1/requirements/sets/{document_id}/versions/{version_id}/approve",
        json={},
        headers=headers,
    )
    assert approve_resp.status_code == 200
    return document_id


async def test_controls_obligations_crosswalk_endpoints(
    client,
    default_jurisdiction,
    program_auth_headers,
    program_admin_user,
    monkeypatch,
):
    from app.config import settings
    monkeypatch.setattr(settings, "installation_operator_ids", [str(program_admin_user.id)])
    control_resp = await client.post(
        "/api/v1/controls",
        json={
            "jurisdiction_id": str(default_jurisdiction.id),
            "code": "DK-CTRL-100",
            "title": "Access governance",
            "description": "Ensure access management controls are active.",
            "cadence_days": 90,
        },
        headers=program_auth_headers,
    )
    assert control_resp.status_code == 201
    control = control_resp.json()

    obligation_resp = await client.post(
        "/api/v1/obligations",
        json={
            "jurisdiction_id": str(default_jurisdiction.id),
            "code": "DK-OBL-100",
            "title": "Access governance obligation",
            "legal_reference": "DK baseline",
        },
        headers=program_auth_headers,
    )
    assert obligation_resp.status_code == 201
    obligation = obligation_resp.json()

    crosswalk_resp = await client.post(
        "/api/v1/crosswalks",
        json={
            "source_control_id": control["id"],
            "target_obligation_id": obligation["id"],
            "mapping_strength": "full",
        },
        headers=program_auth_headers,
    )
    assert crosswalk_resp.status_code == 201

    list_resp = await client.get("/api/v1/crosswalks?limit=100", headers=program_auth_headers)
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert data["total"] >= 1


async def test_installation_catalogue_writes_require_operator(
    client, default_jurisdiction, program_auth_headers, program_admin_user, db_session,
    monkeypatch,
):
    from app.config import settings
    monkeypatch.setattr(settings, "installation_operator_ids", [])
    jurisdiction_id = str(default_jurisdiction.id)
    control_payload = {"jurisdiction_id": jurisdiction_id, "code": "CTRL-1", "title": "Control"}
    obligation_payload = {"jurisdiction_id": jurisdiction_id, "code": "OBL-1", "title": "Obligation"}
    for path, payload in [
        ("controls", control_payload),
        ("obligations", obligation_payload),
        ("crosswalks", {"source_control_id": str(uuid.uuid4()), "target_obligation_id": str(uuid.uuid4())}),
    ]:
        response = await client.post(f"/api/v1/{path}", json=payload, headers=program_auth_headers)
        assert response.status_code == 403

    manager = User(email="catalogue-manager@example.com", password_hash=hash_password("testpass"),
                   full_name="Catalogue Manager", role="manager")
    db_session.add(manager)
    await db_session.commit()
    manager_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(manager.id)})}"}
    response = await client.post("/api/v1/controls", json=control_payload, headers=manager_headers)
    assert response.status_code == 403

    monkeypatch.setattr(settings, "installation_operator_ids", [str(program_admin_user.id)])
    assert (await client.post("/api/v1/controls", json=control_payload, headers=program_auth_headers)).status_code == 201


async def test_new_submission_cycle_ignores_global_requirement_status(
    client, db_session, default_jurisdiction, program_auth_headers, program_admin_user,
):
    document_id = await _create_and_approve_requirement_set(
        client, program_auth_headers, str(default_jurisdiction.id), name="Cycle isolation"
    )
    created = await client.post(
        "/api/v1/certification-projects",
        json={"jurisdiction_id": str(default_jurisdiction.id), "name": "Cycle isolation",
              "requirement_set_ids": [document_id]},
        headers=program_auth_headers,
    )
    assert created.status_code == 201, created.text
    cycle_response = await client.post(
        f"/api/v1/certification-projects/{created.json()['id']}/submission-cycle",
        headers=program_auth_headers,
    )
    assert cycle_response.status_code == 200, cycle_response.text
    cycle_id = cycle_response.json()["review_cycle_id"]
    detail = await client.get(f"/api/v1/review-cycles/{cycle_id}", headers=program_auth_headers)
    item = detail.json()["items"][0]
    assert item["requirement_current_status"] == "not_started"

    db_session.add(RequirementStatus(
        requirement_id=uuid.UUID(item["requirement"]["id"]), status="evidenced",
        comment="Evidence from another workflow", changed_by=program_admin_user.id,
    ))
    await db_session.commit()
    detail = await client.get(f"/api/v1/review-cycles/{cycle_id}", headers=program_auth_headers)
    assert detail.json()["items"][0]["requirement_current_status"] == "not_started"
    closed = await client.post(f"/api/v1/review-cycles/{cycle_id}/close", headers=program_auth_headers)
    assert closed.status_code == 409


async def test_project_setup_without_baseline_keeps_assessment_gate_and_records_lab_result(
    client, default_jurisdiction, program_auth_headers,
):
    created = await client.post(
        "/api/v1/certification-projects",
        json={
            "jurisdiction_id": str(default_jurisdiction.id),
            "name": "Lab engagement",
            "assurance_type": "test",
            "provider_name": "Independent lab",
        },
        headers=program_auth_headers,
    )
    assert created.status_code == 201, created.text
    project = created.json()
    assert project["baseline_versions"] == []
    assert project["provider_name"] == "Independent lab"
    cycle = await client.post(
        f"/api/v1/certification-projects/{project['id']}/submission-cycle",
        headers=program_auth_headers,
    )
    assert cycle.status_code == 409

    invalid = await client.patch(
        f"/api/v1/certification-projects/{project['id']}",
        json={"report_link": "javascript:alert(1)"},
        headers=program_auth_headers,
    )
    assert invalid.status_code == 422
    updated = await client.patch(
        f"/api/v1/certification-projects/{project['id']}",
        json={"report_outcome": "passed_with_findings", "report_link": "https://lab.example/report"},
        headers=program_auth_headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["report_outcome"] == "passed_with_findings"
    assert updated.json()["report_link"] == "https://lab.example/report"


async def test_certification_project_workflow_endpoints(
    client,
    default_jurisdiction,
    program_auth_headers,
):
    source_document_id = await _create_and_approve_requirement_set(
        client,
        program_auth_headers,
        str(default_jurisdiction.id),
        name="Source Requirement Set",
    )

    from_document_resp = await client.post(
        f"/api/v1/certification-projects/from-document/{source_document_id}",
        headers=program_auth_headers,
    )
    assert from_document_resp.status_code == 201
    from_document_data = from_document_resp.json()
    assert from_document_data["created"] is True
    assert from_document_data["project"]["source_document_id"] == str(source_document_id)

    from_document_repeat_resp = await client.post(
        f"/api/v1/certification-projects/from-document/{source_document_id}",
        headers=program_auth_headers,
    )
    assert from_document_repeat_resp.status_code == 201
    assert from_document_repeat_resp.json()["created"] is False

    create_resp = await client.post(
        "/api/v1/certification-projects",
        json={
            "jurisdiction_id": str(default_jurisdiction.id),
            "name": "Nordic launch certification",
            "description": "Initial certification run for launch.",
            "stage": "intake",
            "status": "active",
            "requirement_set_ids": [source_document_id],
        },
        headers=program_auth_headers,
    )
    assert create_resp.status_code == 201
    project = create_resp.json()
    assert project["stage"] == "intake"
    assert project["source_document_id"] == str(source_document_id)

    list_resp = await client.get(
        "/api/v1/certification-projects?limit=100", headers=program_auth_headers
    )
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] >= 1

    milestones_resp = await client.get(
        f"/api/v1/certification-projects/{project['id']}/milestones",
        headers=program_auth_headers,
    )
    assert milestones_resp.status_code == 200
    assert milestones_resp.json()["total"] >= 7
    first_milestone = milestones_resp.json()["items"][0]

    milestone_patch_resp = await client.patch(
        f"/api/v1/certification-projects/{project['id']}/milestones/{first_milestone['id']}",
        json={
            "status": "done",
            "notes": "Scope and inputs confirmed",
        },
        headers=program_auth_headers,
    )
    assert milestone_patch_resp.status_code == 200
    assert milestone_patch_resp.json()["status"] == "done"
    assert milestone_patch_resp.json()["notes"] == "Scope and inputs confirmed"

    patch_resp = await client.patch(
        f"/api/v1/certification-projects/{project['id']}",
        json={"stage": "submission", "status": "on_hold"},
        headers=program_auth_headers,
    )
    assert patch_resp.status_code == 200
    patched = patch_resp.json()
    assert patched["stage"] == "submission"
    assert patched["status"] == "on_hold"

    ensure_cycle_resp = await client.post(
        f"/api/v1/certification-projects/{project['id']}/submission-cycle",
        headers=program_auth_headers,
    )
    assert ensure_cycle_resp.status_code == 200
    ensure_data = ensure_cycle_resp.json()
    assert ensure_data["created"] is True
    assert ensure_data["review_cycle_id"]

    ensure_cycle_repeat_resp = await client.post(
        f"/api/v1/certification-projects/{project['id']}/submission-cycle",
        headers=program_auth_headers,
    )
    assert ensure_cycle_repeat_resp.status_code == 200
    assert ensure_cycle_repeat_resp.json()["created"] is False


async def test_delete_certification_project(
    client,
    default_jurisdiction,
    program_auth_headers,
):
    baseline_document_id = await _create_and_approve_requirement_set(
        client,
        program_auth_headers,
        str(default_jurisdiction.id),
        name="Delete baseline set",
    )
    create_resp = await client.post(
        "/api/v1/certification-projects",
        json={
            "jurisdiction_id": str(default_jurisdiction.id),
            "name": "Delete me",
            "stage": "intake",
            "status": "active",
            "requirement_set_ids": [baseline_document_id],
        },
        headers=program_auth_headers,
    )
    assert create_resp.status_code == 201
    project_id = create_resp.json()["id"]

    delete_resp = await client.delete(
        f"/api/v1/certification-projects/{project_id}",
        headers=program_auth_headers,
    )
    assert delete_resp.status_code == 204

    get_resp = await client.get(
        f"/api/v1/certification-projects/{project_id}",
        headers=program_auth_headers,
    )
    assert get_resp.status_code == 404


async def test_delete_certification_project_rejects_linked_review_cycles(
    client,
    default_jurisdiction,
    program_auth_headers,
):
    baseline_document_id = await _create_and_approve_requirement_set(
        client,
        program_auth_headers,
        str(default_jurisdiction.id),
        name="Delete conflict baseline",
    )
    project_resp = await client.post(
        "/api/v1/certification-projects",
        json={
            "jurisdiction_id": str(default_jurisdiction.id),
            "name": "Delete conflict project",
            "stage": "intake",
            "status": "active",
            "requirement_set_ids": [baseline_document_id],
        },
        headers=program_auth_headers,
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    ensure_cycle_resp = await client.post(
        f"/api/v1/certification-projects/{project_id}/submission-cycle",
        headers=program_auth_headers,
    )
    assert ensure_cycle_resp.status_code == 200
    assert ensure_cycle_resp.json()["review_cycle_id"] is not None

    delete_resp = await client.delete(
        f"/api/v1/certification-projects/{project_id}",
        headers=program_auth_headers,
    )
    assert delete_resp.status_code == 409
    assert "review cycles are linked" in delete_resp.json()["detail"]


async def test_delete_certification_project_forbidden_for_contributor(
    client,
    default_jurisdiction,
    program_auth_headers,
    program_contributor_headers,
):
    baseline_document_id = await _create_and_approve_requirement_set(
        client,
        program_auth_headers,
        str(default_jurisdiction.id),
        name="Delete role baseline",
    )
    project_resp = await client.post(
        "/api/v1/certification-projects",
        json={
            "jurisdiction_id": str(default_jurisdiction.id),
            "name": "Delete role project",
            "stage": "intake",
            "status": "active",
            "requirement_set_ids": [baseline_document_id],
        },
        headers=program_auth_headers,
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    delete_resp = await client.delete(
        f"/api/v1/certification-projects/{project_id}",
        headers=program_contributor_headers,
    )
    assert delete_resp.status_code == 403
    assert delete_resp.json()["detail"] == "Insufficient role"


async def test_submission_package_endpoints(
    client,
    default_jurisdiction,
    program_auth_headers,
):
    baseline_document_id = await _create_and_approve_requirement_set(
        client,
        program_auth_headers,
        str(default_jurisdiction.id),
        name="Submission package baseline",
    )
    project_resp = await client.post(
        "/api/v1/certification-projects",
        json={
            "jurisdiction_id": str(default_jurisdiction.id),
            "name": "Submission package flow",
            "stage": "intake",
            "status": "active",
            "requirement_set_ids": [baseline_document_id],
        },
        headers=program_auth_headers,
    )
    project_id = project_resp.json()["id"]

    ensure_cycle_resp = await client.post(
        f"/api/v1/certification-projects/{project_id}/submission-cycle",
        headers=program_auth_headers,
    )
    assert ensure_cycle_resp.status_code == 200
    cycle_id = ensure_cycle_resp.json()["review_cycle_id"]

    detail = await client.get(f"/api/v1/review-cycles/{cycle_id}", headers=program_auth_headers)
    for item in detail.json()["items"]:
        saved = await client.put(f"/api/v1/review-cycles/{cycle_id}/items/{item['id']}", headers=program_auth_headers, json={"review_status": "confirmed", "requirement_status": "evidenced", "review_evidence": "E-001 fixture control test"})
        assert saved.status_code == 200, saved.text
    close_cycle_resp = await client.post(
        f"/api/v1/review-cycles/{cycle_id}/close",
        headers=program_auth_headers,
    )
    assert close_cycle_resp.status_code == 200
    cycle_snapshot_id = close_cycle_resp.json()["snapshot_id"]
    assert cycle_snapshot_id is not None

    package_resp = await client.post(
        "/api/v1/submission-packages",
        json={
            "project_id": project_id,
            "review_cycle_id": cycle_id,
            "version": "v1",
            "status": "draft",
            "checklist_json": '{"artifacts":[]}',
        },
        headers=program_auth_headers,
    )
    assert package_resp.status_code == 201
    package_data = package_resp.json()
    package_id = package_data["id"]
    assert package_data["review_cycle_id"] == cycle_id
    assert package_data["snapshot_id"] == cycle_snapshot_id

    artifact_resp = await client.post(
        f"/api/v1/submission-packages/{package_id}/artifacts",
        json={
            "artifact_type": "report",
            "name": "SoA",
            "required": True,
            "included": True,
        },
        headers=program_auth_headers,
    )
    assert artifact_resp.status_code == 201
    artifact_id = artifact_resp.json()["id"]
    missing_reference = await client.get(f"/api/v1/submission-packages/{package_id}/gate-check", headers=program_auth_headers)
    assert missing_reference.json()["required_artifacts_included"] == 0
    assert missing_reference.json()["checks_passed"] is False

    artifact_patch_resp = await client.patch(
        f"/api/v1/submission-packages/{package_id}/artifacts/{artifact_id}",
        json={
            "included": False,
            "notes": "Pending updated package file",
        },
        headers=program_auth_headers,
    )
    assert artifact_patch_resp.status_code == 200
    assert artifact_patch_resp.json()["included"] is False
    assert artifact_patch_resp.json()["notes"] == "Pending updated package file"

    gate_check_fail_resp = await client.get(
        f"/api/v1/submission-packages/{package_id}/gate-check",
        headers=program_auth_headers,
    )
    assert gate_check_fail_resp.status_code == 200
    assert gate_check_fail_resp.json()["checks_passed"] is False

    artifact_include_resp = await client.patch(
        f"/api/v1/submission-packages/{package_id}/artifacts/{artifact_id}",
        json={
            "included": True,
            "notes": "Included for submission",
            "link_url": "https://evidence.example.test/soa-v1.pdf",
        },
        headers=program_auth_headers,
    )
    assert artifact_include_resp.status_code == 200

    request_approval_resp = await client.post(
        f"/api/v1/submission-packages/{package_id}/request-approval",
        headers=program_auth_headers,
    )
    assert request_approval_resp.status_code == 200
    assert request_approval_resp.json()["status"] == "pending_approval"

    approve_resp = await client.post(
        f"/api/v1/submission-packages/{package_id}/approve",
        headers=program_auth_headers,
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "approved"

    package_url = f"/api/v1/submission-packages/{package_id}"
    assert (await client.patch(package_url, json={"version": "changed"}, headers=program_auth_headers)).status_code == 409
    assert (await client.patch(f"{package_url}/artifacts/{artifact_id}", json={"included": False}, headers=program_auth_headers)).status_code == 409
    assert (await client.post(f"{package_url}/artifacts", json={"name": "Late file", "artifact_type": "report"}, headers=program_auth_headers)).status_code == 409
    assert (await client.post(f"{package_url}/return-to-draft", json={"reason": " "}, headers=program_auth_headers)).status_code == 422
    returned = await client.post(f"{package_url}/return-to-draft", json={"reason": "Update final checklist"}, headers=program_auth_headers)
    assert returned.status_code == 200
    assert returned.json()["status"] == "draft"
    assert returned.json()["approved_at"] is None
    assert returned.json()["approved_by"] is None
    assert (await client.patch(package_url, json={"version": "v1-updated"}, headers=program_auth_headers)).status_code == 200
    assert (await client.post(f"{package_url}/request-approval", headers=program_auth_headers)).status_code == 200
    assert (await client.post(f"{package_url}/approve", headers=program_auth_headers)).status_code == 200

    lock_resp = await client.post(
        f"/api/v1/submission-packages/{package_id}/lock",
        headers=program_auth_headers,
    )
    assert lock_resp.status_code == 200
    assert lock_resp.json()["status"] == "locked"
    assert (await client.post(f"{package_url}/return-to-draft", json={"reason": "Should remain locked"}, headers=program_auth_headers)).status_code == 409
    assert (await client.patch(f"{package_url}/artifacts/{artifact_id}", json={"included": False}, headers=program_auth_headers)).status_code == 409


    patch_resp = await client.get(
        f"/api/v1/certification-projects/{project_id}",
        headers=program_auth_headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["stage"] == "follow_up"
    assert patch_resp.json()["status"] == "completed"


async def test_stage_gate_check_is_logged_in_warn_only_mode(
    client,
    db_session,
    default_jurisdiction,
    program_auth_headers,
):
    baseline_document_id = await _create_and_approve_requirement_set(
        client,
        program_auth_headers,
        str(default_jurisdiction.id),
        name="Warn-only gate baseline",
    )
    create_resp = await client.post(
        "/api/v1/certification-projects",
        json={
            "jurisdiction_id": str(default_jurisdiction.id),
            "name": "Warn-only project",
            "stage": "intake",
            "status": "active",
            "requirement_set_ids": [baseline_document_id],
        },
        headers=program_auth_headers,
    )
    assert create_resp.status_code == 201
    project = create_resp.json()

    # Intake -> Scoping should pass.
    scope_patch_resp = await client.patch(
        f"/api/v1/certification-projects/{project['id']}",
        json={"stage": "scoping", "status": "active"},
        headers=program_auth_headers,
    )
    assert scope_patch_resp.status_code == 200

    # Scoping -> Gap assessment should fail (no submission cycle), but transition remains allowed in warn-only mode.
    patch_resp = await client.patch(
        f"/api/v1/certification-projects/{project['id']}",
        json={"stage": "gap_assessment", "status": "active"},
        headers=program_auth_headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["stage"] == "gap_assessment"

    audit_result = await db_session.execute(
        select(AuditLog)
        .where(
            AuditLog.entity_type == "certification_project_stage_gate",
            AuditLog.entity_id == str(project["id"]),
        )
        .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
    )
    stage_gate_event = audit_result.scalars().first()
    assert stage_gate_event is not None
    payload = json.loads(stage_gate_event.new_value or "{}")
    assert payload["mode"] == "warn_only"
    assert payload["from_stage"] == "scoping"
    assert payload["to_stage"] == "gap_assessment"
    assert payload["passed"] is False
    assert len(payload["blockers"]) >= 1


async def test_submission_package_patch_rejects_governance_fields(
    client,
    default_jurisdiction,
    program_auth_headers,
):
    baseline_document_id = await _create_and_approve_requirement_set(
        client,
        program_auth_headers,
        str(default_jurisdiction.id),
        name="Submission patch baseline",
    )
    project_resp = await client.post(
        "/api/v1/certification-projects",
        json={
            "jurisdiction_id": str(default_jurisdiction.id),
            "name": "Submission patch guard",
            "stage": "intake",
            "status": "active",
            "requirement_set_ids": [baseline_document_id],
        },
        headers=program_auth_headers,
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    package_resp = await client.post(
        "/api/v1/submission-packages",
        json={
            "project_id": project_id,
            "version": "v1",
            "status": "draft",
        },
        headers=program_auth_headers,
    )
    assert package_resp.status_code == 201
    package_id = package_resp.json()["id"]

    status_patch_resp = await client.patch(
        f"/api/v1/submission-packages/{package_id}",
        json={"status": "pending_approval"},
        headers=program_auth_headers,
    )
    assert status_patch_resp.status_code == 400
    assert "Direct update of governance fields" in status_patch_resp.json()["detail"]
    assert "status" in status_patch_resp.json()["detail"]

    governance_patch_resp = await client.patch(
        f"/api/v1/submission-packages/{package_id}",
        json={"approved_at": datetime.now(timezone.utc).isoformat()},
        headers=program_auth_headers,
    )
    assert governance_patch_resp.status_code == 400
    assert "approved_at" in governance_patch_resp.json()["detail"]


async def test_active_submission_cycle_uniqueness_allows_recreate_after_archive(
    client,
    default_jurisdiction,
    program_auth_headers,
):
    baseline_document_id = await _create_and_approve_requirement_set(
        client,
        program_auth_headers,
        str(default_jurisdiction.id),
        name="Submission uniqueness baseline",
    )
    project_resp = await client.post(
        "/api/v1/certification-projects",
        json={
            "jurisdiction_id": str(default_jurisdiction.id),
            "name": "Submission cycle uniqueness",
            "stage": "intake",
            "status": "active",
            "requirement_set_ids": [baseline_document_id],
        },
        headers=program_auth_headers,
    )
    assert project_resp.status_code == 201
    project = project_resp.json()

    first_cycle_resp = await client.post(
        "/api/v1/review-cycles",
        json={
            "name": "Submission Cycle 1",
            "jurisdiction_id": str(default_jurisdiction.id),
            "certification_project_id": project["id"],
            "cycle_type": "submission",
            "scope": "all",
        },
        headers=program_auth_headers,
    )
    assert first_cycle_resp.status_code == 201
    first_cycle = first_cycle_resp.json()

    duplicate_cycle_resp = await client.post(
        "/api/v1/review-cycles",
        json={
            "name": "Submission Cycle Duplicate",
            "jurisdiction_id": str(default_jurisdiction.id),
            "certification_project_id": project["id"],
            "cycle_type": "submission",
            "scope": "all",
        },
        headers=program_auth_headers,
    )
    assert duplicate_cycle_resp.status_code == 409
    assert "already exists" in duplicate_cycle_resp.json()["detail"].lower()

    archive_resp = await client.post(
        f"/api/v1/review-cycles/{first_cycle['id']}/archive",
        headers=program_auth_headers,
    )
    assert archive_resp.status_code == 200
    assert archive_resp.json()["status"] == "archived"

    recreate_cycle_resp = await client.post(
        "/api/v1/review-cycles",
        json={
            "name": "Submission Cycle 2",
            "jurisdiction_id": str(default_jurisdiction.id),
            "certification_project_id": project["id"],
            "cycle_type": "submission",
            "scope": "all",
        },
        headers=program_auth_headers,
    )
    assert recreate_cycle_resp.status_code == 201

    restore_resp = await client.post(
        f"/api/v1/review-cycles/{first_cycle['id']}/restore",
        headers=program_auth_headers,
    )
    assert restore_resp.status_code == 409
    assert "already exists" in restore_resp.json()["detail"].lower()


async def test_lock_submission_package_creates_maintenance_plan_for_source_document(
    client,
    default_jurisdiction,
    program_auth_headers,
):
    source_document_id = await _create_and_approve_requirement_set(
        client,
        program_auth_headers,
        str(default_jurisdiction.id),
        name="Source maintenance set",
        testing_frequency="monthly",
    )

    project_resp = await client.post(
        f"/api/v1/certification-projects/from-document/{source_document_id}",
        headers=program_auth_headers,
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["project"]["id"]

    ensure_cycle_resp = await client.post(
        f"/api/v1/certification-projects/{project_id}/submission-cycle",
        headers=program_auth_headers,
    )
    cycle_id = ensure_cycle_resp.json()["review_cycle_id"]

    detail = await client.get(f"/api/v1/review-cycles/{cycle_id}", headers=program_auth_headers)
    for item in detail.json()["items"]:
        saved = await client.put(f"/api/v1/review-cycles/{cycle_id}/items/{item['id']}", headers=program_auth_headers, json={"review_status": "confirmed", "requirement_status": "evidenced", "review_evidence": "E-001 fixture control test"})
        assert saved.status_code == 200, saved.text
    close_cycle_resp = await client.post(
        f"/api/v1/review-cycles/{cycle_id}/close",
        headers=program_auth_headers,
    )
    assert close_cycle_resp.status_code == 200

    package_resp = await client.post(
        "/api/v1/submission-packages",
        json={
            "project_id": project_id,
            "review_cycle_id": cycle_id,
            "version": "v1",
            "status": "draft",
        },
        headers=program_auth_headers,
    )
    package_id = package_resp.json()["id"]

    artifact_resp = await client.post(
        f"/api/v1/submission-packages/{package_id}/artifacts",
        json={
            "artifact_type": "report",
            "name": "Required submission artifact",
            "link_url": "https://evidence.example.test/report.pdf",
            "required": True,
            "included": True,
        },
        headers=program_auth_headers,
    )
    assert artifact_resp.status_code == 201

    request_resp = await client.post(
        f"/api/v1/submission-packages/{package_id}/request-approval",
        headers=program_auth_headers,
    )
    assert request_resp.status_code == 200
    approve_resp = await client.post(
        f"/api/v1/submission-packages/{package_id}/approve",
        headers=program_auth_headers,
    )
    assert approve_resp.status_code == 200
    lock_resp = await client.post(
        f"/api/v1/submission-packages/{package_id}/lock",
        headers=program_auth_headers,
    )
    assert lock_resp.status_code == 200

    plans_resp = await client.get(
        "/api/v1/maintenance-plans?limit=1000", headers=program_auth_headers
    )
    assert plans_resp.status_code == 200
    assert any(
        plan["document_id"] == str(source_document_id) for plan in plans_resp.json()["items"]
    )


async def test_maintenance_generation_and_due_cycle_run(
    client,
    default_jurisdiction,
    program_auth_headers,
):
    await _create_and_approve_requirement_set(
        client,
        program_auth_headers,
        str(default_jurisdiction.id),
        name="Maintenance set",
        testing_frequency="monthly",
    )

    generate_resp = await client.post(
        "/api/v1/maintenance-plans/generate",
        json={"jurisdiction_id": str(default_jurisdiction.id), "only_missing": True},
        headers=program_auth_headers,
    )
    assert generate_resp.status_code == 200
    summary = generate_resp.json()
    assert summary["generated"] >= 1

    plans_resp = await client.get(
        "/api/v1/maintenance-plans?limit=100", headers=program_auth_headers
    )
    assert plans_resp.status_code == 200
    plans = plans_resp.json()["items"]
    assert len(plans) >= 1

    plan_id = plans[0]["id"]
    due_patch_resp = await client.patch(
        f"/api/v1/maintenance-plans/{plan_id}",
        json={"next_run_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()},
        headers=program_auth_headers,
    )
    assert due_patch_resp.status_code == 200

    run_due_resp = await client.post(
        "/api/v1/maintenance-plans/run-due",
        headers=program_auth_headers,
    )
    assert run_due_resp.status_code == 200
    run_data = run_due_resp.json()
    assert run_data["generated_cycles"] >= 1

    cycles_resp = await client.get(
        f"/api/v1/review-cycles?jurisdiction_id={default_jurisdiction.id}&limit=1000",
        headers=program_auth_headers,
    )
    assert cycles_resp.status_code == 200
    maintenance_cycles = [
        cycle for cycle in cycles_resp.json()["items"] if cycle["cycle_type"] == "maintenance"
    ]
    assert len(maintenance_cycles) >= 1

    cycle_detail_resp = await client.get(
        f"/api/v1/review-cycles/{maintenance_cycles[0]['id']}",
        headers=program_auth_headers,
    )
    assert cycle_detail_resp.status_code == 200
    cycle_detail = cycle_detail_resp.json()
    assert len(cycle_detail["baseline_versions"]) >= 1
    assert len(cycle_detail["items"]) >= 1


async def test_maintenance_due_run_skips_when_no_resolvable_baseline_versions(
    client,
    db_session,
    default_jurisdiction,
    program_admin_user,
    program_auth_headers,
):
    document = Document(
        organization_id=program_admin_user.organization_id,
        jurisdiction_id=default_jurisdiction.id,
        filename="legacy-maintenance.pdf",
        name="Legacy maintenance set",
        document_type="scp",
        version="1",
        status="approved",
        file_path="/tmp/legacy-maintenance.pdf",
        uploaded_by=program_admin_user.id,
        testing_frequency="monthly",
    )
    db_session.add(document)
    await db_session.flush()

    legacy_requirement = Requirement(
        organization_id=program_admin_user.organization_id,
        jurisdiction_id=default_jurisdiction.id,
        document_id=document.id,
        reference_id="LEGACY-1",
        text="Legacy unversioned requirement",
        requirement_type="mandatory",
        active=True,
        sort_order=1,
    )
    db_session.add(legacy_requirement)
    await db_session.commit()

    generate_resp = await client.post(
        "/api/v1/maintenance-plans/generate",
        json={"jurisdiction_id": str(default_jurisdiction.id), "only_missing": True},
        headers=program_auth_headers,
    )
    assert generate_resp.status_code == 200

    plans_resp = await client.get(
        "/api/v1/maintenance-plans?limit=1000", headers=program_auth_headers
    )
    assert plans_resp.status_code == 200
    matching_plans = [
        plan for plan in plans_resp.json()["items"] if plan["document_id"] == str(document.id)
    ]
    assert len(matching_plans) == 1
    plan_id = matching_plans[0]["id"]

    due_patch_resp = await client.patch(
        f"/api/v1/maintenance-plans/{plan_id}",
        json={"next_run_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()},
        headers=program_auth_headers,
    )
    assert due_patch_resp.status_code == 200

    run_due_resp = await client.post(
        "/api/v1/maintenance-plans/run-due",
        headers=program_auth_headers,
    )
    assert run_due_resp.status_code == 200
    run_data = run_due_resp.json()
    assert run_data["due_plans"] >= 1
    assert run_data["generated_cycles"] == 0


async def test_evidence_items_and_validations(
    client,
    db_session,
    default_jurisdiction,
    program_admin_user,
    program_auth_headers,
):
    requirement = Requirement(
        organization_id=program_admin_user.organization_id,
        jurisdiction_id=default_jurisdiction.id,
        document_id=None,
        reference_id="EVID-1",
        text="Collect monitoring evidence",
        requirement_type="mandatory",
        active=True,
        sort_order=1,
    )
    db_session.add(requirement)
    await db_session.commit()
    await db_session.refresh(requirement)

    create_item_resp = await client.post(
        "/api/v1/evidence-items",
        json={
            "requirement_id": str(requirement.id),
            "evidence_type": "note",
            "title": "Monthly monitoring report",
            "body": "Attached monitoring runbook output",
            "review_status": "in_review",
        },
        headers=program_auth_headers,
    )
    assert create_item_resp.status_code == 201
    item = create_item_resp.json()

    validation_resp = await client.post(
        "/api/v1/evidence-validations",
        json={
            "evidence_item_id": item["id"],
            "validation_status": "pass",
            "comment": "Evidence is current and complete",
        },
        headers=program_auth_headers,
    )
    assert validation_resp.status_code == 201

    list_resp = await client.get(
        f"/api/v1/evidence-validations?evidence_item_id={item['id']}",
        headers=program_auth_headers,
    )
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 1


async def test_contributor_cannot_forge_evidence_approval(
    client,
    db_session,
    default_jurisdiction,
    program_admin_user,
    program_auth_headers,
    program_contributor_headers,
):
    requirement = Requirement(
        organization_id=program_admin_user.organization_id,
        jurisdiction_id=default_jurisdiction.id,
        reference_id="EVID-FORGERY",
        text="Keep evidence review attributable",
        requirement_type="mandatory",
        active=True,
        sort_order=1,
    )
    db_session.add(requirement)
    await db_session.commit()

    create_url = "/api/v1/evidence-items"
    payload = {
        "requirement_id": str(requirement.id),
        "evidence_type": "note",
        "title": "Contributor evidence",
    }
    forged_create = await client.post(
        create_url,
        headers=program_contributor_headers,
        json={**payload, "review_status": "approved", "approved_by": str(program_admin_user.id)},
    )
    assert forged_create.status_code == 403
    rejected_create = await client.post(
        create_url,
        headers=program_contributor_headers,
        json={**payload, "review_status": "rejected"},
    )
    assert rejected_create.status_code == 403

    created = await client.post(
        create_url,
        headers=program_contributor_headers,
        json={
            **payload,
            "approved_by": str(program_admin_user.id),
            "approved_at": "2025-01-01T00:00:00Z",
        },
    )
    assert created.status_code == 201
    assert created.json()["approved_by"] is None
    assert created.json()["approved_at"] is None
    item_id = created.json()["id"]
    url = f"{create_url}/{item_id}"

    edited = await client.patch(
        url,
        headers=program_contributor_headers,
        json={"title": "Edited evidence", "review_status": "in_review"},
    )
    assert edited.status_code == 200
    assert edited.json()["title"] == "Edited evidence"
    assert edited.json()["review_status"] == "in_review"

    for forged_patch in (
        {"approved_by": str(program_admin_user.id), "approved_at": "2025-01-01T00:00:00Z"},
        {"review_status": "approved"},
        {"review_status": "rejected"},
        {"review_status": "approved", "approved_by": str(program_admin_user.id)},
    ):
        response = await client.patch(url, headers=program_contributor_headers, json=forged_patch)
        assert response.status_code in {403, 422}

    listed = await client.get(create_url, headers=program_contributor_headers)
    item = next(row for row in listed.json()["items"] if row["id"] == item_id)
    assert item["review_status"] == "in_review"
    assert item["approved_by"] is None
    assert item["approved_at"] is None


async def test_evidence_approval_records_caller_and_is_tenant_scoped(
    client,
    db_session,
    default_jurisdiction,
    program_admin_user,
    program_auth_headers,
    program_contributor_headers,
):
    requirement = Requirement(
        organization_id=program_admin_user.organization_id,
        jurisdiction_id=default_jurisdiction.id,
        reference_id="EVID-APPROVAL",
        text="Approve evidence",
        requirement_type="mandatory",
        active=True,
        sort_order=1,
    )
    db_session.add(requirement)
    approver = User(
        email="evidence-approver@example.com",
        password_hash=hash_password("testpass"),
        full_name="Evidence Approver",
        role="approver",
    )
    db_session.add(approver)
    await db_session.commit()
    await db_session.refresh(approver)
    approver_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': str(approver.id)})}"
    }
    created = await client.post(
        "/api/v1/evidence-items",
        headers=program_contributor_headers,
        json={
            "requirement_id": str(requirement.id),
            "evidence_type": "note",
            "title": "Reviewable evidence",
            "review_status": "in_review",
            "reviewer_id": str(approver.id),
        },
    )
    assert created.status_code == 201
    url = f"/api/v1/evidence-items/{created.json()['id']}"

    before = datetime.now(timezone.utc)
    approved = await client.patch(url, headers=approver_headers, json={"review_status": "approved"})
    after = datetime.now(timezone.utc)
    assert approved.status_code == 200
    assert approved.json()["review_status"] == "approved"
    assert approved.json()["approved_by"] == str(approver.id)
    approved_at = datetime.fromisoformat(approved.json()["approved_at"])
    assert before <= approved_at.replace(tzinfo=timezone.utc) <= after

    forged = await client.patch(
        url,
        headers=approver_headers,
        json={"approved_by": str(program_admin_user.id), "approved_at": "2025-01-01T00:00:00Z"},
    )
    assert forged.status_code == 422
    downgrade = await client.patch(
        url, headers=program_contributor_headers, json={"review_status": "rejected"}
    )
    assert downgrade.status_code == 403

    edited = await client.patch(
        url, headers=program_contributor_headers, json={"body": "New evidence"}
    )
    assert edited.status_code == 200
    assert edited.json()["review_status"] == "draft"
    assert edited.json()["approved_by"] is None
    assert edited.json()["approved_at"] is None

    other_org = Organization(code="evidence-other", name="Evidence Other", active=True)
    db_session.add(other_org)
    await db_session.flush()
    other_approver = User(
        organization_id=other_org.id,
        email="other-approver@example.com",
        password_hash=hash_password("testpass"),
        full_name="Other Approver",
        role="approver",
    )
    db_session.add(other_approver)
    await db_session.flush()
    other_requirement = Requirement(
        organization_id=other_org.id,
        jurisdiction_id=default_jurisdiction.id,
        reference_id="OTHER-EVID",
        text="Other tenant evidence",
        requirement_type="mandatory",
        active=True,
        sort_order=1,
    )
    db_session.add(other_requirement)
    await db_session.flush()
    other_item = EvidenceItem(
        organization_id=other_org.id,
        requirement_id=other_requirement.id,
        evidence_type="note",
        title="Other tenant evidence",
        review_status="in_review",
        created_by=other_approver.id,
    )
    db_session.add(other_item)
    await db_session.commit()
    await db_session.refresh(other_item)
    foreign_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': str(other_approver.id)})}"
    }
    cross_tenant = await client.patch(
        f"/api/v1/evidence-items/{other_item.id}",
        headers=program_auth_headers,
        json={"review_status": "approved"},
    )
    assert cross_tenant.status_code == 404
    reverse_cross_tenant = await client.patch(
        url, headers=foreign_headers, json={"review_status": "approved"}
    )
    assert reverse_cross_tenant.status_code == 404
    await db_session.refresh(other_item)
    assert other_item.review_status == "in_review"
    assert other_item.approved_by is None


async def test_integration_connections_and_export_manifest(
    client,
    program_auth_headers,
    program_admin_user,
    default_jurisdiction,
    db_session,
):
    create_conn_resp = await client.post(
        "/api/v1/integrations/connections",
        json={
            "provider": "github",
            "name": "GitHub source monitor",
            "config_json": '{"repo":"org/repo"}',
            "enabled": True,
        },
        headers=program_auth_headers,
    )
    assert create_conn_resp.status_code == 201

    list_conn_resp = await client.get(
        "/api/v1/integrations/connections", headers=program_auth_headers
    )
    assert list_conn_resp.status_code == 200
    assert list_conn_resp.json()["total"] >= 1

    from app.models.program import CertificationProject, SubmissionPackage

    project = CertificationProject(
        name="Manifest scope", jurisdiction_id=default_jurisdiction.id,
        created_by=program_admin_user.id,
    )
    db_session.add(project)
    await db_session.flush()
    package = SubmissionPackage(project_id=project.id, version=1, created_by=program_admin_user.id)
    db_session.add(package)
    await db_session.commit()

    create_manifest_resp = await client.post(
        "/api/v1/export-manifests",
        json={
            "scope_type": "submission_package",
            "scope_id": str(package.id),
            "payload": {"files": ["soa.pdf", "audit.csv"]},
        },
        headers=program_auth_headers,
    )
    assert create_manifest_resp.status_code == 201
    manifest = create_manifest_resp.json()

    verify_resp = await client.get(
        f"/api/v1/export-manifests/{manifest['id']}/verify",
        headers=program_auth_headers,
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["valid"] is True


async def test_project_baseline_requires_explicit_upgrade_and_retains_assessments(
    client, default_jurisdiction, program_auth_headers, program_contributor_headers,
):
    headers = program_auth_headers
    document_id = await _create_and_approve_requirement_set(
        client, headers, str(default_jurisdiction.id), name="Versioned platform",
    )
    created = await client.post("/api/v1/certification-projects", json={
        "jurisdiction_id": str(default_jurisdiction.id), "name": "Explicit baseline",
        "requirement_set_ids": [document_id],
    }, headers=headers)
    assert created.status_code == 201
    project = created.json()
    old_version = project["baseline_versions"][0]["requirement_set_version_id"]
    cycle = await client.post("/api/v1/review-cycles", json={
        "name": "Original assessment", "jurisdiction_id": str(default_jurisdiction.id),
        "certification_project_id": project["id"], "cycle_type": "submission", "scope": "all",
    }, headers=headers)
    assert cycle.status_code == 201
    cloned = await client.post(f"/api/v1/requirements/sets/{document_id}/versions/clone",
                              json={"source_version_id": old_version}, headers=headers)
    assert cloned.status_code == 201
    new_version = cloned.json()["id"]
    for action in ("submit", "approve"):
        result = await client.post(f"/api/v1/requirements/sets/{document_id}/versions/{new_version}/{action}", json={}, headers=headers)
        assert result.status_code == 200
    endpoint = f"/api/v1/certification-projects/{project['id']}/baseline"
    # Legacy unchanged selection must no longer silently select the latest version.
    unchanged = await client.put(endpoint, json={"requirement_set_ids": [document_id]}, headers=headers)
    assert unchanged.status_code == 200
    assert unchanged.json()["project"]["baseline_versions"][0]["requirement_set_version_id"] == old_version
    # Adding another set also preserves the older version on an unchanged set.
    second_id = await _create_and_approve_requirement_set(client, headers, str(default_jurisdiction.id), name="Additional requirements")
    added = await client.put(endpoint, json={"requirement_set_ids": [document_id, second_id]}, headers=headers)
    assert added.status_code == 200
    baseline = {item["document_id"]: item["requirement_set_version_id"] for item in added.json()["project"]["baseline_versions"]}
    assert baseline[document_id] == old_version
    payload = {"requirement_set_ids": [document_id, second_id], "target_version_ids": {document_id: new_version}, "expected_baseline_version_ids": baseline}
    denied = await client.put(endpoint, json=payload, headers=program_contributor_headers)
    assert denied.status_code == 403
    wrong_target = await client.put(endpoint, json={**payload, "target_version_ids": {document_id: baseline[second_id]}}, headers=headers)
    assert wrong_target.status_code == 409
    upgraded = await client.put(endpoint, json=payload, headers=headers)
    assert upgraded.status_code == 200
    assert next(item for item in upgraded.json()["project"]["baseline_versions"] if item["document_id"] == document_id)["requirement_set_version_id"] == new_version
    assert "original baseline" in upgraded.json()["warning"]
    original = await client.get(f"/api/v1/review-cycles/{cycle.json()['id']}", headers=headers)
    assert original.status_code == 200
    assert original.json()["baseline_versions"][0]["requirement_set_version_id"] == old_version
    stale = await client.put(endpoint, json=payload, headers=headers)
    assert stale.status_code == 409
