"""
Služby pro M:N user × tenant memberships (OZO multi-client).
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.membership import UserTenantMembership
from app.models.tenant import Tenant


async def get_user_memberships(
    db: AsyncSession, user_id: uuid.UUID
) -> list[dict[str, Any]]:
    """
    Vrátí list memberships pro uživatele s JOIN tenant.name.
    Pozn.: Tabulka memberships nemá RLS — přečteme cross-tenant; ochranu
    zajišťuje filter user_id = caller's user_id.
    """
    result = await db.execute(
        select(UserTenantMembership, Tenant)
        .join(Tenant, UserTenantMembership.tenant_id == Tenant.id)
        .where(UserTenantMembership.user_id == user_id)
        .order_by(
            UserTenantMembership.is_default.desc(),
            Tenant.name,
        )
    )
    rows = []
    for membership, tenant in result.all():
        rows.append({
            "tenant_id": membership.tenant_id,
            "tenant_name": tenant.name,
            "role": membership.role,
            "is_default": membership.is_default,
        })
    return rows


async def has_membership(
    db: AsyncSession, user_id: uuid.UUID, tenant_id: uuid.UUID
) -> UserTenantMembership | None:
    """Vrátí membership pokud user patří do tenantu, jinak None."""
    res = await db.execute(
        select(UserTenantMembership).where(
            UserTenantMembership.user_id == user_id,
            UserTenantMembership.tenant_id == tenant_id,
        )
    )
    return res.scalar_one_or_none()


async def add_membership(
    db: AsyncSession,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    role: str,
    is_default: bool = False,
) -> UserTenantMembership:
    """Vytvoří novou membership. Pokud už existuje, vrátí ji (idempotentní)."""
    existing = await has_membership(db, user_id, tenant_id)
    if existing is not None:
        return existing

    membership = UserTenantMembership(
        user_id=user_id,
        tenant_id=tenant_id,
        role=role,
        is_default=is_default,
    )
    db.add(membership)
    await db.flush()
    return membership


async def get_default_membership(
    db: AsyncSession, user_id: uuid.UUID
) -> UserTenantMembership | None:
    """Vrátí membership s is_default=True. Pokud žádná, vrátí první (pokud existuje)."""
    res = await db.execute(
        select(UserTenantMembership)
        .where(UserTenantMembership.user_id == user_id)
        .order_by(UserTenantMembership.is_default.desc())
    )
    return res.scalars().first()
