"""Confidential application API boundary, including retained documents and metadata."""

# ruff: noqa: F811
import pytest

from app.models import User
from tests.test_applications_api import action, answer, component
from tests.test_preparation_api import actors, headers, make_template  # noqa: F401

BASE = "/api/v1/applications"
PREP = "/api/v1/preparation"


@pytest.fixture
async def account_admin(db_session, actors):
    user = User(
        email="account-admin@privacy.test",
        full_name="Account admin",
        password_hash="unused",
        role="admin",
        active=True,
        organization_id=actors["manager"].organization_id,
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def secret_pack(client, user, jurisdiction):
    response = await client.post(
        BASE,
        headers=headers(user),
        json={
            "name": "Confidential acquisition",
            "scope": "full_pack",
            "jurisdiction_id": str(jurisdiction.id),
            "description": "Secret negotiation",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def grant(client, owner, kind, resource_id, subject, permissions):
    url = f"/api/v1/access/{kind}/{resource_id}"
    existing = await client.get(url, headers=headers(owner))
    assert existing.status_code == 200, existing.text
    policy = existing.json()
    response = await client.put(
        url,
        headers=headers(owner),
        json={
            "visibility": policy["visibility"],
            "expected_revision": policy["revision"],
            "reason": "Authorised confidential review",
            "grants": [
                {
                    "subject_type": "user",
                    "subject_id": str(subject.id),
                    "permissions": permissions,
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_secret_application_is_invisible_to_same_org_account_admin(
    client, actors, account_admin, default_jurisdiction
):
    owner = actors["manager"]
    pack = await secret_pack(client, owner, default_jurisdiction)
    assert pack["access"]["visibility"] == "secret"
    for user in [account_admin, actors["reader"], actors["other"]]:
        response = await client.get(BASE, headers=headers(user), params={"q": "Confidential"})
        assert response.status_code == 200
        assert response.json() == {"items": [], "total": 0}
        response = await client.get(f"{BASE}/{pack['id']}", headers=headers(user))
        assert response.status_code == 404
        response = await client.patch(
            f"{BASE}/{pack['id']}",
            headers=headers(user),
            json={"expected_revision": 1, "name": "Exposed"},
        )
        assert response.status_code in (403, 404)
    await grant(client, owner, "application", pack["id"], account_admin, ["summary"])
    summary = (await client.get(f"{BASE}/{pack['id']}", headers=headers(account_admin))).json()
    assert set(summary) == {"id", "name", "status", "due_date", "access", "summary_only"}
    assert summary["summary_only"] is True
    assert "Secret negotiation" not in str(summary)
    result = await client.get(BASE, headers=headers(account_admin), params={"scope": "full_pack"})
    assert result.json()["total"] == 0


async def test_secret_linked_sources_and_retained_pack_require_explicit_access(
    client, actors, account_admin, default_jurisdiction
):
    owner = actors["manager"]
    pack = await secret_pack(client, owner, default_jurisdiction)
    template = await make_template(client, owner)
    pack = await component(client, owner, pack, template_id=template["id"])
    case_id = pack["components"][0]["case_id"]
    await answer(client, owner, case_id)
    evidence = await client.post(
        f"{PREP}/evidence",
        headers=headers(owner),
        json={
            "kind": "note",
            "title": "Confidential financial statement",
            "body": "Private figures",
        },
    )
    assert evidence.status_code == 201, evidence.text
    evidence_id = evidence.json()["id"]
    pack = await component(client, owner, pack, kind="document", evidence_id=evidence_id)
    for url in [
        f"{PREP}/cases/{case_id}",
        f"{PREP}/cases/{case_id}/export",
        f"{PREP}/evidence/{evidence_id}",
        f"{PREP}/evidence/{evidence_id}/download",
    ]:
        response = await client.get(url, headers=headers(account_admin))
        assert response.status_code == 404, (url, response.text)
    for url in [f"{PREP}/cases", f"{PREP}/evidence"]:
        assert (await client.get(url, headers=headers(account_admin))).json()["total"] == 0
    await grant(
        client, owner, "application", pack["id"], account_admin, ["view", "export", "approve"]
    )
    # Application access cannot override a separately private financial attachment.
    detail = (await client.get(f"{BASE}/{pack['id']}", headers=headers(account_admin))).json()
    assert evidence_id not in str(detail)
    assert "Confidential financial statement" not in str(detail)
    assert detail["readiness"]["blockers"] == [{
        "code": "restricted_source", "message": "Additional access is required to review this pack"
    }]
    assert detail["history"] == []
    assert detail["snapshots"] == []
    pack = await action(client, owner, pack, "request-review")
    # Owner still needs the existing approver business role to approve.
    await grant(
        client, owner, "preparation_evidence", evidence_id, account_admin, ["view", "export"]
    )
    approved = await action(client, account_admin, pack, "approve")
    snapshot_id = approved["snapshots"][0]["id"]
    download = f"{BASE}/{pack['id']}/snapshots/{snapshot_id}/export"
    assert (await client.get(download, headers=headers(account_admin))).status_code == 200
    await grant(client, owner, "application", pack["id"], account_admin, ["view"])
    assert (await client.get(download, headers=headers(account_admin))).status_code == 404
    await grant(
        client, owner, "application", pack["id"], account_admin, ["view", "export", "approve"]
    )
    await grant(client, owner, "preparation_evidence", evidence_id, account_admin, ["summary"])
    # Snapshot bytes remain immutable, but revocation also protects historical copies.
    assert (await client.get(download, headers=headers(account_admin))).status_code == 404


async def test_private_response_evidence_is_not_disclosed_or_reused_through_public_form(
    client, actors, account_admin, default_jurisdiction
):
    owner = actors["manager"]
    template = await make_template(client, owner)
    cases = []
    for name in ("Source", "Target"):
        response = await client.post(
            f"{PREP}/cases",
            headers=headers(owner),
            json={
                "name": name,
                "template_id": template["id"],
                "visibility": "organisation",
                "jurisdiction_id": str(default_jurisdiction.id),
            },
        )
        assert response.status_code == 201, response.text
        cases.append(response.json())
    source, target = cases
    evidence = await client.post(
        f"{PREP}/evidence",
        headers=headers(owner),
        json={
            "kind": "note",
            "title": "Personal declaration",
            "body": "Private evidence",
        },
    )
    evidence_id = evidence.json()["id"]
    written = await client.put(
        f"{PREP}/cases/{source['id']}/responses/answer",
        headers=headers(owner),
        json={
            "expected_revision": source["revision"],
            "value": "Private response",
            "evidence_ids": [evidence_id],
        },
    )
    assert written.status_code == 200, written.text
    accepted = await client.post(
        f"{PREP}/cases/{source['id']}/responses/answer/accept",
        headers=headers(owner),
        json={"expected_revision": written.json()["revision"]},
    )
    assert accepted.status_code == 200, accepted.text
    read = await client.get(f"{PREP}/cases/{source['id']}", headers=headers(account_admin))
    assert read.status_code == 200, read.text
    assert read.json()["responses"] == []
    assert evidence_id not in read.text and "Private response" not in read.text
    suggestions = await client.get(
        f"{PREP}/cases/{target['id']}/reuse",
        headers=headers(account_admin),
        params={"field_key": "answer"},
    )
    assert suggestions.status_code == 200
    assert suggestions.json()["items"] == []
    overwrite = await client.put(
        f"{PREP}/cases/{source['id']}/responses/answer",
        headers=headers(account_admin),
        json={
            "expected_revision": accepted.json()["revision"],
            "value": "Overwrite hidden content",
        },
    )
    assert overwrite.status_code == 404
    exported = await client.get(
        f"{PREP}/cases/{source['id']}/export", headers=headers(account_admin)
    )
    assert exported.status_code in (404, 409)
