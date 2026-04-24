import secrets
import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.validation import assert_in_tenant
from app.models.employee import Employee
from app.models.revision import (
    DUE_SOON_DAYS,
    EmployeePlantResponsibility,
    Revision,
    RevisionRecord,
)
from app.models.risk import Risk
from app.models.training import Training, TrainingAssignment
from app.models.user import User
from app.models.workplace import Plant
from app.schemas.revisions import (
    CalendarItem,
    RevisionCreateRequest,
    RevisionUpdateRequest,
)


def _add_months(d: date, months: int) -> date:
    import calendar
    month = d.month + months
    year = d.year + (month - 1) // 12
    month = ((month - 1) % 12) + 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(d.day, last_day)
    return date(year, month, day)


async def get_revisions(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    revision_type: str | None = None,
    status: str | None = None,
    due_status: str | None = None,
    plant_id: uuid.UUID | None = None,
    device_type: str | None = None,
) -> list[Revision]:
    query = select(Revision).where(Revision.tenant_id == tenant_id)
    if revision_type is not None:
        query = query.where(Revision.revision_type == revision_type)
    if status is not None:
        query = query.where(Revision.status == status)
    if plant_id is not None:
        query = query.where(Revision.plant_id == plant_id)
    if device_type is not None:
        query = query.where(Revision.device_type == device_type)
    query = query.order_by(Revision.next_revision_at.asc().nulls_last())
    result = await db.execute(query)
    rows = list(result.scalars().all())

    if due_status is not None:
        rows = [r for r in rows if r.due_status == due_status]

    return rows


async def get_revision_by_id(
    db: AsyncSession, revision_id: uuid.UUID, tenant_id: uuid.UUID
) -> Revision | None:
    result = await db.execute(
        select(Revision).where(
            Revision.id == revision_id,
            Revision.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def get_revision_by_qr_token(
    db: AsyncSession, qr_token: str, tenant_id: uuid.UUID
) -> Revision | None:
    result = await db.execute(
        select(Revision).where(
            Revision.qr_token == qr_token,
            Revision.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


def _generate_qr_token() -> str:
    return secrets.token_urlsafe(24).replace("-", "").replace("_", "")[:32]


async def create_revision(
    db: AsyncSession,
    data: RevisionCreateRequest,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
) -> Revision:
    if data.plant_id is not None:
        await assert_in_tenant(
            db, Plant, data.plant_id, tenant_id, field_name="plant_id"
        )
    if data.responsible_user_id is not None:
        await assert_in_tenant(
            db, User, data.responsible_user_id, tenant_id,
            field_name="responsible_user_id",
        )

    revision = Revision(
        tenant_id=tenant_id,
        created_by=created_by,
        title=data.title,
        plant_id=data.plant_id,
        device_code=data.device_code,
        device_type=data.device_type,
        revision_type=data.revision_type or "other",
        location=data.location,
        last_revised_at=data.last_revised_at,
        valid_months=data.valid_months,
        next_revision_at=data.next_revision_at,
        technician_name=data.technician_name,
        technician_email=data.technician_email,
        technician_phone=data.technician_phone,
        responsible_user_id=data.responsible_user_id,
        qr_token=_generate_qr_token(),
        notes=data.notes,
    )
    db.add(revision)
    await db.flush()

    # Pokud je zadáno last_revised_at, vytvoříme odpovídající první record
    # aby timeline nebyla prázdná.
    if data.last_revised_at is not None:
        record = RevisionRecord(
            tenant_id=tenant_id,
            revision_id=revision.id,
            performed_at=data.last_revised_at,
            technician_name=data.technician_name,
            created_by=created_by,
        )
        db.add(record)
        await db.flush()

    return revision


async def update_revision(
    db: AsyncSession, revision: Revision, data: RevisionUpdateRequest
) -> Revision:
    update_fields = data.model_dump(exclude_unset=True)

    if "plant_id" in update_fields and update_fields["plant_id"] is not None:
        await assert_in_tenant(
            db, Plant, update_fields["plant_id"], revision.tenant_id,
            field_name="plant_id",
        )
    if (
        "responsible_user_id" in update_fields
        and update_fields["responsible_user_id"] is not None
    ):
        await assert_in_tenant(
            db, User, update_fields["responsible_user_id"], revision.tenant_id,
            field_name="responsible_user_id",
        )
    for field, value in update_fields.items():
        setattr(revision, field, value)

    if "next_revision_at" not in update_fields:
        last = revision.last_revised_at
        months = revision.valid_months
        if last is not None and months is not None:
            revision.next_revision_at = _add_months(last, months)

    await db.flush()
    return revision


# ── Revision records (timeline) ───────────────────────────────────────────────


async def get_revision_records(
    db: AsyncSession, revision_id: uuid.UUID, tenant_id: uuid.UUID
) -> list[RevisionRecord]:
    result = await db.execute(
        select(RevisionRecord)
        .where(
            RevisionRecord.tenant_id == tenant_id,
            RevisionRecord.revision_id == revision_id,
        )
        .order_by(RevisionRecord.performed_at.desc())
    )
    return list(result.scalars().all())


async def get_revision_record_by_id(
    db: AsyncSession, record_id: uuid.UUID, tenant_id: uuid.UUID
) -> RevisionRecord | None:
    result = await db.execute(
        select(RevisionRecord).where(
            RevisionRecord.id == record_id,
            RevisionRecord.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def add_revision_record(
    db: AsyncSession,
    *,
    revision: Revision,
    performed_at: date,
    technician_name: str | None,
    notes: str | None,
    created_by: uuid.UUID,
    pdf_path: str | None = None,
    image_path: str | None = None,
) -> RevisionRecord:
    """Vytvoří record + aktualizuje last_revised_at/next_revision_at."""
    record = RevisionRecord(
        tenant_id=revision.tenant_id,
        revision_id=revision.id,
        performed_at=performed_at,
        pdf_path=pdf_path,
        image_path=image_path,
        technician_name=technician_name,
        notes=notes,
        created_by=created_by,
    )
    db.add(record)
    await db.flush()

    if revision.last_revised_at is None or performed_at > revision.last_revised_at:
        revision.last_revised_at = performed_at
        if revision.valid_months is not None:
            revision.next_revision_at = _add_months(performed_at, revision.valid_months)
        await db.flush()

    return record


# ── QR code generator ────────────────────────────────────────────────────────


def generate_qr_png(url: str) -> bytes:
    """PNG bytes s QR kódem pro daný URL."""
    import io

    import qrcode
    from qrcode.constants import ERROR_CORRECT_M

    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ── Employee plant responsibilities ──────────────────────────────────────────


async def get_employee_responsibilities(
    db: AsyncSession, employee_id: uuid.UUID, tenant_id: uuid.UUID
) -> list[uuid.UUID]:
    result = await db.execute(
        select(EmployeePlantResponsibility.plant_id).where(
            EmployeePlantResponsibility.tenant_id == tenant_id,
            EmployeePlantResponsibility.employee_id == employee_id,
        )
    )
    return [row[0] for row in result.all()]


async def set_employee_responsibilities(
    db: AsyncSession,
    employee_id: uuid.UUID,
    plant_ids: list[uuid.UUID],
    tenant_id: uuid.UUID,
) -> list[uuid.UUID]:
    """Replace-strategie: smaže staré vazby, vloží zadané, upraví user.role."""
    await assert_in_tenant(
        db, Employee, employee_id, tenant_id, field_name="employee_id"
    )
    for pid in plant_ids:
        await assert_in_tenant(db, Plant, pid, tenant_id, field_name="plant_id")

    existing = await db.execute(
        select(EmployeePlantResponsibility).where(
            EmployeePlantResponsibility.tenant_id == tenant_id,
            EmployeePlantResponsibility.employee_id == employee_id,
        )
    )
    for row in existing.scalars():
        await db.delete(row)
    await db.flush()

    for pid in set(plant_ids):
        db.add(
            EmployeePlantResponsibility(
                tenant_id=tenant_id,
                employee_id=employee_id,
                plant_id=pid,
            )
        )
    await db.flush()

    # Synchronizace user.role s flagem „je zodpovědný"
    emp_result = await db.execute(
        select(Employee).where(Employee.id == employee_id)
    )
    employee = emp_result.scalar_one()
    if employee.user_id is not None:
        user_result = await db.execute(
            select(User).where(User.id == employee.user_id)
        )
        user = user_result.scalar_one_or_none()
        if user is not None and user.role in ("employee", "equipment_responsible"):
            user.role = "equipment_responsible" if plant_ids else "employee"

    return list(set(plant_ids))


async def get_responsible_employees_for_plant(
    db: AsyncSession, plant_id: uuid.UUID, tenant_id: uuid.UUID
) -> list[Employee]:
    """Zaměstnanci s vazbou na danou provozovnu (aktivní, pro notifikace)."""
    result = await db.execute(
        select(Employee)
        .join(
            EmployeePlantResponsibility,
            EmployeePlantResponsibility.employee_id == Employee.id,
        )
        .where(
            EmployeePlantResponsibility.tenant_id == tenant_id,
            EmployeePlantResponsibility.plant_id == plant_id,
            Employee.status == "active",
        )
    )
    return list(result.scalars().all())


# ── Response enrichment (JOIN na plant.name pro čitelnost UI) ────────────────


async def revision_to_response_dict(
    db: AsyncSession, revision: Revision
) -> dict[str, Any]:
    plant_name: str | None = None
    if revision.plant_id is not None:
        plant_result = await db.execute(
            select(Plant.name).where(Plant.id == revision.plant_id)
        )
        plant_name = plant_result.scalar_one_or_none()

    return {
        "id": revision.id,
        "tenant_id": revision.tenant_id,
        "title": revision.title,
        "plant_id": revision.plant_id,
        "plant_name": plant_name,
        "device_code": revision.device_code,
        "device_type": revision.device_type,
        "location": revision.location,
        "last_revised_at": revision.last_revised_at,
        "valid_months": revision.valid_months,
        "next_revision_at": revision.next_revision_at,
        "due_status": revision.due_status,
        "technician_name": revision.technician_name,
        "technician_email": revision.technician_email,
        "technician_phone": revision.technician_phone,
        "contractor": revision.contractor,
        "responsible_user_id": revision.responsible_user_id,
        "qr_token": revision.qr_token,
        "notes": revision.notes,
        "status": revision.status,
        "created_by": revision.created_by,
        "revision_type": revision.revision_type,
    }


# ── Agregovaný kalendář (ponecháno z minulé implementace) ────────────────────

def _compute_due_status(due_date: date) -> str:
    today = datetime.now(UTC).date()
    delta = (due_date - today).days
    if delta < 0:
        return "overdue"
    if delta <= DUE_SOON_DAYS:
        return "due_soon"
    return "ok"


async def get_calendar_items(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    days_ahead: int = 90,
) -> list[CalendarItem]:
    today = datetime.now(UTC).date()
    from datetime import timedelta
    horizon = today + timedelta(days=days_ahead)

    items: list[CalendarItem] = []

    rev_result = await db.execute(
        select(Revision).where(
            Revision.tenant_id == tenant_id,
            Revision.status == "active",
            Revision.next_revision_at.is_not(None),
        )
    )
    for rev in rev_result.scalars():
        if rev.next_revision_at <= horizon:  # type: ignore[operator]
            items.append(CalendarItem(
                source="revision",
                source_id=rev.id,
                title=rev.title,
                due_date=rev.next_revision_at,
                due_status=_compute_due_status(rev.next_revision_at),  # type: ignore[arg-type]
                responsible_user_id=rev.responsible_user_id,
                detail_url=f"/api/v1/revisions/{rev.id}",
            ))

    risk_result = await db.execute(
        select(Risk).where(
            Risk.tenant_id == tenant_id,
            Risk.status == "active",
            Risk.review_date.is_not(None),
        )
    )
    for risk in risk_result.scalars():
        if risk.review_date <= horizon:  # type: ignore[operator]
            items.append(CalendarItem(
                source="risk",
                source_id=risk.id,
                title=risk.title,
                due_date=risk.review_date,
                due_status=_compute_due_status(risk.review_date),  # type: ignore[arg-type]
                responsible_user_id=risk.responsible_user_id,
                detail_url=f"/api/v1/risks/{risk.id}",
            ))

    ta_result = await db.execute(
        select(TrainingAssignment, Training)
        .join(Training, TrainingAssignment.training_id == Training.id)
        .where(
            TrainingAssignment.tenant_id == tenant_id,
            TrainingAssignment.status == "completed",
            TrainingAssignment.valid_until.is_not(None),
        )
    )
    for ta, training in ta_result.all():
        if ta.valid_until is None:
            continue
        if ta.valid_until <= horizon:
            items.append(CalendarItem(
                source="training",
                source_id=ta.id,
                title=training.title,
                due_date=ta.valid_until,
                due_status=_compute_due_status(ta.valid_until),
                responsible_user_id=None,
                detail_url=f"/api/v1/trainings/assignments/{ta.id}",
            ))

    items.sort(key=lambda x: x.due_date)
    return items
