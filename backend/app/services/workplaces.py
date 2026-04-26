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


async def get_rfa_by_job_position(
    db: AsyncSession, job_position_id: uuid.UUID, tenant_id: uuid.UUID
) -> RiskFactorAssessment | None:
    """RFA je 1:1 s JobPosition — vrátí jediný záznam (pokud existuje)."""
    result = await db.execute(
        select(RiskFactorAssessment).where(
            RiskFactorAssessment.job_position_id == job_position_id,
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
    """
    Vytvoří RFA. V novém modelu se volá primárně přes job_position_id;
    workplace_id + profese jsou legacy a dopočítají se ze JobPosition.
    """
    from app.services.job_positions import get_job_position_by_id

    if data.job_position_id is not None:
        jp = await get_job_position_by_id(db, data.job_position_id, tenant_id)
        if jp is None:
            raise ValueError(f"Pozice {data.job_position_id} nenalezena")
        workplace_id = jp.workplace_id
        profese = data.profese or jp.name
    else:
        if data.workplace_id is None or data.profese is None:
            raise ValueError("job_position_id NEBO (workplace_id + profese) musí být zadáno")
        workplace = await get_workplace_by_id(db, data.workplace_id, tenant_id)
        if workplace is None:
            raise ValueError(f"Pracoviště {data.workplace_id} nenalezeno")
        workplace_id = data.workplace_id
        profese = data.profese
        # Legacy cesta: auto-vytvoříme JobPosition, aby FK bylo splněné
        from app.models.job_position import JobPosition
        jp = JobPosition(
            tenant_id=tenant_id,
            workplace_id=workplace_id,
            name=profese,
            created_by=created_by,
        )
        db.add(jp)
        await db.flush()

    payload = data.model_dump(exclude={"job_position_id", "workplace_id", "profese"})
    rfa = RiskFactorAssessment(
        tenant_id=tenant_id,
        created_by=created_by,
        workplace_id=workplace_id,
        job_position_id=jp.id,
        profese=profese,
        **payload,
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


# ── PDF per faktor ────────────────────────────────────────────────────────────

async def set_rfa_factor_pdf(
    db: AsyncSession,
    rfa: RiskFactorAssessment,
    factor_key: str,
    pdf_path: str,
) -> RiskFactorAssessment:
    """Zapíše pdf_path do sloupce rf_<factor>_pdf_path."""
    from app.models.risk_factor_assessment import RF_FIELDS
    if factor_key not in RF_FIELDS:
        raise ValueError(f"Neplatný factor_key: {factor_key}")
    setattr(rfa, f"{factor_key}_pdf_path", pdf_path)
    await db.flush()
    return rfa


async def clear_rfa_factor_pdf(
    db: AsyncSession, rfa: RiskFactorAssessment, factor_key: str
) -> RiskFactorAssessment:
    from app.models.risk_factor_assessment import RF_FIELDS
    if factor_key not in RF_FIELDS:
        raise ValueError(f"Neplatný factor_key: {factor_key}")
    setattr(rfa, f"{factor_key}_pdf_path", None)
    await db.flush()
    return rfa


# ── Export helper ─────────────────────────────────────────────────────────────

async def get_workplace_aggregated_rfa(
    db: AsyncSession,
    workplace_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> dict[str, str | None]:
    """Vrátí agregované RFA pro pracoviště — MAX kategorie per faktor napříč
    pozicemi pracoviště. Slouží jako "workplace-level" RFA view.

    Vrací dict {factor_key: rating} (pouze MAX hodnoty; 2R = 2.5 numericky).
    """
    from app.models.job_position import JobPosition
    from app.models.risk_factor_assessment import RF_FIELDS, _rating_numeric

    # Najdi všechny RFAs napříč pozicemi tohoto workplace
    res = await db.execute(
        select(RiskFactorAssessment)
        .join(JobPosition, RiskFactorAssessment.job_position_id == JobPosition.id)
        .where(
            JobPosition.workplace_id == workplace_id,
            RiskFactorAssessment.tenant_id == tenant_id,
            RiskFactorAssessment.status == "active",
        )
    )
    rfas = list(res.scalars().all())

    out: dict[str, str | None] = {f: None for f in RF_FIELDS}
    for f in RF_FIELDS:
        # Kolektuj všechny non-null hodnoty pro daný faktor
        values = [getattr(rfa, f) for rfa in rfas if getattr(rfa, f) is not None]
        if not values:
            continue
        # Vyber MAX podle numeric rating (2R = 2.5)
        max_val = max(values, key=_rating_numeric)
        out[f] = max_val
    return out


async def bulk_update_workplace_rfa(
    db: AsyncSession,
    workplace_id: uuid.UUID,
    tenant_id: uuid.UUID,
    factor: str,
    rating: str | None,
    created_by: uuid.UUID,
) -> dict[str, str | None]:
    """Nastaví hodnotu jednoho rizikového faktoru na všech RFAs daného
    pracoviště (přes všechny pozice). Pokud pozice nemá RFA, vytvoří ji.
    """
    from app.models.job_position import JobPosition
    from app.models.risk_factor_assessment import RF_FIELDS, VALID_RATINGS

    if factor not in RF_FIELDS:
        raise ValueError(f"Neplatný factor: {factor}")
    if rating is not None and rating not in VALID_RATINGS:
        raise ValueError(f"Neplatný rating: {rating}")

    # Workplace existuje a patří tenantu
    wp = await get_workplace_by_id(db, workplace_id, tenant_id)
    if wp is None:
        raise ValueError(f"Pracoviště {workplace_id} nenalezeno")

    # Všechny aktivní pozice pracoviště
    pos_res = await db.execute(
        select(JobPosition).where(
            JobPosition.workplace_id == workplace_id,
            JobPosition.tenant_id == tenant_id,
            JobPosition.status == "active",
        )
    )
    positions = list(pos_res.scalars().all())

    for pos in positions:
        # Najdi nebo vytvoř RFA pro pozici
        rfa = await get_rfa_by_job_position(db, pos.id, tenant_id)
        if rfa is None:
            rfa = RiskFactorAssessment(
                tenant_id=tenant_id,
                workplace_id=workplace_id,
                job_position_id=pos.id,
                profese=pos.name,
                worker_count=0,
                women_count=0,
                created_by=created_by,
            )
            db.add(rfa)
            await db.flush()
        # Nastav daný faktor
        setattr(rfa, factor, rating)

    await db.flush()
    return await get_workplace_aggregated_rfa(db, workplace_id, tenant_id)


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
