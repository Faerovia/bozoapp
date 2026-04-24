import uuid
from datetime import date, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.job_position import JobPosition
from app.models.medical_exam import MedicalExam
from app.schemas.medical_exams import MedicalExamCreateRequest, MedicalExamUpdateRequest


async def _assert_employee_in_tenant(
    db: AsyncSession, employee_id: uuid.UUID, tenant_id: uuid.UUID
) -> None:
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


async def _assert_job_position_in_tenant(
    db: AsyncSession, job_position_id: uuid.UUID, tenant_id: uuid.UUID
) -> None:
    result = await db.execute(
        select(JobPosition.id).where(
            JobPosition.id == job_position_id,
            JobPosition.tenant_id == tenant_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="job_position_id neexistuje v tomto tenantu",
        )


async def get_medical_exams(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    employee_id: uuid.UUID | None = None,
    exam_type: str | None = None,
    status: str | None = None,
    validity_status: str | None = None,
) -> list[MedicalExam]:
    query = (
        select(MedicalExam)
        .where(MedicalExam.tenant_id == tenant_id)
        .order_by(MedicalExam.exam_date.desc())
    )
    if employee_id is not None:
        query = query.where(MedicalExam.employee_id == employee_id)
    if exam_type is not None:
        query = query.where(MedicalExam.exam_type == exam_type)
    if status is not None:
        query = query.where(MedicalExam.status == status)

    result = await db.execute(query)
    rows = list(result.scalars().all())

    # validity_status je computed property – filtrujeme v Pythonu
    if validity_status is not None:
        rows = [r for r in rows if r.validity_status == validity_status]

    return rows


async def get_medical_exam_by_id(
    db: AsyncSession, exam_id: uuid.UUID, tenant_id: uuid.UUID
) -> MedicalExam | None:
    result = await db.execute(
        select(MedicalExam).where(
            MedicalExam.id == exam_id,
            MedicalExam.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def create_medical_exam(
    db: AsyncSession,
    data: MedicalExamCreateRequest,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
) -> MedicalExam:
    await _assert_employee_in_tenant(db, data.employee_id, tenant_id)
    if data.job_position_id is not None:
        await _assert_job_position_in_tenant(db, data.job_position_id, tenant_id)
    exam = MedicalExam(
        tenant_id=tenant_id,
        created_by=created_by,
        employee_id=data.employee_id,
        job_position_id=data.job_position_id,
        exam_type=data.exam_type,
        exam_date=data.exam_date,
        result=data.result,
        physician_name=data.physician_name,
        valid_months=data.valid_months,
        valid_until=data.valid_until,
        notes=data.notes,
    )
    db.add(exam)
    await db.flush()
    return exam


async def update_medical_exam(
    db: AsyncSession, exam: MedicalExam, data: MedicalExamUpdateRequest
) -> MedicalExam:
    update_fields = data.model_dump(exclude_unset=True)
    if "job_position_id" in update_fields and update_fields["job_position_id"] is not None:
        await _assert_job_position_in_tenant(
            db, update_fields["job_position_id"], exam.tenant_id
        )
    for field, value in update_fields.items():
        setattr(exam, field, value)

    # Přepočítej valid_until pokud se změnil exam_date nebo valid_months
    if "valid_until" not in update_fields:
        d = exam.exam_date
        months = exam.valid_months
        if d is not None and months is not None:
            import calendar
            month = d.month + months
            year = d.year + (month - 1) // 12
            month = ((month - 1) % 12) + 1
            last_day = calendar.monthrange(year, month)[1]
            exam.valid_until = date(year, month, min(d.day, last_day))

    await db.flush()
    return exam


async def get_expiring_exams(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    days_ahead: int = 60,
) -> list[MedicalExam]:
    """Vrátí aktivní prohlídky, které vyprší do `days_ahead` dnů."""
    today = date.today()
    cutoff = today + timedelta(days=days_ahead)
    query = (
        select(MedicalExam)
        .where(
            MedicalExam.tenant_id == tenant_id,
            MedicalExam.status == "active",
            MedicalExam.valid_until >= today,
            MedicalExam.valid_until <= cutoff,
        )
        .order_by(MedicalExam.valid_until)
    )
    result = await db.execute(query)
    return list(result.scalars().all())
