import io
import tarfile
import pytest
from app.config import settings
from app.models.user import User
from app.services.auth import create_access_token, decode_token, hash_password
from app.services.jira import normalize_jira_base_url, validate_saved_token_target
from app.services.backups import _safe_extract_tar, BackupValidationError
from types import SimpleNamespace


@pytest.fixture
async def account(db_session):
    user = User(
        email="session@example.test",
        full_name="Session fixture",
        role="admin",
        password_hash=hash_password("test-session-password"),
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def login(client, account):
    response = await client.post(
        "/api/v1/auth/login", json={"email": account.email, "password": "test-session-password"}
    )
    assert response.status_code == 200
    return response.cookies.get("access_token"), response.cookies.get("refresh_token")


async def test_logout_revokes_access_and_refresh(client, account):
    access, refresh = await login(client, account)
    payload = decode_token(access)
    assert payload["sub"] == str(account.id)
    assert payload["jti"] == decode_token(refresh)["jti"]
    response = await client.post(
        "/api/v1/auth/logout", headers={"X-CSRF-Token": client.cookies.get("csrf_token")}
    )
    assert response.status_code == 204
    assert (
        await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + access})
    ).status_code == 401
    client.cookies.set("refresh_token", refresh)
    client.cookies.set("csrf_token", "fixture-csrf")
    assert (
        await client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": "fixture-csrf"})
    ).status_code == 401


async def test_logout_with_invalid_bearer_still_revokes_cookie_session(client, account):
    access, _ = await login(client, account)
    response = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": "Bearer invalid", "X-CSRF-Token": client.cookies["csrf_token"]},
    )
    assert response.status_code == 204
    assert (
        await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + access})
    ).status_code == 401


async def test_bearer_header_cannot_skip_cookie_logout_csrf(client, account):
    access, _ = await login(client, account)
    response = await client.post(
        "/api/v1/auth/logout", headers={"Authorization": "Bearer " + access}
    )
    assert response.status_code == 403
    assert (
        await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + access})
    ).status_code == 200


async def test_cookie_logout_does_not_revoke_a_separate_bearer_session(client, account):
    access, _ = await login(client, account)
    bearer = create_access_token({"sub": str(account.id)})
    assert decode_token(bearer)["jti"] != decode_token(access)["jti"]
    response = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": "Bearer " + bearer, "X-CSRF-Token": client.cookies["csrf_token"]},
    )
    assert response.status_code == 204
    assert (
        await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + access})
    ).status_code == 401
    assert (
        await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + bearer})
    ).status_code == 200


async def test_bearer_only_logout_revokes_its_session(client, account):
    access, _ = await login(client, account)
    client.cookies.clear()
    response = await client.post(
        "/api/v1/auth/logout", headers={"Authorization": "Bearer " + access}
    )
    assert response.status_code == 204
    assert (
        await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + access})
    ).status_code == 401


async def test_refresh_requires_csrf_and_preserves_absolute_expiry(client, account):
    access, refresh = await login(client, account)
    assert (await client.post("/api/v1/auth/refresh")).status_code == 403
    original = decode_token(refresh)
    response = await client.post(
        "/api/v1/auth/refresh", headers={"X-CSRF-Token": client.cookies.get("csrf_token")}
    )
    assert response.status_code == 200
    assert decode_token(response.cookies.get("refresh_token"))["exp"] == original["exp"]
    assert decode_token(response.cookies.get("access_token"))["jti"] == original["jti"]


async def test_account_change_revokes_old_tokens_and_email_reuse_cannot_impersonate(
    client, db_session, account
):
    token = create_access_token({"sub": str(account.id)})
    response = await client.put(
        f"/api/v1/users/{account.id}",
        headers={"Authorization": "Bearer " + token},
        json={"password": "new-password-123"},
    )
    assert response.status_code == 200
    assert (
        await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token})
    ).status_code == 401
    legacy = create_access_token({"sub": account.email})
    assert (
        await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + legacy})
    ).status_code == 401


@pytest.mark.parametrize("via_api", [False, True])
async def test_email_reassigned_across_organisations_never_transfers_identity(
    client, db_session, account, via_api
):
    from app.models.organization import Organization

    original_org = Organization(code="original", name="Original organisation")
    replacement_org = Organization(code="replacement", name="Replacement organisation")
    db_session.add_all([original_org, replacement_org])
    await db_session.flush()
    account.organization_id = original_org.id
    await db_session.commit()
    old_email = account.email
    token = create_access_token({"sub": str(account.id)})
    legacy = create_access_token({"sub": old_email})
    headers = {"Authorization": "Bearer " + token}
    if via_api:
        response = await client.put(
            f"/api/v1/users/{account.id}", headers=headers,
            json={"email": "renamed@example.com"},
        )
        assert response.status_code == 200
    else:
        # Even an out-of-band rename that omits revocation must not transfer identity.
        account.email = "renamed@example.com"
        await db_session.commit()
    replacement = User(
        organization_id=replacement_org.id, email=old_email, full_name="Replacement",
        role="admin", password_hash=account.password_hash,
    )
    db_session.add(replacement)
    await db_session.commit()
    response = await client.get("/api/v1/auth/me", headers=headers)
    if via_api:
        assert response.status_code == 401
    else:
        assert response.status_code == 200
        assert response.json()["id"] == str(account.id)
        assert response.json()["organization_id"] == str(original_org.id)
    assert (
        await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + legacy})
    ).status_code == 401


@pytest.mark.parametrize("change", [
    {"email": "renamed@example.com"},
    {"role": "manager"},
    {"active": False},
])
async def test_identity_or_authority_change_revokes_old_token(client, account, change):
    access, _ = await login(client, account)
    response = await client.put(
        f"/api/v1/users/{account.id}",
        headers={"Authorization": "Bearer " + access},
        json=change,
    )
    assert response.status_code == 200
    assert (
        await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + access})
    ).status_code == 401


async def test_deactivation_and_reactivation_do_not_restore_old_token(client, db_session, account):
    access, _ = await login(client, account)
    response = await client.delete(
        f"/api/v1/users/{account.id}",
        headers={"Authorization": "Bearer " + access},
    )
    assert response.status_code == 400  # Self-deletion is forbidden.
    from app.models.user import User
    actor = User(
        email="other-admin@example.test", full_name="Other admin", role="admin",
        password_hash=hash_password("other-password"),
    )
    db_session.add(actor)
    await db_session.commit()
    actor_headers = {"Authorization": "Bearer " + create_access_token({"sub": str(actor.id)})}
    assert (await client.delete(f"/api/v1/users/{account.id}", headers=actor_headers)).status_code == 204
    assert (
        await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + access})
    ).status_code == 401
    assert (
        await client.put(f"/api/v1/users/{account.id}", headers=actor_headers, json={"active": True})
    ).status_code == 200
    assert (
        await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + access})
    ).status_code == 401


async def test_overlong_password_rejected_without_changing_account(client, account):
    access, _ = await login(client, account)
    headers = {"Authorization": "Bearer " + access}
    response = await client.put(
        f"/api/v1/users/{account.id}", headers=headers, json={"password": "é" * 37}
    )
    assert response.status_code == 422
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200


async def test_shared_login_throttle_blocks_repeated_guesses(client, account):
    for i in range(9):
        response = await client.post(
            "/api/v1/auth/login", json={"email": account.email, "password": "wrong"}
        )
        assert response.status_code == (401 if i < 8 else 429)
    assert response.headers["retry-after"] == "600"


async def test_source_throttle_is_shared_across_accounts(db_session):
    from fastapi import HTTPException
    from app.services.login_throttle import check_login_limit

    for i in range(60):
        await check_login_limit(db_session, f"different-{i}@example.test", "192.0.2.8")
    with pytest.raises(HTTPException) as error:
        await check_login_limit(db_session, "yet-another@example.test", "192.0.2.8")
    assert error.value.status_code == 429


async def test_account_throttle_is_shared_across_sources(db_session):
    from fastapi import HTTPException
    from app.services.login_throttle import check_login_limit

    for i in range(8):
        await check_login_limit(db_session, "same@example.test", f"192.0.2.{i + 1}")
    with pytest.raises(HTTPException) as error:
        await check_login_limit(db_session, "same@example.test", "192.0.2.100")
    assert error.value.status_code == 429


async def test_company_admin_cannot_manage_installation(client, account, monkeypatch):
    monkeypatch.setattr(settings, "installation_operator_ids", [])
    headers = {"Authorization": "Bearer " + create_access_token({"sub": str(account.id)})}
    assert (await client.get("/api/v1/admin/backups", headers=headers)).status_code == 403
    assert (await client.get("/api/v1/auth/me", headers=headers)).json()[
        "installation_operator"
    ] is False


@pytest.mark.parametrize(
    "url",
    [
        "http://example.atlassian.net",
        "https://127.0.0.1",
        "https://example.atlassian.net.attacker.test",
        "https://u:p@example.atlassian.net",
        "https://example.atlassian.net:444",
    ],
)
def test_jira_rejects_untrusted_destinations(url):
    with pytest.raises(ValueError):
        normalize_jira_base_url(url)


def test_jira_saved_token_is_bound_to_site_and_account():
    saved = SimpleNamespace(base_url="https://old.atlassian.net", user_email="owner@example.test")
    for url, email in [
        ("https://new.atlassian.net", saved.user_email),
        (saved.base_url, "different@example.test"),
    ]:
        with pytest.raises(ValueError):
            validate_saved_token_target(saved, url, email, None)
    validate_saved_token_target(saved, saved.base_url, saved.user_email, None)


def test_backup_rejects_expansion_and_links(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "backup_expanded_max_mb", 1)
    for link in (False, True):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            info = tarfile.TarInfo("oversized")
            if link:
                info.type = tarfile.SYMTYPE
                info.linkname = "/etc/passwd"
                tar.addfile(info)
            else:
                info.size = 1024 * 1024 + 1
                tar.addfile(info, io.BytesIO(b"0" * info.size))
        buffer.seek(0)
        with tarfile.open(fileobj=buffer, mode="r:gz") as tar, pytest.raises(BackupValidationError):
            _safe_extract_tar(tar, tmp_path)
        assert not (tmp_path / "oversized").exists()
