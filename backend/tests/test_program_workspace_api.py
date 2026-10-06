import pytest

from app.models.user import User
from app.services.auth import create_access_token, hash_password


@pytest.fixture
async def workspace_admin_user(db_session):
    user = User(
        email="workspace-admin@example.com",
        password_hash=hash_password("testpass"),
        full_name="Workspace Admin",
        role="admin",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def workspace_admin_headers(workspace_admin_user):
    token = create_access_token({"sub": str(workspace_admin_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def workspace_contributor_user(db_session):
    user = User(
        email="workspace-contributor@example.com",
        password_hash=hash_password("testpass"),
        full_name="Workspace Contributor",
        role="contributor",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def workspace_contributor_headers(workspace_contributor_user):
    token = create_access_token({"sub": str(workspace_contributor_user.id)})
    return {"Authorization": f"Bearer {token}"}


async def _create_and_approve_requirement_set(
    client,
    headers,
    jurisdiction_id: str,
    *,
    name: str,
) -> str:
    set_resp = await client.post(
        "/api/v1/requirements/sets",
        json={
            "jurisdiction_id": jurisdiction_id,
            "name": name,
            "document_type": "scp",
            "testing_frequency": "monthly",
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


async def test_program_workspace_summary_shows_stage_blockers_and_actions(
    client,
    default_jurisdiction,
    workspace_admin_headers,
):
    baseline_document_id = await _create_and_approve_requirement_set(
        client,
        workspace_admin_headers,
        str(default_jurisdiction.id),
        name="Workspace baseline",
    )

    project_resp = await client.post(
        "/api/v1/certification-projects",
        json={
            "jurisdiction_id": str(default_jurisdiction.id),
            "name": "Workspace project",
            "stage": "intake",
            "status": "active",
            "requirement_set_ids": [baseline_document_id],
        },
        headers=workspace_admin_headers,
    )
    assert project_resp.status_code == 201
    project = project_resp.json()

    # Move to scoping so "submission cycle exists" becomes the active blocker.
    patch_resp = await client.patch(
        f"/api/v1/certification-projects/{project['id']}",
        json={"stage": "scoping"},
        headers=workspace_admin_headers,
    )
    assert patch_resp.status_code == 200

    summary_resp = await client.get(
        f"/api/v1/program-workspace/summary?project_id={project['id']}",
        headers=workspace_admin_headers,
    )
    assert summary_resp.status_code == 200
    data = summary_resp.json()

    assert data["items"]
    item = data["items"][0]
    assert item["project_id"] == project["id"]
    assert item["stage"] == "scoping"
    assert item["current_stage_readiness"]["ready"] is False
    assert item["current_stage_readiness"]["blocker_count"] >= 1
    assert item["blockers"][0]["code"] == "submission_cycle_exists"
    assert len(item["stage_states"]) == 7
    assert data["next_actions"]
    assert data["next_actions"][0]["cta_path"].startswith("/certification-projects?project=")


async def test_program_workspace_actions_are_role_scoped(
    client,
    default_jurisdiction,
    workspace_admin_headers,
    workspace_contributor_headers,
):
    baseline_document_id = await _create_and_approve_requirement_set(
        client,
        workspace_admin_headers,
        str(default_jurisdiction.id),
        name="Role scoped baseline",
    )

    project_resp = await client.post(
        "/api/v1/certification-projects",
        json={
            "jurisdiction_id": str(default_jurisdiction.id),
            "name": "Role scoped project",
            "stage": "scoping",
            "status": "active",
            "requirement_set_ids": [baseline_document_id],
        },
        headers=workspace_admin_headers,
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    admin_resp = await client.get(
        f"/api/v1/program-workspace/summary?project_id={project_id}",
        headers=workspace_admin_headers,
    )
    assert admin_resp.status_code == 200
    assert admin_resp.json()["next_actions"]

    contributor_resp = await client.get(
        f"/api/v1/program-workspace/summary?project_id={project_id}",
        headers=workspace_contributor_headers,
    )
    assert contributor_resp.status_code == 200
    contributor_data = contributor_resp.json()
    assert contributor_data["items"]
    assert contributor_data["next_actions"] == []
