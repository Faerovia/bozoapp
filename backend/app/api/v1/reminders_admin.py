"""
Platform admin endpointy pro reminder emaily.

- POST /admin/reminders/run-now           — manuální trigger (všichni tenanti)
- GET  /admin/reminders/preview/{tenant}  — náhled (bez odeslání)
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_platform_admin
from app.models.tenant import Tenant
from app.models.user import User
from app.services.reminders import collect_all_reminders_for_tenant
from app.services.reminders_email import (
    build_email_body,
    collect_recipient_emails,
    send_reminder_email,
)

router = APIRouter()


@router.post("/admin/reminders/run-now")
async def admin_run_reminders(
    dry_run: bool = False,
    _admin: User = Depends(require_platform_admin()),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Manuální trigger reminder cronu. `dry_run=true` neposílá emaily, vrátí jen stats.
    """
    today = date.today()
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))

    tenants = (await db.execute(
        select(Tenant)
        .where(Tenant.is_active.is_(True))
        .where(Tenant.name != "__PLATFORM__")
    )).scalars().all()

    tenants_processed = 0
    emails_sent = 0
    items_total = 0
    per_tenant: list[dict[str, Any]] = []

    for tenant in tenants:
        items = await collect_all_reminders_for_tenant(db, tenant.id, today=today)
        recipients = await collect_recipient_emails(db, tenant.id)

        if not items or not recipients:
            per_tenant.append({
                "tenant_id": str(tenant.id),
                "tenant_name": tenant.name,
                "items_count": len(items),
                "recipients_count": len(recipients),
                "skipped": True,
            })
            continue

        if not dry_run:
            for r in recipients:
                try:
                    await send_reminder_email(
                        db, recipient=r,
                        tenant_name=tenant.name, items=items,
                    )
                    emails_sent += 1
                except Exception:
                    pass

        per_tenant.append({
            "tenant_id": str(tenant.id),
            "tenant_name": tenant.name,
            "items_count": len(items),
            "recipients_count": len(recipients),
            "skipped": False,
        })
        tenants_processed += 1
        items_total += len(items)

    return {
        "dry_run": dry_run,
        "tenants_processed": tenants_processed,
        "emails_sent": emails_sent,
        "items_total": items_total,
        "per_tenant": per_tenant,
    }


@router.get("/admin/reminders/preview/{tenant_id}")
async def admin_preview_reminders(
    tenant_id: uuid.UUID,
    _admin: User = Depends(require_platform_admin()),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Náhled co by se poslalo — subject + body, bez odeslání."""
    today = date.today()
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))
    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant nenalezen")

    items = await collect_all_reminders_for_tenant(db, tenant_id, today=today)
    recipients = await collect_recipient_emails(db, tenant_id)

    if not items:
        return {
            "tenant_name": tenant.name,
            "items_count": 0,
            "recipients": recipients,
            "subject": None,
            "body_text": "(žádné expirace)",
        }

    subject, body = build_email_body(items, tenant.name)
    return {
        "tenant_name": tenant.name,
        "items_count": len(items),
        "recipients": recipients,
        "subject": subject,
        "body_text": body,
        "items": [
            {
                "module": it.module.value,
                "title": it.title,
                "person_name": it.person_name,
                "due_date": it.due_date.isoformat(),
                "days_until": it.days_until,
                "detail": it.detail,
            }
            for it in items
        ],
    }
