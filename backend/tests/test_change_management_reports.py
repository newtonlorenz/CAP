import pytest
from datetime import datetime, timezone
from tests.change_management_fixtures import assurance, certified_baseline, compliance

from app.models.user import User
from app.services.auth import create_access_token, hash_password


@pytest.fixture
async def report_manager_user(db_session):
    user = User(
        email="cm-report-manager@example.com",
        password_hash=hash_password("testpass"),
        full_name="CM Report Manager",
        role="manager",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def report_manager_headers(report_manager_user):
    token = create_access_token({"sub": str(report_manager_user.id)})
    return {"Authorization": f"Bearer {token}"}


async def _create_register(client, headers, jurisdiction_id: str) -> str:
    response = await client.post(
        "/api/v1/change-management/registers",
        json={
            "jurisdiction_id": jurisdiction_id,
            "name": "Report Register",
            "responsibility_role": "licensed_operator",
            "programme_assurance": assurance(),
            "status": "active",
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _create_component(
    client,
    headers,
    register_id: str,
    *,
    uid: str,
    is_hardware: bool = False,
    location: str = None,
) -> str:
    response = await client.post(
        f"/api/v1/change-management/registers/{register_id}/components",
        json={
            "component_uid": uid,
            "regulatory_scope": "base_platform",
            "definition": f"Definition {uid}",
            "version": "1.0.0",
            "identifying_characteristics": "service",
            "change_owner_name": "Ops Team",
            "confidentiality_code": 2,
            "integrity_code": 2,
            "availability_code": 2,
            "accountability_code": 2,
            "is_hardware": is_hardware,
            "geographic_location": location,
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
    await certified_baseline(client, headers, register_id)
    return response.json()["id"]


async def _create_verified_change(
    client,
    headers,
    register_id: str,
    component_id: str,
    *,
    integration_related: bool = False,
) -> str:
    create_response = await client.post(
        f"/api/v1/change-management/registers/{register_id}/changes",
        json={
            "title": "Report change",
            "compliance": compliance(component_id),
            "description": "Change for reports",
            "category": "ops",
            "change_type": "normal",
            "complexity_classification": "low",
            "resource_assessment": "small",
            "scheduling_assessment": "window",
            "planned_start_at": "2026-02-17T09:00:00Z",
            "planned_end_at": "2026-02-17T10:00:00Z",
            "justification": "routine",
            "affected_documentation": "doc",
            "evaluation_effect": "positive",
            "evaluation_risk": "low",
            "evaluation_regulatory_impact": "none",
            "evaluation_ciaa_impact": "none",
            "testing_org_required": True,
            "testing_org_status": "approved",
            "testing_org_cycle": "annual",
            "testing_org_next_due_at": "2027-02-17T00:00:00Z",
            "testing_org_approved_at": "2026-02-17T08:00:00Z",
            "integration_related": integration_related,
            "components": [
                {
                    "component_id": component_id,
                    "version_at_proposal": "1.0.0",
                    "planned_version": "1.0.1",
                }
            ],
        },
        headers=headers,
    )
    assert create_response.status_code == 201
    change_id = create_response.json()["id"]

    approve_response = await client.post(
        f"/api/v1/change-management/changes/{change_id}/approve",
        json={"approval_decision": "Approved"},
        headers=headers,
    )
    assert approve_response.status_code == 200

    implement_response = await client.post(
        f"/api/v1/change-management/changes/{change_id}/implement",
        json={
            "implementation_notes": "Done",
            "components": [{"component_id": component_id, "implemented_version": "1.0.1"}],
        },
        headers=headers,
    )
    assert implement_response.status_code == 200

    if integration_related:
        integration_check_response = await client.post(
            f"/api/v1/change-management/changes/{change_id}/integration-checks",
            json={
                "action": "Pre-verify integration check",
                "action_reference": "REP-INT-001",
                "result": "pass",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "notes": "completed prior to verification",
                "evidence_notes": "attached integration evidence",
            },
            headers=headers,
        )
        assert integration_check_response.status_code == 201

    verify_response = await client.post(
        f"/api/v1/change-management/changes/{change_id}/verify",
        json={"verification_notes": "Verified"},
        headers=headers,
    )
    assert verify_response.status_code == 200
    return change_id


async def test_change_management_components_report(
    client,
    default_jurisdiction,
    report_manager_headers,
):
    register_id = await _create_register(
        client, report_manager_headers, str(default_jurisdiction.id)
    )
    await _create_component(client, report_manager_headers, register_id, uid="REP-COMP-1")

    response = await client.get(
        f"/api/v1/reports/change-management/components?jurisdiction_id={default_jurisdiction.id}",
        headers=report_manager_headers,
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert "REP-COMP-1" in response.text


async def test_change_management_component_history_report(
    client,
    default_jurisdiction,
    report_manager_headers,
):
    register_id = await _create_register(
        client, report_manager_headers, str(default_jurisdiction.id)
    )
    component_id = await _create_component(
        client, report_manager_headers, register_id, uid="REP-HIST-1"
    )
    change_id = await _create_verified_change(
        client,
        report_manager_headers,
        register_id,
        component_id,
    )

    response = await client.get(
        f"/api/v1/reports/change-management/component-history?component_id={component_id}",
        headers=report_manager_headers,
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert "REP-HIST-1" in response.text
    assert str(change_id) in response.text


async def test_change_management_hardware_locations_report(
    client,
    default_jurisdiction,
    report_manager_headers,
):
    register_id = await _create_register(
        client, report_manager_headers, str(default_jurisdiction.id)
    )
    await _create_component(
        client,
        report_manager_headers,
        register_id,
        uid="REP-HW-1",
        is_hardware=True,
        location="Copenhagen DC",
    )

    response = await client.get(
        f"/api/v1/reports/change-management/hardware-locations?jurisdiction_id={default_jurisdiction.id}",
        headers=report_manager_headers,
    )
    assert response.status_code == 200
    assert "REP-HW-1" in response.text
    assert "Copenhagen DC" in response.text


async def test_change_management_verified_changes_period_validation(
    client,
    default_jurisdiction,
    report_manager_headers,
):
    register_id = await _create_register(
        client, report_manager_headers, str(default_jurisdiction.id)
    )
    component_id = await _create_component(
        client, report_manager_headers, register_id, uid="REP-VER-1"
    )
    await _create_verified_change(
        client,
        report_manager_headers,
        register_id,
        component_id,
    )

    bad_response = await client.get(
        f"/api/v1/reports/change-management/verified-changes?jurisdiction_id={default_jurisdiction.id}&period_days=30",
        headers=report_manager_headers,
    )
    assert bad_response.status_code == 400

    ok_response = await client.get(
        f"/api/v1/reports/change-management/verified-changes?jurisdiction_id={default_jurisdiction.id}&period_days=90",
        headers=report_manager_headers,
    )
    assert ok_response.status_code == 200
    assert "REP-VER-1" in ok_response.text


async def test_change_management_integration_changes_report(
    client,
    default_jurisdiction,
    report_manager_headers,
):
    register_id = await _create_register(
        client, report_manager_headers, str(default_jurisdiction.id)
    )
    component_id = await _create_component(
        client, report_manager_headers, register_id, uid="REP-INT-1"
    )
    change_id = await _create_verified_change(
        client,
        report_manager_headers,
        register_id,
        component_id,
        integration_related=True,
    )

    integration_check_response = await client.post(
        f"/api/v1/change-management/changes/{change_id}/integration-checks",
        json={
            "action": "Sanity check",
            "action_reference": "REP-INT-002",
            "result": "pass",
            "notes": "All green",
            "evidence_notes": "supplementary sanity evidence",
        },
        headers=report_manager_headers,
    )
    assert integration_check_response.status_code == 409

    response = await client.get(
        f"/api/v1/reports/change-management/integration-changes?jurisdiction_id={default_jurisdiction.id}&period_days=365",
        headers=report_manager_headers,
    )
    assert response.status_code == 200
    assert "REP-INT-1" in response.text
    assert "Pre-verify integration check" in response.text
    assert "Sanity check" not in response.text


@pytest.mark.parametrize(
    'role,expected',
    [('manager', 200), ('approver', 200), ('admin', 200), ('contributor', 403), ('assigned_reviewer', 403)],
)
async def test_programme_export_preserves_report_download_roles(
    client, db_session, default_jurisdiction, report_manager_headers, role, expected
):
    await _create_register(client, report_manager_headers, str(default_jurisdiction.id))
    reader = User(
        email=f'programme-export-{role}@example.com',
        password_hash=hash_password('testpass'),
        full_name='Synthetic report reader',
        role=role,
    )
    db_session.add(reader)
    await db_session.commit()
    token = create_access_token({'sub': str(reader.id)})
    response = await client.get(
        f'/api/v1/reports/change-management/programme-assurance?jurisdiction_id={default_jurisdiction.id}',
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == expected, response.text
    if expected == 200:
        assert response.headers['content-type'].startswith('text/csv')
        assert 'PLAN-1' in response.text
