import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.training import Training
from app.schemas.trainings import TrainingCreateRequest, TrainingUpdateRequest


async def _assert_employee_in_tenant(
    db: AsyncSession, employee_id: uuid.UUID, tenant_id: uuid.UUID
) -> None:
    """Ochrana proti cross-tenant FK injection — employee_id musí patřit do tenantu."""
    result = await db.execute(
        select(Employee.id).where(
            Employee.id == employee_id,
            Employee.tenant_id == tenant_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="employee_id neexistuje v tomto tenantu",
        )


async def get_trainings(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    employee_id: uuid.UUID | None = None,
    training_type: str | None = None,
    status: str | None = None,
    validity_status: str | None = None,
) -> list[Training]:
    query = select(Training).where(Training.tenant_id == tenant_id)

    if employee_id is not None:
        query = query.where(Training.employee_id == employee_id)
    if training_type is not None:
        query = query.where(Training.training_type == training_type)
    if status is not None:
        query = query.where(Training.status == status)

    query = query.order_by(Training.trained_at.desc())
    result = await db.execute(query)
    rows = list(result.scalars().all())

    # validity_status filtr se dělá in-memory (computed property, ne DB sloupec)
    if validity_status is not None:
        rows = [r for r in rows if r.validity_status == validity_status]

    return rows


async def get_training_by_id(
    db: AsyncSession, training_id: uuid.UUID, tenant_id: uuid.UUID
) -> Training | None:
    result = await db.execute(
        select(Training).where(
            Training.id == training_id,
            Training.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def create_training(
    db: AsyncSession,
    data: TrainingCreateRequest,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
) -> Training:
    await _assert_employee_in_tenant(db, data.employee_id, tenant_id)
    training = Training(
        tenant_id=tenant_id,
        created_by=created_by,
        employee_id=data.employee_id,
        title=data.title,
        training_type=data.training_type,
        trained_at=data.trained_at,
        valid_months=data.valid_months,
        valid_until=data.valid_until,
        trainer_name=data.trainer_name,
        notes=data.notes,
    )
    db.add(training)
    await db.flush()
    return training


async def update_training(
    db: AsyncSession, training: Training, data: TrainingUpdateRequest
) -> Training:
    update_fields = data.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        setattr(training, field, value)

    # Pokud se změnil trained_at nebo valid_months, přepočítej valid_until
    # (pouze pokud valid_until nebyl explicitně nastaven v tomto requestu)
    if "valid_until" not in update_fields:
        trained_at = training.trained_at
        valid_months = training.valid_months
        if trained_at is not None and valid_months is not None:
            import calendar
            month = trained_at.month + valid_months
            year = trained_at.year + (month - 1) // 12
            month = ((month - 1) % 12) + 1
            last_day = calendar.monthrange(year, month)[1]
            day = min(trained_at.day, last_day)
            from datetime import date
            training.valid_until = date(year, month, day)

    await db.flush()
    return training
