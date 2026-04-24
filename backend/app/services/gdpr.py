"""
GDPR utilities — právo na portabilitu (čl. 20) + právo na výmaz (čl. 17).

Funkce:
- `export_tenant_data(db, tenant_id)` — dict všech dat tenantu, caller
  serializuje do JSON.
- `soft_delete_tenant(db, tenant_id)` — deaktivuje tenant. Data zůstávají
  grace window (90 dní default) pro recovery / dotazy od zákazníka.
- `hard_delete_soft_deleted(db, grace_days)` — cron: fyzicky smaže tenanty
  jejichž deactivation_at je starší než grace window. Cascade smete child data.

export_tenant_data vypíše i audit_log → soubory mohou být 100+ MB.
Frontend by měl exportovat přes streaming endpoint, ne JSON response.
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accident_report import AccidentReport
from app.models.audit_log import AuditLog
from app.models.employee import Employee
from app.models.job_position import JobPosition
from app.models.medical_exam import MedicalExam
from app.models.oopp import OOPPAssignment
from app.models.revision import Revision
from app.models.risk import Risk
from app.models.risk_factor_assessment import RiskFactorAssessment
from app.models.tenant import Tenant
from app.models.training import Training
from app.models.user import User
from app.models.workplace import Plant, Workplace

# Pořadí: parents first (usnadní budoucí re-import).
_EXPORT_MODELS: list[tuple[str, Any]] = [
    ("plants", Plant),
    ("workplaces", Workplace),
    ("job_positions", JobPosition),
    ("users", User),
    ("employees", Employee),
    ("risks", Risk),
    ("risk_factor_assessments", RiskFactorAssessment),
    ("trainings", Training),
    ("medical_exams", MedicalExam),
    ("revisions", Revision),
    ("accident_reports", AccidentReport),
    ("oopp_assignments", OOPPAssignment),
    ("audit_log", AuditLog),
]

# Sloupce, které do exportu nikdy nezahrnujeme (tajnosti, interní metadata).
_EXPORT_SKIP_COLUMNS = frozenset({"hashed_password", "totp_secret"})


def _serialize_row(instance: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for col in instance.__table__.columns:
        name = col.name
        if name in _EXPORT_SKIP_COLUMNS:
            continue
        value = getattr(instance, name, None)
        if isinstance(value, uuid.UUID):
            out[name] = str(value)
        elif isinstance(value, datetime):
            out[name] = value.isoformat()
        elif hasattr(value, "isoformat"):
            out[name] = value.isoformat()
        elif value is None or isinstance(value, (str, int, float, bool, list, dict)):
            out[name] = value
        else:
            out[name] = str(value)
    return out


async def export_tenant_data(
    db: AsyncSession, tenant_id: uuid.UUID
) -> dict[str, Any]:
    """
    Vrátí dict: {table_name: [row, ...], ...} + _meta.
    """
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))

    data: dict[str, Any] = {
        "_meta": {
            "tenant_id": str(tenant_id),
            "exported_at": datetime.now(UTC).isoformat(),
            "format_version": 1,
        },
    }

    # Export tenant row zvlášť (nemá tenant_id column)
    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    data["tenant"] = _serialize_row(tenant) if tenant else None

    for name, model in _EXPORT_MODELS:
        result = await db.execute(
            select(model).where(model.tenant_id == tenant_id)
        )
        rows = result.scalars().all()
        data[name] = [_serialize_row(r) for r in rows]

    return data


def export_to_json_bytes(data: dict[str, Any]) -> bytes:
    """JSON dump pro streaming download response."""
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")


async def soft_delete_tenant(
    db: AsyncSession, tenant_id: uuid.UUID
) -> Tenant | None:
    """
    Označí tenant.is_active=False. `updated_at` slouží jako timestamp
    deaktivace (využívá TimestampMixin onupdate). Fyzický smaz proběhne
    v `hard_delete_soft_deleted()` po uplynutí grace window.
    """
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))
    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    if tenant is None:
        return None
    tenant.is_active = False
    await db.flush()
    return tenant


async def hard_delete_soft_deleted(
    db: AsyncSession, grace_days: int = 90
) -> list[uuid.UUID]:
    """
    CRON: fyzicky smaž tenanty soft-deleted před víc než grace_days.
    Cascade v FK smete všechny child tabulky.
    """
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))
    threshold = datetime.now(UTC) - timedelta(days=grace_days)

    inactive = (await db.execute(
        select(Tenant).where(
            Tenant.is_active == False,  # noqa: E712
            Tenant.updated_at < threshold,
        )
    )).scalars().all()

    deleted_ids: list[uuid.UUID] = [t.id for t in inactive]
    for t in inactive:
        await db.execute(delete(Tenant).where(Tenant.id == t.id))
    await db.flush()
    return deleted_ids
