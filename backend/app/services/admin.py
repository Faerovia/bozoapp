"""
Platform-admin služby pro správu tenantů.

Hlavní operace:
- `create_tenant_with_ozo(...)` — vytvoří nový tenant + prvního OZO usera se
  random heslem; spustí password-reset flow aby OZO dostal email se setup
  linkem (→ nastaví si heslo sám).
- `list_tenants(...)` — seznam všech tenantů (jen admin).
- `update_tenant(...)` — pozastavit / aktivovat tenant, změnit plán.

Platform admin má cross-tenant přístup přes `app.is_platform_admin` (nastaveno
v dependencies.get_current_user). Všechny DB dotazy v tomto modulu mohou
opouštět tenant boundary — to je záměr.
"""
from __future__ import annotations

import re
import secrets as pysecrets
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.membership import UserTenantMembership
from app.models.tenant import Tenant
from app.models.user import User
from app.services.password_reset import request_reset


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug[:100]


async def create_tenant_with_ozo(
    db: AsyncSession,
    *,
    tenant_name: str,
    ozo_email: str,
    ozo_full_name: str | None = None,
    external_login_enabled: bool = False,
    reset_url_template: str = "https://app.bozoapp.cz/reset-password?token={token}",
) -> tuple[Tenant, User]:
    """
    Vytvoří nový tenant + OZO uživatele. Pokud OZO s daným emailem už
    existuje (typicky multi-client OZO), pouze přidá novou membership
    (NEvytváří nového usera ani neposílá password reset).

    `external_login_enabled` — pokud True, klientův HR/admin se může
    zaregistrovat do tenantu. Default False (OZO-only tenant).
    """
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))

    tenant = Tenant(
        name=tenant_name,
        slug=_slugify(tenant_name),
        external_login_enabled=external_login_enabled,
    )
    db.add(tenant)
    await db.flush()

    # Pokud OZO už v systému existuje (multi-client) — jen přidáme membership.
    existing = (await db.execute(
        select(User).where(User.email == ozo_email)
    )).scalar_one_or_none()

    if existing is not None:
        membership = UserTenantMembership(
            user_id=existing.id,
            tenant_id=tenant.id,
            role="ozo",
            is_default=False,
        )
        db.add(membership)
        await db.flush()
        return tenant, existing

    # Nový OZO — vytvoříme usera + reset email + membership na nový tenant
    random_pwd = pysecrets.token_urlsafe(32)
    user = User(
        tenant_id=tenant.id,
        email=ozo_email,
        hashed_password=hash_password(random_pwd),
        full_name=ozo_full_name,
        role="ozo",
        is_active=True,
    )
    db.add(user)
    await db.flush()

    # Membership pro nového usera — is_default=True (jediný klient)
    membership = UserTenantMembership(
        user_id=user.id,
        tenant_id=tenant.id,
        role="ozo",
        is_default=True,
    )
    db.add(membership)
    await db.flush()

    await request_reset(
        db, ozo_email, request_ip=None, reset_url_template=reset_url_template
    )

    return tenant, user


async def list_tenants(db: AsyncSession) -> list[Tenant]:
    """Všechny tenanty (bez filtrování). Platform admin only."""
    await db.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
    result = await db.execute(select(Tenant).order_by(Tenant.created_at.desc()))
    return list(result.scalars().all())


async def get_tenant_by_id(db: AsyncSession, tenant_id: uuid.UUID) -> Tenant | None:
    await db.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    return result.scalar_one_or_none()


async def set_tenant_active(
    db: AsyncSession, tenant_id: uuid.UUID, active: bool
) -> Tenant | None:
    """Pozastavení (suspend) / reaktivace tenantu."""
    tenant = await get_tenant_by_id(db, tenant_id)
    if tenant is None:
        return None
    tenant.is_active = active
    await db.flush()
    return tenant
