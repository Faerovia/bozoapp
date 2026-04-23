import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.risk_factor_assessment import RiskFactorAssessment
from app.models.workplace import Plant, Workplace
from app.schemas.workplaces import (
    PlantCreateRequest,
    PlantUpdateRequest,
    RiskFactorAssessmentCreateRequest,
    RiskFactorAssessmentUpdateRequest,
    WorkplaceCreateRequest,
    WorkplaceUpdateRequest,
)


# ── Plants ────────────────────────────────────────────────────────────────────

async def get_plants(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    status: str | None = None,
) -> list[Plant]:
    query = (
        select(Plant)
        .where(Plant.tenant_id == tenant_id)
        .order_by(Plant.name)
    )
    if status is not None:
        query = query.where(Plant.status == status)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_plant_by_id(
    db: AsyncSession, plant_id: uuid.UUID, tenant_id: uuid.UUID
) -> Plant | None:
    result = await db.execute(
        select(Plant).where(Plant.id == plant_id, Plant.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


async def create_plant(
    db: AsyncSession,
    data: PlantCreateRequest,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
) -> Plant:
    plant = Plant(
        tenant_id=tenant_id,
        created_by=created_by,
        **data.model_dump(),
    )
    db.add(plant)
    await db.flush()
    return plant


async def update_plant(
    db: AsyncSession, plant: Plant, data: PlantUpdateRequest
) -> Plant:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(plant, field, value)
    await db.flush()
    return plant


# ── Workplaces ────────────────────────────────────────────────────────────────

async def get_workplaces(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    plant_id: uuid.UUID | None = None,
    status: str | None = None,
) -> list[Workplace]:
    query = (
        select(Workplace)
        .where(Workplace.tenant_id == tenant_id)
        .order_by(Workplace.name)
    )
    if plant_id is not None:
        query = query.where(Workplace.plant_id == plant_id)
    if status is not None:
        query = query.where(Workplace.status == status)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_workplace_by_id(
    db: AsyncSession, workplace_id: uuid.UUID, tenant_id: uuid.UUID
) -> Workplace | None:
    result = await db.execute(
        select(Workplace).where(
            Workplace.id == workplace_id, Workplace.tenant_id == tenant_id
        )
    )
    return result.scalar_one_or_none()


async def create_workplace(
    db: AsyncSession,
    data: WorkplaceCreateRequest,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
) -> Workplace:
    # Ověří, že plant_id patří tomuto tenantovi
    plant = await get_plant_by_id(db, data.plant_id, tenant_id)
    if plant is None:
        raise ValueError(f"Závod {data.plant_id} nenalezen")

    workplace = Workplace(
        tenant_id=tenant_id,
        created_by=created_by,
        **data.model_dump(),
    )
    db.add(workplace)
    await db.flush()
    return workplace


async def update_workplace(
    db: AsyncSession, workplace: Workplace, data: WorkplaceUpdateRequest
) -> Workplace:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(workplace, field, value)
    await db.flush()
    return workplace


# ── RiskFactorAssessments ─────────────────────────────────────────────────────

async def get_risk_factor_assessments(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    workplace_id: uuid.UUID | None = None,
    status: str | None = None,
) -> list[RiskFactorAssessment]:
    query = (
        select(RiskFactorAssessment)
        .where(RiskFactorAssessment.tenant_id == tenant_id)
        .order_by(RiskFactorAssessment.sort_order, RiskFactorAssessment.profese)
    )
    if workplace_id is not None:
        query = query.where(RiskFactorAssessment.workplace_id == workplace_id)
    if status is not None:
        query = query.where(RiskFactorAssessment.status == status)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_rfa_by_id(
    db: AsyncSession, rfa_id: uuid.UUID, tenant_id: uuid.UUID
) -> RiskFactorAssessment | None:
    result = await db.execute(
        select(RiskFactorAssessment).where(
            RiskFactorAssessment.id == rfa_id,
            RiskFactorAssessment.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def create_rfa(
    db: AsyncSession,
    data: RiskFactorAssessmentCreateRequest,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
) -> RiskFactorAssessment:
    # Ověří, že workplace_id patří tomuto tenantovi
    workplace = await get_workplace_by_id(db, data.workplace_id, tenant_id)
    if workplace is None:
        raise ValueError(f"Pracoviště {data.workplace_id} nenalezeno")

    rfa = RiskFactorAssessment(
        tenant_id=tenant_id,
        created_by=created_by,
        **data.model_dump(),
    )
    db.add(rfa)
    await db.flush()
    return rfa


async def update_rfa(
    db: AsyncSession, rfa: RiskFactorAssessment, data: RiskFactorAssessmentUpdateRequest
) -> RiskFactorAssessment:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(rfa, field, value)
    await db.flush()
    return rfa


# ── Export helper ─────────────────────────────────────────────────────────────

async def get_rfa_grouped_for_export(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    plant_id: uuid.UUID | None = None,
) -> list[tuple[Plant, list[tuple[Workplace, list[RiskFactorAssessment]]]]]:
    """
    Vrátí data pro PDF export: [(plant, [(workplace, [rfa, ...]), ...]), ...]
    Seřazeno: závod → pracoviště → sort_order.
    """
    plants = await get_plants(db, tenant_id, status="active")
    if plant_id is not None:
        plants = [p for p in plants if p.id == plant_id]

    result = []
    for plant in plants:
        workplaces = await get_workplaces(db, tenant_id, plant_id=plant.id, status="active")
        plant_data = []
        for wp in workplaces:
            rfas = await get_risk_factor_assessments(
                db, tenant_id, workplace_id=wp.id, status="active"
            )
            if rfas:
                plant_data.append((wp, rfas))
        if plant_data:
            result.append((plant, plant_data))

    return result
