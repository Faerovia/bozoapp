"""
Weekly reminder cron — projde všechny aktivní tenanty a pošle agregované
emaily o blížících se expiracích (školení, lékařské prohlídky, úrazy).

Spouštění:
    python -m app.tasks.weekly_reminders

Default schedule: pondělí 5:00 (cron: `0 5 * * MON`). Konkrétní schedule
nastavuje admin v platform_settings a vlastním systemd timerem / crontab
záznamem na hostiteli.

Master switch `reminders.enabled` umožňuje globální vypnutí bez úpravy cronu.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import UTC, date, datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models.tenant import Tenant
from app.services.platform_settings import get_setting, set_setting
from app.services.reminders import collect_all_reminders_for_tenant
from app.services.reminders_email import (
    collect_recipient_emails,
    send_reminder_email,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("weekly_reminders")


async def run_reminders(today: date | None = None) -> dict[str, int]:
    """
    Hlavní entry point. Vrátí stats {tenants_processed, emails_sent, items_total}.
    """
    today = today or date.today()
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    stats = {"tenants_processed": 0, "emails_sent": 0, "items_total": 0}

    async with session_maker() as db:
        async with db.begin():
            await db.execute(
                text("SELECT set_config('app.is_superadmin', 'true', true)")
            )

            enabled = await get_setting(db, "reminders.enabled", True)
            if not enabled:
                log.info("Reminders disabled (reminders.enabled=false). Skipping.")
                await engine.dispose()
                return stats

            tenants = (await db.execute(
                select(Tenant)
                .where(Tenant.is_active.is_(True))
                .where(Tenant.name != "__PLATFORM__")
            )).scalars().all()

            for tenant in tenants:
                items = await collect_all_reminders_for_tenant(
                    db, tenant.id, today=today,
                )
                if not items:
                    log.info("Tenant %s — žádné expirace", tenant.name)
                    continue

                recipients = await collect_recipient_emails(db, tenant.id)
                if not recipients:
                    log.warning(
                        "Tenant %s — %d expirací, ale žádný příjemce",
                        tenant.name, len(items),
                    )
                    continue

                log.info(
                    "Tenant %s — %d expirací → %d příjemců",
                    tenant.name, len(items), len(recipients),
                )
                for r in recipients:
                    try:
                        await send_reminder_email(
                            db, recipient=r,
                            tenant_name=tenant.name, items=items,
                        )
                        stats["emails_sent"] += 1
                    except Exception:
                        log.exception(
                            "Reminder send failed (tenant=%s, to=%s)",
                            tenant.name, r,
                        )
                stats["items_total"] += len(items)
                stats["tenants_processed"] += 1

            # Aktualizuj last_run_at
            await set_setting(
                db, "reminders.last_run_at",
                datetime.now(UTC).isoformat(),
            )

    await engine.dispose()
    log.info(
        "Done. tenants=%d emails=%d items=%d",
        stats["tenants_processed"], stats["emails_sent"], stats["items_total"],
    )
    return stats


if __name__ == "__main__":
    asyncio.run(run_reminders())
    sys.exit(0)
