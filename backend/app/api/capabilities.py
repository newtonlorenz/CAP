from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.installation_settings import resolve_installation_settings
from app.models.user import User
from app.services.capabilities import installation_capabilities

router = APIRouter(prefix="/api/v1", tags=["capabilities"])


@router.get("/capabilities")
async def capabilities(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return installation_capabilities(await resolve_installation_settings(db))
