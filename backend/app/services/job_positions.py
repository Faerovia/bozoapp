import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.validation import assert_in_tenant
from app.models.job_position import JobPosition
from app.models.risk_factor_assessment import RiskFactorAssessment
from app.models.workplace import Workplace
from app.schemas.job_positions import JobPositionCreateRequest, JobPositionUpdateRequest


async def get_job_positions(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    status: str | None = None,
    work_category: str | None = None,
    workplace_id: uuid.UUID | None = None,
) -> list[JobPosition]:
    query = (
        select(JobPosition)
        .where(JobPosition.tenant_id == tenant_id)
        .order_by(JobPosition.name)
    )
    if status is not None:
        query = query.where(JobPosition.status == status)
    if work_category is not None:
        query = query.where(JobPosition.work_category == work_category)
    if workplace_id is not None:
        query = query.where(JobPosition.workplace_id == workplace_id)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_job_position_by_id(
    db: AsyncSession, jp_id: uuid.UUID, tenant_id: uuid.UUID
) -> JobPosition | None:
    result = await db.execute(
        select(JobPosition).where(
            JobPosition.id == jp_id,
            JobPosition.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def create_job_position(
    db: AsyncSession,
    data: JobPositionCreateRequest,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
) -> JobPosition:
    # Validace FK na workplace v rámci tenantu (cross-tenant ochrana)
    await assert_in_tenant(
        db, Workplace, data.workplace_id, tenant_id, field_name="workplace_id"
    )

    jp = JobPosition(
        tenant_id=tenant_id,
        created_by=created_by,
        **data.model_dump(),
    )
    db.add(jp)
    await db.flush()

    # Auto-vytvoř RFA stub (1:1). Uživatel ho pak vyplní v UI.
    rfa = RiskFactorAssessment(
        tenant_id=tenant_id,
        workplace_id=jp.workplace_id,   # legacy pole, drží konzistenci
        job_position_id=jp.id,
        profese=jp.name,
        worker_count=0,
        women_count=0,
        created_by=created_by,
    )
    db.add(rfa)
    await db.flush()

    return jp


async def update_job_position(
    db: AsyncSession,
    jp: JobPosition,
    data: JobPositionUpdateRequest,
    *,
    created_by: uuid.UUID | None = None,
) -> JobPosition:
    """Update JobPosition + reconciliace lékařských prohlídek.

    Pokud se mění `work_category`, propsat do plánu lékařských prohlídek
    (preventivní cat 1 = volitelné, jinak povinná periodicita).
    Reconciliace běží i tady, aby pokryla scénář "snížím kategorii pozice
    na 1 a chci, aby se vyčistily nepotřebné odborné prohlídky" — i když
    samotné odborné se vážou na rf_* faktory na RFA, ne na work_category.
    """
    update_fields = data.model_dump(exclude_unset=True)
    if "workplace_id" in update_fields and update_fields["workplace_id"] is not None:
        await assert_in_tenant(
            db, Workplace, update_fields["workplace_id"], jp.tenant_id,
            field_name="workplace_id",
        )

    work_category_changed = (
        "work_category" in update_fields
        and update_fields["work_category"] != jp.work_category
    )

    for field, value in update_fields.items():
        setattr(jp, field, value)
    await db.flush()

    if work_category_changed and created_by is not None:
        from app.services.medical_exams import (
            reconcile_exams_for_employees_on_position,
        )
        await reconcile_exams_for_employees_on_position(
            db,
            job_position_id=jp.id,
            tenant_id=jp.tenant_id,
            created_by=created_by,
        )

    return jp
