import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.validation import assert_in_tenant
from app.models.employee import Employee
from app.models.job_position import JobPosition
from app.models.medical_exam import MedicalExam
from app.schemas.medical_exams import MedicalExamCreateRequest, MedicalExamUpdateRequest
from app.services.medical_specialty_catalog import (
    SPECIALTY_CATALOG,
    get_required_specialties_for_category,
)


def _specialty_label(specialty: str | None) -> str | None:
    if not specialty:
        return None
    for entry in SPECIALTY_CATALOG:
        if entry["key"] == specialty:
            return entry["label"]
    return specialty  # fallback — neznámé


async def attach_employee_info(
    db: AsyncSession,
    exams: list[MedicalExam],
    *,
    include_personal_id: bool = False,
) -> list[dict[str, Any]]:
    """
    Obohatí prohlídky o jméno + RČ zaměstnance + název pozice.
    Vrací list dictů kompatibilních s MedicalExamResponse.

    Pozn.: čerstvě flushnuté ORM objekty mohou mít expired atributy v async
    session — proto čteme přes db.refresh, ne přes __table__.columns + getattr.
    """
    if not exams:
        return []

    # Refresh každé prohlídky, aby všechna pole byla načtená v tomto greenlet
    for exam in exams:
        await db.refresh(exam)

    employee_ids = {e.employee_id for e in exams}
    position_ids = {e.job_position_id for e in exams if e.job_position_id}

    emp_rows = (await db.execute(
        select(Employee).where(Employee.id.in_(employee_ids))
    )).scalars().all()
    emp_map = {emp.id: emp for emp in emp_rows}

    pos_map: dict[uuid.UUID, JobPosition] = {}
    if position_ids:
        pos_rows = (await db.execute(
            select(JobPosition).where(JobPosition.id.in_(position_ids))
        )).scalars().all()
        pos_map = {p.id: p for p in pos_rows}

    result: list[dict[str, Any]] = []
    for exam in exams:
        emp = emp_map.get(exam.employee_id)
        pos = pos_map.get(exam.job_position_id) if exam.job_position_id else None
        d: dict[str, Any] = {
            "id":                 exam.id,
            "tenant_id":          exam.tenant_id,
            "employee_id":        exam.employee_id,
            "job_position_id":    exam.job_position_id,
            "exam_category":      exam.exam_category,
            "exam_type":          exam.exam_type,
            "specialty":          exam.specialty,
            "exam_date":          exam.exam_date,
            "result":             exam.result,
            "physician_name":     exam.physician_name,
            "valid_months":       exam.valid_months,
            "valid_until":        exam.valid_until,
            "report_path":        exam.report_path,
            "notes":              exam.notes,
            "status":             exam.status,
            "created_by":         exam.created_by,
            "validity_status":    exam.validity_status,
            "days_until_expiry":  exam.days_until_expiry,
            "employee_name": (
                f"{emp.first_name} {emp.last_name}".strip() if emp else None
            ),
            "employee_personal_id": (
                emp.personal_id if (emp and include_personal_id) else None
            ),
            "job_position_name": pos.name if pos else None,
            "work_category":     pos.work_category if pos else None,
            "specialty_label":   _specialty_label(exam.specialty),
            "has_report":        bool(exam.report_path),
        }
        result.append(d)
    return result


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
    await assert_in_tenant(db, Employee, data.employee_id, tenant_id, field_name="employee_id")
    if data.job_position_id is not None:
        await assert_in_tenant(
            db, JobPosition, data.job_position_id, tenant_id, field_name="job_position_id"
        )
    exam = MedicalExam(
        tenant_id=tenant_id,
        created_by=created_by,
        employee_id=data.employee_id,
        job_position_id=data.job_position_id,
        exam_category=data.exam_category,
        exam_type=data.exam_type,
        specialty=data.specialty,
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


async def generate_initial_exam_requests(
    db: AsyncSession,
    employee_id: uuid.UUID,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
) -> dict[str, Any]:
    """
    Auto-vygeneruje vstupní lékařskou prohlídku + povinné odborné prohlídky
    podle kategorie práce zaměstnance (z jeho přiřazené job_position).

    Záznamy se vytvoří jako 'planned' draft — bez exam_date (default today),
    bez výsledku. OZO je následně doplní po skutečné prohlídce.

    Pokud zaměstnanec už má aktivní prohlídku stejného typu/specialty
    (status=active, validity_status != expired), nevytvoří se duplikát.
    """
    await assert_in_tenant(db, Employee, employee_id, tenant_id, field_name="employee_id")
    emp = (await db.execute(
        select(Employee).where(Employee.id == employee_id)
    )).scalar_one()

    work_category: str | None = None
    job_position_id: uuid.UUID | None = emp.job_position_id
    if job_position_id is not None:
        pos = (await db.execute(
            select(JobPosition).where(JobPosition.id == job_position_id)
        )).scalar_one_or_none()
        if pos is not None:
            work_category = pos.work_category

    # Existující aktivní prohlídky tohoto zaměstnance
    existing = (await db.execute(
        select(MedicalExam).where(
            MedicalExam.employee_id == employee_id,
            MedicalExam.tenant_id == tenant_id,
            MedicalExam.status == "active",
        )
    )).scalars().all()
    existing_specialties = {e.specialty for e in existing if e.specialty}
    has_vstupni = any(
        e.exam_type == "vstupni" and e.validity_status != "expired" for e in existing
    )

    today = date.today()
    created_exams: list[MedicalExam] = []
    skipped: list[str] = []

    # 1) Vstupní preventivní prohlídka
    if not has_vstupni:
        exam = MedicalExam(
            tenant_id=tenant_id,
            created_by=created_by,
            employee_id=employee_id,
            job_position_id=job_position_id,
            exam_category="preventivni",
            exam_type="vstupni",
            exam_date=today,
            notes="Auto-vygenerováno na základě nástupu zaměstnance.",
        )
        db.add(exam)
        created_exams.append(exam)
    else:
        skipped.append("vstupni")

    # 2) Odborné prohlídky podle kategorie práce
    if work_category is not None:
        required = get_required_specialties_for_category(work_category)
        for specialty in required:
            if specialty in existing_specialties:
                skipped.append(specialty)
                continue
            exam = MedicalExam(
                tenant_id=tenant_id,
                created_by=created_by,
                employee_id=employee_id,
                job_position_id=job_position_id,
                exam_category="odborna",
                exam_type="odborna",
                specialty=specialty,
                exam_date=today,
                notes=(
                    f"Auto-vygenerováno na základě kategorie práce {work_category}."
                ),
            )
            db.add(exam)
            created_exams.append(exam)

    await db.flush()
    return {
        "created":             len(created_exams),
        "exam_ids":            [e.id for e in created_exams],
        "skipped_specialties": skipped,
        "work_category":       work_category,
    }


async def update_medical_exam(
    db: AsyncSession, exam: MedicalExam, data: MedicalExamUpdateRequest
) -> MedicalExam:
    update_fields = data.model_dump(exclude_unset=True)
    if "job_position_id" in update_fields and update_fields["job_position_id"] is not None:
        await assert_in_tenant(
            db, JobPosition, update_fields["job_position_id"], exam.tenant_id,
            field_name="job_position_id",
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
