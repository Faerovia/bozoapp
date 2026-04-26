"""
CLI: vytvoří platform admin uživatele (is_platform_admin=True, role='admin').

Platform admin má cross-tenant přístup a může vytvářet tenanty přes
POST /api/v1/admin/tenants. Prvního admin musíš vytvořit tímto skriptem —
přes API to nejde (chicken-and-egg).

Usage:
    # Interaktivně
    docker compose exec backend python -m app.commands.create_platform_admin

    # Neinteraktivně (heslo z env)
    docker compose exec \\
      -e ADMIN_EMAIL=admin@bozoapp.cz \\
      -e ADMIN_PASSWORD='...' \\
      -e ADMIN_TENANT_NAME='DigitalOZO Internal' \\
      backend \\
      python -m app.commands.create_platform_admin --non-interactive

Skript:
1. Vytvoří (pokud neexistuje) servisní tenant — všichni platform admins
   technicky žijí v jednom "service" tenantu aby RLS FK constrainty fungovaly.
2. Vytvoří/aktualizuje admin uživatele s is_platform_admin=True, role='admin'.
3. Vypíše user_id — pro záznam do password manageru.
"""
import argparse
import asyncio
import os
import sys
from getpass import getpass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.security import hash_password
from app.models.tenant import Tenant
from app.models.user import User

SERVICE_TENANT_NAME = "DigitalOZO Platform"
SERVICE_TENANT_SLUG = "bozoapp-platform"


async def _ensure_service_tenant(db: AsyncSession) -> Tenant:
    """Servisní tenant = kontejner pro všechny platform admins."""
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))
    existing = (await db.execute(
        select(Tenant).where(Tenant.slug == SERVICE_TENANT_SLUG)
    )).scalar_one_or_none()
    if existing is not None:
        return existing
    t = Tenant(name=SERVICE_TENANT_NAME, slug=SERVICE_TENANT_SLUG)
    db.add(t)
    await db.flush()
    return t


async def _upsert_admin(
    db: AsyncSession,
    tenant: Tenant,
    *,
    email: str,
    password: str,
    full_name: str | None = None,
) -> User:
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))

    existing = (await db.execute(
        select(User).where(User.email == email)
    )).scalar_one_or_none()

    if existing is not None:
        existing.hashed_password = hash_password(password)
        existing.role = "admin"
        existing.is_platform_admin = True
        existing.is_active = True
        if full_name:
            existing.full_name = full_name
        await db.flush()
        return existing

    user = User(
        tenant_id=tenant.id,
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
        role="admin",
        is_platform_admin=True,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


async def run(email: str, password: str, full_name: str | None) -> None:
    settings = get_settings()
    # Pro CLI jedeme přes MIGRATION_DATABASE_URL (owner), pokud je k dispozici;
    # jinak fallback na DATABASE_URL. Owner má RLS bypass pro FORCE ROW LEVEL
    # SECURITY → bootstrap ze začátku je jednodušší.
    url = settings.migration_database_url or settings.database_url
    engine = create_async_engine(url, pool_pre_ping=True)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_maker() as db:
            tenant = await _ensure_service_tenant(db)
            user = await _upsert_admin(
                db, tenant, email=email, password=password, full_name=full_name
            )
            await db.commit()
            print("OK: platform admin created/updated")
            print(f"   tenant_id:     {tenant.id}")
            print(f"   user_id:       {user.id}")
            print(f"   email:         {user.email}")
            print(f"   role:          {user.role}")
            print(f"   is_platform_admin: {user.is_platform_admin}")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--non-interactive", action="store_true")
    parser.add_argument("--email")
    parser.add_argument("--full-name")
    args = parser.parse_args()

    if args.non_interactive or os.environ.get("ADMIN_EMAIL"):
        email = args.email or os.environ.get("ADMIN_EMAIL")
        password = os.environ.get("ADMIN_PASSWORD")
        full_name = args.full_name or os.environ.get("ADMIN_FULL_NAME")
        if not email or not password:
            print(
                "ERROR: --email a ADMIN_PASSWORD env jsou povinné v non-interactive",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        email = input("Admin email: ").strip()
        full_name = input("Full name (optional): ").strip() or None
        password = getpass("Password: ")
        confirm = getpass("Confirm password: ")
        if password != confirm:
            print("ERROR: hesla se neshodují", file=sys.stderr)
            sys.exit(1)

    if len(password) < 12:
        print("ERROR: heslo musí mít min 12 znaků pro platform admin", file=sys.stderr)
        sys.exit(1)

    asyncio.run(run(email, password, full_name))


if __name__ == "__main__":
    main()
