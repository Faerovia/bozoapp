"""
Onboarding progress — počítá checklist podle reálných dat v DB.

9 položek (každá bool flag):
1. has_company_info  — billing_company_name + billing_ico vyplněné
2. has_plant         — alespoň 1 plant
3. has_workplace     — alespoň 1 workplace
4. has_position      — alespoň 1 job_position
5. has_rfa           — alespoň 1 risk_factor_assessment
6. has_employee      — alespoň 1 active employee
7. has_training      — alespoň 1 training (vlastní nebo aktivovaný marketplace)
8. has_revision      — alespoň 1 revision device
9. has_logo          — tenant.logo_path NOT NULL

Auto-completion: pokud >= 6/9 done, ukáže button "Mám hotovo, skrýt".
Manual: tlačítko "Skrýt navždy" nastaví onboarding_dismissed=true.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.job_position import JobPosition
from app.models.revision import Revision
from app.models.risk_factor_assessment import RiskFactorAssessment
from app.models.tenant import Tenant
from app.models.training import Training
from app.models.workplace import Plant, Workplace


@dataclass
class OnboardingItem:
    key: str
    label: str
    done: bool
    href: str | None = None


@dataclass
class OnboardingProgress:
    items: list[OnboardingItem]
    done_count: int
    total_count: int
    percent: int
    step1_completed: bool
    can_finish: bool        # >= 6 done → user může označit za completed
    completed: bool         # onboarding_completed_at != NULL
    dismissed: bool         # uživatel skryl navždy


async def _count(db: AsyncSession, model: type, tenant_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count()).select_from(model).where(model.tenant_id == tenant_id)  # type: ignore[attr-defined]
    )
    return int(result.scalar_one())


async def compute_progress(
    db: AsyncSession, tenant: Tenant,
) -> OnboardingProgress:
    """Spočítá 9 checklist items podle DB stavu."""
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))

    plants = await _count(db, Plant, tenant.id)
    workplaces = await _count(db, Workplace, tenant.id)
    positions = await _count(db, JobPosition, tenant.id)
    rfas = await _count(db, RiskFactorAssessment, tenant.id)
    employees_active = int((await db.execute(
        select(func.count())
        .select_from(Employee)
        .where(Employee.tenant_id == tenant.id)
        .where(Employee.status == "active")
    )).scalar_one())
    trainings = await _count(db, Training, tenant.id)
    revisions = await _count(db, Revision, tenant.id)

    has_company = bool(tenant.billing_company_name and tenant.billing_ico)
    has_logo = bool(tenant.logo_path)

    items = [
        OnboardingItem(
            "company_info", "Údaje firmy (z ARES)",
            has_company, "/admin/settings/invoice-issuer",
        ),
        OnboardingItem(
            "plant", "První pracoviště (provozovna)",
            plants > 0, "/workplaces",
        ),
        OnboardingItem(
            "workplace", "Detailní pracoviště",
            workplaces > 0, "/workplaces",
        ),
        OnboardingItem(
            "position", "Pracovní pozice (kategorie 1/2/2R/3/4)",
            positions > 0, "/workplaces",
        ),
        OnboardingItem(
            "rfa", "Hodnocení rizikových faktorů (RFA)",
            rfas > 0, "/workplaces",
        ),
        OnboardingItem(
            "employee", "Zaměstnanci (CSV import nebo ručně)",
            employees_active > 0, "/employees",
        ),
        OnboardingItem(
            "training", "Aktivovat školení BOZP/PO",
            trainings > 0, "/trainings",
        ),
        OnboardingItem(
            "revision", "Naplánovat revize zařízení",
            revisions > 0, "/revisions",
        ),
        OnboardingItem(
            "logo", "Nahrát logo firmy",
            has_logo, "/admin/settings/invoice-issuer",
        ),
    ]

    done_count = sum(1 for it in items if it.done)
    total_count = len(items)
    percent = int(round(100 * done_count / total_count)) if total_count else 0

    return OnboardingProgress(
        items=items,
        done_count=done_count,
        total_count=total_count,
        percent=percent,
        step1_completed=tenant.onboarding_step1_completed_at is not None,
        can_finish=done_count >= 6,
        completed=tenant.onboarding_completed_at is not None,
        dismissed=tenant.onboarding_dismissed,
    )
