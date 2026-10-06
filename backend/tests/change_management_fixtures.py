"""Evidence-bearing Denmark fixtures shared by endpoint and CSV contract owners."""

from datetime import datetime, timedelta, timezone


def assurance():
    latest = datetime.now(timezone.utc) - timedelta(days=30)
    return {
        "change_plan_reference": "PLAN-1",
        "change_plan_approved_at": latest.isoformat(),
        "change_plan_approved_by": "Senior management",
        "change_plan_approval_evidence": "Signed plan",
        "responsible_owner": "Compliance",
        "ato_accreditation_reference": "ACC-1",
        "ato_accreditation_evidence": "Accreditation scope",
        "latest_certification_at": latest.isoformat(),
        "certification_reference": "SCP06-1",
        "certification_evidence": "Signed certification report",
        "certification_ato": "Accredited laboratory",
        "report_submitted_at": (latest + timedelta(days=1)).isoformat(),
        "integration_procedure_reference": "INT-PROC-1",
        "integration_procedure_ato": "Accredited laboratory",
        "integration_procedure_approved_at": latest.isoformat(),
    }


def compliance(component_id, version="1.0.1", checksum="new123"):
    approved = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    return {
        "evaluation": {
            "status": "approved",
            "provider": "Accredited laboratory",
            "reference": "EVAL-1",
            "evidence": "Approved change evaluation",
            "approved_at": approved,
        },
        "certification": {
            "status": "certified",
            "provider": "Accredited laboratory",
            "reference": "CERT-1",
            "evidence": "Signed test report",
            "certified_at": approved,
            "component_versions": {component_id: version},
            "component_checksums": {component_id: checksum},
        },
        "integration_procedure_reference": "INT-PROC-1",
        "integration_requirement_references": ["SCP.02 integration", "SCP.07 integration"],
    }


async def certified_baseline(client, headers, register_id):
    response = await client.post(
        f"/api/v1/change-management/registers/{register_id}/baselines",
        json={
            "label": "Certified whole-platform configuration",
            "certification_scope": "whole_platform",
            "certification_reference": "PLATFORM-INITIAL-1",
            "certification_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            "certification_ato": "Accredited laboratory",
            "certification_evidence": "Signed whole-platform certification and component register",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]
