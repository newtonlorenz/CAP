"""Public authority, secret isolation, revision and saved-configuration test contracts."""

import asyncio
import json
import secrets
import smtplib
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import select

from app.config import settings
from app.models.audit import AuditLog
from app.models.installation_settings import InstallationSettings
from app.models.user import User
from app.services.auth import create_access_token
from app.services.installation_settings import resolve_installation_settings

BASE = "/api/v1/admin/installation-settings"


@pytest.fixture
async def operator(db_session, monkeypatch):
    monkeypatch.setattr(settings, "installation_operator_ids", [])
    user = User(
        email="operator@example.com",
        full_name="Operator",
        password_hash="unused",
        role="admin",
        operator_trusted=True,
    )
    db_session.add(user)
    await db_session.commit()
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}


def email_body(**changes):
    return {
        "mode": "smtp",
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_user": "account",
        "smtp_from": "sender@example.com",
        "smtp_security": "starttls",
        "revision": 0,
        **changes,
    }


@pytest.mark.parametrize("role,trusted", [("admin", False), ("contributor", True)])
async def test_system_admin_authority_covers_all_endpoints(
    client, db_session, monkeypatch, role, trusted
):
    monkeypatch.setattr(settings, "installation_operator_ids", [])
    user = User(
        email="tenant@example.com",
        full_name="Tenant",
        password_hash="unused",
        role=role,
        operator_trusted=trusted,
    )
    db_session.add(user)
    await db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}
    for method, path, body in [
        ("GET", "", None),
        ("PUT", "/email", email_body()),
        ("PUT", "/ai", {"provider": "none", "revision": 0}),
        ("POST", "/email/test", None),
        ("POST", "/ai/test", None),
        ("PUT", "/jev", {"enabled": False, "revision": 0}),
        ("POST", "/jev/test", None),
    ]:
        response = await client.request(method, BASE + path, headers=headers, json=body)
        assert response.status_code == 403


async def test_environment_snapshot_is_encrypted_and_explicit_clear_blocks_fallback(
    client, operator, monkeypatch, setup_database
):
    secret = secrets.token_urlsafe(30)
    for field, value in {
        "email_mode": "smtp",
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_user": "account",
        "smtp_from": "sender@example.com",
        "smtp_use_tls": True,
        "smtp_use_ssl": False,
        "smtp_password": secret,
    }.items():
        monkeypatch.setattr(settings, field, value)
    initial = (await client.get(BASE, headers=operator)).json()["email"]
    assert initial["source"] == "environment" and initial["revision"] == 0
    assert initial["password_configured"]
    saved = await client.put(BASE + "/email", headers=operator, json=email_body(password=""))
    assert saved.status_code == 200
    assert saved.json()["revision"] == 1 and saved.json()["source"] == "database"
    assert secret not in saved.text
    monkeypatch.setattr(settings, "smtp_password", "changed-environment")
    async with setup_database() as db:
        resolved = await resolve_installation_settings(db)
        row = await db.get(InstallationSettings, "email")
        assert secret not in row.secret_encrypted and secret not in json.dumps(row.configuration)
        assert resolved.smtp_password == secret and settings.smtp_password == "changed-environment"
        audits = (await db.scalars(select(AuditLog))).all()
        assert secret not in str([(a.old_value, a.new_value) for a in audits])
    cleared = await client.put(
        BASE + "/email", headers=operator, json=email_body(revision=1, clear_password=True)
    )
    assert cleared.status_code == 200 and not cleared.json()["password_configured"]
    async with setup_database() as db:
        resolved = await resolve_installation_settings(db)
        assert resolved.smtp_password == "" and not resolved.email_available


@pytest.mark.parametrize(
    "field,value",
    [
        ("smtp_host", "other.example.com"),
        ("smtp_port", 465),
        ("smtp_user", "other"),
        ("smtp_security", "ssl"),
    ],
)
async def test_changed_smtp_target_requires_fresh_credentials(
    client, operator, setup_database, field, value
):
    secret = secrets.token_urlsafe(30)
    assert (
        await client.put(BASE + "/email", headers=operator, json=email_body(password=secret))
    ).status_code == 200
    changed = email_body(revision=1, **{field: value})
    denied = await client.put(BASE + "/email", headers=operator, json=changed)
    assert denied.status_code == 400 and secret not in denied.text
    changed["password"] = replacement = secrets.token_urlsafe(30)
    assert (await client.put(BASE + "/email", headers=operator, json=changed)).status_code == 200
    async with setup_database() as db:
        effective = await resolve_installation_settings(db)
        assert effective.smtp_password == replacement
        if field == "smtp_security":
            assert effective.smtp_use_ssl and not effective.smtp_use_tls


async def test_ai_disable_retains_bound_key_and_switching_never_reuses_it(
    client, operator, setup_database, monkeypatch
):
    monkeypatch.setattr(settings, "ai_provider_setting", "none")
    monkeypatch.setattr(settings, "anthropic_api_key", "unrelated-environment-key")
    secret = secrets.token_urlsafe(30)
    body = {"provider": "openai", "model": "chosen-model", "api_key": secret, "revision": 0}
    assert (await client.put(BASE + "/ai", headers=operator, json=body)).status_code == 200
    async with setup_database() as db:
        first = await resolve_installation_settings(db)
        assert first.ai_provider == "openai" and first.ai_model == "chosen-model"
        assert first.openai_api_key == secret and first.anthropic_api_key == ""
        disabled = dict(body, revision=1, api_key="", provider="none")
        response = await client.put(BASE + "/ai", headers=operator, json=disabled)
        assert response.status_code == 200 and response.json()["credential_provider"] == "openai"
        assert response.json()["api_key_configured"]
        second = await resolve_installation_settings(db)
        assert second.ai_provider == "none" and second.openai_api_key == ""
        enabled = dict(body, revision=2, api_key="", model="another-model")
        assert (await client.put(BASE + "/ai", headers=operator, json=enabled)).status_code == 200
        third = await resolve_installation_settings(db)
        assert third.ai_model == "another-model" and third.openai_api_key == secret
    switched = dict(enabled, revision=3, provider="anthropic")
    assert (await client.put(BASE + "/ai", headers=operator, json=switched)).status_code == 400
    switched["api_key"] = replacement = secrets.token_urlsafe(30)
    assert (await client.put(BASE + "/ai", headers=operator, json=switched)).status_code == 200
    async with setup_database() as db:
        effective = await resolve_installation_settings(db)
        assert effective.ai_provider == "anthropic" and effective.anthropic_api_key == replacement
        assert effective.openai_api_key == ""
    switched.update(revision=4, api_key="", clear_api_key=True)
    assert (await client.put(BASE + "/ai", headers=operator, json=switched)).status_code == 200
    async with setup_database() as db:
        cleared = await resolve_installation_settings(db)
        assert cleared.anthropic_api_key == "" and cleared.openai_api_key == ""


async def test_parallel_saves_protect_insert_and_existing_revision(client, operator):
    async def save(revision, model):
        return await client.put(
            BASE + "/ai",
            headers=operator,
            json={
                "provider": "none",
                "model": model,
                "revision": revision,
            },
        )

    for revision in (0, 1):
        results = await asyncio.gather(save(revision, "first"), save(revision, "second"))
        assert sorted(result.status_code for result in results) == [200, 409]
        winner = next(result.json() for result in results if result.status_code == 200)
        assert (await client.get(BASE, headers=operator)).json()["ai"] == winner
        assert winner["revision"] == revision + 1


async def test_saved_email_test_limits_recipient_and_audits_revision(
    client, operator, monkeypatch, setup_database
):
    secret = secrets.token_urlsafe(30)
    assert (
        await client.put(BASE + "/email", headers=operator, json=email_body(password=secret))
    ).status_code == 200
    send = Mock()
    monkeypatch.setattr("app.api.installation_settings.send_email", send)
    success = await client.post(
        BASE + "/email/test",
        headers=operator,
        json={"recipient": "other@example.com", "smtp_host": "evil.example.com"},
    )
    assert success.status_code == 200 and success.json()["ok"]
    assert "accepted" in success.json()["message"] and "not confirmed" in success.json()["message"]
    assert send.call_args.args[0] == ["operator@example.com"]
    assert send.call_args.kwargs["config"].smtp_host == "smtp.example.com"
    send.side_effect = smtplib.SMTPAuthenticationError(535, secret.encode())
    failed = await client.post(BASE + "/email/test", headers=operator)
    assert failed.status_code == 200 and not failed.json()["ok"] and secret not in failed.text
    assert "authentication" in failed.json()["message"]
    async with setup_database() as db:
        tests = (await db.scalars(select(AuditLog).where(AuditLog.action == "test"))).all()
        assert [json.loads(row.new_value) for row in tests] == [
            {"ok": True, "revision": 1},
            {"ok": False, "revision": 1},
        ]


async def test_saved_ai_test_generates_synthetic_response_and_sanitizes_failures(
    client, operator, monkeypatch
):
    secret = secrets.token_urlsafe(30)
    assert (
        await client.put(
            BASE + "/ai",
            headers=operator,
            json={
                "provider": "openai",
                "model": "saved-model",
                "api_key": secret,
                "revision": 0,
            },
        )
    ).status_code == 200
    received = []

    async def complete(parser, prompt, schema, *, max_tokens):
        received.append((parser.config, prompt, schema, max_tokens))
        return '{"ok": true}'

    monkeypatch.setattr("app.api.installation_settings.RemoteParser.complete", complete)
    success = await client.post(BASE + "/ai/test", headers=operator)
    assert success.status_code == 200 and success.json()["ok"]
    config, prompt, schema, max_tokens = received[0]
    assert config.model == "saved-model" and config.api_key == secret and config.timeout <= 20
    assert (
        "connection test" in prompt
        and max_tokens <= 1024
        and schema["schema"]["required"] == ["ok"]
    )
    for error, expected in [
        (RuntimeError(secret), "failed"),
        (TimeoutError(), "timed out"),
        (ValueError("Extraction provider returned HTTP 429."), "quota"),
    ]:
        monkeypatch.setattr(
            "app.api.installation_settings.RemoteParser.complete", AsyncMock(side_effect=error)
        )
        failed = await client.post(BASE + "/ai/test", headers=operator)
        assert failed.status_code == 200 and not failed.json()["ok"] and secret not in failed.text
        assert expected in failed.json()["message"]


@pytest.mark.parametrize(
    "corrupt_section,email_mode",
    [
        ("email", "smtp"),
        ("email", "disabled"),
        ("ai", "smtp"),
    ],
)
async def test_unreadable_credentials_disable_only_the_affected_service(
    client, operator, setup_database, corrupt_section, email_mode
):
    smtp_secret, ai_secret = secrets.token_urlsafe(30), secrets.token_urlsafe(30)
    email = email_body(password=smtp_secret, mode=email_mode)
    ai = {"provider": "openai", "model": "configured-model", "api_key": ai_secret, "revision": 0}
    assert (await client.put(BASE + "/email", headers=operator, json=email)).status_code == 200
    assert (await client.put(BASE + "/ai", headers=operator, json=ai)).status_code == 200
    async with setup_database() as db:
        row = await db.get(InstallationSettings, corrupt_section)
        row.secret_encrypted = "unreadable-restored-credential"
        await db.commit()
    async with setup_database() as db:
        effective = await resolve_installation_settings(db)
        assert effective.smtp_password == ("" if corrupt_section == "email" else smtp_secret)
        assert effective.openai_api_key == ("" if corrupt_section == "ai" else ai_secret)
    capabilities = await client.get("/api/v1/capabilities", headers=operator)
    assert capabilities.status_code == 200
    assert capabilities.json()["email"]["enabled"] is (corrupt_section != "email")
    assert capabilities.json()["ai"]["enabled"] is (corrupt_section != "ai")
    # Retention cannot silently replace an unreadable credential with an empty one.
    secret_field = "password" if corrupt_section == "email" else "api_key"
    body = {**(email if corrupt_section == "email" else ai), "revision": 1, secret_field: ""}
    denied = await client.put(BASE + "/" + corrupt_section, headers=operator, json=body)
    assert denied.status_code == 400 and "replacement credentials" in denied.json()["detail"]
    body[secret_field] = secrets.token_urlsafe(30)
    assert (
        await client.put(BASE + "/" + corrupt_section, headers=operator, json=body)
    ).status_code == 200


async def test_jev_secret_revision_and_independence(client, operator, monkeypatch, setup_database):
    secret = secrets.token_urlsafe(30)
    monkeypatch.setattr(settings, "typesafe_api_key", secret)
    initial = (await client.get(BASE, headers=operator)).json()
    assert initial["jev"]["api_key_configured"]
    body = {"enabled": True, "model": "jev-1.13.0", "revision": 0}
    saved = await client.put(BASE + "/jev", headers=operator, json=body)
    assert saved.status_code == 200 and saved.json()["revision"] == 1
    assert secret not in saved.text
    assert (await client.put(BASE + "/jev", headers=operator, json=body)).status_code == 409
    async with setup_database() as db:
        row = await db.get(InstallationSettings, "jev")
        runtime = await resolve_installation_settings(db)
        assert secret not in row.secret_encrypted
        assert (
            runtime.typesafe_api_key == secret
            and runtime.jev_enabled
            and runtime.jev_settings_revision == 1
        )
        assert runtime.ai_provider == settings.ai_provider
    removed = await client.put(
        BASE + "/jev", headers=operator, json={**body, "revision": 1, "clear_api_key": True}
    )
    assert removed.status_code == 200 and not removed.json()["api_key_configured"]
    async with setup_database() as db:
        runtime = await resolve_installation_settings(db)
        assert runtime.typesafe_api_key == ""
    assert (await client.get(BASE, headers=operator)).json()["ai"] == initial["ai"]


async def test_jev_connection_test_uses_saved_settings_and_synthetic_data(
    client, operator, monkeypatch
):
    from app.api import installation_settings as api_module

    body = {"enabled": True, "model": "jev-1.13.0", "revision": 0, "api_key": "test-private-key"}
    assert (await client.put(BASE + "/jev", headers=operator, json=body)).status_code == 200
    calls = []

    class TestClient:
        def __init__(self, config):
            assert config.api_key == "test-private-key" and config.revision == 1
            assert config.model == "jev-1.13.0" and config.enabled

        async def evaluate(self, state, questions):
            calls.append((state, questions))
            return {
                "model": "jev-1.13.0",
                "answers": {"supported": {"type": "noul", "noul": 1}},
                "usage": {"input_tokens": 10, "output_tokens": 1},
            }

    monkeypatch.setattr(api_module, "JevClient", TestClient)
    result = await client.post(BASE + "/jev/test", headers=operator)
    assert result.status_code == 200 and result.json()["ok"]
    assert len(calls) == 1
    assert calls[0][0] == {"synthetic_test": "A square has four sides."}
    assert "test-private-key" not in result.text
