"""Decision-boundary regressions for Denmark SCP.06.00 v3.1.

Primary owners: HTTP workflow rejects release bypasses; CSV exposes preserved
historical identity. Each negative control completes independent prerequisites.
"""

import csv
import io
from datetime import datetime, timedelta, timezone

import pytest

from tests.test_change_management_api import (
    _complete_change_payload,
    _create_component,
    _create_register,
)

from tests.test_change_management_api import (
    contributor_headers as contributor_headers,
    contributor_user as contributor_user,
    manager_headers as manager_headers,
    manager_user as manager_user,
)


async def proposal(
    client,
    default_jurisdiction,
    manager_headers,
    contributor_headers,
    *,
    scope="base_platform",
    edit=None,
    certified_baseline_enabled=True,
):
    register = await _create_register(client, manager_headers, str(default_jurisdiction.id))
    component = await _create_component(
        client,
        contributor_headers,
        register,
        baseline_headers=manager_headers if certified_baseline_enabled else None,
    )
    assert (
        await client.patch(
            f"/api/v1/change-management/components/{component}",
            json={"regulatory_scope": scope},
            headers=contributor_headers,
        )
    ).status_code == 200
    payload = _complete_change_payload(component)
    if scope in {"game", "game_platform"}:
        payload["compliance"]["regulator"] = {
            "game_approval_required": False,
            "game_approval_basis": "Documented existing game no relevant reporting change",
        }
    if scope == "rng":
        payload["compliance"]["regulator"] = {
            "rng_notified_at": (datetime.now(timezone.utc) - timedelta(days=15)).isoformat(),
            "rng_reference": "DGA-receipt-1",
        }
    if edit:
        edit(payload)
    response = await client.post(
        f"/api/v1/change-management/registers/{register}/changes",
        json=payload,
        headers=contributor_headers,
    )
    assert response.status_code == 201, response.text
    return register, component, response.json()["id"], payload


async def approve(client, change, headers):
    response = await client.post(
        f"/api/v1/change-management/changes/{change}/approve",
        json={"approval_decision": "Approve scoped proposal"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response


async def implement(client, change, component, headers):
    return await client.post(
        f"/api/v1/change-management/changes/{change}/implement",
        json={
            "implementation_notes": "Observed controlled release",
            "components": [
                {
                    "component_id": component,
                    "implemented_version": "1.0.1",
                    "implemented_checksum_hash": "new123",
                }
            ],
        },
        headers=headers,
    )


@pytest.mark.parametrize(
    "scope,edit",
    [
        ("rng", lambda p: p["compliance"].update(certification={"status": "pending"})),
        (
            "base_platform",
            lambda p: p["compliance"].update(
                certification={"status": "pending"},
                deferral={
                    "permission_reference": "ATO-1",
                    "permission_evidence": "Permission",
                    "qa_function": "Delivery",
                    "qa_qualified": True,
                    "qa_separate": False,
                    "due_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
                },
            ),
        ),
        (
            "rng",
            lambda p: p["compliance"]["regulator"].update(
                rng_notified_at=datetime.now(timezone.utc).isoformat()
            ),
        ),
        ("base_platform", lambda p: p["compliance"]["certification"].update(component_versions={})),
    ],
)
async def test_release_rejects_unresolved_certification_and_notice(
    client, default_jurisdiction, manager_headers, contributor_headers, scope, edit
):
    _, component, change, _ = await proposal(
        client, default_jurisdiction, manager_headers, contributor_headers, scope=scope, edit=edit
    )
    await approve(client, change, manager_headers)
    response = await implement(client, change, component, contributor_headers)
    assert response.status_code == 400, response.text
    # Observable refusal is the owner contract; exact wording is not coupled.
    assert "certif" in response.text.lower() or "working days" in response.text.lower()


async def test_pending_evaluation_does_not_approve_code2(
    client, default_jurisdiction, manager_headers, contributor_headers
):
    register, component, change, payload = await proposal(
        client,
        default_jurisdiction,
        manager_headers,
        contributor_headers,
        edit=lambda p: p["compliance"]["evaluation"].update(status="pending"),
    )
    response = await client.patch(
        f"/api/v1/change-management/components/{component}",
        json={"integrity_code": 2},
        headers=contributor_headers,
    )
    assert response.status_code == 200
    response = await client.post(
        f"/api/v1/change-management/changes/{change}/approve",
        json={"approval_decision": "Attempt premature approval"},
        headers=manager_headers,
    )
    assert response.status_code == 400
    assert "ATO approval" in response.text


async def test_approved_scope_cannot_be_downgraded_through_component_edits(
    client, default_jurisdiction, manager_headers, contributor_headers
):
    _, component, change, _ = await proposal(
        client, default_jurisdiction, manager_headers, contributor_headers
    )
    await approve(client, change, manager_headers)
    assert (
        await client.patch(
            f"/api/v1/change-management/components/{component}",
            json={
                "integrity_code": 1,
                "confidentiality_code": 1,
                "availability_code": 1,
                "accountability_code": 1,
            },
            headers=contributor_headers,
        )
    ).status_code == 200
    response = await implement(client, change, component, contributor_headers)
    assert response.status_code == 400
    assert "since approval" in response.text


async def test_qa_postponement_is_bounded_and_historical_verification_uses_frozen_scope(
    client, default_jurisdiction, manager_headers, contributor_headers
):
    def pending_with_qa(p):
        p["compliance"]["certification"] = {"status": "pending"}
        p["compliance"]["deferral"] = {
            "permission_reference": "ATO-PERM-1",
            "permission_evidence": "Signed permission",
            "qa_function": "Independent quality",
            "qa_qualified": True,
            "qa_separate": True,
            "due_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        }

    _, component, change, payload = await proposal(
        client, default_jurisdiction, manager_headers, contributor_headers, edit=pending_with_qa
    )
    await approve(client, change, manager_headers)
    response = await implement(client, change, component, contributor_headers)
    assert response.status_code == 200, response.text
    # Current relevance is no authority to downgrade recorded release obligations.
    assert (
        await client.patch(
            f"/api/v1/change-management/components/{component}",
            json={
                "integrity_code": 1,
                "confidentiality_code": 1,
                "availability_code": 1,
                "accountability_code": 1,
            },
            headers=contributor_headers,
        )
    ).status_code == 200
    payload["compliance"]["deferral"]["due_at"] = (
        datetime.now(timezone.utc) - timedelta(days=1)
    ).isoformat()
    assert (
        await client.patch(
            f"/api/v1/change-management/changes/{change}",
            json={"compliance": payload["compliance"]},
            headers=contributor_headers,
        )
    ).status_code == 200
    response = await client.post(
        f"/api/v1/change-management/changes/{change}/verify",
        json={"verification_notes": "Attempt downgraded verification"},
        headers=manager_headers,
    )
    assert response.status_code == 400
    assert "code 3" in response.text


async def test_reports_preserve_frozen_uid_and_omit_deleted_integration_checks(
    client, default_jurisdiction, manager_headers, contributor_headers
):
    _, component, change, payload = await proposal(
        client,
        default_jurisdiction,
        manager_headers,
        contributor_headers,
        edit=lambda p: p.update(integration_related=True),
    )
    await approve(client, change, manager_headers)
    assert (await implement(client, change, component, contributor_headers)).status_code == 200
    checks = []
    for action in ["Successful active check", "Deleted failed check"]:
        response = await client.post(
            f"/api/v1/change-management/changes/{change}/integration-checks",
            json={
                "action": action,
                "action_reference": "INT-PROC-1",
                "result": "pass",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "evidence_notes": "Post integration test evidence",
            },
            headers=contributor_headers,
        )
        assert response.status_code == 201
        checks.append(response.json()["id"])
    assert (
        await client.request(
            "DELETE",
            f"/api/v1/change-management/changes/{change}/integration-checks/{checks[1]}",
            json={"reason": "Superseded"},
            headers=contributor_headers,
        )
    ).status_code == 200
    assert (
        await client.post(
            f"/api/v1/change-management/changes/{change}/verify",
            json={"verification_notes": "Integration passed"},
            headers=manager_headers,
        )
    ).status_code == 200
    assert (
        await client.patch(
            f"/api/v1/change-management/components/{component}",
            json={"component_uid": "RENAMED-UID"},
            headers=contributor_headers,
        )
    ).status_code == 200
    response = await client.get(
        f"/api/v1/reports/change-management/integration-changes?jurisdiction_id={default_jurisdiction.id}",
        headers=manager_headers,
    )
    assert response.status_code == 200
    row = list(csv.DictReader(io.StringIO(response.text)))[0]
    assert row["linked components"] == "COMP-1"
    assert row["integration checks total"] == "1"
    assert "Deleted failed check" not in row["integration actions"]
    assert "CERT-1" in row["compliance attestations"]


async def test_dismissing_supplier_recommendation_needs_ato_attestation(
    client, default_jurisdiction, manager_headers, contributor_headers
):
    def recommendation(p):
        p["compliance"]["supplier"] = {
            "recommended_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            "whole_system_evaluation": "Operator system impact",
            "delay_justification": "Controlled release window",
        }

    _, _, change, _ = await proposal(
        client, default_jurisdiction, manager_headers, contributor_headers, edit=recommendation
    )
    response = await client.post(
        f"/api/v1/change-management/changes/{change}/reject",
        json={"rejection_reason": "Declined vendor recommendation"},
        headers=manager_headers,
    )
    assert response.status_code == 400
    assert "ATO attestation" in response.text


async def test_unknown_legacy_scope_stays_unresolved_and_actual_versions_are_required(
    client, default_jurisdiction, manager_headers, contributor_headers
):
    _, component, change, _ = await proposal(
        client, default_jurisdiction, manager_headers, contributor_headers, scope="unknown"
    )
    response = await client.post(
        f"/api/v1/change-management/changes/{change}/approve",
        json={"approval_decision": "Try unresolved scope"},
        headers=manager_headers,
    )
    assert response.status_code == 400
    assert "regulatory scope" in response.text
    assert (
        await client.patch(
            f"/api/v1/change-management/components/{component}",
            json={"regulatory_scope": "base_platform"},
            headers=contributor_headers,
        )
    ).status_code == 200
    await approve(client, change, manager_headers)
    response = await client.post(
        f"/api/v1/change-management/changes/{change}/implement",
        json={"implementation_notes": "Incomplete observation"},
        headers=contributor_headers,
    )
    assert response.status_code == 400
    assert "actual implemented" in response.text
    response = await implement(client, change, component, contributor_headers)
    assert response.status_code == 200
    components = await client.get(
        f"/api/v1/change-management/registers/{response.json()['register_id']}/components",
        headers=manager_headers,
    )
    assert components.json()["items"][0]["version"] == "1.0.1"
    assert components.json()["items"][0]["checksum_hash"] == "new123"


async def test_optional_assessment_does_not_gate_until_explicitly_required(
    client, db_session, default_jurisdiction, manager_user, manager_headers, contributor_headers
):
    import uuid
    from app.models.review import ReviewCycle

    _, _, change, _ = await proposal(
        client, default_jurisdiction, manager_headers, contributor_headers
    )
    cycle = ReviewCycle(
        organization_id=manager_user.organization_id,
        jurisdiction_id=default_jurisdiction.id,
        change_entry_id=uuid.UUID(change),
        cycle_type="change",
        name="Optional unresolved assessment",
        created_by=manager_user.id,
    )
    db_session.add(cycle)
    await db_session.commit()
    # An optional empty assessment doesn't replace source-backed change gates.
    response = await client.get(
        f"/api/v1/change-management/changes/{change}", headers=manager_headers
    )
    assert response.json()["readiness"]["approval"]["ready"] is True
    response = await client.patch(
        f"/api/v1/change-management/changes/{change}",
        json={"blocking_assessment_ids": [str(cycle.id)]},
        headers=manager_headers,
    )
    assert response.status_code == 200
    response = await client.post(
        f"/api/v1/change-management/changes/{change}/approve",
        json={"approval_decision": "Try required unresolved assessment"},
        headers=manager_headers,
    )
    assert response.status_code == 400
    assert "explicitly required assessment" in response.text


@pytest.mark.parametrize("revision", ["add_assessment", "remove_assessment", "responsibility"])
async def test_reapproval_evaluates_revised_prerequisites_and_responsibility(
    client,
    db_session,
    default_jurisdiction,
    manager_user,
    manager_headers,
    contributor_headers,
    revision,
):
    import uuid
    from app.models.review import ReviewCycle, ReviewItem
    from app.models.requirement import Requirement

    register, _, change, _ = await proposal(
        client, default_jurisdiction, manager_headers, contributor_headers
    )
    cycle = ReviewCycle(
        organization_id=manager_user.organization_id,
        jurisdiction_id=default_jurisdiction.id,
        change_entry_id=uuid.UUID(change),
        cycle_type="change",
        name="Revised prerequisite",
        created_by=manager_user.id,
    )
    requirement = Requirement(
        jurisdiction_id=default_jurisdiction.id,
        reference_id="REVISED-1",
        text="Required control",
    )
    db_session.add_all([cycle, requirement])
    await db_session.flush()
    item = ReviewItem(
        review_cycle_id=cycle.id,
        requirement_id=requirement.id,
        review_status="confirmed",
        assessment_status="compliant",
    )
    db_session.add(item)
    await db_session.commit()
    if revision == "remove_assessment":
        response = await client.patch(
            f"/api/v1/change-management/changes/{change}",
            json={"blocking_assessment_ids": [str(cycle.id)]},
            headers=manager_headers,
        )
        assert response.status_code == 200
    await approve(client, change, manager_headers)
    response = await client.post(
        f"/api/v1/change-management/changes/{change}/reject",
        json={"rejection_reason": "Revise responsibility and prerequisite scope"},
        headers=manager_headers,
    )
    assert response.status_code == 200
    item.review_status = "pending"
    await db_session.commit()
    if revision == "responsibility":
        response = await client.patch(
            f"/api/v1/change-management/registers/{register}",
            json={"responsibility_role": "unknown"},
            headers=manager_headers,
        )
    else:
        response = await client.patch(
            f"/api/v1/change-management/changes/{change}",
            json={
                "blocking_assessment_ids": [str(cycle.id)] if revision == "add_assessment" else []
            },
            headers=manager_headers,
        )
    assert response.status_code == 200, response.text
    response = await client.post(
        f"/api/v1/change-management/changes/{change}/approve",
        json={"approval_decision": "Review revised proposal"},
        headers=manager_headers,
    )
    assert response.status_code == (200 if revision == "remove_assessment" else 400), response.text
    if revision == "remove_assessment":
        assert response.json()["approved_scope"]["blocking_assessment_ids"] == []
    else:
        assert (
            "responsibility" if revision == "responsibility" else "required assessment"
        ) in response.text


async def test_reapproval_binds_renewed_certified_baseline_and_preserves_prior_lineage(
    client,
    db_session,
    default_jurisdiction,
    manager_headers,
    contributor_headers,
):
    import uuid
    import json
    from sqlalchemy import select, update
    from app.models.audit import AuditLog
    from app.models.change_management import ComponentBaseline
    from tests.change_management_fixtures import certified_baseline

    register, component, change, _ = await proposal(
        client, default_jurisdiction, manager_headers, contributor_headers
    )
    initial = await approve(client, change, manager_headers)
    old_baseline = initial.json()["components"][0]["baseline_id"]
    await db_session.execute(
        update(ComponentBaseline)
        .where(ComponentBaseline.id == uuid.UUID(old_baseline))
        .values(certification_at=datetime.now(timezone.utc) - timedelta(days=400))
    )
    await db_session.commit()
    response = await implement(client, change, component, contributor_headers)
    assert response.status_code == 400
    assert "annual recertification" in response.text
    renewed = await certified_baseline(client, manager_headers, register)
    response = await client.post(
        f"/api/v1/change-management/changes/{change}/reject",
        json={"rejection_reason": "Review against renewed whole-platform certification"},
        headers=manager_headers,
    )
    assert response.status_code == 200
    response = await approve(client, change, manager_headers)
    assert response.json()["components"][0]["baseline_id"] == renewed
    assert response.json()["approved_scope"]["baseline_bindings"][0]["baseline_id"] == renewed
    assert (await implement(client, change, component, contributor_headers)).status_code == 200
    records = (
        await db_session.scalars(
            select(AuditLog).where(
                AuditLog.entity_type == "change_entry",
                AuditLog.entity_id == change,
                AuditLog.action == "approve",
            )
        )
    ).all()
    assert {
        json.loads(x.new_value)["approved_scope"]["baseline_bindings"][0]["baseline_id"]
        for x in records
    } == {old_baseline, renewed}


async def test_programme_postponement_preserves_original_cadence_and_report_deadline(
    client, default_jurisdiction, manager_headers
):
    from tests.change_management_fixtures import assurance

    original = assurance()
    # Fixed official calendar example, independent of the production date helper.
    original.update(
        latest_certification_at="2025-09-15T00:00:00Z",
        report_submitted_at="2025-09-16T00:00:00Z",
        postponed_until="2026-11-15T00:00:00Z",
        postponement_notified_at="2026-09-14T00:00:00Z",
        postponement_reference="DGA-postponement-receipt",
    )
    response = await client.post(
        "/api/v1/change-management/registers",
        json={
            "jurisdiction_id": str(default_jurisdiction.id),
            "name": "Annual assurance",
            "responsibility_role": "licensed_operator",
            "programme_assurance": original,
        },
        headers=manager_headers,
    )
    assert response.status_code == 201
    register = response.json()["id"]
    assert response.json()["programme_readiness"]["certification_due_at"].startswith("2026-11-15")
    renewed = {
        **original,
        "latest_certification_at": "2026-10-01T00:00:00Z",
        "certification_reference": "SCP06-renewed",
        "report_submitted_at": "2026-10-01T12:00:00Z",
    }
    response = await client.patch(
        f"/api/v1/change-management/registers/{register}",
        json={"programme_assurance": renewed},
        headers=manager_headers,
    )
    assert response.status_code == 200
    assert response.json()["programme_readiness"]["certification_due_at"].startswith("2027-09-15")
    assert response.json()["programme_readiness"]["report_due_at"].startswith("2026-11-15")
    invalid = {**renewed, "postponed_until": "2028-01-01T00:00:00Z"}
    response = await client.patch(
        f"/api/v1/change-management/registers/{register}",
        json={"programme_assurance": invalid},
        headers=manager_headers,
    )
    assert response.status_code == 200
    assert response.json()["programme_readiness"]["ready"] is False
    assert any(
        x["code"] == "programme_postponement"
        for x in response.json()["programme_readiness"]["reasons"]
    )


async def test_verified_qa_change_can_receive_manager_certification_without_reopening(
    client, default_jurisdiction, manager_headers, contributor_headers
):
    from tests.change_management_fixtures import compliance

    def deferred(p):
        p["compliance"]["certification"] = {"status": "pending"}
        p["compliance"]["deferral"] = {
            "permission_reference": "ATO-PERM-1",
            "permission_evidence": "Signed permission",
            "qa_function": "Independent quality",
            "qa_qualified": True,
            "qa_separate": True,
            "due_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        }

    _, component, change, _ = await proposal(
        client, default_jurisdiction, manager_headers, contributor_headers, edit=deferred
    )
    await approve(client, change, manager_headers)
    assert (await implement(client, change, component, contributor_headers)).status_code == 200
    verified = await client.post(
        f"/api/v1/change-management/changes/{change}/verify",
        json={"verification_notes": "Independent QA completed"},
        headers=manager_headers,
    )
    assert verified.status_code == 200
    evidence = verified.json()["compliance"]
    evidence["certification"] = compliance(component)["certification"]
    evidence["certification"]["certified_at"] = datetime.now(timezone.utc).isoformat()
    response = await client.patch(
        f"/api/v1/change-management/changes/{change}",
        json={"compliance": evidence},
        headers=contributor_headers,
    )
    assert response.status_code == 403
    response = await client.patch(
        f"/api/v1/change-management/changes/{change}",
        json={"compliance": evidence},
        headers=manager_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "verified"
    assert response.json()["verified_at"] == verified.json()["verified_at"]
    evidence["certification"]["reference"] = "replacement unsigned report"
    assert (
        await client.patch(
            f"/api/v1/change-management/changes/{change}",
            json={"compliance": evidence},
            headers=manager_headers,
        )
    ).status_code == 409


@pytest.mark.parametrize("classification", [2, 3])
@pytest.mark.parametrize("deadline_edit", ["erase", "extend"])
async def test_certification_completion_cannot_erase_or_extend_release_deadline(
    client,
    default_jurisdiction,
    manager_headers,
    contributor_headers,
    monkeypatch,
    classification,
    deadline_edit,
):
    from tests.change_management_fixtures import compliance
    from app.services import change_readiness

    released = datetime.now(timezone.utc)
    original_due = released + timedelta(days=30)

    def pending(p):
        p["compliance"]["certification"] = {"status": "pending"}
        if classification == 3:
            p["compliance"]["deferral"] = {
                "permission_reference": "ATO-PERM-1",
                "permission_evidence": "Signed one month permission",
                "qa_function": "Independent quality",
                "qa_qualified": True,
                "qa_separate": True,
                "due_at": original_due.isoformat(),
            }
        else:
            p["compliance"].update(
                annual_certification_anchor_at=(released - timedelta(days=30)).isoformat(),
                annual_certification_reference="Previous SCP02/SCP07 certification",
                annual_certification_provider="Accredited laboratory",
                annual_certification_evidence="Signed annual certification",
                annual_certification_due_at=original_due.isoformat(),
            )

    _, component, change, payload = await proposal(
        client, default_jurisdiction, manager_headers, contributor_headers, edit=pending
    )
    if classification == 2:
        response = await client.patch(
            f"/api/v1/change-management/components/{component}",
            json={"integrity_code": 2},
            headers=contributor_headers,
        )
        assert response.status_code == 200
    await approve(client, change, manager_headers)
    assert (await implement(client, change, component, contributor_headers)).status_code == 200

    later = released + timedelta(days=40)

    class LaterDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return later.astimezone(tz) if tz else later.replace(tzinfo=None)

    monkeypatch.setattr(change_readiness, "datetime", LaterDateTime)
    from app.api import change_management

    monkeypatch.setattr(change_management, "datetime", LaterDateTime)
    evidence = payload["compliance"]
    evidence["certification"] = compliance(component)["certification"]
    evidence["certification"]["certified_at"] = (released + timedelta(days=35)).isoformat()
    edited_due = None if deadline_edit == "erase" else (released + timedelta(days=60)).isoformat()
    if classification == 3:
        evidence["deferral"]["due_at"] = edited_due
    else:
        evidence["annual_certification_due_at"] = edited_due
    response = await client.patch(
        f"/api/v1/change-management/changes/{change}",
        json={"compliance": evidence},
        headers=manager_headers,
    )
    assert response.status_code == 200, response.text
    response = await client.post(
        f"/api/v1/change-management/changes/{change}/verify",
        json={"verification_notes": "Record delayed ATO completion"},
        headers=manager_headers,
    )
    assert response.status_code == 400, response.text
    assert "completed after" in response.text


async def test_rejected_proposal_can_replace_external_decisions_before_reapproval(
    client,
    default_jurisdiction,
    manager_headers,
    contributor_headers,
):
    _, _, change, payload = await proposal(
        client, default_jurisdiction, manager_headers, contributor_headers
    )
    await approve(client, change, manager_headers)
    response = await client.post(
        f"/api/v1/change-management/changes/{change}/reject",
        json={"rejection_reason": "Revise proposal with a new ATO evaluation"},
        headers=manager_headers,
    )
    assert response.status_code == 200
    payload["compliance"]["evaluation"]["reference"] = "EVAL-revised"
    payload["compliance"]["certification"]["reference"] = "CERT-revised"
    response = await client.patch(
        f"/api/v1/change-management/changes/{change}",
        json={"compliance": payload["compliance"]},
        headers=contributor_headers,
    )
    assert response.status_code == 200, response.text
    response = await approve(client, change, manager_headers)
    assert (
        response.json()["approved_scope"]["evaluation_attestation"]["reference"] == "EVAL-revised"
    )


@pytest.mark.parametrize("continuity_confirmed,expected_status", [(True, 200), (False, 400)])
async def test_ato_direct_continuation_can_finish_after_release_without_becoming_unqualified_delay(
    client,
    default_jurisdiction,
    manager_headers,
    contributor_headers,
    continuity_confirmed,
    expected_status,
):
    def pending(p):
        p["compliance"]["certification"] = {"status": "pending"}

    _, component, change, payload = await proposal(
        client, default_jurisdiction, manager_headers, contributor_headers, edit=pending
    )
    approval = await approve(client, change, manager_headers)
    started = datetime.now(timezone.utc)
    ended = datetime.now(timezone.utc)
    payload["compliance"]["certification"] = {
        "status": "pending",
        "provider": "Accredited laboratory",
        "timing": "direct_continuation",
        "planned_at": (ended + timedelta(days=1)).isoformat(),
        "schedule_reference": "ATO-continuous-test-plan",
        "continuation_started_at": started.isoformat(),
        "continuation_confirmed": continuity_confirmed,
        "continuation_evidence": "ATO began the uninterrupted certification during the controlled implementation",
    }
    assert (
        await client.patch(
            f"/api/v1/change-management/changes/{change}",
            json={"compliance": payload["compliance"]},
            headers=contributor_headers,
        )
    ).status_code == 200
    response = await client.post(
        f"/api/v1/change-management/changes/{change}/implement",
        json={
            "implementation_notes": "Release observed with continuous ATO certification",
            "implemented_start_at": approval.json()["approved_at"],
            "implemented_end_at": ended.isoformat(),
            "components": [
                {
                    "component_id": component,
                    "implemented_version": "1.0.1",
                    "implemented_checksum_hash": "new123",
                }
            ],
        },
        headers=contributor_headers,
    )
    assert response.status_code == expected_status, response.text
    if continuity_confirmed:
        assert response.json()["readiness"]["certification_status"] == "pending"
        assert response.json()["readiness"]["verification"]["ready"] is False


async def test_rollback_requires_managed_recovery_and_remains_immutable(
    client, default_jurisdiction, manager_headers, contributor_headers
):
    import uuid
    from tests.change_management_fixtures import compliance

    register, component, original, original_payload = await proposal(
        client, default_jurisdiction, manager_headers, contributor_headers
    )
    await approve(client, original, manager_headers)
    assert (await implement(client, original, component, contributor_headers)).status_code == 200
    observation = {
        "recovery_change_id": str(uuid.uuid4()),
        "reason": "Recover previous release",
        "outcome": "Restored",
        "follow_up": "Investigate cause",
        "components": [
            {
                "component_id": component,
                "implemented_version": "1.0.0",
                "implemented_checksum_hash": "abc123",
            }
        ],
    }
    # Editing an inventory value isn't proof of an approved recovery release.
    assert (
        await client.patch(
            f"/api/v1/change-management/components/{component}",
            json={"version": "1.0.0", "checksum_hash": "abc123"},
            headers=contributor_headers,
        )
    ).status_code == 200
    assert (
        await client.post(
            f"/api/v1/change-management/changes/{original}/rollback",
            json=observation,
            headers=manager_headers,
        )
    ).status_code == 409
    assert (
        await client.patch(
            f"/api/v1/change-management/components/{component}",
            json={"version": "1.0.1", "checksum_hash": "new123"},
            headers=contributor_headers,
        )
    ).status_code == 200
    recovery_payload = _complete_change_payload(component)
    recovery_payload["components"] = [
        {
            "component_id": component,
            "version_at_proposal": "1.0.1",
            "planned_version": "1.0.0",
            "planned_checksum_hash": "abc123",
        }
    ]
    recovery_payload["compliance"] = compliance(component, "1.0.0", "abc123")
    response = await client.post(
        f"/api/v1/change-management/registers/{register}/changes",
        json=recovery_payload,
        headers=contributor_headers,
    )
    assert response.status_code == 201
    recovery = response.json()["id"]
    observation["recovery_change_id"] = recovery
    await approve(client, recovery, manager_headers)
    response = await client.post(
        f"/api/v1/change-management/changes/{recovery}/implement",
        json={
            "implementation_notes": "Approved recovery observed",
            "components": observation["components"],
        },
        headers=contributor_headers,
    )
    assert response.status_code == 200, response.text
    response = await client.post(
        f"/api/v1/change-management/changes/{original}/rollback",
        json=observation,
        headers=manager_headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "rolled_back"
    assert response.json()["components"][0]["implemented_version"] == "1.0.1"
    assert recovery in response.json()["events"][-1]["note"]
    assert (
        await client.post(
            f"/api/v1/change-management/changes/{original}/reject",
            json={"rejection_reason": "Try reopening rollback"},
            headers=manager_headers,
        )
    ).status_code == 409


@pytest.mark.parametrize("implemented_checksum_missing", [True, False])
async def test_historical_scope_attestation_resolves_identity_without_inventing_certification(
    client,
    db_session,
    default_jurisdiction,
    manager_headers,
    contributor_headers,
    implemented_checksum_missing,
):
    import uuid
    from sqlalchemy import update
    from app.models.change_management import ChangeEntry, ChangeEntryComponent

    _, component, change, payload = await proposal(
        client, default_jurisdiction, manager_headers, contributor_headers
    )
    await approve(client, change, manager_headers)
    assert (await implement(client, change, component, contributor_headers)).status_code == 200
    # Reproduce the nullable fields left by the additive legacy migration.
    await db_session.execute(
        update(ChangeEntry)
        .where(ChangeEntry.id == uuid.UUID(change))
        .values(compliance=None, approved_scope=None)
    )
    await db_session.execute(
        update(ChangeEntryComponent)
        .where(ChangeEntryComponent.change_entry_id == uuid.UUID(change))
        .values(
            frozen_snapshot=None,
            planned_checksum_hash=None,
            implemented_checksum_hash=None if implemented_checksum_missing else "new123",
        )
    )
    await db_session.commit()
    attestation = {
        "evidence_reference": "Historic release dossier",
        "evidence": "Original register and ATO evaluation scope",
        "responsibility_role": "licensed_operator",
        "components": [
            {
                "component_id": component,
                "component_uid": "COMP-1",
                "version": "1.0.0",
                "checksum_hash": "abc123",
                "planned_checksum_hash": "new123",
                "implemented_checksum_hash": "new123",
                "regulatory_scope": "base_platform",
                "confidentiality_code": 2,
                "integrity_code": 3,
                "availability_code": 2,
                "accountability_code": 2,
            }
        ],
    }
    if not implemented_checksum_missing:
        attestation["components"][0]["implemented_checksum_hash"] = "replacement-unproven-hash"
        response = await client.post(
            f"/api/v1/change-management/changes/{change}/historical-scope-attestation",
            json=attestation,
            headers=manager_headers,
        )
        assert response.status_code == 409
        attestation["components"][0]["implemented_checksum_hash"] = "new123"
    response = await client.post(
        f"/api/v1/change-management/changes/{change}/historical-scope-attestation",
        json=attestation,
        headers=manager_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "implemented"
    assert response.json()["compliance"] is None
    assert response.json()["components"][0]["frozen_snapshot"]["component_uid"] == "COMP-1"
    assert response.json()["readiness"]["verification"]["ready"] is False
    response = await client.patch(
        f"/api/v1/change-management/changes/{change}",
        json={"compliance": payload["compliance"]},
        headers=manager_headers,
    )
    assert response.status_code == 200, response.text
    response = await client.post(
        f"/api/v1/change-management/changes/{change}/verify",
        json={"verification_notes": "Historic scope and ATO certification reconciled"},
        headers=manager_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["components"][0]["planned_checksum_hash"] == "new123"
    assert response.json()["components"][0]["implemented_checksum_hash"] == "new123"
    assert (
        await client.post(
            f"/api/v1/change-management/changes/{change}/historical-scope-attestation",
            json=attestation,
            headers=manager_headers,
        )
    ).status_code == 409


async def test_component_audit_binds_real_identity_and_preserves_full_material_changes(
    client, db_session, default_jurisdiction, manager_headers, contributor_headers
):
    import json
    from sqlalchemy import select
    from app.models.audit import AuditLog

    register = await _create_register(client, manager_headers, str(default_jurisdiction.id))
    component = await _create_component(client, contributor_headers, register)
    created = await db_session.scalar(
        select(AuditLog).where(
            AuditLog.entity_type == "component",
            AuditLog.entity_id == component,
            AuditLog.action == "create",
        )
    )
    assert created is not None
    assert json.loads(created.new_value)["checksum_hash"] == "abc123"
    assert json.loads(created.new_value)["regulatory_scope"] == "base_platform"
    response = await client.patch(
        f"/api/v1/change-management/components/{component}",
        json={
            "checksum_hash": "corrected456",
            "definition": "Corrected definition",
            "change_owner_name": "New owner",
        },
        headers=contributor_headers,
    )
    assert response.status_code == 200
    edited = await db_session.scalar(
        select(AuditLog).where(
            AuditLog.entity_type == "component",
            AuditLog.entity_id == component,
            AuditLog.action == "update",
        )
    )
    before, after = json.loads(edited.old_value), json.loads(edited.new_value)
    assert before["checksum_hash"] == "abc123" and after["checksum_hash"] == "corrected456"
    assert (
        before["definition"] == "Core transaction service"
        and after["definition"] == "Corrected definition"
    )
    assert before["change_owner_name"] == "Ops Team" and after["change_owner_name"] == "New owner"


async def test_certified_platform_baseline_is_required_and_legitimate_version_lineage_can_differ(
    client, default_jurisdiction, manager_headers, contributor_headers
):
    from tests.change_management_fixtures import certified_baseline, compliance

    register, component, change, _ = await proposal(
        client,
        default_jurisdiction,
        manager_headers,
        contributor_headers,
        certified_baseline_enabled=False,
    )
    await approve(client, change, manager_headers)
    response = await implement(client, change, component, contributor_headers)
    assert response.status_code == 400
    assert "whole-platform configuration baseline" in response.text
    baseline = await certified_baseline(client, manager_headers, register)
    assert (
        await client.post(
            f"/api/v1/change-management/changes/{change}/reject",
            json={"rejection_reason": "Bind evidenced initial baseline"},
            headers=manager_headers,
        )
    ).status_code == 200
    await approve(client, change, manager_headers)
    response = await implement(client, change, component, contributor_headers)
    assert response.status_code == 200
    assert response.json()["components"][0]["baseline_id"] == baseline
    payload = _complete_change_payload(component)
    payload["components"] = [
        {
            "component_id": component,
            "version_at_proposal": "1.0.1",
            "planned_version": "1.0.2",
            "planned_checksum_hash": "patch2",
            "baseline_id": baseline,
        }
    ]
    payload["compliance"] = compliance(component, "1.0.2", "patch2")
    response = await client.post(
        f"/api/v1/change-management/registers/{register}/changes",
        json=payload,
        headers=contributor_headers,
    )
    assert response.status_code == 201
    second = response.json()["id"]
    approved = await approve(client, second, manager_headers)
    assert approved.json()["approved_scope"]["baseline_bindings"][0]["differences"]["version"] == {
        "baseline": "1.0.0",
        "current": "1.0.1",
    }
    response = await client.post(
        f"/api/v1/change-management/changes/{second}/implement",
        json={
            "implementation_notes": "Next managed change retains initial lineage",
            "components": [
                {
                    "component_id": component,
                    "implemented_version": "1.0.2",
                    "implemented_checksum_hash": "patch2",
                }
            ],
        },
        headers=contributor_headers,
    )
    assert response.status_code == 200, response.text
