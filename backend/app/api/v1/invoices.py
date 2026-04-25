"""
Tenant endpointy pro vlastní fakturaci.
Tenant vidí jen svoje faktury (RLS to vynucuje).
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.invoice import Invoice
from app.models.user import User
from app.schemas.invoice import InvoiceListItem, InvoiceResponse

router = APIRouter()


@router.get("/billing/invoices", response_model=list[InvoiceListItem])
async def list_my_invoices(
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Any]:
    """Vrátí faktury aktuálního tenantu (přes RLS)."""
    invoices = (await db.execute(
        select(Invoice)
        .where(Invoice.status != "cancelled")
        .order_by(Invoice.issued_at.desc(), Invoice.invoice_number.desc())
    )).scalars().all()
    return list(invoices)


@router.get("/billing/invoices/{invoice_id}", response_model=InvoiceResponse)
async def get_my_invoice(
    invoice_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    invoice = (await db.execute(
        select(Invoice).where(Invoice.id == invoice_id)
    )).scalar_one_or_none()
    if invoice is None:
        raise HTTPException(status_code=404, detail="Faktura nenalezena")
    return invoice
