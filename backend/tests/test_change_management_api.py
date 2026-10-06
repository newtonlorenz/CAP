import pytest
from datetime import datetime, timedelta, timezone
from tests.change_management_fixtures import assurance, certified_baseline, compliance

from app.models.user import User
from app.services.auth import create_access_token, hash_password


@pytest.fixture
async def manager_user(db_session):
    user = User(
        email="cm-manager@example.com",
        password_hash=hash_password("testpass"),
        full_name="CM Manager",
        role="manager",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def contributor_user(db_session):
    user = User(
        email="cm-contributor@example.com",
        password_hash=hash_password("testpass"),
        full_name="CM Contributor",
        role="contributor",
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
def contributor_headers(contributor_user):
    token = create_access_token({"sub": str(contributor_user.id)})
    return {"Authorization": f"Bearer {token}"}


async def _create_register(client, headers, jurisdiction_id: str) -> str:
    response = await client.post(
        "/api/v1/change-management/registers",
        json={
            "jurisdiction_id": jurisdiction_id,
            "name": "DK Component Register",
            "responsibility_role": "licensed_operator",
            "programme_assurance": assurance(),
            "status": "active",
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _create_component(
    client, headers, register_id: str, component_uid: str = "COMP-1", *, baseline_headers=None
) -> str:
    response = await client.post(
        f"/api/v1/change-management/registers/{register_id}/components",
        json={
            "component_uid": component_uid,
            "regulatory_scope": "base_platform",
            "definition": "Core transaction service",
            "version": "1.0.0",
            "identifying_characteristics": "python-service",
            "change_owner_name": "Ops Team",
            "confidentiality_code": 2,
            "integrity_code": 3,
            "availability_code": 2,
            "accountability_code": 2,
            "checksum_hash": "abc123",
            "is_hardware": False,
            "hosting_model": "on_prem",
            "virtualized": False,
            "public_cloud_iso27001": False,
            "public_cloud_independent": False,
            "public_cloud_redundancy": False,
            "status": "active",
        },
        headers=headers,
    )
    assert response.status_code == 201
    if baseline_headers:
        await certified_baseline(client, baseline_headers, register_id)
    return response.json()["id"]


def _complete_change_payload(component_id: str, *, integration_related: bool = False) -> dict:
    return {
        "title": "Apply patch",
        "compliance": compliance(component_id),
        "description": "Security patch deployment",
        "category": "security",
        "change_type": "normal",
        "complexity_classification": "medium",
        "resource_assessment": "2 engineers",
        "scheduling_assessment": "maintenance window",
        "affected_components_summary": "Core transaction service",
        "affected_docs_summary": "runbook and architecture notes",
        "planned_start_at": "2026-02-17T09:00:00Z",
        "planned_end_at": "2026-02-17T10:00:00Z",
        "justification": "Mitigate vulnerability",
        "affected_documentation": "runbook + architecture notes",
        "evaluation_effect": "Improves system resilience",
        "evaluation_risk": "Low operational risk",
        "evaluation_regulatory_impact": "No negative impact",
        "evaluation_ciaa_impact": "Integrity improved",
        "testing_org_required": True,
        "testing_org_status": "approved",
        "testing_org_cycle": "immediate",
        "testing_org_approved_at": "2026-02-17T08:30:00Z",
        "integration_related": integration_related,
        "components": [
            {
                "component_id": component_id,
                "version_at_proposal": "1.0.0",
                "planned_version": "1.0.1",
                "planned_checksum_hash": "new123",
            }
        ],
    }


async def test_register_creation_requires_manager_or_admin(
    client,
    default_jurisdiction,
    contributor_headers,
):
    response = await client.post(
        "/api/v1/change-management/registers",
        json={
            "jurisdiction_id": str(default_jurisdiction.id),
            "name": "Attempted Register",
            "status": "active",
        },
        headers=contributor_headers,
    )
    assert response.status_code == 403


async def test_component_validation_checksum_required_for_relevance_3(
    client,
    default_jurisdiction,
    manager_headers,
    contributor_headers,
):
    register_id = await _create_register(client, manager_headers, str(default_jurisdiction.id))
    response = await client.post(
        f"/api/v1/change-management/registers/{register_id}/components",
        json={
            "component_uid": "COMP-3",
            "definition": "Critical component",
            "version": "1.0.0",
            "identifying_characteristics": "critical",
            "change_owner_name": "Ops Team",
            "confidentiality_code": 3,
            "integrity_code": 2,
            "availability_code": 2,
            "accountability_code": 2,
            "is_hardware": False,
            "hosting_model": "on_prem",
            "virtualized": False,
            "public_cloud_iso27001": False,
            "public_cloud_independent": False,
            "public_cloud_redundancy": False,
            "status": "active",
        },
        headers=contributor_headers,
    )
    assert response.status_code == 400
    assert "checksum_hash" in response.json()["detail"]


async def test_component_validation_hardware_location_required_unless_cloud_exempt(
    client,
    default_jurisdiction,
    manager_headers,
    contributor_headers,
):
    register_id = await _create_register(client, manager_headers, str(default_jurisdiction.id))
    response = await client.post(
        f"/api/v1/change-management/registers/{register_id}/components",
        json={
            "component_uid": "HW-1",
            "definition": "Server node",
            "version": "1.0.0",
            "identifying_characteristics": "rack-node",
            "change_owner_name": "Infra Team",
            "confidentiality_code": 2,
            "integrity_code": 2,
            "availability_code": 2,
            "accountability_code": 2,
            "checksum_hash": None,
            "is_hardware": True,
            "hosting_model": "on_prem",
            "virtualized": False,
            "public_cloud_iso27001": False,
            "public_cloud_independent": False,
            "public_cloud_redundancy": False,
            "status": "active",
        },
        headers=contributor_headers,
    )
    assert response.status_code == 400
    assert "geographic_location" in response.json()["detail"]


async def test_component_uid_must_be_unique_within_register(
    client,
    default_jurisdiction,
    manager_headers,
    contributor_headers,
):
    register_id = await _create_register(client, manager_headers, str(default_jurisdiction.id))
    await _create_component(
        client, contributor_headers, register_id, "COMP-UNIQUE", baseline_headers=manager_headers
    )

    duplicate_response = await client.post(
        f"/api/v1/change-management/registers/{register_id}/components",
        json={
            "component_uid": "COMP-UNIQUE",
            "definition": "Duplicate",
            "version": "1.0.0",
            "identifying_characteristics": "duplicate",
            "change_owner_name": "Ops Team",
            "confidentiality_code": 2,
            "integrity_code": 2,
            "availability_code": 2,
            "accountability_code": 2,
            "checksum_hash": None,
            "is_hardware": False,
            "hosting_model": "on_prem",
            "virtualized": False,
            "public_cloud_iso27001": False,
            "public_cloud_independent": False,
            "public_cloud_redundancy": False,
            "status": "active",
        },
        headers=contributor_headers,
    )
    assert duplicate_response.status_code == 409


async def test_classification_code_is_derived_from_ciaa_max(
    client,
    default_jurisdiction,
    manager_headers,
    contributor_headers,
):
    register_id = await _create_register(client, manager_headers, str(default_jurisdiction.id))
    response = await client.post(
        f"/api/v1/change-management/registers/{register_id}/components",
        json={
            "component_uid": "COMP-CLASS",
            "definition": "Service",
            "version": "1.0.0",
            "identifying_characteristics": "svc",
            "change_owner_name": "Ops",
            "confidentiality_code": 1,
            "integrity_code": 2,
            "availability_code": 3,
            "accountability_code": 1,
            "checksum_hash": "hash-333",
            "is_hardware": False,
            "hosting_model": "on_prem",
            "virtualized": False,
            "public_cloud_iso27001": False,
            "public_cloud_independent": False,
            "public_cloud_redundancy": False,
            "status": "active",
        },
        headers=contributor_headers,
    )
    assert response.status_code == 201
    assert response.json()["classification_code"] == 3


async def test_change_cannot_be_approved_without_required_fields(
    client,
    default_jurisdiction,
    manager_headers,
    contributor_headers,
):
    register_id = await _create_register(client, manager_headers, str(default_jurisdiction.id))
    component_id = await _create_component(
        client, contributor_headers, register_id, baseline_headers=manager_headers
    )

    create_change_response = await client.post(
        f"/api/v1/change-management/registers/{register_id}/changes",
        json={
            "title": "Incomplete change",
            "components": [{"component_id": component_id}],
        },
        headers=contributor_headers,
    )
    assert create_change_response.status_code == 201
    change_id = create_change_response.json()["id"]

    approve_response = await client.post(
        f"/api/v1/change-management/changes/{change_id}/approve",
        json={"approval_decision": "Approved"},
        headers=manager_headers,
    )
    assert approve_response.status_code == 400


async def test_change_cannot_be_verified_before_implementation(
    client,
    default_jurisdiction,
    manager_headers,
    contributor_headers,
):
    register_id = await _create_register(client, manager_headers, str(default_jurisdiction.id))
    component_id = await _create_component(
        client, contributor_headers, register_id, baseline_headers=manager_headers
    )

    create_change_response = await client.post(
        f"/api/v1/change-management/registers/{register_id}/changes",
        json=_complete_change_payload(component_id),
        headers=contributor_headers,
    )
    assert create_change_response.status_code == 201
    change_id = create_change_response.json()["id"]

    approve_response = await client.post(
        f"/api/v1/change-management/changes/{change_id}/approve",
        json={"approval_decision": "Approved by CAB"},
        headers=manager_headers,
    )
    assert approve_response.status_code == 200

    verify_response = await client.post(
        f"/api/v1/change-management/changes/{change_id}/verify",
        json={"verification_notes": "too early"},
        headers=manager_headers,
    )
    assert verify_response.status_code == 409


async def test_full_change_workflow_creates_status_events(
    client,
    default_jurisdiction,
    manager_headers,
    contributor_headers,
):
    register_id = await _create_register(client, manager_headers, str(default_jurisdiction.id))
    component_id = await _create_component(
        client, contributor_headers, register_id, baseline_headers=manager_headers
    )

    create_change_response = await client.post(
        f"/api/v1/change-management/registers/{register_id}/changes",
        json=_complete_change_payload(component_id),
        headers=contributor_headers,
    )
    assert create_change_response.status_code == 201
    change_id = create_change_response.json()["id"]

    approve_response = await client.post(
        f"/api/v1/change-management/changes/{change_id}/approve",
        json={"approval_decision": "Approved by CAB"},
        headers=manager_headers,
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "approved"

    implement_response = await client.post(
        f"/api/v1/change-management/changes/{change_id}/implement",
        json={
            "implementation_notes": "Deployed in window",
            "components": [
                {
                    "component_id": component_id,
                    "implemented_version": "1.0.1",
                    "implemented_checksum_hash": "new123",
                }
            ],
        },
        headers=contributor_headers,
    )
    assert implement_response.status_code == 200
    assert implement_response.json()["status"] == "implemented"

    verify_response = await client.post(
        f"/api/v1/change-management/changes/{change_id}/verify",
        json={"verification_notes": "Checks passed"},
        headers=manager_headers,
    )
    assert verify_response.status_code == 200
    assert verify_response.json()["status"] == "verified"

    list_changes_response = await client.get(
        f"/api/v1/change-management/registers/{register_id}/changes",
        headers=manager_headers,
    )
    assert list_changes_response.status_code == 200
    change_entry = list_changes_response.json()["items"][0]
    event_statuses = [
        event["status_to"]
        for event in change_entry["events"]
        if event["event_type"] == "status_change"
    ]
    assert event_statuses == ["draft", "approved", "implemented", "verified"]


async def test_integration_related_change_requires_completed_check_before_verification(
    client,
    default_jurisdiction,
    manager_headers,
    contributor_headers,
):
    register_id = await _create_register(client, manager_headers, str(default_jurisdiction.id))
    component_id = await _create_component(
        client, contributor_headers, register_id, baseline_headers=manager_headers
    )

    create_change_response = await client.post(
        f"/api/v1/change-management/registers/{register_id}/changes",
        json=_complete_change_payload(component_id, integration_related=True),
        headers=contributor_headers,
    )
    assert create_change_response.status_code == 201
    change_id = create_change_response.json()["id"]

    approve_response = await client.post(
        f"/api/v1/change-management/changes/{change_id}/approve",
        json={"approval_decision": "Approved by CAB"},
        headers=manager_headers,
    )
    assert approve_response.status_code == 200

    implement_response = await client.post(
        f"/api/v1/change-management/changes/{change_id}/implement",
        json={
            "implementation_notes": "Implemented in window",
            "components": [
                {
                    "component_id": component_id,
                    "implemented_version": "1.0.1",
                    "implemented_checksum_hash": "new123",
                }
            ],
        },
        headers=contributor_headers,
    )
    assert implement_response.status_code == 200

    verify_without_checks = await client.post(
        f"/api/v1/change-management/changes/{change_id}/verify",
        json={"verification_notes": "No checks"},
        headers=manager_headers,
    )
    assert verify_without_checks.status_code == 400
    assert "integration check" in verify_without_checks.json()["detail"].lower()

    add_incomplete_check = await client.post(
        f"/api/v1/change-management/changes/{change_id}/integration-checks",
        json={"action": "Basic smoke test", "result": "pass", "notes": "ran"},
        headers=contributor_headers,
    )
    assert add_incomplete_check.status_code == 201

    verify_without_completed_check = await client.post(
        f"/api/v1/change-management/changes/{change_id}/verify",
        json={"verification_notes": "Still incomplete"},
        headers=manager_headers,
    )
    assert verify_without_completed_check.status_code == 400
    assert "completed integration check" in verify_without_completed_check.json()["detail"].lower()

    add_completed_check = await client.post(
        f"/api/v1/change-management/changes/{change_id}/integration-checks",
        json={
            "action": "Regression suite",
            "action_reference": "CAB-INT-2026-17",
            "result": "pass",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "notes": "all checks passed",
            "evidence_notes": "Attached integration regression report",
        },
        headers=contributor_headers,
    )
    assert add_completed_check.status_code == 201

    blocked = await client.post(
        f"/api/v1/change-management/changes/{change_id}/verify",
        json={"verification_notes": "One passing check is insufficient"},
        headers=manager_headers,
    )
    assert blocked.status_code == 400
    assert "Basic smoke test" in blocked.json()["detail"]
    check_id = add_incomplete_check.json()["id"]
    check_url = f"/api/v1/change-management/changes/{change_id}/integration-checks/{check_id}"
    completed = {
        "result": "fail",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "action_reference": "SMOKE-01",
        "evidence_notes": "Smoke test results",
    }
    assert (
        await client.patch(check_url, json=completed, headers=contributor_headers)
    ).status_code == 200
    failed_check = await client.post(
        f"/api/v1/change-management/changes/{change_id}/verify",
        json={"verification_notes": "Failed check must block verification"},
        headers=manager_headers,
    )
    assert failed_check.status_code == 400
    assert (
        await client.patch(check_url, json={"result": "pass"}, headers=contributor_headers)
    ).status_code == 200

    verify_response = await client.post(
        f"/api/v1/change-management/changes/{change_id}/verify",
        json={"verification_notes": "Checks complete"},
        headers=manager_headers,
    )
    assert verify_response.status_code == 200
    assert verify_response.json()["status"] == "verified"
    assert (
        await client.patch(check_url, json={"result": "fail"}, headers=contributor_headers)
    ).status_code == 409
    assert (
        await client.request(
            "DELETE",
            check_url,
            json={"reason": "Attempt to remove verified evidence"},
            headers=contributor_headers,
        )
    ).status_code == 409
    assert (
        await client.post(
            f"/api/v1/change-management/changes/{change_id}/integration-checks",
            json={"action": "Late check"},
            headers=contributor_headers,
        )
    ).status_code == 409


async def test_baseline_creation_requires_manager_and_diff_is_deterministic(
    client,
    default_jurisdiction,
    manager_headers,
    contributor_headers,
):
    register_id = await _create_register(client, manager_headers, str(default_jurisdiction.id))
    component_id = await _create_component(
        client, contributor_headers, register_id, "COMP-BL", baseline_headers=manager_headers
    )

    forbidden_baseline = await client.post(
        f"/api/v1/change-management/registers/{register_id}/baselines",
        json={"label": "Attempted Baseline"},
        headers=contributor_headers,
    )
    assert forbidden_baseline.status_code == 403

    baseline_response = await client.post(
        f"/api/v1/change-management/registers/{register_id}/baselines",
        json={"label": "Initial Baseline"},
        headers=manager_headers,
    )
    assert baseline_response.status_code == 201
    baseline_id = baseline_response.json()["id"]

    patch_component_response = await client.patch(
        f"/api/v1/change-management/components/{component_id}",
        json={"version": "2.0.0"},
        headers=contributor_headers,
    )
    assert patch_component_response.status_code == 200

    diff_response = await client.get(
        f"/api/v1/change-management/registers/{register_id}/baselines/{baseline_id}/diff",
        headers=manager_headers,
    )
    assert diff_response.status_code == 200
    payload = diff_response.json()
    assert payload["summary"]["changed"] == 1
    assert payload["summary"]["added"] == 0
    assert payload["summary"]["removed"] == 0
    assert payload["items"][0]["component_uid"] == "COMP-BL"


async def test_component_delete_succeeds_when_not_linked_to_changes(
    client,
    default_jurisdiction,
    manager_headers,
    contributor_headers,
):
    register_id = await _create_register(client, manager_headers, str(default_jurisdiction.id))
    component_id = await _create_component(client, contributor_headers, register_id, "COMP-DEL-1")

    delete_response = await client.delete(
        f"/api/v1/change-management/components/{component_id}",
        headers=contributor_headers,
    )
    assert delete_response.status_code == 204

    list_response = await client.get(
        f"/api/v1/change-management/registers/{register_id}/components",
        headers=manager_headers,
    )
    assert list_response.status_code == 200
    assert all(item["id"] != component_id for item in list_response.json()["items"])


async def test_component_delete_is_blocked_when_linked_to_change_history(
    client,
    default_jurisdiction,
    manager_headers,
    contributor_headers,
):
    register_id = await _create_register(client, manager_headers, str(default_jurisdiction.id))
    component_id = await _create_component(
        client, contributor_headers, register_id, "COMP-DEL-2", baseline_headers=manager_headers
    )

    create_change_response = await client.post(
        f"/api/v1/change-management/registers/{register_id}/changes",
        json=_complete_change_payload(component_id),
        headers=contributor_headers,
    )
    assert create_change_response.status_code == 201

    delete_response = await client.delete(
        f"/api/v1/change-management/components/{component_id}",
        headers=contributor_headers,
    )
    assert delete_response.status_code == 409
    assert "linked to change records" in delete_response.json()["detail"]


async def test_register_lifecycle_allows_multiple_inactive_and_single_active(
    client,
    default_jurisdiction,
    manager_headers,
):
    create_active = await client.post(
        "/api/v1/change-management/registers",
        json={
            "jurisdiction_id": str(default_jurisdiction.id),
            "name": "Lifecycle Register A",
            "status": "active",
        },
        headers=manager_headers,
    )
    assert create_active.status_code == 201
    register_a = create_active.json()["id"]

    deactivate_a = await client.patch(
        f"/api/v1/change-management/registers/{register_a}",
        json={"status": "inactive"},
        headers=manager_headers,
    )
    assert deactivate_a.status_code == 200

    create_inactive = await client.post(
        "/api/v1/change-management/registers",
        json={
            "jurisdiction_id": str(default_jurisdiction.id),
            "name": "Lifecycle Register B",
            "status": "inactive",
        },
        headers=manager_headers,
    )
    assert create_inactive.status_code == 201

    create_active_again = await client.post(
        "/api/v1/change-management/registers",
        json={
            "jurisdiction_id": str(default_jurisdiction.id),
            "name": "Lifecycle Register C",
            "status": "active",
        },
        headers=manager_headers,
    )
    assert create_active_again.status_code == 201

    conflict_active = await client.post(
        "/api/v1/change-management/registers",
        json={
            "jurisdiction_id": str(default_jurisdiction.id),
            "name": "Lifecycle Register D",
            "status": "active",
        },
        headers=manager_headers,
    )
    assert conflict_active.status_code == 409


async def test_relevance_2_verification_requires_annual_testing_cycle_metadata(
    client,
    default_jurisdiction,
    manager_headers,
    contributor_headers,
):
    register_id = await _create_register(client, manager_headers, str(default_jurisdiction.id))
    component_response = await client.post(
        f"/api/v1/change-management/registers/{register_id}/components",
        json={
            "component_uid": "COMP-REL2",
            "regulatory_scope": "base_platform",
            "definition": "Medium relevance component",
            "version": "1.0.0",
            "identifying_characteristics": "medium-service",
            "change_owner_name": "Ops Team",
            "confidentiality_code": 2,
            "integrity_code": 2,
            "availability_code": 2,
            "accountability_code": 2,
            "is_hardware": False,
            "hosting_model": "on_prem",
            "virtualized": False,
            "public_cloud_iso27001": False,
            "public_cloud_independent": False,
            "public_cloud_redundancy": False,
            "status": "active",
        },
        headers=contributor_headers,
    )
    assert component_response.status_code == 201
    component_id = component_response.json()["id"]

    await certified_baseline(client, manager_headers, register_id)
    payload = _complete_change_payload(component_id)
    payload["compliance"]["certification"] = {"status": "pending"}
    register_response = await client.get(
        "/api/v1/change-management/registers", headers=manager_headers
    )
    payload["compliance"]["annual_certification_anchor_at"] = register_response.json()["items"][0][
        "programme_assurance"
    ]["latest_certification_at"]
    payload["compliance"]["annual_certification_reference"] = "SCP02-annual"
    payload["compliance"]["annual_certification_provider"] = "Accredited laboratory"
    payload["compliance"]["annual_certification_evidence"] = "Annual base platform certification"
    payload["compliance"]["annual_certification_due_at"] = (
        datetime.now(timezone.utc) + timedelta(days=200)
    ).isoformat()
    payload["testing_org_status"] = "approved"
    payload["testing_org_cycle"] = "immediate"
    payload["testing_org_approved_at"] = "2026-02-17T08:30:00Z"

    create_change_response = await client.post(
        f"/api/v1/change-management/registers/{register_id}/changes",
        json=payload,
        headers=contributor_headers,
    )
    assert create_change_response.status_code == 201
    change_id = create_change_response.json()["id"]

    approve_response = await client.post(
        f"/api/v1/change-management/changes/{change_id}/approve",
        json={"approval_decision": "Approved by CAB"},
        headers=manager_headers,
    )
    assert approve_response.status_code == 200

    implement_response = await client.post(
        f"/api/v1/change-management/changes/{change_id}/implement",
        json={
            "implementation_notes": "Implemented in window",
            "components": [
                {
                    "component_id": component_id,
                    "implemented_version": "1.0.1",
                    "implemented_checksum_hash": "new123",
                }
            ],
        },
        headers=contributor_headers,
    )
    assert implement_response.status_code == 200

    expired = payload["compliance"].copy()
    expired["annual_certification_due_at"] = (
        datetime.now(timezone.utc) - timedelta(days=1)
    ).isoformat()
    assert (
        await client.patch(
            f"/api/v1/change-management/changes/{change_id}",
            json={"compliance": expired},
            headers=contributor_headers,
        )
    ).status_code == 200
    verify_blocked = await client.post(
        f"/api/v1/change-management/changes/{change_id}/verify",
        json={"verification_notes": "Attempt without annual cadence"},
        headers=manager_headers,
    )
    assert verify_blocked.status_code == 400
    assert "annual certification" in verify_blocked.json()["detail"]

    patch_change = await client.patch(
        f"/api/v1/change-management/changes/{change_id}",
        json={
            "compliance": payload["compliance"],
        },
        headers=contributor_headers,
    )
    assert patch_change.status_code == 200

    verify_ok = await client.post(
        f"/api/v1/change-management/changes/{change_id}/verify",
        json={"verification_notes": "Annual cadence metadata recorded"},
        headers=manager_headers,
    )
    assert verify_ok.status_code == 200
    assert verify_ok.json()["status"] == "verified"


async def test_event_and_integration_check_edit_delete_are_visible_in_activity(
    client,
    default_jurisdiction,
    manager_headers,
    contributor_headers,
):
    register_id = await _create_register(client, manager_headers, str(default_jurisdiction.id))
    component_id = await _create_component(
        client, contributor_headers, register_id, "COMP-ACT", baseline_headers=manager_headers
    )

    create_change_response = await client.post(
        f"/api/v1/change-management/registers/{register_id}/changes",
        json=_complete_change_payload(component_id, integration_related=True),
        headers=contributor_headers,
    )
    assert create_change_response.status_code == 201
    change_id = create_change_response.json()["id"]

    add_event = await client.post(
        f"/api/v1/change-management/changes/{change_id}/events",
        json={"event_type": "decision", "note": "Initial risk decision"},
        headers=contributor_headers,
    )
    assert add_event.status_code == 201
    event_id = add_event.json()["id"]

    update_event = await client.patch(
        f"/api/v1/change-management/changes/{change_id}/events/{event_id}",
        json={"note": "Updated risk decision"},
        headers=contributor_headers,
    )
    assert update_event.status_code == 200
    assert update_event.json()["note"] == "Updated risk decision"

    delete_event = await client.request(
        "DELETE",
        f"/api/v1/change-management/changes/{change_id}/events/{event_id}",
        json={"reason": "Superseded by CAB notes"},
        headers=contributor_headers,
    )
    assert delete_event.status_code == 200
    assert delete_event.json()["deleted_at"] is not None

    add_check = await client.post(
        f"/api/v1/change-management/changes/{change_id}/integration-checks",
        json={"action": "Run integration suite", "result": "pending", "notes": "queued"},
        headers=contributor_headers,
    )
    assert add_check.status_code == 201
    check_id = add_check.json()["id"]

    update_check = await client.patch(
        f"/api/v1/change-management/changes/{change_id}/integration-checks/{check_id}",
        json={
            "result": "pass",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "action_reference": "INT-2026-100",
            "evidence_notes": "suite execution report attached",
        },
        headers=contributor_headers,
    )
    assert update_check.status_code == 200
    assert update_check.json()["completed_at"] is not None

    delete_check = await client.request(
        "DELETE",
        f"/api/v1/change-management/changes/{change_id}/integration-checks/{check_id}",
        json={"reason": "Merged into consolidated check"},
        headers=contributor_headers,
    )
    assert delete_check.status_code == 200
    assert delete_check.json()["deleted_at"] is not None

    activity_response = await client.get(
        f"/api/v1/change-management/changes/{change_id}/activity",
        headers=manager_headers,
    )
    assert activity_response.status_code == 200
    items = activity_response.json()["items"]
    assert any(item["activity_type"] == "event" for item in items)
    assert any(item["activity_type"] == "integration_check" for item in items)
    assert any(item["activity_type"] == "audit_log" for item in items)


async def test_future_testing_approval_is_not_recorded_as_an_actual_decision(
    client, default_jurisdiction, manager_headers, contributor_headers
):
    from datetime import datetime, timedelta, timezone

    register_id = await _create_register(client, manager_headers, str(default_jurisdiction.id))
    component_id = await _create_component(
        client, contributor_headers, register_id, baseline_headers=manager_headers
    )
    payload = _complete_change_payload(component_id)
    payload["testing_org_approved_at"] = (
        datetime.now(timezone.utc) + timedelta(days=1)
    ).isoformat()
    response = await client.post(
        f"/api/v1/change-management/registers/{register_id}/changes",
        json=payload,
        headers=contributor_headers,
    )
    assert response.status_code == 400
    assert "future" in response.json()["detail"].lower()


async def test_approved_proposal_cannot_be_rewritten_but_testing_can_be_recorded(
    client, default_jurisdiction, manager_headers, contributor_headers
):
    register_id = await _create_register(client, manager_headers, str(default_jurisdiction.id))
    component_id = await _create_component(
        client, contributor_headers, register_id, baseline_headers=manager_headers
    )
    response = await client.post(
        f"/api/v1/change-management/registers/{register_id}/changes",
        json=_complete_change_payload(component_id),
        headers=contributor_headers,
    )
    change_id = response.json()["id"]
    url = f"/api/v1/change-management/changes/{change_id}"
    assert (
        await client.post(
            f"{url}/approve", json={"approval_decision": "CAB approval"}, headers=manager_headers
        )
    ).status_code == 200
    for payload in [
        {"title": "Changed after approval"},
        {"components": []},
        {"integration_related": False},
    ]:
        assert (
            await client.patch(url, json=payload, headers=contributor_headers)
        ).status_code == 409
    assert (
        await client.patch(
            url, json={"testing_org_status": "certified"}, headers=contributor_headers
        )
    ).status_code == 200
    assert (
        await client.post(
            f"{url}/reject",
            json={"rejection_reason": "Revise scope and reapprove"},
            headers=manager_headers,
        )
    ).status_code == 200
    assert (
        await client.patch(
            url, json={"title": "Revised for new approval"}, headers=contributor_headers
        )
    ).status_code == 200
