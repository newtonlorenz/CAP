"""Content-authority boundary: administrators, explicit grants and inherited privacy.

These API scenarios guard new disclosure/reset and team-escalation paths not covered
by the application workflow suite; they exercise actual persisted policies.
"""

# ruff: noqa: F811
import pytest

from app.models.application import Application
from app.models.user import User
from app.services.access import (
    effective_permissions,
    has_confidential_access,
    initialize_access,
    protect_child,
)
from tests.test_preparation_api import actors, headers  # noqa: F401


@pytest.fixture
async def secret(db_session, actors, default_jurisdiction):
    owner = actors["manager"]
    row = Application(
        name="Secret acquisition",
        scope="licence",
        jurisdiction_id=default_jurisdiction.id,
        organization_id=owner.organization_id,
        created_by=owner.id,
    )
    db_session.add(row)
    await db_session.flush()
    await initialize_access(db_session, "application", row.id, owner)
    await db_session.commit()
    return row


async def test_named_grants_do_not_allow_admin_takeover_and_revisions_fence_changes(
    client, db_session, actors, secret
):
    owner, reader = actors["manager"], actors["reader"]
    admin = User(
        email="content-admin@example.test",
        full_name="Admin",
        password_hash="unused",
        role="admin",
        organization_id=owner.organization_id,
        active=True,
    )
    db_session.add(admin)
    await db_session.commit()
    path = f"/api/v1/access/application/{secret.id}"
    assert (await client.get(path, headers=headers(admin))).status_code == 404
    assert (
        await client.put(
            path,
            headers=headers(admin),
            json={
                "expected_revision": 1,
                "visibility": "organisation",
                "grants": [],
                "reason": "Take over",
            },
        )
    ).status_code == 404
    response = await client.put(
        path,
        headers=headers(owner),
        json={
            "expected_revision": 1,
            "visibility": "secret",
            "grants": [
                {"subject_type": "user", "subject_id": str(reader.id), "permissions": ["summary"]}
            ],
            "reason": "Status only",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["revision"] == 2
    summary = (await client.get(path, headers=headers(reader))).json()
    assert summary["effective_permissions"] == ["summary"]
    assert summary["grants"] == []
    assert await has_confidential_access(db_session, reader)
    stale = await client.put(
        path,
        headers=headers(owner),
        json={
            "expected_revision": 1,
            "visibility": "organisation",
            "grants": [],
            "reason": "Stale",
        },
    )
    assert stale.status_code == 409
    assert (await client.get(path, headers=headers(admin))).status_code == 404


async def test_secret_rejects_teams_and_team_membership_is_owner_controlled(
    client, db_session, actors, secret
):
    owner, colleague = actors["manager"], actors["contributor"]
    team = await client.post(
        "/api/v1/access/teams",
        headers=headers(owner),
        json={"name": "Licensing", "member_ids": [str(colleague.id)]},
    )
    assert team.status_code == 201, team.text
    team_id = team.json()["id"]
    blocked = await client.put(
        f"/api/v1/access/teams/{team_id}",
        headers=headers(colleague),
        json={
            "name": "Licensing",
            "member_ids": [str(actors["reader"].id)],
            "expected_revision": 1,
        },
    )
    assert blocked.status_code == 404
    path = f"/api/v1/access/application/{secret.id}"
    body = {
        "expected_revision": 1,
        "visibility": "secret",
        "grants": [{"subject_type": "team", "subject_id": team_id, "permissions": ["view"]}],
        "reason": "Team sharing",
    }
    assert (await client.put(path, headers=headers(owner), json=body)).status_code == 422
    body["visibility"] = "restricted"
    response = await client.put(path, headers=headers(owner), json=body)
    assert response.status_code == 200, response.text
    assert (
        "view"
        in (await client.get(path, headers=headers(colleague))).json()["effective_permissions"]
    )
    assert (await client.get(path, headers=headers(actors["reader"]))).status_code == 404


async def test_inheritance_intersects_grants_and_cannot_be_reparented(
    db_session, actors, secret, default_jurisdiction
):
    owner = actors["manager"]
    child = Application(
        name="Child",
        scope="licence",
        jurisdiction_id=default_jurisdiction.id,
        organization_id=owner.organization_id,
        created_by=owner.id,
    )
    another = Application(
        name="Other",
        scope="licence",
        jurisdiction_id=default_jurisdiction.id,
        organization_id=owner.organization_id,
        created_by=owner.id,
    )
    db_session.add_all([child, another])
    await db_session.flush()
    await initialize_access(db_session, "application", child.id, owner, "organisation")
    await initialize_access(db_session, "application", another.id, owner, "organisation")
    assert "view" in await effective_permissions(
        db_session, "application", child.id, actors["reader"]
    )
    await protect_child(db_session, "application", secret.id, "application", child.id, owner)
    assert not await effective_permissions(db_session, "application", child.id, actors["reader"])
    assert await has_confidential_access(db_session, owner)
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        await protect_child(db_session, "application", another.id, "application", child.id, owner)
    assert error.value.status_code == 409
    with pytest.raises(HTTPException) as error:
        await protect_child(db_session, "application", child.id, "application", secret.id, owner)
    assert error.value.status_code == 409


async def test_tightening_existing_application_protects_form_and_response_evidence(
    client, db_session, actors, default_jurisdiction
):
    from app.models.preparation import (
        PreparationEvidence,
        PreparationResponse,
        PreparationResponseEvidence,
    )
    from tests.test_applications_api import component, create
    from tests.test_preparation_api import make_template

    owner, reader = actors["manager"], actors["reader"]
    template = await make_template(client, owner)
    pack = await create(client, owner, default_jurisdiction)
    pack = await component(client, owner, pack, template_id=template["id"])
    import uuid

    case_id = uuid.UUID(pack["components"][0]["case_id"])
    evidence = PreparationEvidence(
        organization_id=owner.organization_id,
        title="Bank details",
        kind="note",
        body="Confidential bank details",
        created_by=owner.id,
    )
    response = PreparationResponse(case_id=case_id, field_key="proof")
    db_session.add_all([evidence, response])
    await db_session.flush()
    db_session.add(PreparationResponseEvidence(response_id=response.id, evidence_id=evidence.id))
    await db_session.commit()
    assert "view" in await effective_permissions(db_session, "preparation_case", case_id, reader)
    assert "view" in await effective_permissions(
        db_session, "preparation_evidence", evidence.id, reader
    )
    path = f"/api/v1/access/application/{pack['id']}"
    revision = (await client.get(path, headers=headers(owner))).json()["revision"]
    changed = await client.put(
        path,
        headers=headers(owner),
        json={
            "expected_revision": revision,
            "visibility": "secret",
            "grants": [],
            "reason": "Restrict transaction team",
        },
    )
    assert changed.status_code == 200, changed.text
    assert not await effective_permissions(db_session, "preparation_case", case_id, reader)
    assert not await effective_permissions(db_session, "preparation_evidence", evidence.id, reader)
    assert (
        await client.get(f"/api/v1/preparation/cases/{case_id}", headers=headers(reader))
    ).status_code == 404
