"""
Platform admin endpointy pro fakturaci.

Endpointy (vyžadují platform admin):
- POST   /admin/invoices                — vystavit fakturu pro daný tenant + období
- POST   /admin/invoices/run-monthly    — spustit cron generation (idempotentní)
- GET    /admin/invoices                — list všech faktur (filtry: tenant, status)
- GET    /admin/invoices/{id}           — detail
- PATCH  /admin/invoices/{id}           — mark paid / cancel / poznámka
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_platform_admin
from app.models.invoice import Invoice
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.invoice import (
    GenerateInvoiceRequest,
    InvoiceListItem,
    InvoicePatchRequest,
    InvoiceResponse,
)
from app.services.invoice_delivery import (
    deliver_invoice,
    render_and_save_pdf,
    send_invoice_email,
)
from app.services.invoicing import (
    cancel_invoice,
    generate_invoice,
    generate_monthly_invoices,
    mark_paid,
)

router = APIRouter()


@router.post(
    "/admin/invoices",
    response_model=InvoiceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def admin_create_invoice(
    data: GenerateInvoiceRequest,
    admin: User = Depends(require_platform_admin()),
    db: AsyncSession = Depends(get_db),
) -> Any:
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))
    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == data.tenant_id)
    )).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant nenalezen")

    if not tenant.billing_company_name or not tenant.billing_ico:
        raise HTTPException(
            status_code=400,
            detail=(
                "Tenant nemá vyplněné fakturační údaje "
                "(billing_company_name + billing_ico jsou povinné)."
            ),
        )

    invoice = await generate_invoice(
        db, tenant=tenant,
        period_from=data.period_from,
        period_to=data.period_to,
        issued_at=data.issued_at,
        created_by=admin.id,
    )
    if invoice is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Faktura by měla nulovou částku — zkontroluj billing_type "
                "a billing_amount tenantu."
            ),
        )
    return invoice


@router.post("/admin/invoices/run-monthly")
async def admin_run_monthly(
    today: date | None = None,
    _admin: User = Depends(require_platform_admin()),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Manuální trigger měsíčního cronu (idempotentní jen do míry sekvence — pozor)."""
    invoices = await generate_monthly_invoices(db, today=today)
    return {
        "generated_count": len(invoices),
        "invoice_numbers": [inv.invoice_number for inv in invoices],
    }


@router.get("/admin/invoices", response_model=list[InvoiceListItem])
async def admin_list_invoices(
    tenant_id: uuid.UUID | None = Query(None),
    invoice_status: str | None = Query(None, pattern="^(draft|sent|paid|cancelled)$"),
    _admin: User = Depends(require_platform_admin()),
    db: AsyncSession = Depends(get_db),
) -> list[Any]:
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))
    stmt = select(Invoice).order_by(Invoice.issued_at.desc(), Invoice.invoice_number.desc())
    if tenant_id:
        stmt = stmt.where(Invoice.tenant_id == tenant_id)
    if invoice_status:
        stmt = stmt.where(Invoice.status == invoice_status)
    return list((await db.execute(stmt)).scalars().all())


@router.get("/admin/invoices/{invoice_id}", response_model=InvoiceResponse)
async def admin_get_invoice(
    invoice_id: uuid.UUID,
    _admin: User = Depends(require_platform_admin()),
    db: AsyncSession = Depends(get_db),
) -> Any:
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))
    invoice = (await db.execute(
        select(Invoice).where(Invoice.id == invoice_id)
    )).scalar_one_or_none()
    if invoice is None:
        raise HTTPException(status_code=404, detail="Faktura nenalezena")
    return invoice


@router.patch("/admin/invoices/{invoice_id}", response_model=InvoiceResponse)
async def admin_patch_invoice(
    invoice_id: uuid.UUID,
    data: InvoicePatchRequest,
    _admin: User = Depends(require_platform_admin()),
    db: AsyncSession = Depends(get_db),
) -> Any:
    if data.status == "paid":
        await mark_paid(db, invoice_id, paid_at=data.paid_at)
    elif data.status == "cancelled":
        await cancel_invoice(db, invoice_id)

    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))
    invoice = (await db.execute(
        select(Invoice).where(Invoice.id == invoice_id)
    )).scalar_one_or_none()
    if invoice is None:
        raise HTTPException(status_code=404, detail="Faktura nenalezena")

    if data.notes is not None:
        invoice.notes = data.notes
    if data.status == "draft":
        invoice.status = "draft"
    if data.status == "sent" and invoice.status != "sent":
        invoice.status = "sent"
    await db.flush()
    return invoice
