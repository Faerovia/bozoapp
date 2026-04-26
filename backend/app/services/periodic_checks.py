"""Service pro modul Pravidelné kontroly."""
from __future__ import annotations

import calendar
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.validation import assert_in_tenant
from app.models.periodic_check import PeriodicCheck, PeriodicCheckRecord
from app.models.workplace import Plant, Workplace
from app.schemas.periodic_checks import (
    PeriodicCheckCreateRequest,
    PeriodicCheckRecordCreateRequest,
    PeriodicCheckUpdateRequest,
)


def _add_months(d: date, months: int) -> date:
    month = d.month + months
    year = d.year + (month - 1) // 12
    month = ((month - 1) % 12) + 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(d.day, last_day)
    return date(year, month, day)


# ── PeriodicCheck CRUD ──────────────────────────────────────────────────────


async def list_checks(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    check_kind: str | None = None,
    status: str | None = None,
    plant_id: uuid.UUID | None = None,
) -> list[PeriodicCheck]:
    q = (
        select(PeriodicCheck)
        .where(PeriodicCheck.tenant_id == tenant_id)
        .order_by(PeriodicCheck.title)
    )
    if check_kind is not None:
        q = q.where(PeriodicCheck.check_kind == check_kind)
    if status is not None:
        q = q.where(PeriodicCheck.status == status)
    if plant_id is not None:
        q = q.where(PeriodicCheck.plant_id == plant_id)
    res = await db.execute(q)
    return list(res.scalars().all())


async def get_check(
    db: AsyncSession, check_id: uuid.UUID, tenant_id: uuid.UUID,
) -> PeriodicCheck | None:
    res = await db.execute(
        select(PeriodicCheck).where(
            PeriodicCheck.id == check_id,
            PeriodicCheck.tenant_id == tenant_id,
        )
    )
    return res.scalar_one_or_none()


async def create_check(
    db: AsyncSession,
    data: PeriodicCheckCreateRequest,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
) -> PeriodicCheck:
    if data.plant_id is not None:
        await assert_in_tenant(db, Plant, data.plant_id, tenant_id, field_name="plant_id")
    if data.workplace_id is not None:
        await assert_in_tenant(
            db, Workplace, data.workplace_id, tenant_id, field_name="workplace_id",
        )
    check = PeriodicCheck(
        tenant_id=tenant_id,
        created_by=created_by,
        **data.model_dump(),
    )
    db.add(check)
    await db.flush()
    return check


async def update_check(
    db: AsyncSession,
    check: PeriodicCheck,
    data: PeriodicCheckUpdateRequest,
) -> PeriodicCheck:
    payload = data.model_dump(exclude_unset=True)
    for k, v in payload.items():
        setattr(check, k, v)
    # Auto-recompute next_check_at po update
    if (
        check.last_checked_at is not None
        and check.valid_months is not None
        and "next_check_at" not in payload
    ):
        check.next_check_at = _add_months(check.last_checked_at, check.valid_months)
    await db.flush()
    return check


# ── Records ──────────────────────────────────────────────────────────────────


async def list_records(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    periodic_check_id: uuid.UUID,
) -> list[PeriodicCheckRecord]:
    res = await db.execute(
        select(PeriodicCheckRecord)
        .where(
            PeriodicCheckRecord.tenant_id == tenant_id,
            PeriodicCheckRecord.periodic_check_id == periodic_check_id,
        )
        .order_by(PeriodicCheckRecord.performed_at.desc())
    )
    return list(res.scalars().all())


async def create_record(
    db: AsyncSession,
    data: PeriodicCheckRecordCreateRequest,
    *,
    check: PeriodicCheck,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
) -> PeriodicCheckRecord:
    record = PeriodicCheckRecord(
        tenant_id=tenant_id,
        periodic_check_id=check.id,
        created_by=created_by,
        **data.model_dump(),
    )
    db.add(record)

    # Update parent: posun last_checked_at + recompute next_check_at
    check.last_checked_at = data.performed_at
    if check.valid_months is not None:
        check.next_check_at = _add_months(data.performed_at, check.valid_months)

    await db.flush()
    return record
