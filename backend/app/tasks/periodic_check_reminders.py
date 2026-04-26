"""
Cron: připomínky pravidelných kontrol (sanační sady, záchytné vany, lékárničky).

Každý běh:
1. Načte prahy `reminders.thresholds.periodic_check` z platform_settings
   (default [30, 14, 7]).
2. Najde všechny aktivní `periodic_checks` napříč tenanty, kde
   `next_check_at` spadá do některého z prahů (incl. po termínu).
3. Pro každého tenanta agreguje seznam upozornění a pošle ho
   zodpovědným osobám provozovny (přes EmployeePlantResponsibility).

Idempotence:
- Není track-state per zaslaný reminder; cron běží pravidelně (např.
  pondělí 5:00) a pokaždé pošle aktuální stav. Recipient toleruje
  duplikáty díky agregovanému tělu emailu.

Spouštění:
    python -m app.tasks.periodic_check_reminders
"""
from __future__ import annotations

import asyncio
import logging
import sys
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.email import EmailMessage, get_email_sender
from app.models.employee import Employee
from app.models.periodic_check import PeriodicCheck
from app.models.revision import EmployeePlantResponsibility
from app.models.workplace import Plant
from app.services.platform_settings import get_setting

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("periodic_check_reminders")


CHECK_KIND_LABEL = {
    "sanitation_kit": "Sanační sada",
    "spill_tray":     "Záchytná vana",
    "first_aid_kit":  "Lékárnička",
}


def _format_due(days: int) -> str:
    if days < 0:
        return f"PO TERMÍNU o {abs(days)} dní"
    if days == 0:
        return "dnes"
    if days == 1:
        return "zítra"
    return f"za {days} dní"


def _build_email(
    tenant_name: str,
    plant_name: str,
    items: list[tuple[PeriodicCheck, int]],
) -> tuple[str, str]:
    n = len(items)
    overdue = sum(1 for _, d in items if d < 0)
    subject = (
        f"Pravidelné kontroly: {n} položek, {overdue} po termínu"
        f" — {plant_name}"
    )
    lines = [
        "Dobrý den,",
        "",
        f"přehled pravidelných kontrol pro provozovnu „{plant_name}“ "
        f"({tenant_name}), které vyžadují pozornost:",
        "",
    ]
    by_kind: dict[str, list[tuple[PeriodicCheck, int]]] = defaultdict(list)
    for c, d in items:
        by_kind[c.check_kind].append((c, d))
    for kind in sorted(by_kind):
        kind_items = by_kind[kind]
        lines.append(f"━━ {CHECK_KIND_LABEL.get(kind, kind)} ({len(kind_items)}) ━━")
        for c, days in sorted(kind_items, key=lambda x: x[0].next_check_at or datetime.max.date()):
            label_date = c.next_check_at.strftime("%d.%m.%Y") if c.next_check_at else "—"
            line = f"  • {c.title}"
            if c.location:
                line += f" ({c.location})"
            line += f" — {label_date} ({_format_due(days)})"
            lines.append(line)
        lines.append("")
    lines.extend([
        "Kontroly můžete provést a zaznamenat v aplikaci DigitalOZO →",
        "Pravidelné kontroly.",
        "",
        "—",
        "Tato zpráva je generována automaticky systémem DigitalOZO.",
    ])
    return subject, "\n".join(lines)


async def _process(db: AsyncSession) -> int:
    """Vrátí počet odeslaných emailů."""
    thresholds: list[int] = await get_setting(
        db, "reminders.thresholds.periodic_check", [30, 14, 7],
    )
    if not thresholds:
        log.info("No periodic_check thresholds configured")
        return 0
    horizon_days = max(thresholds)
    today = datetime.now(UTC).date()
    horizon = today + timedelta(days=horizon_days)

    res = await db.execute(
        select(PeriodicCheck).where(
            PeriodicCheck.status == "active",
            PeriodicCheck.next_check_at.is_not(None),
            PeriodicCheck.next_check_at <= horizon,
            PeriodicCheck.plant_id.is_not(None),
        )
    )
    due_checks: list[PeriodicCheck] = list(res.scalars().all())
    log.info("Found %d due periodic_checks across tenants", len(due_checks))
    if not due_checks:
        return 0

    # Group by (tenant_id, plant_id) → list[(PeriodicCheck, days_until)]
    grouped: dict[tuple[uuid.UUID, uuid.UUID], list[tuple[PeriodicCheck, int]]] = defaultdict(list)
    for c in due_checks:
        assert c.plant_id is not None and c.next_check_at is not None
        days = (c.next_check_at - today).days
        grouped[(c.tenant_id, c.plant_id)].append((c, days))

    sender = get_email_sender()
    sent = 0

    for (tenant_id, plant_id), items in grouped.items():
        plant = (await db.execute(
            select(Plant).where(Plant.id == plant_id)
        )).scalar_one_or_none()
        plant_name = plant.name if plant else "—"
        # Tenant name: jen pro display v emailu
        from app.models.tenant import Tenant
        tenant_row = (await db.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )).scalar_one_or_none()
        tenant_name = tenant_row.name if tenant_row else "—"

        recipients_res = await db.execute(
            select(Employee).join(
                EmployeePlantResponsibility,
                EmployeePlantResponsibility.employee_id == Employee.id,
            ).where(
                EmployeePlantResponsibility.tenant_id == tenant_id,
                EmployeePlantResponsibility.plant_id == plant_id,
                Employee.status == "active",
            )
        )
        recipients = [
            e.email for e in recipients_res.scalars() if e.email
        ]
        if not recipients:
            log.info(
                "No responsible employees with email for plant %s — skip",
                plant_id,
            )
            continue

        subject, body = _build_email(tenant_name, plant_name, items)
        for to in recipients:
            try:
                await sender.send(EmailMessage(
                    to=to, subject=subject, body_text=body,
                ))
                sent += 1
                log.info(
                    "Sent periodic_check reminder to %s (plant=%s, items=%d)",
                    to, plant_name, len(items),
                )
            except Exception:  # noqa: BLE001
                log.exception("Failed to send to %s", to)

    return sent


async def main() -> int:
    settings = get_settings()
    db_url = settings.migration_database_url or settings.database_url
    engine = create_async_engine(db_url, echo=False)
    async_session = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession,
    )
    async with async_session() as db, db.begin():
        await db.execute(
            text("SELECT set_config('app.is_platform_admin', 'true', true)")
        )
        sent = await _process(db)
    await engine.dispose()
    log.info("Done. %d emails sent.", sent)
    return sent


if __name__ == "__main__":
    sent = asyncio.run(main())
    sys.exit(0 if sent >= 0 else 1)
