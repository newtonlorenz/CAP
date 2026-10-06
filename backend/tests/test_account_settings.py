"""Self-service identity, session rotation and stored personal preference contracts."""

import pytest
from sqlalchemy import select

from app.models.audit import AuditLog
from app.models.user import User
from app.services.auth import create_access_token, hash_password


@pytest.fixture
async def account(db_session):
    user = User(
        email="member@example.com",
        full_name="Member",
        role="contributor",
        password_hash=hash_password("original-password"),
    )
    db_session.add(user)
    await db_session.commit()
    return user


def account_headers(account):
    return {"Authorization": f"Bearer {create_access_token({'sub': str(account.id)})}"}


async def test_account_name_update_is_self_service_and_cannot_change_privileges(client, account):
    headers = account_headers(account)
    response = await client.patch(
        "/api/v1/auth/me", headers=headers, json={"full_name": " New Name "}
    )
    assert response.status_code == 200
    assert response.json()["full_name"] == "New Name"
    assert response.json()["role"] == "contributor"
    assert (await client.get("/api/v1/auth/me", headers=headers)).json()["full_name"] == "New Name"
    for body in ({"full_name": " "}, {"full_name": "Name", "role": "admin"}):
        assert (
            await client.patch("/api/v1/auth/me", headers=headers, json=body)
        ).status_code == 422
    assert (
        await client.patch("/api/v1/auth/me", json={"full_name": "Anonymous"})
    ).status_code == 401


async def test_notification_preferences_default_enabled_and_persist(client, account):
    headers = account_headers(account)
    endpoint = "/api/v1/auth/notification-settings"
    assert (await client.get(endpoint, headers=headers)).json() == {
        "review_mentions": True,
        "review_reminders": True,
    }
    preferences = {"review_mentions": False, "review_reminders": True}
    assert (await client.patch(endpoint, headers=headers, json=preferences)).json() == preferences
    assert (await client.get(endpoint, headers=headers)).json() == preferences
    assert (await client.patch(endpoint, json=preferences)).status_code == 401


async def test_password_change_verifies_current_password_and_rotates_all_sessions(
    client,
    account,
    db_session,
):
    login_body = {"email": account.email, "password": "original-password"}
    assert (await client.post("/api/v1/auth/login", json=login_body)).status_code == 200
    old_access = client.cookies.get("access_token")
    old_refresh = client.cookies.get("refresh_token")
    csrf = {"x-csrf-token": client.cookies.get("csrf_token")}
    endpoint = "/api/v1/auth/change-password"
    body = {"current_password": "original-password", "new_password": "new-password-123"}
    assert (await client.post(endpoint, json=body)).status_code == 403
    wrong = await client.post(endpoint, headers=csrf, json={**body, "current_password": "wrong"})
    assert wrong.status_code == 400
    assert (await client.get("/api/v1/auth/me")).status_code == 200
    too_long = await client.post(endpoint, headers=csrf, json={**body, "new_password": "é" * 37})
    assert too_long.status_code == 422
    assert (await client.post(endpoint, headers=csrf, json=body)).status_code == 204
    assert (await client.get("/api/v1/auth/me")).status_code == 200
    assert (
        await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {old_access}"},
        )
    ).status_code == 401
    # The old refresh token cannot resurrect another browser's invalidated session.
    current_refresh = client.cookies.get("refresh_token")
    client.cookies.set("refresh_token", old_refresh, domain="localhost.local", path="/")
    assert (
        await client.post(
            "/api/v1/auth/refresh",
            headers={"x-csrf-token": client.cookies.get("csrf_token")},
        )
    ).status_code == 401
    client.cookies.set("refresh_token", current_refresh, domain="localhost.local", path="/")
    assert (
        await client.post(
            "/api/v1/auth/refresh",
            headers={"x-csrf-token": client.cookies.get("csrf_token")},
        )
    ).status_code == 200
    assert (await client.post("/api/v1/auth/login", json=login_body)).status_code == 401
    assert (
        await client.post(
            "/api/v1/auth/login",
            json={**login_body, "password": body["new_password"]},
        )
    ).status_code == 200
    entries = (
        (await db_session.execute(select(AuditLog).where(AuditLog.action == "update")))
        .scalars()
        .all()
    )
    assert entries
    for entry in entries:
        assert "original-password" not in (entry.new_value or "")
        assert "new-password-123" not in (entry.new_value or "")
