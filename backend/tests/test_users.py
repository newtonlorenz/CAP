from uuid import UUID

import pytest

from app.config import settings
from app.models.organization import Organization
from app.models.user import User
from app.services.auth import create_access_token, hash_password, verify_password


async def test_create_user_model(db_session):
    user = User(
        email="test@example.com",
        password_hash="hashed",
        full_name="Test User",
        role="contributor",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    assert user.id is not None
    assert user.email == "test@example.com"
    assert user.role == "contributor"
    assert user.active is True


async def test_create_user_as_admin(client, db_session):
    admin = User(
        email="admin@test.com",
        password_hash=hash_password("pass"),
        full_name="Admin",
        role="admin",
    )
    db_session.add(admin)
    await db_session.commit()

    token = create_access_token({"sub": str(admin.id), "role": "admin"})
    response = await client.post(
        "/api/v1/users",
        json={"email": "new@test.com", "password": "newpass123", "full_name": "New User"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    assert response.json()["email"] == "new@test.com"
    assert response.json()["role"] == "contributor"


async def test_create_user_as_contributor_forbidden(client, db_session):
    user = User(
        email="user@test.com",
        password_hash=hash_password("pass"),
        full_name="User",
        role="contributor",
    )
    db_session.add(user)
    await db_session.commit()

    token = create_access_token({"sub": str(user.id), "role": "contributor"})
    response = await client.post(
        "/api/v1/users",
        json={"email": "new@test.com", "password": "newpass123", "full_name": "New User"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


async def test_list_users(client, db_session):
    admin = User(
        email="admin@test.com",
        password_hash=hash_password("pass"),
        full_name="Admin",
        role="admin",
    )
    db_session.add(admin)
    await db_session.commit()

    token = create_access_token({"sub": str(admin.id), "role": "admin"})
    response = await client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["total"] >= 1


async def test_list_users_unauthorized(client):
    response = await client.get("/api/v1/users")
    assert response.status_code == 401  # No token = unauthorized


async def test_user_search_pagination_and_tenant_scope(client, db_session):
    from app.models.organization import Organization

    org = Organization(code="directory", name="Directory test")
    other_org = Organization(code="directory-other", name="Other organisation")
    db_session.add_all([org, other_org])
    await db_session.flush()
    admin = User(
        email="directory-admin@example.test",
        password_hash="unused",
        full_name="Admin",
        role="admin",
        organization_id=org.id,
    )
    db_session.add(admin)
    for index in range(25):
        db_session.add(
            User(
                email=f"colleague-{index:02}@example.test",
                password_hash="unused",
                full_name=f"Colleague {index:02}",
                organization_id=org.id,
                active=index < 22,
            )
        )
    db_session.add(
        User(
            email="outsider@example.test",
            password_hash="unused",
            full_name="Colleague outside",
            organization_id=other_org.id,
        )
    )
    await db_session.commit()
    headers = {
        "Authorization": f"Bearer {create_access_token({'sub': str(admin.id), 'role': 'admin'})}"
    }
    first = (await client.get("/api/v1/users?q=colleague&limit=20", headers=headers)).json()
    second = (
        await client.get("/api/v1/users?q=colleague&limit=20&skip=20", headers=headers)
    ).json()
    assert first["total"] == second["total"] == 25
    assert len(first["items"]) == 20 and len(second["items"]) == 5
    assert len({entry["id"] for entry in first["items"] + second["items"]}) == 25
    match = (await client.get("/api/v1/users?q=COLLEAGUE-24", headers=headers)).json()
    assert match["total"] == 1
    assert match["items"][0]["email"] == "colleague-24@example.test"
    literal = (await client.get("/api/v1/users?q=%25", headers=headers)).json()
    assert literal["total"] == 0
    active = (
        await client.get("/api/v1/users?q=colleague&active=true&limit=20&skip=20", headers=headers)
    ).json()
    inactive = (await client.get("/api/v1/users?q=colleague&active=false", headers=headers)).json()
    assert active["total"] == 22
    assert len(active["items"]) == 2
    assert all(entry["active"] for entry in active["items"])
    assert inactive["total"] == 3
    assert all(not entry["active"] for entry in inactive["items"])
    for invalid in ("skip=-1", "limit=0", "limit=1001", "active=unknown"):
        assert (await client.get("/api/v1/users?" + invalid, headers=headers)).status_code == 422


@pytest.mark.parametrize(
    "changes",
    [
        {"password": "attacker-password"},
        {"email": "attacker@example.com"},
        {"role": "contributor"},
        {"full_name": "Attacker's operator"},
        {"active": False},
    ],
)
async def test_org_admin_cannot_change_installation_operator(
    client, db_session, monkeypatch, changes
):
    org = Organization(code="operator-guard", name="Operator guard")
    db_session.add(org)
    await db_session.flush()
    admin = User(
        organization_id=org.id,
        email="tenant-admin@example.test",
        password_hash=hash_password("admin-password"),
        full_name="Tenant Admin",
        role="admin",
    )
    operator = User(
        organization_id=org.id,
        email="operator@example.test",
        password_hash=hash_password("operator-password"),
        full_name="Installation Operator",
        role="admin",
    )
    db_session.add_all([admin, operator])
    await db_session.commit()
    monkeypatch.setattr(settings, "installation_operator_ids", [str(operator.id)])

    response = await client.put(
        f"/api/v1/users/{operator.id}",
        json=changes,
        headers={"Authorization": f"Bearer {create_access_token({'sub': str(admin.id)})}"},
    )
    assert response.status_code == 403
    await db_session.refresh(operator)
    assert operator.email == "operator@example.test"
    assert operator.full_name == "Installation Operator"
    assert operator.role == "admin"
    assert operator.active is True
    assert operator.auth_version == 0
    assert verify_password("operator-password", operator.password_hash)


@pytest.mark.parametrize("active", [True, False])
async def test_org_admin_cannot_deactivate_installation_operator(client, db_session, monkeypatch, active):
    org = Organization(code="operator-delete", name="Operator delete")
    db_session.add(org)
    await db_session.flush()
    admin = User(
        organization_id=org.id,
        email="delete-admin@example.test",
        password_hash="unused",
        full_name="Tenant Admin",
        role="admin",
    )
    operator = User(
        organization_id=org.id,
        email="delete-operator@example.test",
        password_hash="unused",
        full_name="Installation Operator",
        role="admin",
        active=active,
    )
    db_session.add_all([admin, operator])
    await db_session.commit()
    monkeypatch.setattr(settings, "installation_operator_ids", [str(operator.id)])

    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(admin.id)})}"}
    account = await client.get(f"/api/v1/users/{operator.id}", headers=headers)
    assert account.status_code == 200
    assert account.json()["system_admin_designated"] is True
    assert account.json()["installation_operator"] is active

    response = await client.delete(
        f"/api/v1/users/{operator.id}",
        headers={"Authorization": f"Bearer {create_access_token({'sub': str(admin.id)})}"},
    )
    assert response.status_code == 403
    await db_session.refresh(operator)
    assert operator.active is active


async def test_org_admin_can_manage_ordinary_user_in_same_org(client, db_session, monkeypatch):
    org = Organization(code="ordinary-users", name="Ordinary users")
    db_session.add(org)
    await db_session.flush()
    admin = User(
        organization_id=org.id,
        email="ordinary-admin@example.test",
        password_hash="unused",
        full_name="Tenant Admin",
        role="admin",
    )
    operator = User(
        organization_id=org.id,
        email="ordinary-operator@example.test",
        password_hash="unused",
        full_name="Installation Operator",
        role="admin",
    )
    db_session.add_all([admin, operator])
    await db_session.commit()
    monkeypatch.setattr(settings, "installation_operator_ids", [str(operator.id)])
    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(admin.id)})}"}

    created = await client.post(
        "/api/v1/users",
        json={
            "email": "colleague@example.com",
            "password": "first-password",
            "full_name": "Colleague",
        },
        headers=headers,
    )
    assert created.status_code == 201
    user_id = created.json()["id"]
    updated = await client.put(
        f"/api/v1/users/{user_id}",
        json={
            "email": "colleague-new@example.com",
            "password": "second-password",
            "role": "manager",
            "full_name": "New Name",
        },
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["email"] == "colleague-new@example.com"
    assert updated.json()["role"] == "manager"
    assert updated.json()["full_name"] == "New Name"
    ordinary = await db_session.get(User, UUID(user_id))
    assert verify_password("second-password", ordinary.password_hash)
    assert (await client.delete(f"/api/v1/users/{user_id}", headers=headers)).status_code == 204
    await db_session.refresh(ordinary)
    assert ordinary.active is False
    active_directory = (await client.get("/api/v1/users?active=true", headers=headers)).json()
    assert user_id not in {entry["id"] for entry in active_directory["items"]}
    inactive_directory = (await client.get("/api/v1/users?active=false", headers=headers)).json()
    assert [entry["id"] for entry in inactive_directory["items"]] == [user_id]
    history = await client.get(f"/api/v1/users/{user_id}/edits", headers=headers)
    assert history.status_code == 200
    assert any(entry["action"] == "delete" for entry in history.json()["items"])


async def test_installation_operator_can_update_operator_in_same_org(
    client, db_session, monkeypatch
):
    org = Organization(code="operator-flow", name="Operator flow")
    db_session.add(org)
    await db_session.flush()
    actor = User(
        organization_id=org.id,
        email="actor-operator@example.test",
        password_hash="unused",
        full_name="Actor Operator",
        role="admin",
    )
    target = User(
        organization_id=org.id,
        email="target-operator@example.test",
        password_hash=hash_password("old-password"),
        full_name="Target Operator",
        role="admin",
    )
    db_session.add_all([actor, target])
    await db_session.commit()
    monkeypatch.setattr(settings, "installation_operator_ids", [str(actor.id), str(target.id)])

    response = await client.put(
        f"/api/v1/users/{target.id}",
        json={
            "email": "target-new@example.com",
            "password": "new-password",
            "full_name": "New Operator Name",
        },
        headers={"Authorization": f"Bearer {create_access_token({'sub': str(actor.id)})}"},
    )
    assert response.status_code == 200
    await db_session.refresh(target)
    assert target.email == "target-new@example.com"
    assert target.full_name == "New Operator Name"
    assert verify_password("new-password", target.password_hash)
    assert target.auth_version == 1
