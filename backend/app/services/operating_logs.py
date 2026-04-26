"""Service pro Provozní deníky."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.validation import assert_in_tenant
from app.models.operating_log import OperatingLogDevice, OperatingLogEntry
from app.models.workplace import Plant, Workplace
from app.schemas.operating_logs import (
    DeviceCreateRequest,
    DeviceUpdateRequest,
    EntryCreateRequest,
)


async def list_devices(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    category: str | None = None,
    status: str | None = None,
    plant_id: uuid.UUID | None = None,
) -> list[OperatingLogDevice]:
    q = (
        select(OperatingLogDevice)
        .where(OperatingLogDevice.tenant_id == tenant_id)
        .order_by(OperatingLogDevice.title)
    )
    if category:
        q = q.where(OperatingLogDevice.category == category)
    if status:
        q = q.where(OperatingLogDevice.status == status)
    if plant_id is not None:
        q = q.where(OperatingLogDevice.plant_id == plant_id)
    res = await db.execute(q)
    return list(res.scalars().all())


async def get_device(
    db: AsyncSession, device_id: uuid.UUID, tenant_id: uuid.UUID,
) -> OperatingLogDevice | None:
    res = await db.execute(
        select(OperatingLogDevice).where(
            OperatingLogDevice.id == device_id,
            OperatingLogDevice.tenant_id == tenant_id,
        )
    )
    return res.scalar_one_or_none()


async def create_device(
    db: AsyncSession,
    data: DeviceCreateRequest,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
) -> OperatingLogDevice:
    if data.plant_id is not None:
        await assert_in_tenant(db, Plant, data.plant_id, tenant_id, field_name="plant_id")
    if data.workplace_id is not None:
        await assert_in_tenant(
            db, Workplace, data.workplace_id, tenant_id, field_name="workplace_id",
        )
    device = OperatingLogDevice(
        tenant_id=tenant_id,
        created_by=created_by,
        **data.model_dump(),
    )
    db.add(device)
    await db.flush()
    return device


async def update_device(
    db: AsyncSession,
    device: OperatingLogDevice,
    data: DeviceUpdateRequest,
) -> OperatingLogDevice:
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(device, k, v)
    await db.flush()
    return device


async def list_entries(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    device_id: uuid.UUID,
    *,
    limit: int = 100,
) -> list[OperatingLogEntry]:
    res = await db.execute(
        select(OperatingLogEntry)
        .where(
            OperatingLogEntry.tenant_id == tenant_id,
            OperatingLogEntry.device_id == device_id,
        )
        .order_by(OperatingLogEntry.performed_at.desc())
        .limit(limit)
    )
    return list(res.scalars().all())


async def create_entry(
    db: AsyncSession,
    data: EntryCreateRequest,
    *,
    device: OperatingLogDevice,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
) -> OperatingLogEntry:
    # Validace: capable_items délka musí odpovídat device.check_items
    if len(data.capable_items) != len(device.check_items):
        raise ValueError(
            f"capable_items má délku {len(data.capable_items)}, "
            f"očekáváno {len(device.check_items)} (dle definovaných kontrolních úkonů)"
        )
    entry = OperatingLogEntry(
        tenant_id=tenant_id,
        device_id=device.id,
        created_by=created_by,
        **data.model_dump(),
    )
    db.add(entry)
    await db.flush()
    return entry
