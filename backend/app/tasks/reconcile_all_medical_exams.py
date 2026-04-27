"""One-shot CLI: spustí reconcile lékařských prohlídek pro všechny pozice
napříč všemi tenanty.

Použití:
    docker compose exec backend python -m app.tasks.reconcile_all_medical_exams

Účel: po změně logiky (např. cat 1 = bez odborných) sjednotit existující
data v DB. Bez tohoto skriptu by stará pending odborná prohlídka zůstala
viset, dokud OZO ručně neudělá další update na RFA / pozici.

Idempotentní — opakované spuštění nemá vliv (reconcile je sám idempotentní).
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select, text

from app.core.database import AsyncSessionLocal
from app.models.job_position import JobPosition
from app.models.membership import UserTenantMembership
from app.models.tenant import Tenant
from app.models.user import User
from app.services.medical_exams import (
    reconcile_exams_for_employees_on_position,
)

log = logging.getLogger("reconcile_all")


async def _enable_superadmin(db) -> None:  # type: ignore[no-untyped-def]
    """RLS bypass — `set_config(..., true)` je transakční, takže ho voláme
    před každou novou transakcí."""
    await db.execute(
        text("SELECT set_config('app.is_superadmin', 'true', false)"),
    )


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    async with AsyncSessionLocal() as db:
        await _enable_superadmin(db)

        tenants = (await db.execute(
            select(Tenant).where(Tenant.name != "__PLATFORM__"),
        )).scalars().all()

        total_archived = 0
        total_created = 0
        total_employees: set[str] = set()

        for tenant in tenants:
            # Actor pro audit: 1) přímý User.tenant_id, 2) přes membership
            # (OZO multi-client), 3) platform admin jako fallback.
            actor = (await db.execute(
                select(User).where(
                    User.tenant_id == tenant.id,
                    User.is_active.is_(True),
                ).limit(1),
            )).scalar_one_or_none()
            if actor is None:
                actor = (await db.execute(
                    select(User)
                    .join(UserTenantMembership, UserTenantMembership.user_id == User.id)
                    .where(
                        UserTenantMembership.tenant_id == tenant.id,
                        User.is_active.is_(True),
                    )
                    .limit(1),
                )).scalar_one_or_none()
            if actor is None:
                actor = (await db.execute(
                    select(User).where(
                        User.is_platform_admin.is_(True),
                        User.is_active.is_(True),
                    ).limit(1),
                )).scalar_one_or_none()
            if actor is None:
                log.warning(
                    "Tenant %s (%s) — žádný použitelný actor user, přeskakuju",
                    tenant.slug, tenant.name,
                )
                continue

            positions = (await db.execute(
                select(JobPosition).where(
                    JobPosition.tenant_id == tenant.id,
                    JobPosition.status == "active",
                ),
            )).scalars().all()

            tenant_archived = 0
            tenant_created = 0
            for pos in positions:
                result = await reconcile_exams_for_employees_on_position(
                    db,
                    job_position_id=pos.id,
                    tenant_id=tenant.id,
                    created_by=actor.id,
                )
                tenant_archived += int(result.get("archived", 0))
                tenant_created += int(result.get("created", 0))
                for eid in result.get("affected_employees", []):
                    total_employees.add(str(eid))

            await db.commit()
            # Po commit() je session-wide setting OK (false=is_local), ale pro
            # jistotu ho znovu nastavíme — některé pool drivery resetují.
            await _enable_superadmin(db)

            log.info(
                "Tenant %s (%s): pozic=%d, archived=%d, created=%d",
                tenant.slug, tenant.name, len(positions),
                tenant_archived, tenant_created,
            )
            total_archived += tenant_archived
            total_created += tenant_created

        log.info("=" * 60)
        log.info(
            "CELKEM: archived=%d, created=%d, affected_employees=%d",
            total_archived, total_created, len(total_employees),
        )


if __name__ == "__main__":
    asyncio.run(main())
