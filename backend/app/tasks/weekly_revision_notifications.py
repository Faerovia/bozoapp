"""
Týdenní notifikace blížících se revizí.

Spouští se každý pondělí v 5:00 (systemd timer / cron). Projde všechna aktivní
zařízení (Revision.status='active') všech tenantů a u každého, jehož
next_revision_at je do 30 dní nebo překročen, sestaví notifikaci. Notifikace
jde e-mailem všem zaměstnancům s aktivním EmployeePlantResponsibility
na odpovídající provozovnu, agregovaně (jeden e-mail per zaměstnanec).

Spouštění:
    python -m app.tasks.weekly_revision_notifications

V Docker Compose lze napojit přes samostatnou službu s `restart: no`
a systemd timer, nebo přes docker-swarm cron, nebo jako entry v crontabu
hostitele.

Pozn.: Všechny DB dotazy jdou mimo request kontext, proto musí ručně
nastavit RLS bypass (`app.is_platform_admin='true'`), jinak by narazily
na RLS policy. Alternativa: iterovat per-tenant a nastavit
`app.current_tenant_id` — zvolili jsme platform-level bypass pro jednoduchost.
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
from app.models.revision import EmployeePlantResponsibility, Revision
from app.models.workplace import Plant

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("weekly_revision_notifications")


DUE_HORIZON_DAYS = 30


def _format_due(days: int) -> str:
    if days < 0:
        return f"PO TERMÍNU o {abs(days)} dní"
    if days == 0:
        return "dnes"
    if days == 1:
        return "zítra"
    return f"za {days} dní"


def _build_email_body(
    employee: Employee,
    plant_name: str,
    revisions: list[tuple[Revision, int]],
) -> tuple[str, str]:
    """Vrátí (subject, body_text)."""
    count = len(revisions)
    subject = f"Blížící se revize zařízení — {plant_name} ({count})"

    lines = [
        f"Dobrý den {employee.first_name} {employee.last_name},",
        "",
        f"posíláme přehled zařízení v provozovně '{plant_name}', kterým se blíží",
        "termín revize (do 30 dní) nebo jsou po termínu:",
        "",
    ]
    for rev, days in sorted(revisions, key=lambda r: r[0].next_revision_at or datetime.max.date()):
        due_label = _format_due(days)
        date_str = rev.next_revision_at.isoformat() if rev.next_revision_at else "—"
        device_code = f" ({rev.device_code})" if rev.device_code else ""
        lines.append(f"  • {rev.title}{device_code} — {date_str} ({due_label})")

    lines.extend([
        "",
        "Detail revizí a zaznamenání provedené kontroly najdete v aplikaci OZODigi.",
        "",
        "Tato zpráva je automatická — v případě dotazů kontaktujte OZO ve firmě.",
    ])
    body = "\n".join(lines)
    return subject, body


async def _collect_and_send(db: AsyncSession) -> int:
    """Projde revize napříč všemi tenanty, agreguje per employee, odešle emaily.

    Vrátí počet odeslaných zpráv.
    """
    today = datetime.now(UTC).date()
    horizon = today + timedelta(days=DUE_HORIZON_DAYS)

    # 1) Najdi všechna aktivní zařízení blížící se nebo po termínu
    result = await db.execute(
        select(Revision).where(
            Revision.status == "active",
            Revision.next_revision_at.is_not(None),
            Revision.next_revision_at <= horizon,
            Revision.plant_id.is_not(None),
        )
    )
    due_revisions: list[Revision] = list(result.scalars().all())
    log.info("Found %d due/overdue revisions across all tenants", len(due_revisions))

    if not due_revisions:
        return 0

    # 2) Pro každou získej odpovědné zaměstnance přes M:N
    # Grouping key: (employee.id, plant_id) → list[Revision]
    per_employee_plant: dict[tuple[uuid.UUID, uuid.UUID], list[Revision]] = defaultdict(list)

    for rev in due_revisions:
        assert rev.plant_id is not None  # filter above
        resp_result = await db.execute(
            select(Employee)
            .join(
                EmployeePlantResponsibility,
                EmployeePlantResponsibility.employee_id == Employee.id,
            )
            .where(
                EmployeePlantResponsibility.tenant_id == rev.tenant_id,
                EmployeePlantResponsibility.plant_id == rev.plant_id,
                Employee.status == "active",
            )
        )
        for employee in resp_result.scalars():
            if not employee.email:
                continue
            key = (employee.id, rev.plant_id)
            per_employee_plant[key].append(rev)

    if not per_employee_plant:
        log.info("No responsible employees with email for any due revision")
        return 0

    # 3) Vytvoř maps pro rychlý lookup
    plant_ids = {p for _, p in per_employee_plant}
    plant_names: dict[uuid.UUID, str] = {}
    for pid in plant_ids:
        name = (await db.execute(
            select(Plant.name).where(Plant.id == pid)
        )).scalar_one_or_none()
        plant_names[pid] = name or "Neznámá provozovna"

    employee_ids = {eid for eid, _ in per_employee_plant}
    employees_map: dict[uuid.UUID, Employee] = {}
    for eid in employee_ids:
        emp = (await db.execute(
            select(Employee).where(Employee.id == eid)
        )).scalar_one_or_none()
        if emp is not None:
            employees_map[eid] = emp

    # 4) Odešli emaily
    sender = get_email_sender()
    sent_count = 0

    for (employee_id, plant_id), revisions in per_employee_plant.items():
        emp_obj = employees_map.get(employee_id)
        if emp_obj is None or not emp_obj.email:
            continue

        pairs = [(r, (r.next_revision_at - today).days if r.next_revision_at else 999)
                 for r in revisions]
        subject, body = _build_email_body(emp_obj, plant_names[plant_id], pairs)

        try:
            await sender.send(EmailMessage(
                to=emp_obj.email,
                subject=subject,
                body_text=body,
            ))
            sent_count += 1
            log.info("Sent notification to %s (%d revisions, plant=%s)",
                     emp_obj.email, len(revisions), plant_names[plant_id])
        except Exception:  # noqa: BLE001
            log.exception("Failed to send notification to %s", emp_obj.email)

    return sent_count


async def main() -> int:
    settings = get_settings()
    # Použij owner DB URL (bozoapp) místo app URL (bozoapp_app), abychom
    # mohli nastavit session-level settings bypass.
    db_url = settings.migration_database_url or settings.database_url
    engine = create_async_engine(db_url, echo=False)

    async_session = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )

    async with async_session() as db:
        # RLS bypass — background task nemá tenant kontext, vidí všechny
        # tenanty. SET LOCAL vyžaduje otevřenou transakci; session.begin()
        # ji zaručí. GUC se pak propaguje do dalších queries v téže session.
        async with db.begin():
            await db.execute(
                text("SELECT set_config('app.is_platform_admin', 'true', true)")
            )
            sent = await _collect_and_send(db)

    await engine.dispose()
    log.info("Done. %d notifications sent.", sent)
    return sent


if __name__ == "__main__":
    sent = asyncio.run(main())
    sys.exit(0 if sent >= 0 else 1)
