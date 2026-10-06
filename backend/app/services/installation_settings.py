"""Resolve fresh installation settings without mutating process-wide configuration."""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, settings
from app.models.installation_settings import InstallationSettings
from app.schemas.installation_settings import (
    AIResponse,
    AIUpdate,
    EmailResponse,
    EmailUpdate,
    InstallationSettingsResponse,
    JevResponse,
    JevUpdate,
)


class SettingsConflict(ValueError):
    pass


def _cipher():
    key = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def _encrypt(secret):
    return _cipher().encrypt(secret.encode("utf-8")).decode("ascii") if secret else ""


def _decrypt(secret):
    if not secret:
        return ""
    try:
        return _cipher().decrypt(secret.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeError):
        raise ValueError(
            "Saved credentials cannot be read. Enter and save replacement credentials."
        ) from None


async def _rows(db):
    # populate_existing avoids stale identity-map values in long-running sessions.
    return {
        row.section: row
        for row in (
            await db.scalars(select(InstallationSettings).execution_options(populate_existing=True))
        ).all()
    }


def _email_environment():
    return {
        "mode": "smtp" if settings.email_mode == "smtp" else "disabled",
        "smtp_host": settings.smtp_host,
        "smtp_port": settings.smtp_port,
        "smtp_user": settings.smtp_user,
        "smtp_from": settings.smtp_from,
        "smtp_security": (
            "ssl"
            if getattr(settings, "smtp_use_ssl", False)
            else ("starttls" if settings.smtp_use_tls else "none")
        ),
    }


def _ai_environment():
    return {
        "provider": settings.ai_provider,
        "model": settings.ai_model if settings.ai_provider != "none" else "",
        "credential_provider": settings.ai_provider if settings.ai_provider != "none" else None,
    }


def _public(rows):
    email, ai = rows.get("email"), rows.get("ai")
    jev = rows.get("jev")
    return InstallationSettingsResponse(
        jev=JevResponse(
            **(
                jev.configuration
                if jev
                else {"enabled": settings.jev_enabled, "model": settings.jev_model}
            ),
            api_key_configured=bool(jev.secret_encrypted if jev else settings.typesafe_api_key),
            source="database" if jev else "environment",
            revision=jev.revision if jev else 0,
        ),
        email=EmailResponse(
            **(email.configuration if email else _email_environment()),
            password_configured=bool(email.secret_encrypted if email else settings.smtp_password),
            source="database" if email else "environment",
            revision=email.revision if email else 0,
        ),
        ai=AIResponse(
            **(ai.configuration if ai else _ai_environment()),
            api_key_configured=bool(
                ai.secret_encrypted
                if ai
                else getattr(settings, f"{settings.ai_provider}_api_key", "")
            ),
            source="database" if ai else "environment",
            revision=ai.revision if ai else 0,
        ),
    )


async def get_installation_settings(db: AsyncSession):
    return _public(await _rows(db))


def _runtime_secret(encrypted):
    # A restored database can have credentials encrypted with another installation's key.
    # Fail closed for that service while allowing independent workflows to continue.
    try:
        return _decrypt(encrypted)
    except ValueError:
        return ""


def _resolve(rows) -> Settings:
    overrides = {}
    if email := rows.get("email"):
        values = email.configuration
        overrides.update(
            email_mode=values["mode"],
            smtp_host=values["smtp_host"],
            smtp_port=values["smtp_port"],
            smtp_user=values["smtp_user"],
            smtp_from=values["smtp_from"],
            smtp_use_tls=values["smtp_security"] == "starttls",
            smtp_use_ssl=values["smtp_security"] == "ssl",
            smtp_password=(
                _runtime_secret(email.secret_encrypted) if values["mode"] == "smtp" else ""
            ),
        )
    if ai := rows.get("ai"):
        values = ai.configuration
        overrides.update(
            ai_provider_setting=values["provider"], openai_api_key="", anthropic_api_key=""
        )
        if values["provider"] != "none":
            overrides[f'{values["provider"]}_model'] = values["model"]
            if values.get("credential_provider") == values["provider"]:
                overrides[f'{values["provider"]}_api_key'] = _runtime_secret(ai.secret_encrypted)
    if jev := rows.get("jev"):
        overrides.update(
            jev_enabled=jev.configuration["enabled"],
            jev_model=jev.configuration["model"],
            typesafe_api_key=_runtime_secret(jev.secret_encrypted),
            jev_settings_revision=jev.revision,
        )
    return settings.model_copy(update=overrides)


async def resolve_installation_settings(db: AsyncSession) -> Settings:
    return _resolve(await _rows(db))


async def resolve_installation_settings_snapshot(db: AsyncSession):
    rows = await _rows(db)
    return _resolve(rows), _public(rows)


async def _save(db, section, revision, configuration, secret):
    if revision == 0:
        db.add(
            InstallationSettings(
                section=section,
                configuration=configuration,
                secret_encrypted=_encrypt(secret),
                revision=1,
            )
        )
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            raise SettingsConflict("Settings changed. Reload before saving again.") from None
    else:
        result = await db.execute(
            update(InstallationSettings)
            .where(
                InstallationSettings.section == section, InstallationSettings.revision == revision
            )
            .values(
                configuration=configuration,
                secret_encrypted=_encrypt(secret),
                revision=revision + 1,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            raise SettingsConflict("Settings changed. Reload before saving again.")


async def save_email_settings(db: AsyncSession, body: EmailUpdate):
    rows = await _rows(db)
    old = _public(rows).email
    if body.revision != old.revision:
        raise SettingsConflict("Settings changed. Reload before saving again.")
    password = body.password.get_secret_value() if body.password else ""
    if body.clear_password and password:
        raise ValueError("Choose either a replacement password or clear password.")
    configuration = body.model_dump(exclude={"revision", "password", "clear_password"})
    if body.mode == "smtp" and (not body.smtp_host or not body.smtp_from):
        raise ValueError("SMTP host and sender are required when email is enabled.")
    changed_target = any(
        getattr(body, key) != getattr(old, key)
        for key in ("smtp_host", "smtp_port", "smtp_user", "smtp_security")
    )
    if body.smtp_user and changed_target and not password and not body.clear_password:
        raise ValueError(
            "Enter a new SMTP password when changing the server, security or username."
        )
    if body.clear_password or not body.smtp_user:
        password = ""
    elif not password:
        password = (
            _decrypt(rows["email"].secret_encrypted) if "email" in rows else settings.smtp_password
        )
    await _save(db, "email", body.revision, configuration, password)
    return old, (await get_installation_settings(db)).email


async def save_ai_settings(db: AsyncSession, body: AIUpdate):
    rows = await _rows(db)
    old = _public(rows).ai
    if body.revision != old.revision:
        raise SettingsConflict("Settings changed. Reload before saving again.")
    key = body.api_key.get_secret_value().strip() if body.api_key else ""
    if body.clear_api_key and key:
        raise ValueError("Choose either a replacement API key or clear API key.")
    if body.provider != "none" and not body.model:
        raise ValueError("A model is required when an AI provider is selected.")
    binding = old.credential_provider
    if body.provider != "none" and body.provider != binding and not key and not body.clear_api_key:
        raise ValueError("Enter a new API key when changing AI provider.")
    if key and body.provider == "none":
        raise ValueError("Select an AI provider before entering an API key.")
    if body.clear_api_key:
        key, binding = "", None
    elif key:
        binding = body.provider
    else:
        key = (
            _decrypt(rows["ai"].secret_encrypted)
            if "ai" in rows
            else getattr(settings, f"{binding}_api_key", "")
        )
    configuration = body.model_dump(exclude={"revision", "api_key", "clear_api_key"})
    configuration["credential_provider"] = binding
    await _save(db, "ai", body.revision, configuration, key)
    return old, (await get_installation_settings(db)).ai


async def save_jev_settings(db: AsyncSession, body: JevUpdate):
    rows = await _rows(db)
    old = _public(rows).jev
    if body.revision != old.revision:
        raise SettingsConflict("Settings changed. Reload before saving again.")
    key = body.api_key.get_secret_value().strip() if body.api_key else ""
    if body.clear_api_key and key:
        raise ValueError("Choose either a replacement API key or clear API key.")
    if body.clear_api_key:
        key = ""
    elif not key:
        key = _decrypt(rows["jev"].secret_encrypted) if "jev" in rows else settings.typesafe_api_key
    configuration = body.model_dump(exclude={"revision", "api_key", "clear_api_key"})
    await _save(db, "jev", body.revision, configuration, key)
    return old, (await get_installation_settings(db)).jev
