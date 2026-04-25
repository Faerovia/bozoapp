"""
Invoice model — manuální fakturace pro tenanty.

Workflow:
- platform admin (nebo cron) vystaví fakturu (status=draft)
- email odeslán → status=sent + sent_at
- po doručení platby admin označí jako paid + paid_at
- případně cancel pro storno

issuer_snapshot a recipient_snapshot držet snapshot platform_settings a tenant
fakturačních údajů z momentu vystavení — abychom uchovali přesný stav i po
změně settings/tenantu (právní compliance).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class Invoice(Base, TimestampMixin):
    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False,
    )
    invoice_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)

    issued_at: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    period_from: Mapped[date] = mapped_column(Date, nullable=False)
    period_to: Mapped[date] = mapped_column(Date, nullable=False)
    paid_at: Mapped[date | None] = mapped_column(Date)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")

    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="CZK")
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    vat_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0"),
    )
    vat_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0"),
    )
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    issuer_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    recipient_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)

    notes: Mapped[str | None] = mapped_column(Text)
    pdf_path: Mapped[str | None] = mapped_column(String(500))

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
    )


class InvoiceCounter(Base):
    """
    Tabulka držící poslední vydané pořadí faktury per rok.
    Používá `SELECT ... FOR UPDATE` pro atomický increment.
    """

    __tablename__ = "invoice_counters"

    year: Mapped[int] = mapped_column(primary_key=True)
    last_seq: Mapped[int] = mapped_column(nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
