"""
CLI skript pro vytvoření platform admin účtu.

Použití (uvnitř docker compose):
    docker compose exec backend python -m scripts.create_platform_admin \\
        --username admin --password admin

Bez argumentů → username=admin, password=admin (DEV ONLY).
V produkci nutno změnit heslo přes admin UI nebo druhým spuštěním
s --password=NEW.

Idempotentní: pokud user s daným username existuje, jen aktualizuje heslo.
"""

import argparse
import asyncio
import sys
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.security import hash_password
from app.models.tenant import Tenant
from app.models.user import User


async def ensure_platform_admin(username: str, password: str) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async with session_maker() as session:
        # Bypass RLS — admin nemá tenant_id v běžném smyslu
        await session.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))

        # 1) Existuje user s tímto username?
        user = (await session.execute(
            select(User).where(User.username == username)
        )).scalar_one_or_none()

        if user is not None:
            user.hashed_password = hash_password(password)
            user.is_platform_admin = True
            user.is_active = True
            await session.commit()
            print(f"OK — heslo platform admina '{username}' aktualizováno.")
            await engine.dispose()
            return

        # 2) Nový admin → potřebuje tenant_id (NOT NULL constraint).
        #    Použijeme/vytvoříme systémový "platform" tenant.
        platform_tenant = (await session.execute(
            select(Tenant).where(Tenant.name == "__PLATFORM__")
        )).scalar_one_or_none()
        if platform_tenant is None:
            platform_tenant = Tenant(
                id=uuid.uuid4(),
                name="__PLATFORM__",
                slug="__platform__",
            )
            session.add(platform_tenant)
            await session.flush()

        admin = User(
            id=uuid.uuid4(),
            tenant_id=platform_tenant.id,
            username=username,
            email=f"{username}@platform.local",
            hashed_password=hash_password(password),
            full_name="Platform Admin",
            role="admin",
            is_platform_admin=True,
            is_active=True,
        )
        session.add(admin)
        await session.commit()
        print(f"OK — platform admin '{username}' vytvořen.")
        print(f"   ID: {admin.id}")
        print(f"   Heslo: {password}")

    await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Vytvoří/aktualizuje platform admin účet.")
    parser.add_argument("--username", default="admin", help="Username pro login (default: admin)")
    parser.add_argument("--password", default="admin", help="Heslo (default: admin)")
    args = parser.parse_args()

    asyncio.run(ensure_platform_admin(args.username, args.password))
    return 0


if __name__ == "__main__":
    sys.exit(main())
