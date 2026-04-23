import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.permissions import require_role
from app.models.user import User
from app.schemas.risks import RiskCreateRequest, RiskResponse, RiskUpdateRequest
from app.services.risks import create_risk, get_risk_by_id, get_risks, update_risk

router = APIRouter()


@router.get("/risks", response_model=list[RiskResponse])
async def list_risks(
    status: str | None = Query(None, pattern="^(active|archived)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list:
    """
    Vrátí registr rizik tenantu.
    Volitelný filtr: ?status=active nebo ?status=archived
    Přístup: všechny role (employee vidí rizika svého pracoviště).
    """
    return await get_risks(db, current_user.tenant_id, status=status)


@router.post("/risks", response_model=RiskResponse, status_code=status.HTTP_201_CREATED)
async def create_risk_endpoint(
    data: RiskCreateRequest,
    current_user: User = Depends(require_role("ozo", "manager")),
    db: AsyncSession = Depends(get_db),
) -> object:
    """Vytvoří nový záznam rizika. Přístup: ozo, manager."""
    return await create_risk(db, data, current_user.tenant_id, current_user.id)


@router.get("/risks/{risk_id}", response_model=RiskResponse)
async def get_risk(
    risk_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> object:
    """Vrátí detail rizika. Přístup: všechny role."""
    risk = await get_risk_by_id(db, risk_id, current_user.tenant_id)
    if risk is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Riziko nenalezeno")
    return risk


@router.patch("/risks/{risk_id}", response_model=RiskResponse)
async def update_risk_endpoint(
    risk_id: uuid.UUID,
    data: RiskUpdateRequest,
    current_user: User = Depends(require_role("ozo", "manager")),
    db: AsyncSession = Depends(get_db),
) -> object:
    """Aktualizuje riziko. Přístup: ozo, manager."""
    risk = await get_risk_by_id(db, risk_id, current_user.tenant_id)
    if risk is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Riziko nenalezeno")
    return await update_risk(db, risk, data)


@router.delete("/risks/{risk_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_risk(
    risk_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "manager")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Archivuje riziko (status=archived). Neprovádí fyzické smazání –
    záznamy o rizicích jsou součástí BOZP dokumentace a musí být dohledatelné.
    """
    risk = await get_risk_by_id(db, risk_id, current_user.tenant_id)
    if risk is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Riziko nenalezeno")
    risk.status = "archived"
    await db.flush()
