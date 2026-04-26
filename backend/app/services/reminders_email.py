"""
Sestavení a odeslání reminder emailu.

Strategie: ze všech nasbíraných reminder items per tenant složíme JEDEN email
per recipient. Email obsahuje sekci pro každý modul (Školení, Lékařské,
Akční plány) seřazenou podle kritičnosti.
"""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.email import EmailMessage, get_email_sender
from app.models.employee import Employee
from app.models.user import User
from app.services.platform_settings import get_setting
from app.services.reminders import ReminderItem, ReminderModule

MODULE_LABELS = {
    ReminderModule.TRAINING:           "Školení (BOZP/PO)",
    ReminderModule.MEDICAL_EXAM:       "Lékařské prohlídky",
    ReminderModule.ACCIDENT_FOLLOWUP:  "Akční plány úrazů",
}


def _format_days(days: int) -> str:
    if days < 0:
        return f"PO TERMÍNU o {abs(days)} dní"
    if days == 0:
        return "dnes"
    if days == 1:
        return "zítra"
    return f"za {days} dní"


def build_email_body(items: list[ReminderItem], tenant_name: str) -> tuple[str, str]:
    """
    Vrátí (subject, body_text) pro reminder email.
    Group by modul, sort by days_until ascending.
    """
    overdue_count = sum(1 for it in items if it.days_until < 0)
    upcoming_count = len(items) - overdue_count

    if overdue_count > 0:
        subject = (
            f"OZODigi: {overdue_count} po termínu, "
            f"{upcoming_count} blížící se ({tenant_name})"
        )
    else:
        subject = f"OZODigi: {upcoming_count} blížících se expirací ({tenant_name})"

    by_module: dict[ReminderModule, list[ReminderItem]] = defaultdict(list)
    for it in items:
        by_module[it.module].append(it)

    lines = [
        "Dobrý den,",
        "",
        f"níže je přehled blížících se nebo propadlých termínů pro {tenant_name}:",
        "",
    ]

    for module, label in MODULE_LABELS.items():
        module_items = by_module.get(module, [])
        if not module_items:
            continue
        lines.append(f"━━ {label} ({len(module_items)}) ━━")
        for it in module_items:
            line = (
                f"  • {it.person_name} — {it.title} "
                f"(splatnost {it.due_date.strftime('%d.%m.%Y')}, "
                f"{_format_days(it.days_until)})"
            )
            if it.detail:
                line += f"  [{it.detail}]"
            lines.append(line)
        lines.append("")

    lines.extend([
        "Pro správu otevři OZODigi:",
        "  https://app.bozoapp.cz",
        "",
        "—",
        "Tento email je generován automaticky systémem OZODigi.",
        "Nastavení reminderů: /admin/settings/reminders",
    ])

    return subject, "\n".join(lines)


async def collect_recipient_emails(
    db: AsyncSession,
    tenant_id: uuid.UUID,
) -> list[str]:
    """
    Vrátí emaily uživatelů kteří mají dostat reminder pro daný tenant.
    Filtruje podle reminders.send_to_managers / send_to_equipment_responsible.
    """
    send_managers = await get_setting(db, "reminders.send_to_managers", True)
    send_equipment = await get_setting(db, "reminders.send_to_equipment_responsible", True)

    target_roles: list[str] = []
    if send_managers:
        target_roles.extend(["ozo", "hr_manager"])
    if send_equipment:
        target_roles.append("equipment_responsible")

    if not target_roles:
        return []

    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))

    # Přímí users tenantu (např. vlastní OZO)
    stmt_users = (
        select(User.email)
        .where(User.tenant_id == tenant_id)
        .where(User.is_active.is_(True))
        .where(User.role.in_(target_roles))
        .where(User.email.is_not(None))
    )
    user_emails = list((await db.execute(stmt_users)).scalars().all())

    # Equipment responsible přes Employee → User (pokud má přiřazený auth account)
    if "equipment_responsible" in target_roles:
        stmt_emp = (
            select(Employee.email)
            .where(Employee.tenant_id == tenant_id)
            .where(Employee.status == "active")
            .where(Employee.email.is_not(None))
        )
        # Strategie: posílat všem zaměstnancům s rolí equipment_responsible
        # přes user_id → User. User.email už je v user_emails. Aby to bylo
        # robustní i pro zaměstnance bez auth účtu, můžeme přidat i email
        # přímo z Employee — to ale děláme jen pro managery v jiné cestě.
        # Pro v1 stačí users path.
        _ = stmt_emp  # pro budoucí rozšíření

    # Deduplikace
    return sorted(set(e for e in user_emails if e))


async def send_reminder_email(
    db: AsyncSession,
    *,
    recipient: str,
    tenant_name: str,
    items: list[ReminderItem],
) -> None:
    """Pošle JEDEN reminder email konkrétnímu příjemci."""
    if not items:
        return
    subject, body = build_email_body(items, tenant_name)
    await get_email_sender().send(EmailMessage(
        to=recipient, subject=subject, body_text=body,
    ))
