"""Audit readers must not recover private source content through a visible parent."""
# ruff: noqa: F811

from sqlalchemy import select

from app.models.audit import AuditLog
from app.services.access_audit import audit_access_clause
from tests.test_application_privacy import account_admin, grant, secret_pack  # noqa: F401
from tests.test_applications_api import component
from tests.test_preparation_api import actors, headers, make_template  # noqa: F401


async def test_audit_filters_partial_parent_events_before_pagination_and_export(
    client, db_session, actors, account_admin, default_jurisdiction
):
    owner = actors["manager"]
    pack = await secret_pack(client, owner, default_jurisdiction)
    template = await make_template(client, owner)
    pack = await component(client, owner, pack, template_id=template["id"])
    case_id = pack["components"][0]["case_id"]
    evidence = await client.post(
        "/api/v1/preparation/evidence",
        headers=headers(owner),
        json={
            "kind": "note",
            "title": "Hidden declaration",
            "body": "Confidential finances",
        },
    )
    evidence_id = evidence.json()["id"]
    saved = await client.put(
        f"/api/v1/preparation/cases/{case_id}/responses/answer",
        headers=headers(owner),
        json={
            "expected_revision": 1,
            "value": "Confidential answer",
            "evidence_ids": [evidence_id],
        },
    )
    assert saved.status_code == 200, saved.text
    await grant(client, owner, "application", pack["id"], account_admin, ["view"])
    response = await client.get(f"/api/v1/users/{owner.id}/audit", headers=headers(account_admin))
    assert response.status_code == 200, response.text
    assert all(
        item["entity_type"]
        not in ("application", "preparation_case", "preparation_response", "preparation_evidence")
        for item in response.json()["items"]
    )
    assert "Hidden declaration" not in response.text
    assert "Confidential answer" not in response.text
    count = response.json()["total"]
    all_events = await client.get(
        f"/api/v1/users/{owner.id}/audit", headers=headers(account_admin), params={"limit": 500}
    )
    assert count == len(all_events.json()["items"])
    csv = await client.get("/api/v1/reports/audit-trail", headers=headers(account_admin))
    assert csv.status_code == 200, csv.text
    assert evidence_id not in csv.text and "Confidential answer" not in csv.text
    # Restoring source visibility allows the event to appear, with payload minimised.
    await grant(client, owner, "preparation_evidence", evidence_id, account_admin, ["view"])
    visible = await client.get(
        f"/api/v1/users/{owner.id}/audit", headers=headers(account_admin), params={"limit": 500}
    )
    response_events = [
        item for item in visible.json()["items"] if item["entity_type"] == "preparation_response"
    ]
    assert response_events
    assert all(item["old_value"] is None and item["new_value"] is None for item in response_events)


async def test_unlinked_private_source_still_hides_application_audit_history(
    client, db_session, actors, account_admin, default_jurisdiction
):
    owner = actors["manager"]
    pack = await secret_pack(client, owner, default_jurisdiction)
    evidence = await client.post(
        "/api/v1/preparation/evidence",
        headers=headers(owner),
        json={
            "kind": "note",
            "title": "Removed private material",
            "body": "Historical confidential information",
        },
    )
    evidence_id = evidence.json()["id"]
    pack = await component(client, owner, pack, kind="document", evidence_id=evidence_id)
    component_id = pack["components"][0]["id"]
    patched = await client.patch(
        f"/api/v1/applications/{pack['id']}/components/{component_id}",
        headers=headers(owner),
        json={"expected_revision": pack["revision"], "evidence_id": None},
    )
    assert patched.status_code == 200, patched.text
    await grant(client, owner, "application", pack["id"], account_admin, ["view"])
    detail = await client.get(f"/api/v1/applications/{pack['id']}", headers=headers(account_admin))
    assert detail.status_code == 200
    assert detail.json()["history"] == []
    app_events = (
        await db_session.scalars(
            select(AuditLog).where(
                AuditLog.entity_type == "application",
                AuditLog.entity_id == pack["id"],
                audit_access_clause(account_admin),
            )
        )
    ).all()
    assert app_events == []
