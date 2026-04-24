import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_role
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.workplaces import (
    PlantCreateRequest,
    PlantResponse,
    PlantUpdateRequest,
    RiskFactorAssessmentCreateRequest,
    RiskFactorAssessmentResponse,
    RiskFactorAssessmentUpdateRequest,
    WorkplaceCreateRequest,
    WorkplaceResponse,
    WorkplaceUpdateRequest,
)
from app.services.export_pdf import generate_risk_factor_list_pdf
from app.services.workplaces import (
    create_plant,
    create_rfa,
    create_workplace,
    get_plant_by_id,
    get_plants,
    get_rfa_by_id,
    get_rfa_grouped_for_export,
    get_risk_factor_assessments,
    get_workplace_by_id,
    get_workplaces,
    update_plant,
    update_rfa,
    update_workplace,
)

router = APIRouter()


# ── Plants ────────────────────────────────────────────────────────────────────

@router.get("/plants", response_model=list[PlantResponse])
async def list_plants(
    plant_status: str | None = Query(None, pattern="^(active|archived)$"),
    current_user: User = Depends(require_role("ozo", "manager", "employee")),
    db: AsyncSession = Depends(get_db),
) -> list[Any]:
    return await get_plants(db, current_user.tenant_id, status=plant_status)


@router.post("/plants", response_model=PlantResponse, status_code=status.HTTP_201_CREATED)
async def create_plant_endpoint(
    data: PlantCreateRequest,
    current_user: User = Depends(require_role("ozo", "manager")),
    db: AsyncSession = Depends(get_db),
) -> object:
    return await create_plant(db, data, current_user.tenant_id, current_user.id)


@router.get("/plants/{plant_id}", response_model=PlantResponse)
async def get_plant(
    plant_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "manager", "employee")),
    db: AsyncSession = Depends(get_db),
) -> object:
    plant = await get_plant_by_id(db, plant_id, current_user.tenant_id)
    if plant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Závod nenalezen")
    return plant


@router.patch("/plants/{plant_id}", response_model=PlantResponse)
async def update_plant_endpoint(
    plant_id: uuid.UUID,
    data: PlantUpdateRequest,
    current_user: User = Depends(require_role("ozo", "manager")),
    db: AsyncSession = Depends(get_db),
) -> object:
    plant = await get_plant_by_id(db, plant_id, current_user.tenant_id)
    if plant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Závod nenalezen")
    return await update_plant(db, plant, data)


@router.delete("/plants/{plant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_plant(
    plant_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "manager")),
    db: AsyncSession = Depends(get_db),
) -> None:
    plant = await get_plant_by_id(db, plant_id, current_user.tenant_id)
    if plant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Závod nenalezen")
    plant.status = "archived"
    await db.flush()


# ── Workplaces ────────────────────────────────────────────────────────────────

@router.get("/workplaces", response_model=list[WorkplaceResponse])
async def list_workplaces(
    plant_id: uuid.UUID | None = Query(None),
    workplace_status: str | None = Query(None, pattern="^(active|archived)$"),
    current_user: User = Depends(require_role("ozo", "manager", "employee")),
    db: AsyncSession = Depends(get_db),
) -> list[Any]:
    return await get_workplaces(
        db, current_user.tenant_id, plant_id=plant_id, status=workplace_status
    )


@router.post("/workplaces", response_model=WorkplaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workplace_endpoint(
    data: WorkplaceCreateRequest,
    current_user: User = Depends(require_role("ozo", "manager")),
    db: AsyncSession = Depends(get_db),
) -> object:
    try:
        return await create_workplace(db, data, current_user.tenant_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.get("/workplaces/{workplace_id}", response_model=WorkplaceResponse)
async def get_workplace(
    workplace_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "manager", "employee")),
    db: AsyncSession = Depends(get_db),
) -> object:
    workplace = await get_workplace_by_id(db, workplace_id, current_user.tenant_id)
    if workplace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pracoviště nenalezeno")
    return workplace


@router.patch("/workplaces/{workplace_id}", response_model=WorkplaceResponse)
async def update_workplace_endpoint(
    workplace_id: uuid.UUID,
    data: WorkplaceUpdateRequest,
    current_user: User = Depends(require_role("ozo", "manager")),
    db: AsyncSession = Depends(get_db),
) -> object:
    workplace = await get_workplace_by_id(db, workplace_id, current_user.tenant_id)
    if workplace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pracoviště nenalezeno")
    return await update_workplace(db, workplace, data)


@router.delete("/workplaces/{workplace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_workplace(
    workplace_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "manager")),
    db: AsyncSession = Depends(get_db),
) -> None:
    workplace = await get_workplace_by_id(db, workplace_id, current_user.tenant_id)
    if workplace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pracoviště nenalezeno")
    workplace.status = "archived"
    await db.flush()


# ── Risk Factor Assessments ───────────────────────────────────────────────────

@router.get("/risk-factors", response_model=list[RiskFactorAssessmentResponse])
async def list_risk_factors(
    workplace_id: uuid.UUID | None = Query(None),
    rfa_status: str | None = Query(None, pattern="^(active|archived)$"),
    current_user: User = Depends(require_role("ozo", "manager", "employee")),
    db: AsyncSession = Depends(get_db),
) -> list[Any]:
    return await get_risk_factor_assessments(
        db, current_user.tenant_id, workplace_id=workplace_id, status=rfa_status
    )


# DŮLEŽITÉ: /risk-factors/export/pdf musí být před /risk-factors/{rfa_id}
@router.get("/risk-factors/export/pdf")
async def export_risk_factors_pdf(
    plant_id: uuid.UUID | None = Query(None),
    download: bool = Query(False),
    current_user: User = Depends(require_role("ozo", "manager")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Exportuje Seznam rizikových faktorů jako PDF.
    Seskupeno: závod → pracoviště → profese.
    Nepovinný filtr: ?plant_id=
    """
    tenant = (
        await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    ).scalar_one_or_none()
    tenant_name = tenant.name if tenant else str(current_user.tenant_id)

    grouped = await get_rfa_grouped_for_export(db, current_user.tenant_id, plant_id=plant_id)
    pdf_bytes = generate_risk_factor_list_pdf(grouped, tenant_name)

    disposition = "attachment" if download else "inline"
    filename = f"seznam_rizikových_faktoru_{date.today()}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


@router.post(
    "/risk-factors",
    response_model=RiskFactorAssessmentResponse,
    status_code=status.HTTP_201_CREATED,
)  # noqa: E501
async def create_rfa_endpoint(
    data: RiskFactorAssessmentCreateRequest,
    current_user: User = Depends(require_role("ozo", "manager")),
    db: AsyncSession = Depends(get_db),
) -> object:
    try:
        return await create_rfa(db, data, current_user.tenant_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.get("/risk-factors/{rfa_id}", response_model=RiskFactorAssessmentResponse)
async def get_rfa_endpoint(
    rfa_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "manager", "employee")),
    db: AsyncSession = Depends(get_db),
) -> object:
    rfa = await get_rfa_by_id(db, rfa_id, current_user.tenant_id)
    if rfa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hodnocení nenalezeno")
    return rfa


@router.patch("/risk-factors/{rfa_id}", response_model=RiskFactorAssessmentResponse)
async def update_rfa_endpoint(
    rfa_id: uuid.UUID,
    data: RiskFactorAssessmentUpdateRequest,
    current_user: User = Depends(require_role("ozo", "manager")),
    db: AsyncSession = Depends(get_db),
) -> object:
    rfa = await get_rfa_by_id(db, rfa_id, current_user.tenant_id)
    if rfa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hodnocení nenalezeno")
    return await update_rfa(db, rfa, data)


@router.delete("/risk-factors/{rfa_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_rfa(
    rfa_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "manager")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Archivuje hodnocení. Fyzické smazání není povoleno – BOZP dokumentace."""
    rfa = await get_rfa_by_id(db, rfa_id, current_user.tenant_id)
    if rfa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hodnocení nenalezeno")
    rfa.status = "archived"
    await db.flush()
