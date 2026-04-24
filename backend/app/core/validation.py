"""
Sdílené validační helpery pro services vrstvu.

Primární účel: obrana proti cross-tenant FK injection. Když API přijímá
foreign key (employee_id, risk_id, job_position_id, ...), app musí
ověřit, že FK patří do tenantu uživatele — jinak útočník z tenantu A
může vytvořit záznam odkazující na entitu z tenantu B.

RLS tuto třídu útoků přímo nechytí, protože FK integrity check v PG
probíhá mimo policy kontext (čte skrz RLS).
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from sqlalchemy.orm import DeclarativeBase


async def assert_in_tenant(
    db: AsyncSession,
    model: type["DeclarativeBase"],
    entity_id: uuid.UUID,
    tenant_id: uuid.UUID,
    *,
    field_name: str = "id",
) -> None:
    """
    Ověří, že řádek modelu s daným id patří do tenantu. Jinak 422.

    Usage:
        await assert_in_tenant(db, Employee, data.employee_id, tenant_id,
                               field_name="employee_id")
    """
    # Každý tenantovaný model musí mít .id a .tenant_id — runtime kontrola
    # by stála za to, ale v praxi models/* mají konzistentní strukturu.
    stmt = select(model.id).where(  # type: ignore[attr-defined]
        model.id == entity_id,  # type: ignore[attr-defined]
        model.tenant_id == tenant_id,  # type: ignore[attr-defined]
    )
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{field_name} neexistuje v tomto tenantu",
        )
