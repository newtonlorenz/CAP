"""System-admin management and bounded tests of saved installation settings."""

import asyncio
import json
import re
import smtplib
import ssl
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.api.deps import require_installation_operator
from app.database import get_db
from app.models.user import User
from app.schemas.installation_settings import (
    AIResponse,
    AIUpdate,
    EmailResponse,
    EmailUpdate,
    InstallationSettingsResponse,
    JevResponse,
    JevUpdate,
    SettingsTestResponse,
)
from app.services.ai_provider import ProviderConfig, RemoteParser
from app.services.audit import log_action
from app.services.email import send_email
from app.services.installation_settings import (
    SettingsConflict,
    get_installation_settings,
    resolve_installation_settings_snapshot,
    save_ai_settings,
    save_email_settings,
    save_jev_settings,
)
from app.services.jev_provider import JevClient, JevConfig, JevError

Database = Annotated[AsyncSession, Depends(get_db)]
SystemAdmin = Annotated[User, Depends(require_installation_operator)]

router = APIRouter(prefix="/api/v1/admin/installation-settings", tags=["installation settings"])


@router.get("", response_model=InstallationSettingsResponse)
async def get_settings(db: Database, current_user: SystemAdmin):
    return await get_installation_settings(db)


async def _save_section(db, user, section, save, body):
    try:
        old, new = await save(db, body)
    except SettingsConflict as exc:
        raise HTTPException(409, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    await log_action(
        db,
        user,
        "update",
        "installation_settings",
        section,
        old_value=old.model_dump(),
        new_value=new.model_dump(),
    )
    await db.commit()
    return new


@router.put("/email", response_model=EmailResponse)
async def put_email(body: EmailUpdate, db: Database, current_user: SystemAdmin):
    return await _save_section(db, current_user, "email", save_email_settings, body)


@router.put("/ai", response_model=AIResponse)
async def put_ai(body: AIUpdate, db: Database, current_user: SystemAdmin):
    return await _save_section(db, current_user, "ai", save_ai_settings, body)


async def _test_result(db, user, section, ok, message, revision=None):
    await log_action(
        db,
        user,
        "test",
        "installation_settings",
        section,
        new_value={"ok": ok, "revision": revision},
    )
    await db.commit()
    return SettingsTestResponse(ok=ok, message=message)


@router.post("/email/test", response_model=SettingsTestResponse)
async def test_email(db: Database, current_user: SystemAdmin):
    revision = None
    ok = False
    try:
        config, snapshot = await resolve_installation_settings_snapshot(db)
        revision = snapshot.email.revision
        if config.email_mode != "smtp" or not config.email_available:
            message = "Enable email and save a complete SMTP configuration first."
        else:
            await run_in_threadpool(
                send_email,
                [current_user.email],
                "CAP email configuration test",
                "This is a test of your saved CAP email configuration.",
                config=config,
                raise_on_error=True,
            )
            ok = True
            message = "SMTP server accepted the test email for your account. Inbox delivery is not confirmed."
    except Exception as exc:  # noqa: BLE001 - provider errors must never expose secrets
        message = _email_error(exc)
    return await _test_result(db, current_user, "email", ok, message, revision)


@router.post("/ai/test", response_model=SettingsTestResponse)
async def test_ai(db: Database, current_user: SystemAdmin):
    revision = None
    ok = False
    try:
        config, snapshot = await resolve_installation_settings_snapshot(db)
        revision = snapshot.ai.revision
        if config.ai_provider == "none":
            message = "Select an AI provider and save its model and API key first."
        elif not getattr(config, f"{config.ai_provider}_api_key", ""):
            message = "Save an API key for the selected AI provider first."
        else:
            selected = ProviderConfig.from_settings(config)
            selected = ProviderConfig(
                selected.provider, selected.model, selected.api_key, min(selected.timeout, 20)
            )
            schema = {
                "name": "connection_test",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {"ok": {"type": "boolean"}},
                    "required": ["ok"],
                    "additionalProperties": False,
                },
            }
            async with asyncio.timeout(20):
                raw = await RemoteParser(selected).complete(
                    'Return only the JSON object {"ok": true}. This is a connection test.',
                    schema,
                    max_tokens=1024,
                )
            if json.loads(raw) != {"ok": True}:
                raise ValueError("Unexpected test response")
            ok = True
            message = "The saved AI provider and model generated a valid test response."
    except Exception as exc:  # noqa: BLE001 - provider errors must never expose secrets
        message = _ai_error(exc)
    return await _test_result(db, current_user, "ai", ok, message, revision)


def _email_error(exc):
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "SMTP authentication was rejected. Check the saved username and password."
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return "SMTP rejected the sender. Check the saved sender address and sending permissions."
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "SMTP rejected your account email address as a recipient."
    if isinstance(exc, (ssl.SSLError, smtplib.SMTPNotSupportedError)):
        return "SMTP could not establish the selected TLS mode. Check the saved security mode and port."
    if isinstance(exc, TimeoutError):
        return "SMTP timed out. Check the saved server address, port and network access."
    if isinstance(exc, (OSError, smtplib.SMTPServerDisconnected)):
        return "SMTP could not connect. Check the saved server address, port and network access."
    return "SMTP test failed. Check the saved server settings and credentials."


def _ai_error(exc):
    if isinstance(exc, TimeoutError):
        return "AI test timed out. Check provider availability and try again."
    status = (
        re.fullmatch(r"Extraction provider returned HTTP (\d{3})\.", str(exc))
        if isinstance(exc, ValueError)
        else None
    )
    if status:
        code = int(status.group(1))
        if code in {401, 403}:
            return "AI access was rejected. Check the saved API key and model permissions."
        if code == 404:
            return "The AI model was not found. Check the saved model name and account access."
        if code == 429:
            return "The AI provider reported a rate or quota limit. Check account usage and retry later."
        return "The AI provider rejected the test request. Check the model settings and provider availability."
    if isinstance(exc, (json.JSONDecodeError, ValueError)):
        return "AI test returned no valid result. Check model support and provider availability."
    return "AI test failed. Check the saved provider, model and API key."


@router.put("/jev", response_model=JevResponse)
async def put_jev(body: JevUpdate, db: Database, current_user: SystemAdmin):
    return await _save_section(db, current_user, "jev", save_jev_settings, body)


@router.post("/jev/test", response_model=SettingsTestResponse)
async def test_jev(db: Database, current_user: SystemAdmin):
    revision, ok = None, False
    try:
        config, snapshot = await resolve_installation_settings_snapshot(db)
        revision = snapshot.jev.revision
        async with asyncio.timeout(20):
            await JevClient(JevConfig.from_settings(config)).evaluate(
                {"synthetic_test": "A square has four sides."},
                {
                    "supported": {
                        "type": "noul",
                        "instructions": "Does synthetic_test state that a square has four sides?",
                    }
                },
            )
        ok, message = True, "The saved Jev model returned a valid synthetic test response."
    except JevError as exc:
        message = str(exc)
    except TimeoutError:
        message = "Jev test timed out. Check provider availability and try again."
    except Exception:  # noqa: BLE001 - unexpected provider failures must not expose secrets
        message = "Jev test failed. Check the saved model and API key."
    return await _test_result(db, current_user, "jev", ok, message, revision)
