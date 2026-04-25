"""
OZO multi-client cross-tenant overview.

Pro current_user (typicky OZO) iteruje všechny tenanty, kde má membership,
a spočítá agregované metriky (expirace, úkoly).
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accident_report import AccidentReport
from app.models.medical_exam import MedicalExam
from app.models.oopp import EmployeeOoppIssue
from app.models.revision import Revision
from app.models.tenant import Tenant
from app.models.training import TrainingAssignment
from app.services.memberships import get_user_memberships

DUE_HORIZON_DAYS = 30


async def _set_tenant_context(db: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Nastav app.current_tenant_id GUC pro tuto session/transakci.

    RLS pak izoluje další dotazy na tento tenant. Volat na začátku každé
    iterace v overview, abychom přepnuli kontext.
    """
    await db.execute(
        text("SELECT set_config('app.current_tenant_id', :tid, true)"),
        {"tid": str(tenant_id)},
    )


async def _count_tenant_metrics(
    db: AsyncSession, tenant_id: uuid.UUID
) -> dict[str, int]:
    """Spočítá metriky pro 1 tenant (předpokládá, že je nastaven RLS kontext)."""
    today = datetime.now(UTC).date()
    horizon = today + timedelta(days=DUE_HORIZON_DAYS)

    # 1. Expirující školení (TrainingAssignment.valid_until <= horizon)
    res = await db.execute(
        select(func.count(TrainingAssignment.id)).where(
            TrainingAssignment.tenant_id == tenant_id,
            TrainingAssignment.status == "completed",
            TrainingAssignment.valid_until.is_not(None),
            TrainingAssignment.valid_until <= horizon,
        )
    )
    expiring_trainings = int(res.scalar_one() or 0)

    # 2. Po termínu / blížící se revize
    res = await db.execute(
        select(func.count(Revision.id)).where(
            Revision.tenant_id == tenant_id,
            Revision.status == "active",
            Revision.next_revision_at.is_not(None),
            Revision.next_revision_at <= horizon,
        )
    )
    due_revisions = int(res.scalar_one() or 0)

    res = await db.execute(
        select(func.count(Revision.id)).where(
            Revision.tenant_id == tenant_id,
            Revision.status == "active",
            Revision.next_revision_at.is_not(None),
            Revision.next_revision_at < today,
        )
    )
    overdue_revisions = int(res.scalar_one() or 0)

    # 3. Expirující LP
    res = await db.execute(
        select(func.count(MedicalExam.id)).where(
            MedicalExam.tenant_id == tenant_id,
            MedicalExam.status == "active",
            MedicalExam.valid_until.is_not(None),
            MedicalExam.valid_until <= horizon,
        )
    )
    expiring_medical_exams = int(res.scalar_one() or 0)

    # 4. Draft pracovní úrazy (čekají na finalizaci)
    res = await db.execute(
        select(func.count(AccidentReport.id)).where(
            AccidentReport.tenant_id == tenant_id,
            AccidentReport.status == "draft",
        )
    )
    draft_accident_reports = int(res.scalar_one() or 0)

    # 5. Expirující OOPP výdeje
    res = await db.execute(
        select(func.count(EmployeeOoppIssue.id)).where(
            EmployeeOoppIssue.tenant_id == tenant_id,
            EmployeeOoppIssue.status == "active",
            EmployeeOoppIssue.valid_until.is_not(None),
            EmployeeOoppIssue.valid_until <= horizon,
        )
    )
    expiring_oopp = int(res.scalar_one() or 0)

    return {
        "expiring_trainings": expiring_trainings,
        "due_revisions": due_revisions,
        "overdue_revisions": overdue_revisions,
        "expiring_medical_exams": expiring_medical_exams,
        "draft_accident_reports": draft_accident_reports,
        "expiring_oopp": expiring_oopp,
    }


async def get_ozo_overview(
    db: AsyncSession, user_id: uuid.UUID
) -> list[dict[str, Any]]:
    """
    Pro každý tenant, kde má user membership, spočítá agregované metriky.
    Vrací list[ClientOverview]:
        [
          {
            "tenant_id", "tenant_name", "role", "is_default",
            "metrics": {
              "expiring_trainings", "due_revisions", "overdue_revisions",
              "expiring_medical_exams", "draft_accident_reports",
              "expiring_oopp",
            },
            "total_actions": int  # součet všech čísel pro řazení
          }
        ]
    """
    memberships = await get_user_memberships(db, user_id)
    out: list[dict[str, Any]] = []

    for m in memberships:
        tenant_id: uuid.UUID = m["tenant_id"]
        await _set_tenant_context(db, tenant_id)
        metrics = await _count_tenant_metrics(db, tenant_id)
        total = sum(metrics.values()) - metrics["overdue_revisions"]
        # overdue_revisions je podmnožina due_revisions; nezapočítavej dvakrát
        out.append({
            "tenant_id": tenant_id,
            "tenant_name": m["tenant_name"],
            "role": m["role"],
            "is_default": m["is_default"],
            "metrics": metrics,
            "total_actions": total,
        })

    # Seřaď podle total_actions DESC (nejvíce zanedbávané klienti nahoře)
    out.sort(key=lambda x: x["total_actions"], reverse=True)
    return out


# ── Schémata pro response ──────────────────────────────────────────────────

# Pozn.: Pydantic schema dáme do api vrstvy / schemas/ozo_overview.py
# (pro čistotu). Tady jen plain dict[str, Any] pro typing.

_ = date  # date import nepoužitý — zachováno pro budoucí enrichment
