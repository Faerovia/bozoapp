from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class InvoiceItem(BaseModel):
    description: str
    quantity: float
    unit: str
    unit_price: float
    total: float


class InvoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    invoice_number: str

    issued_at: date
    due_date: date
    period_from: date
    period_to: date
    paid_at: date | None
    sent_at: datetime | None

    status: str
    currency: str
    subtotal: Decimal
    vat_rate: Decimal
    vat_amount: Decimal
    total: Decimal

    issuer_snapshot: dict[str, Any]
    recipient_snapshot: dict[str, Any]
    items: list[dict[str, Any]]

    notes: str | None
    pdf_path: str | None

    created_at: datetime
    updated_at: datetime


class InvoiceListItem(BaseModel):
    """Lehčí varianta pro list view — bez snapshot polí."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    invoice_number: str
    issued_at: date
    due_date: date
    period_from: date
    period_to: date
    paid_at: date | None
    status: str
    currency: str
    total: Decimal


class GenerateInvoiceRequest(BaseModel):
    tenant_id: uuid.UUID
    period_from: date
    period_to: date
    issued_at: date | None = None


class InvoicePatchRequest(BaseModel):
    status: str | None = Field(None, pattern="^(draft|sent|paid|cancelled)$")
    paid_at: date | None = None
    notes: str | None = None


class TenantBillingDetailsRequest(BaseModel):
    """PATCH část pro fakturační údaje tenantu (admin endpoint)."""
    billing_company_name: str | None = None
    billing_ico: str | None = None
    billing_dic: str | None = None
    billing_address_street: str | None = None
    billing_address_city: str | None = None
    billing_address_zip: str | None = None
    billing_email: str | None = None
