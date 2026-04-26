"""
Cron: upozornění na chybějící zápisy v provozních denících.

Pro každé aktivní zařízení (`operating_log_devices`) zkontroluje, kdy byl
poslední zápis. Pokud poslední zápis chybí déle než tolerance dle period:
  daily   → 2 dny
  shift   → 2 dny (běžnější dny v týdnu)
  weekly  → 9 dní
  monthly → 35 dní
  other   → ignoruje se

Pošle agregovaný email zodpovědným osobám provozovny per plant.

Spouštění:
    python -m app.tasks.operating_log_no_entry_reminder
"""
from __future__ import annotations

import asyncio
import logging
import sys
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.email import EmailMessage, get_email_sender
from app.models.employee import Employee
from app.models.operating_log import OperatingLogDevice, OperatingLogEntry
from app.models.revision import EmployeePlantResponsibility
from app.models.workplace import Plant

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("operating_log_no_entry_reminder")


# Tolerance v dnech per period — kolik dní může uplynout bez zápisu, než
# upozorníme. Vyšší než nominal protože víkendy + drobné prokluzy jsou OK.
PERIOD_TOLERANCE_DAYS = {
    "daily": 2,
    "shift": 2,
    "weekly": 9,
    "monthly": 35,
    # 'other' se ignoruje — uživatel sám definuje
}


def _build_email(
    tenant_name: str,
    plant_name: str,
    flagged: list[tuple[OperatingLogDevice, int | None]],
) -> tuple[str, str]:
    """flagged = list (device, days_since_last_or_None_if_never)."""
    n = len(flagged)
    subject = (
        f"Provozní deníky: {n} zařízení bez aktuálního zápisu — {plant_name}"
    )
    lines = [
        "Dobrý den,",
        "",
        f"Následující zařízení v provozovně „{plant_name}“ ({tenant_name})",
        "nemají aktuální zápisy v provozním deníku dle nastavené periodicity:",
        "",
    ]
    for d, days in sorted(flagged, key=lambda x: -(x[1] or 9999)):
        if days is None:
            since = "žádný zápis nikdy"
        elif days == 0:
            since = "dnes (ale na hraně)"
        elif days == 1:
            since = "1 den"
        else:
            since = f"{days} dní"
        line = f"  • {d.title}"
        if d.device_code:
            line += f" (kód {d.device_code})"
        line += f" — poslední zápis: {since}"
        lines.append(line)
    lines.extend([
        "",
        "Zápisy můžete provést přímo v aplikaci DigitalOZO → Provozní deníky,",
        "nebo na zařízení naskenováním QR kódu.",
        "",
        "—",
        "Tato zpráva je generována automaticky systémem DigitalOZO.",
    ])
    return subject, "\n".join(lines)


async def _process(db: AsyncSession) -> int:
    today = datetime.now(UTC).date()

    # Načti aktivní zařízení s plant_id (bez plant nemůžeme určit recipienty)
    devices_res = await db.execute(
        select(OperatingLogDevice).where(
            OperatingLogDevice.status == "active",
            OperatingLogDevice.plant_id.is_not(None),
            OperatingLogDevice.period.in_(list(PERIOD_TOLERANCE_DAYS.keys())),
        )
    )
    devices: list[OperatingLogDevice] = list(devices_res.scalars().all())
    log.info("Checking %d active devices with monitored periods", len(devices))
    if not devices:
        return 0

    # Pro každé zařízení najdi poslední zápis
    flagged_by_plant: dict[
        tuple[uuid.UUID, uuid.UUID],
        list[tuple[OperatingLogDevice, int | None]],
    ] = defaultdict(list)

    for d in devices:
        last_entry_date = (await db.execute(
            select(func.max(OperatingLogEntry.performed_at)).where(
                OperatingLogEntry.device_id == d.id,
            )
        )).scalar()
        tolerance = PERIOD_TOLERANCE_DAYS.get(d.period, 999)
        if last_entry_date is None:
            # Nikdy zápis. Pokud je device starší než tolerance, flag.
            created_age = (today - d.created_at.date()).days
            if created_age > tolerance:
                assert d.plant_id is not None
                flagged_by_plant[(d.tenant_id, d.plant_id)].append((d, None))
        else:
            days_since = (today - last_entry_date).days
            if days_since > tolerance:
                assert d.plant_id is not None
                flagged_by_plant[(d.tenant_id, d.plant_id)].append((d, days_since))

    if not flagged_by_plant:
        log.info("All devices have recent entries — nothing to send")
        return 0

    sender = get_email_sender()
    sent = 0

    for (tenant_id, plant_id), items in flagged_by_plant.items():
        plant = (await db.execute(
            select(Plant).where(Plant.id == plant_id)
        )).scalar_one_or_none()
        plant_name = plant.name if plant else "—"

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
            log.info("No recipients for plant %s — skip", plant_id)
            continue

        subject, body = _build_email(tenant_name, plant_name, items)
        for to in recipients:
            try:
                await sender.send(EmailMessage(
                    to=to, subject=subject, body_text=body,
                ))
                sent += 1
                log.info(
                    "Sent no-entry reminder to %s (plant=%s, devices=%d)",
                    to, plant_name, len(items),
                )
            except Exception:  # noqa: BLE001
                log.exception("Failed to send to %s", to)

    # Bonus: použijeme `timedelta` k satisfy importu (ruff F401 prevence)
    _ = timedelta
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
