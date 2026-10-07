"""Requirement evidence must not be disclosed or changed by unrelated tenant users."""

# ruff: noqa: F811

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.audit import AuditLog
from app.models.program import EvidenceItem, EvidenceValidation
from app.models.requirement import Requirement
from app.models.user import User
from app.services.access import access_clause
from app.services.access_audit import audit_access_clause
from tests.test_preparation_api import actors, headers  # noqa: F401

BASE = "/api/v1/evidence-items"
VALIDATIONS = "/api/v1/evidence-validations"


@pytest.fixture
async def evidence_users(db_session, actors):
    for label, role in [
        ("owner", "contributor"),
        ("reviewer", "approver"),
        ("admin", "admin"),
        ("other_manager", "manager"),
        ("other_approver", "approver"),
    ]:
        user = User(
            email=f"evidence-{label}@example.test",
            full_name=label,
            password_hash="unused",
            role=role,
            organization_id=actors["manager"].organization_id,
            active=True,
        )
        db_session.add(user)
        actors[label] = user
    await db_session.commit()
    return actors


@pytest.fixture
async def evidence_requirement(db_session, evidence_users, default_jurisdiction):
    row = Requirement(
        organization_id=evidence_users["manager"].organization_id,
        jurisdiction_id=default_jurisdiction.id,
        reference_id="PRIVATE-EVIDENCE",
        text="Retain proof",
        requirement_type="mandatory",
        active=True,
        sort_order=1,
    )
    db_session.add(row)
    await db_session.commit()
    return row


async def create(client, users, requirement, **changes):
    response = await client.post(
        BASE,
        headers=headers(users["manager"]),
        json={
            "requirement_id": str(requirement.id),
            "evidence_type": "note",
            "title": "Confidential evidence",
            "body": "Private findings",
            "file_path": "/private/evidence.txt",
            "link_url": "https://example.test/private",
            "owner_id": str(users["owner"].id),
            "reviewer_id": str(users["reviewer"].id),
            "valid_to": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
            **changes,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize(
    "actor",
    ["contributor", "reader", "admin", "other_manager", "other_approver", "other", "null_manager"],
)
async def test_unrelated_users_cannot_enumerate_tamper_or_validate(
    client,
    db_session,
    evidence_users,
    evidence_requirement,
    actor,
):
    users = evidence_users
    item = await create(client, users, evidence_requirement)
    path = f"{BASE}/{item['id']}"
    approved = await client.patch(
        path, headers=headers(users["reviewer"]), json={"review_status": "approved"}
    )
    assert approved.status_code == 200, approved.text
    validation = await client.post(
        VALIDATIONS,
        headers=headers(users["reviewer"]),
        json={
            "evidence_item_id": item["id"],
            "validation_status": "pass",
            "comment": "Secret review",
        },
    )
    assert validation.status_code == 201, validation.text
    for query in (
        "",
        "?limit=1&skip=0",
        f"?requirement_id={evidence_requirement.id}",
        "?review_status=approved",
        "?stale_only=true",
    ):
        response = await client.get(BASE + query, headers=headers(users[actor]))
        assert response.status_code == 200, response.text
        assert response.json() == {"items": [], "total": 0}
    for payload in (
        {"body": "Tampered"},
        {"owner_id": str(users[actor].id)},
        {"reviewer_id": str(users[actor].id)},
        {"review_status": "draft"},
        {"review_status": "approved"},
        {},
    ):
        denied = await client.patch(path, headers=headers(users[actor]), json=payload)
        assert denied.status_code == 404, denied.text
    for query in ("", f"?evidence_item_id={item['id']}"):
        response = await client.get(VALIDATIONS + query, headers=headers(users[actor]))
        assert response.json() == {"items": [], "total": 0}
    denied = await client.post(
        VALIDATIONS,
        headers=headers(users[actor]),
        json={
            "evidence_item_id": item["id"],
            "validation_status": "fail",
            "comment": "Tampered",
        },
    )
    assert denied.status_code == 404, denied.text
    stored = await db_session.get(EvidenceItem, uuid.UUID(item["id"]))
    assert stored.body == "Private findings" and stored.review_status == "approved"
    assert str(stored.approved_by) == str(users["reviewer"].id)
    assert str(stored.owner_id) == str(users["owner"].id)
    assert str(stored.reviewer_id) == str(users["reviewer"].id)


async def test_participants_have_separate_content_and_decision_rights(
    client,
    db_session,
    evidence_users,
    evidence_requirement,
):
    users = evidence_users
    item = await create(client, users, evidence_requirement)
    path = f"{BASE}/{item['id']}"
    for actor in ("manager", "owner", "reviewer"):
        response = await client.get(BASE, headers=headers(users[actor]))
        assert response.json()["total"] == 1
        assert response.json()["items"][0]["body"] == "Private findings"
    for actor in ("manager", "owner"):
        edit = await client.patch(path, headers=headers(users[actor]), json={"body": actor})
        assert edit.status_code == 200, edit.text
        decision = await client.patch(
            path, headers=headers(users[actor]), json={"review_status": "approved"}
        )
        assert decision.status_code == 403
    for payload in (
        {"body": "Reviewer edit"},
        {"owner_id": str(users["reviewer"].id)},
        {"body": "Reviewer edit", "review_status": "approved"},
    ):
        denied = await client.patch(path, headers=headers(users["reviewer"]), json=payload)
        assert denied.status_code == 404
    for status in ("approved", "rejected", "approved", "draft"):
        decision = await client.patch(
            path, headers=headers(users["reviewer"]), json={"review_status": status}
        )
        # A reviewer can withdraw approval, but cannot submit draft content for review.
        assert decision.status_code == 200, decision.text
    approved = await client.patch(
        path, headers=headers(users["reviewer"]), json={"review_status": "approved"}
    )
    assert approved.status_code == 200
    edited = await client.patch(path, headers=headers(users["owner"]), json={"body": "Revised"})
    assert edited.status_code == 200
    assert edited.json()["review_status"] == "draft"
    assert edited.json()["approved_at"] is None and edited.json()["approved_by"] is None
    # Reassigning a reviewer removes their access on the next request.
    reassigned = await client.patch(
        path, headers=headers(users["owner"]), json={"reviewer_id": str(users["reader"].id)}
    )
    assert reassigned.status_code == 200
    assert (await client.get(BASE, headers=headers(users["reviewer"]))).json()["total"] == 0
    assert (await client.get(BASE, headers=headers(users["reader"]))).json()["total"] == 1
    assert (
        await client.patch(path, headers=headers(users["reader"]), json={"body": "Read-only edit"})
    ).status_code == 404
    # Owner reassignment cannot smuggle a user from another tenant into the audience.
    assert (
        await client.patch(
            path, headers=headers(users["owner"]), json={"owner_id": str(users["other"].id)}
        )
    ).status_code == 404


async def test_existing_unassigned_items_and_pagination_fail_closed(
    client,
    db_session,
    evidence_users,
    evidence_requirement,
):
    users = evidence_users
    for creator in (users["manager"], users["contributor"]):
        db_session.add(
            EvidenceItem(
                organization_id=creator.organization_id,
                requirement_id=evidence_requirement.id,
                evidence_type="note",
                title=f"Existing {creator.id}",
                body="Private",
                created_by=creator.id,
            )
        )
    await db_session.commit()
    for skip, size in ((0, 1), (1, 0)):
        response = await client.get(
            f"{BASE}?limit=1&skip={skip}", headers=headers(users["contributor"])
        )
        assert response.json()["total"] == 1
        assert len(response.json()["items"]) == size
    assert (await client.get(BASE, headers=headers(users["admin"]))).json()["total"] == 0
    assert (
        await client.post(
            BASE,
            headers=headers(users["reader"]),
            json={
                "requirement_id": str(evidence_requirement.id),
                "title": "No read-only writes",
                "evidence_type": "note",
            },
        )
    ).status_code == 403


async def test_assigned_admin_can_edit_and_approve_but_manager_cannot_validate(
    client, evidence_users, evidence_requirement
):
    users = evidence_users
    item = await create(
        client,
        users,
        evidence_requirement,
        owner_id=str(users["admin"].id),
    )
    path = f"{BASE}/{item['id']}"
    decision = await client.patch(
        path,
        headers=headers(users["admin"]),
        json={"body": "Approved replacement", "review_status": "approved"},
    )
    assert decision.status_code == 200, decision.text
    assert decision.json()["body"] == "Approved replacement"
    assert decision.json()["approved_by"] == str(users["admin"].id)
    for actor, expected in (("manager", 404), ("admin", 201)):
        validation = await client.post(
            VALIDATIONS,
            headers=headers(users[actor]),
            json={"evidence_item_id": item["id"], "validation_status": "pass"},
        )
        assert validation.status_code == expected, validation.text


async def test_revoked_owner_and_inactive_participant_have_no_sql_access(
    client, db_session, evidence_users, evidence_requirement
):
    users = evidence_users
    item = await create(client, users, evidence_requirement)
    reassigned = await client.patch(
        f"{BASE}/{item['id']}",
        headers=headers(users["manager"]),
        json={"owner_id": str(users["contributor"].id)},
    )
    assert reassigned.status_code == 200, reassigned.text
    assert (await client.get(BASE, headers=headers(users["owner"]))).json()["total"] == 0
    assert (await client.get(BASE, headers=headers(users["contributor"]))).json()["total"] == 1
    for actor in ("owner", "contributor"):
        if actor == "contributor":
            users[actor].active = False
            await db_session.commit()
        for action in ("summary", "view", "edit", "approve", "export", "manage_access"):
            visible = list(
                await db_session.scalars(
                    select(EvidenceItem.id).where(
                        EvidenceItem.id == uuid.UUID(item["id"]),
                        access_clause(EvidenceItem, users[actor], action),
                    )
                )
            )
            assert visible == [], (actor, action)


async def test_evidence_and_validation_audits_do_not_leak_to_account_admin(
    client,
    db_session,
    evidence_users,
    evidence_requirement,
):
    users = evidence_users
    item = await create(client, users, evidence_requirement)
    validated = await client.post(
        VALIDATIONS,
        headers=headers(users["reviewer"]),
        json={
            "evidence_item_id": item["id"],
            "validation_status": "pass",
            "comment": "Private",
        },
    )
    assert validated.status_code == 201
    for actor, expected in (("manager", 2), ("owner", 2), ("reviewer", 2), ("admin", 0)):
        logs = list(
            (
                await db_session.scalars(
                    select(AuditLog).where(
                        AuditLog.entity_type.in_(("evidence_item", "evidence_validation")),
                        audit_access_clause(users[actor]),
                    )
                )
            ).all()
        )
        assert len(logs) == expected
    for subject in ("manager", "reviewer"):
        response = await client.get(
            f"/api/v1/users/{users[subject].id}/audit", headers=headers(users["admin"])
        )
        assert response.status_code == 200, response.text
        assert response.json() == {"items": [], "total": 0}
    exported = await client.get("/api/v1/reports/audit-trail", headers=headers(users["admin"]))
    assert exported.status_code == 200, exported.text
    assert item["id"] not in exported.text and "Confidential evidence" not in exported.text
    # Associated rows use the same rule for SQL consumers outside these routes.
    ids = list(
        (
            await db_session.scalars(
                select(EvidenceValidation.id).where(
                    access_clause(EvidenceValidation, users["admin"], "view")
                )
            )
        ).all()
    )
    assert ids == []


async def test_direct_patch_cannot_invalidate_another_users_approved_evidence(
    client,
    db_session,
    evidence_users,
    evidence_requirement,
):
    users = evidence_users
    item = await create(client, users, evidence_requirement)
    path = f"{BASE}/{item['id']}"
    approved = await client.patch(
        path, headers=headers(users["reviewer"]), json={"review_status": "approved"}
    )
    assert approved.status_code == 200
    response = await client.patch(
        path, headers=headers(users["contributor"]), json={"body": "Unauthorised replacement"}
    )
    assert response.status_code == 404, response.text
    stored = await db_session.get(EvidenceItem, uuid.UUID(item["id"]))
    assert stored.body == "Private findings" and stored.review_status == "approved"
    assert stored.approved_by == users["reviewer"].id
