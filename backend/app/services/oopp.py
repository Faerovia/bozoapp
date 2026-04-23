import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.oopp import OOPPAssignment
from app.schemas.oopp import OOPPCreateRequest, OOPPUpdateRequest


async def get_oopp_assignments(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    employee_id: uuid.UUID | None = None,
    oopp_type: str | None = None,
    status: str | None = None,
    validity_status: str | None = None,
) -> list[OOPPAssignment]:
    query = (
        select(OOPPAssignment)
        .where(OOPPAssignment.tenant_id == tenant_id)
        .order_by(OOPPAssignment.issued_at.desc())
    )
    if employee_id is not None:
        query = query.where(OOPPAssignment.employee_id == employee_id)
    if oopp_type is not None:
        query = query.where(OOPPAssignment.oopp_type == oopp_type)
    if status is not None:
        query = query.where(OOPPAssignment.status == status)

    result = await db.execute(query)
    rows = list(result.scalars().all())

    # validity_status je computed property – filtrujeme v Pythonu
    if validity_status is not None:
        rows = [r for r in rows if r.validity_status == validity_status]

    return rows


async def get_oopp_by_id(
    db: AsyncSession, assignment_id: uuid.UUID, tenant_id: uuid.UUID
) -> OOPPAssignment | None:
    result = await db.execute(
        select(OOPPAssignment).where(
            OOPPAssignment.id == assignment_id,
            OOPPAssignment.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def create_oopp_assignment(
    db: AsyncSession,
    data: OOPPCreateRequest,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
) -> OOPPAssignment:
    assignment = OOPPAssignment(
        tenant_id=tenant_id,
        created_by=created_by,
        employee_id=data.employee_id,
        employee_name=data.employee_name,
        item_name=data.item_name,
        oopp_type=data.oopp_type,
        issued_at=data.issued_at,
        quantity=data.quantity,
        size_spec=data.size_spec,
        serial_number=data.serial_number,
        valid_months=data.valid_months,
        valid_until=data.valid_until,
        notes=data.notes,
    )
    db.add(assignment)
    await db.flush()
    return assignment


async def update_oopp_assignment(
    db: AsyncSession, assignment: OOPPAssignment, data: OOPPUpdateRequest
) -> OOPPAssignment:
    update_fields = data.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        setattr(assignment, field, value)

    # Přepočítej valid_until pokud se změnil issued_at nebo valid_months
    # a valid_until nebyl explicitně nastaven v tomto requestu
    if "valid_until" not in update_fields:
        issued = assignment.issued_at
        months = assignment.valid_months
        if issued is not None and months is not None:
            import calendar
            month = issued.month + months
            year = issued.year + (month - 1) // 12
            month = ((month - 1) % 12) + 1
            last_day = calendar.monthrange(year, month)[1]
            day = min(issued.day, last_day)
            from datetime import date
            assignment.valid_until = date(year, month, day)

    await db.flush()
    return assignment
