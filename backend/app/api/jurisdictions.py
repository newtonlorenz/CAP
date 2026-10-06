from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_installation_operator
from app.database import get_db
from app.models.jurisdiction import Jurisdiction
from app.models.market_pack import MarketPack
from app.models.user import User
from app.schemas.jurisdiction import (
    JurisdictionCreate,
    JurisdictionResponse,
    JurisdictionUpdate,
)
from app.services.audit import log_action

router = APIRouter(prefix="/api/v1/jurisdictions", tags=["jurisdictions"])

CODE_RE = re.compile(r"^[a-z0-9_-]{2,20}$")


async def _get_jurisdiction_or_404(db: AsyncSession, jurisdiction_id: uuid.UUID) -> Jurisdiction:
    result = await db.execute(select(Jurisdiction).where(Jurisdiction.id == jurisdiction_id))
    jurisdiction = result.scalar_one_or_none()
    if jurisdiction is None:
        raise HTTPException(status_code=404, detail="Jurisdiction not found")
    return jurisdiction


async def _get_market_pack_for_jurisdiction(
    db: AsyncSession,
    jurisdiction_id: uuid.UUID,
) -> MarketPack | None:
    result = await db.execute(
        select(MarketPack).where(MarketPack.jurisdiction_id == jurisdiction_id)
    )
    return result.scalar_one_or_none()


def _normalize_code(value: str) -> str:
    return (value or "").strip().lower()


def _validate_code(value: str) -> str:
    code = _normalize_code(value)
    if not CODE_RE.fullmatch(code):
        raise HTTPException(
            status_code=400,
            detail="Invalid jurisdiction code. Use 2-20 chars: a-z, 0-9, '_' or '-'.",
        )
    return code


def _serialize_jurisdiction(
    jurisdiction: Jurisdiction,
    market_pack: MarketPack | None = None,
) -> JurisdictionResponse:
    return JurisdictionResponse.model_validate(
        {
            "id": jurisdiction.id,
            "code": jurisdiction.code,
            "name": jurisdiction.name,
            "regulator_name": jurisdiction.regulator_name,
            "report_header_text": jurisdiction.report_header_text,
            "pack_status": market_pack.status if market_pack else None,
            "pack_version": market_pack.version if market_pack else None,
            "parser_mode": market_pack.parser_mode if market_pack else None,
            "supports_deterministic_import": (
                market_pack.supports_deterministic_import if market_pack else None
            ),
            "coverage_notes": market_pack.coverage_notes if market_pack else None,
            "active": jurisdiction.active,
            "created_at": jurisdiction.created_at,
        }
    )


@router.get("", response_model=dict)
async def list_jurisdictions(
    include_inactive: bool = Query(False),
    skip: int = 0,
    limit: int = 1000,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if include_inactive and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Insufficient role")

    query = (
        select(Jurisdiction, MarketPack)
        .outerjoin(MarketPack, MarketPack.jurisdiction_id == Jurisdiction.id)
        .order_by(Jurisdiction.name)
    )
    count_query = select(func.count(Jurisdiction.id))

    if not include_inactive:
        query = query.where(Jurisdiction.active.is_(True))
        count_query = count_query.where(Jurisdiction.active.is_(True))

    total_result = await db.execute(count_query)
    total = int(total_result.scalar() or 0)
    result = await db.execute(query.offset(skip).limit(limit))
    rows = result.all()
    return {
        "items": [
            _serialize_jurisdiction(jurisdiction, market_pack) for jurisdiction, market_pack in rows
        ],
        "total": total,
    }


@router.post("", response_model=JurisdictionResponse, status_code=201)
async def create_jurisdiction(
    body: JurisdictionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_installation_operator),
):
    code = _validate_code(body.code)
    existing = await db.execute(select(Jurisdiction).where(Jurisdiction.code == code))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Jurisdiction code already exists")

    jurisdiction = Jurisdiction(
        code=code,
        name=body.name.strip(),
        regulator_name=body.regulator_name.strip() if body.regulator_name else None,
        report_header_text=body.report_header_text,
        active=bool(body.active),
    )
    db.add(jurisdiction)
    await db.flush()

    await log_action(
        db,
        current_user,
        "create",
        "jurisdiction",
        str(jurisdiction.id),
        new_value={
            "code": jurisdiction.code,
            "name": jurisdiction.name,
            "active": jurisdiction.active,
        },
    )
    await db.commit()
    await db.refresh(jurisdiction)
    market_pack = await _get_market_pack_for_jurisdiction(db, jurisdiction.id)
    return _serialize_jurisdiction(jurisdiction, market_pack)


@router.put("/{jurisdiction_id}", response_model=JurisdictionResponse)
async def update_jurisdiction(
    jurisdiction_id: uuid.UUID,
    body: JurisdictionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_installation_operator),
):
    jurisdiction = await _get_jurisdiction_or_404(db, jurisdiction_id)

    old_value = {
        "code": jurisdiction.code,
        "name": jurisdiction.name,
        "regulator_name": jurisdiction.regulator_name,
        "report_header_text": jurisdiction.report_header_text,
        "active": jurisdiction.active,
    }

    fields_set = body.model_fields_set
    if "code" in fields_set and body.code is not None:
        new_code = _validate_code(body.code)
        if new_code != jurisdiction.code:
            existing = await db.execute(select(Jurisdiction).where(Jurisdiction.code == new_code))
            if existing.scalar_one_or_none():
                raise HTTPException(status_code=400, detail="Jurisdiction code already exists")
            jurisdiction.code = new_code

    if "name" in fields_set and body.name is not None:
        jurisdiction.name = body.name.strip()

    if "regulator_name" in fields_set:
        jurisdiction.regulator_name = body.regulator_name.strip() if body.regulator_name else None

    if "report_header_text" in fields_set:
        jurisdiction.report_header_text = body.report_header_text

    if "active" in fields_set and body.active is not None:
        if jurisdiction.active and body.active is False:
            active_count_result = await db.execute(
                select(func.count(Jurisdiction.id)).where(Jurisdiction.active.is_(True))
            )
            active_count = int(active_count_result.scalar() or 0)
            if active_count <= 1:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot deactivate the last active jurisdiction",
                )
        jurisdiction.active = bool(body.active)

    new_value = {
        "code": jurisdiction.code,
        "name": jurisdiction.name,
        "regulator_name": jurisdiction.regulator_name,
        "report_header_text": jurisdiction.report_header_text,
        "active": jurisdiction.active,
    }

    await log_action(
        db,
        current_user,
        "update",
        "jurisdiction",
        str(jurisdiction.id),
        old_value=old_value,
        new_value=new_value,
    )
    await db.commit()
    await db.refresh(jurisdiction)
    market_pack = await _get_market_pack_for_jurisdiction(db, jurisdiction.id)
    return _serialize_jurisdiction(jurisdiction, market_pack)
