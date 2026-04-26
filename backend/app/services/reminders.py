"""
Sběr expirujících záznamů pro email reminders.

Funkce vrací list `ReminderItem` objektů — sjednocená struktura napříč moduly,
takže email rendering nemusí znát detaily Training/MedicalExam/AccidentAction.

Používá platform_settings pro konfiguraci prahů (30/14/7 dnů default).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accident_action import AccidentActionItem
from app.models.accident_report import AccidentReport
from app.models.employee import Employee
from app.models.medical_exam import MedicalExam
from app.models.training import Training, TrainingAssignment
from app.services.platform_settings import get_setting


class ReminderModule(StrEnum):
    TRAINING = "training"
    MEDICAL_EXAM = "medical_exam"
    ACCIDENT_FOLLOWUP = "accident_followup"


@dataclass
class ReminderItem:
    module: ReminderModule
    tenant_id: uuid.UUID
    title: str  # Název školení / typ prohlídky / název akce
    person_name: str  # Zaměstnanec / odpovědná osoba
    due_date: date
    days_until: int  # Záporné = po termínu
    detail: str = ""  # Volitelný extra kontext (typ školení, kategorie atd.)


# ── Loaders ──────────────────────────────────────────────────────────────────


async def collect_expiring_trainings(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    today: date,
    threshold_days: int,
) -> list[ReminderItem]:
    """
    Vrátí TrainingAssignmenty kde valid_until je v intervalu (-∞, today + threshold_days].
    Skipuje záznamy bez valid_until.
    """
    cutoff = today + timedelta(days=threshold_days)

    stmt = (
        select(
            TrainingAssignment, Training.title, Training.training_type,
            Employee.first_name, Employee.last_name,
        )
        .join(Training, TrainingAssignment.training_id == Training.id)
        .join(Employee, TrainingAssignment.employee_id == Employee.id)
        .where(TrainingAssignment.tenant_id == tenant_id)
        .where(TrainingAssignment.valid_until.is_not(None))
        .where(TrainingAssignment.valid_until <= cutoff)
        .where(Employee.status == "active")
    )

    rows = (await db.execute(stmt)).all()
    items: list[ReminderItem] = []
    for assignment, title, ttype, fn, ln in rows:
        days_until = (assignment.valid_until - today).days
        items.append(ReminderItem(
            module=ReminderModule.TRAINING,
            tenant_id=tenant_id,
            title=title,
            person_name=f"{fn} {ln}",
            due_date=assignment.valid_until,
            days_until=days_until,
            detail=f"typ: {ttype}",
        ))
    return items


async def collect_expiring_medical_exams(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    today: date,
    threshold_days: int,
) -> list[ReminderItem]:
    """Lékařské prohlídky končící do threshold_days nebo už po termínu."""
    cutoff = today + timedelta(days=threshold_days)

    stmt = (
        select(MedicalExam, Employee.first_name, Employee.last_name)
        .join(Employee, MedicalExam.employee_id == Employee.id)
        .where(MedicalExam.tenant_id == tenant_id)
        .where(MedicalExam.valid_until.is_not(None))
        .where(MedicalExam.valid_until <= cutoff)
        .where(Employee.status == "active")
    )

    rows = (await db.execute(stmt)).all()
    items: list[ReminderItem] = []
    for exam, fn, ln in rows:
        if exam.valid_until is None:
            continue
        days_until = (exam.valid_until - today).days
        exam_type = getattr(exam, "exam_type", "") or ""
        category = getattr(exam, "work_category", "") or ""
        detail_parts = [p for p in [exam_type, f"kat. {category}" if category else ""] if p]
        items.append(ReminderItem(
            module=ReminderModule.MEDICAL_EXAM,
            tenant_id=tenant_id,
            title="Lékařská prohlídka",
            person_name=f"{fn} {ln}",
            due_date=exam.valid_until,
            days_until=days_until,
            detail=" · ".join(detail_parts),
        ))
    return items


async def collect_pending_accident_actions(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    today: date,
    threshold_days: int,
) -> list[ReminderItem]:
    """Akcie z action plánu úrazů s blížícím se / propadlým due_date."""
    cutoff = today + timedelta(days=threshold_days)

    stmt = (
        select(
            AccidentActionItem,
            AccidentReport.employee_name,
            AccidentReport.accident_date,
        )
        .join(
            AccidentReport,
            AccidentActionItem.accident_report_id == AccidentReport.id,
        )
        .where(AccidentActionItem.tenant_id == tenant_id)
        .where(AccidentActionItem.due_date.is_not(None))
        .where(AccidentActionItem.due_date <= cutoff)
        .where(AccidentActionItem.status.in_(["pending", "in_progress"]))
    )

    rows = (await db.execute(stmt)).all()
    items: list[ReminderItem] = []
    for action, injured_name, accident_dt in rows:
        if action.due_date is None:
            continue
        days_until = (action.due_date - today).days
        items.append(ReminderItem(
            module=ReminderModule.ACCIDENT_FOLLOWUP,
            tenant_id=tenant_id,
            title=action.title,
            person_name=injured_name or "—",
            due_date=action.due_date,
            days_until=days_until,
            detail=(
                f"úraz {accident_dt.strftime('%d.%m.%Y')}"
                if accident_dt else "akční plán"
            ),
        ))
    return items


# ── Aggregator ───────────────────────────────────────────────────────────────


async def collect_all_reminders_for_tenant(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    today: date | None = None,
) -> list[ReminderItem]:
    """
    Sjednocený sběr napříč moduly. Vrací deduplikovaný a setříděný list.
    Prahy se berou jako MAX z konfigurované sekvence (např. [30,14,7] → 30).
    """
    today = today or date.today()

    # Bypass RLS — background context, vidíme všechny záznamy daného tenantu
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))

    thresholds_training = await get_setting(
        db, "reminders.thresholds.training", [30, 14, 7],
    )
    thresholds_exam = await get_setting(
        db, "reminders.thresholds.medical_exam", [30, 14, 7],
    )
    thresholds_accident = await get_setting(
        db, "reminders.thresholds.accident_followup", [14, 7, 0],
    )

    items: list[ReminderItem] = []
    items.extend(await collect_expiring_trainings(
        db, tenant_id, today, max(thresholds_training, default=30),
    ))
    items.extend(await collect_expiring_medical_exams(
        db, tenant_id, today, max(thresholds_exam, default=30),
    ))
    items.extend(await collect_pending_accident_actions(
        db, tenant_id, today, max(thresholds_accident, default=14),
    ))

    # Sort: nejvíc kritické (po termínu) první, pak ascending podle dnů
    items.sort(key=lambda it: it.days_until)
    return items
