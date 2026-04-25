import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.http_utils import content_disposition
from app.core.permissions import require_role
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.risks import RiskCreateRequest, RiskResponse, RiskUpdateRequest
from app.services.export_pdf import generate_risks_pdf
from app.services.risks import create_risk, get_risk_by_id, get_risks, update_risk

router = APIRouter()


@router.get("/risks", response_model=list[RiskResponse])
async def list_risks(
    status: str | None = Query(None, pattern="^(active|archived)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Any]:
    """
    Vrátí registr rizik tenantu.
    Volitelný filtr: ?status=active nebo ?status=archived
    Přístup: všechny role (employee vidí rizika svého pracoviště).
    """
    return await get_risks(db, current_user.tenant_id, status=status)


@router.post("/risks", response_model=RiskResponse, status_code=status.HTTP_201_CREATED)
async def create_risk_endpoint(
    data: RiskCreateRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> object:
    """Vytvoří nový záznam rizika. Přístup: ozo, manager."""
    return await create_risk(db, data, current_user.tenant_id, current_user.id)


# DŮLEŽITÉ: /risks/export/pdf musí být před /risks/{risk_id}
# Jinak FastAPI matchuje "export" jako UUID a vrátí 422.
@router.get("/risks/export/pdf")
async def export_risks_pdf(
    risk_status: str | None = Query(None, pattern="^(active|archived)$"),
    download: bool = Query(False),
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Exportuje registr rizik jako PDF (pro SÚIP kontroly, interní archivaci).
    ?risk_status=active|archived  – filtr (výchozí: vše)
    ?download=true                – stažení místo zobrazení v prohlížeči
    """
    tenant = (
        await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    ).scalar_one_or_none()
    tenant_name = tenant.name if tenant else str(current_user.tenant_id)

    risks = await get_risks(db, current_user.tenant_id, status=risk_status)
    pdf_bytes = generate_risks_pdf(risks, tenant_name)

    filename = f"registr_rizik_{date.today()}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": content_disposition(filename, inline=not download)},
    )


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
    current_user: User = Depends(require_role("ozo", "hr_manager")),
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
    current_user: User = Depends(require_role("ozo", "hr_manager")),
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
