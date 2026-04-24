import re

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import RegisterRequest


def _slugify(name: str) -> str:
    """Převede název firmy na URL-friendly slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug[:100]


async def register_user(
    db: AsyncSession, data: RegisterRequest
) -> tuple[User, str, str]:
    """
    Vytvoří tenant + prvního uživatele (role=ozo).
    Vrátí (user, access_token, refresh_token).

    RLS bypass: při registraci ještě nemáme tenant_id, takže
    dočasně nastavíme superadmin flag aby INSERT prošel přes RLS.
    """
    await db.execute(
        text("SELECT set_config('app.is_superadmin', 'true', true)")
    )

    tenant = Tenant(name=data.tenant_name, slug=_slugify(data.tenant_name))
    db.add(tenant)
    await db.flush()  # Získáme tenant.id bez commitu

    user = User(
        tenant_id=tenant.id,
        email=data.email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        role="ozo",  # První uživatel v tenantu je vždy OZO
    )
    db.add(user)
    await db.flush()

    access_token = create_access_token(user.id, tenant.id, user.role)
    refresh_token = create_refresh_token(user.id, tenant.id)

    return user, access_token, refresh_token


async def login_user(
    db: AsyncSession, email: str, password: str
) -> tuple[User, str, str] | None:
    """
    Ověří přihlašovací údaje.
    Vrátí (user, access_token, refresh_token) nebo None.

    RLS bypass: hledáme uživatele podle emailu napříč tenanty,
    tenant_id ještě neznáme.
    """
    await db.execute(
        text("SELECT set_config('app.is_superadmin', 'true', true)")
    )

    result = await db.execute(
        select(User).where(User.email == email, User.is_active == True)  # noqa: E712
    )
    user = result.scalar_one_or_none()

    if user is None or not verify_password(password, user.hashed_password):
        return None

    access_token = create_access_token(user.id, user.tenant_id, user.role)
    refresh_token = create_refresh_token(user.id, user.tenant_id)

    return user, access_token, refresh_token
