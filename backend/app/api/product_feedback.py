"""CAP authentication adapter for the independent Page Feedback service."""

from typing import Annotated, Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.config import settings
from app.database import get_db
from app.models.user import User
from app.services.audit import log_action

router = APIRouter(prefix="/api/v1/product-feedback", tags=["product-feedback"])
Status = Literal["new", "in_progress", "done"]
CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_role("admin"))]
Database = Annotated[AsyncSession, Depends(get_db)]


class Pin(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    selector: str = Field(max_length=1000)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    viewport_width: int = Field(ge=1, le=20000)
    viewport_height: int = Field(ge=1, le=20000)


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: UUID
    kind: Literal["bug", "feature", "other"]
    message: str = Field(min_length=1, max_length=5000)
    page_path: str = Field(min_length=1, max_length=2000)
    pin: Pin | None = None
    screenshot: str | None = Field(default=None, max_length=2_700_000)

    @field_validator("page_path")
    @classmethod
    def path_only(cls, value):
        value = value.split("?", 1)[0].split("#", 1)[0]
        if (
            not value.startswith("/")
            or value.startswith("//")
            or "\\" in value
            or any(ord(char) < 32 for char in value)
        ):
            raise ValueError("Use a local page path")
        return value


class StatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Status


async def parse_body(request: Request, model: type[BaseModel]) -> BaseModel:
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > 3_000_000:
            raise HTTPException(413, "Feedback exceeds 3 MB")
    try:
        return model.model_validate_json(data)
    except ValidationError:
        # Do not reflect the screenshot or user-supplied data in validation responses.
        raise HTTPException(422, "Invalid feedback data") from None


async def forward(method: str, path: str, user: User, *, body=None, params=None):
    if not settings.feedback_service_url or not settings.feedback_service_key:
        raise HTTPException(503, "Product feedback is not configured")
    headers = {
        "Authorization": "Bearer " + settings.feedback_service_key,
        "X-Feedback-Scope": f"{settings.feedback_project}:{user.organization_id or 'legacy'}",
        "X-Feedback-Actor": str(user.id),
        "X-Feedback-Role": "admin" if user.role == "admin" else "reporter",
    }
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False, trust_env=False) as client:
            response = await client.request(
                method,
                settings.feedback_service_url.rstrip("/") + "/v1/" + path,
                headers=headers,
                json=body,
                params=params,
            )
    except httpx.HTTPError:
        raise HTTPException(503, "Feedback service is unavailable. Please try again.") from None
    if response.status_code >= 300:
        messages = {
            404: "Feedback not found",
            409: "This feedback ID is already used",
            413: "Screenshot is too large",
            422: "Invalid feedback or screenshot",
            429: "Feedback limit reached. Please try again next hour.",
        }
        if response.status_code in messages:
            raise HTTPException(response.status_code, messages[response.status_code])
        raise HTTPException(503, "Feedback service is unavailable. Please try again.")
    return response


@router.get("/config")
async def configuration(user: CurrentUser):
    return {"enabled": bool(settings.feedback_service_url and settings.feedback_service_key)}


@router.post("", status_code=201)
async def submit(request: Request, user: CurrentUser, db: Database):
    body = await parse_body(request, Submission)
    result = await forward("POST", "reports", user, body=body.model_dump(mode="json"))
    data = result.json()
    await log_action(
        db,
        user,
        "submit",
        "product_feedback",
        data["id"],
        new_value={"kind": data["kind"], "page_path": data["page_path"]},
    )
    await db.commit()
    return data


@router.get("")
async def inbox(
    user: AdminUser,
    status: Status | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    params = {"skip": skip, "limit": limit}
    if status:
        params["status"] = status
    return (await forward("GET", "reports", user, params=params)).json()


@router.get("/{report_id}/screenshot")
async def screenshot(report_id: UUID, user: AdminUser):
    result = await forward("GET", f"reports/{report_id}/screenshot", user)
    return Response(
        result.content,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": 'inline; filename="feedback.jpg"',
        },
    )


@router.patch("/{report_id}")
async def change_status(
    report_id: UUID,
    request: Request,
    user: AdminUser,
    db: Database,
):
    body = await parse_body(request, StatusUpdate)
    result = await forward("PATCH", f"reports/{report_id}", user, body=body.model_dump(mode="json"))
    await log_action(
        db, user, "update", "product_feedback", str(report_id), new_value={"status": body.status}
    )
    await db.commit()
    return result.json()
