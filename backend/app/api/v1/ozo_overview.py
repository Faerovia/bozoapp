"""OZO multi-client overview API."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.ozo_overview import ClientOverview
from app.services.ozo_overview import get_ozo_overview

router = APIRouter()


@router.get("/ozo/overview", response_model=list[ClientOverview])
async def list_my_clients(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ClientOverview]:
    """
    Vrátí přehled klientů (tenantů), kam má current user membership.
    Pro každého klienta: agregované počty expirací a otevřených úkolů.

    Použití: OZO landing page /my-clients.
    """
    rows = await get_ozo_overview(db, current_user.id)
    return [ClientOverview.model_validate(r) for r in rows]
