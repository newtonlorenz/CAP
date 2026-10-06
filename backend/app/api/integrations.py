from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.database import get_db
from app.models.user import User
from app.schemas.jira import (
    JiraIntegrationResponse,
    JiraIntegrationTestRequest,
    JiraIntegrationTestResponse,
    JiraIntegrationUpdate,
)
from app.services.audit import log_action
from app.services.jira import (
    decrypt_token,
    validate_saved_token_target,
    get_jira_integration,
    normalize_jira_base_url,
    normalize_project_key,
    test_jira_connection,
    upsert_jira_integration,
)

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])


def _to_response(integration) -> JiraIntegrationResponse:
    return JiraIntegrationResponse(
        base_url=integration.base_url,
        project_key=integration.project_key,
        user_email=integration.user_email,
        enabled=integration.enabled,
        token_configured=bool(integration.api_token_encrypted),
        last_tested_at=integration.last_tested_at,
        last_test_status=integration.last_test_status,
        last_test_message=integration.last_test_message,
    )


@router.get("/jira", response_model=dict)
async def get_jira_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    integration = await get_jira_integration(db, current_user.organization_id)
    return {
        "configured": integration is not None,
        "integration": _to_response(integration) if integration is not None else None,
    }


@router.put("/jira", response_model=JiraIntegrationResponse)
async def put_jira_settings(
    body: JiraIntegrationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    existing = await get_jira_integration(db, current_user.organization_id)
    old_value = None
    if existing is not None:
        old_value = {
            "base_url": existing.base_url,
            "project_key": existing.project_key,
            "user_email": existing.user_email,
            "enabled": existing.enabled,
            "token_configured": bool(existing.api_token_encrypted),
        }

    try:
        integration = await upsert_jira_integration(
            db,
            base_url=body.base_url,
            project_key=body.project_key,
            user_email=body.user_email,
            api_token=body.api_token,
            enabled=body.enabled,
            updated_by=current_user.id,
            organization_id=current_user.organization_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    new_value = {
        "base_url": integration.base_url,
        "project_key": integration.project_key,
        "user_email": integration.user_email,
        "enabled": integration.enabled,
        "token_configured": bool(integration.api_token_encrypted),
    }

    await log_action(
        db,
        current_user,
        "update",
        "jira_integration",
        str(integration.id),
        old_value=old_value,
        new_value=new_value,
    )
    await db.commit()
    await db.refresh(integration)
    return _to_response(integration)


@router.post("/jira/test", response_model=JiraIntegrationTestResponse)
async def test_jira_settings(
    body: JiraIntegrationTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    existing = await get_jira_integration(db, current_user.organization_id)
    token = (body.api_token or "").strip()
    if not token and existing is not None:
        try:
            validate_saved_token_target(existing, body.base_url, body.user_email, token)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        try:
            token = decrypt_token(existing.api_token_encrypted)
        except ValueError:
            token = ""

    if not token:
        raise HTTPException(
            status_code=400, detail="Jira API token is required for connection test"
        )

    try:
        ok, message = await test_jira_connection(
            base_url=body.base_url,
            project_key=body.project_key,
            user_email=body.user_email,
            api_token=token,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    normalized_base = normalize_jira_base_url(body.base_url)
    normalized_project = normalize_project_key(body.project_key)
    normalized_email = body.user_email.strip().lower()

    if (
        existing is not None
        and existing.base_url == normalized_base
        and existing.project_key == normalized_project
        and existing.user_email == normalized_email
    ):
        existing.last_tested_at = datetime.now(timezone.utc)
        existing.last_test_status = "ok" if ok else "error"
        existing.last_test_message = message
        existing.updated_by = current_user.id
        await db.commit()

    await log_action(
        db,
        current_user,
        "test",
        "jira_integration",
        str(existing.id) if existing else "draft",
        new_value={"ok": ok, "message": message},
    )
    await db.commit()

    return JiraIntegrationTestResponse(ok=ok, message=message)
