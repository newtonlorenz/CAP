from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.jurisdiction import Jurisdiction
from app.models.market_pack import MarketPack
from app.models.user import User
from app.schemas.market_pack import MarketPackResponse

router = APIRouter(prefix="/api/v1/market-packs", tags=["market-packs"])


def _serialize_market_pack(
    jurisdiction: Jurisdiction,
    market_pack: MarketPack,
) -> MarketPackResponse:
    return MarketPackResponse.model_validate(
        {
            "id": market_pack.id,
            "jurisdiction_id": jurisdiction.id,
            "jurisdiction_code": jurisdiction.code,
            "jurisdiction_name": jurisdiction.name,
            "version": market_pack.version,
            "status": market_pack.status,
            "parser_mode": market_pack.parser_mode,
            "supports_deterministic_import": market_pack.supports_deterministic_import,
            "coverage_notes": market_pack.coverage_notes,
            "source_label": market_pack.source_label,
            "published_at": market_pack.published_at,
            "created_at": market_pack.created_at,
        }
    )


@router.get("", response_model=dict)
async def list_market_packs(
    skip: int = 0,
    limit: int = 1000,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    query = (
        select(MarketPack, Jurisdiction)
        .join(Jurisdiction, MarketPack.jurisdiction_id == Jurisdiction.id)
        .order_by(Jurisdiction.name)
    )
    count_result = await db.execute(select(func.count(MarketPack.id)))
    total = int(count_result.scalar() or 0)
    result = await db.execute(query.offset(skip).limit(limit))
    rows = result.all()
    return {
        "items": [
            _serialize_market_pack(jurisdiction, market_pack) for market_pack, jurisdiction in rows
        ],
        "total": total,
    }


@router.get("/{jurisdiction_code}", response_model=MarketPackResponse)
async def get_market_pack_by_jurisdiction_code(
    jurisdiction_code: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    normalized_code = (jurisdiction_code or "").strip().lower()
    result = await db.execute(
        select(MarketPack, Jurisdiction)
        .join(Jurisdiction, MarketPack.jurisdiction_id == Jurisdiction.id)
        .where(Jurisdiction.code == normalized_code)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Market pack not found")

    market_pack, jurisdiction = row
    return _serialize_market_pack(jurisdiction, market_pack)
