"""
Service pro vystavování a správu faktur.

Workflow:
- `next_invoice_number(year)` — atomicky inkrementuje invoice_counter, vrátí
  formátované číslo dle invoice_number_format setting
- `build_issuer_snapshot()` — načte aktuální platform_settings issuer_*
- `build_recipient_snapshot(tenant)` — z tenant.billing_company_* polí
- `compute_amount_for_tenant(tenant, period)` — spočítá fakturovanou částku
  podle billing_type (monthly/yearly/per_employee/custom/free)
- `generate_invoice(tenant, period_from, period_to, ...)` — vystaví fakturu
- `mark_paid`, `cancel_invoice`
- `generate_monthly_invoices(today)` — pro cron, vystaví všem aktivním tenantům
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.invoice import Invoice, InvoiceCounter
from app.models.tenant import Tenant
from app.services.platform_settings import get_setting

# ── Numbering ────────────────────────────────────────────────────────────────


async def next_invoice_number(db: AsyncSession, year: int) -> str:
    """
    Atomicky vezme další pořadí pro daný rok a vrátí formátované číslo faktury
    podle `invoice_number_format` setting (default `{year}{seq:04d}`).
    Používá `SELECT ... FOR UPDATE` na řádku v `invoice_counters`.
    """
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))

    counter = (await db.execute(
        select(InvoiceCounter).where(InvoiceCounter.year == year).with_for_update()
    )).scalar_one_or_none()

    if counter is None:
        counter = InvoiceCounter(
            year=year, last_seq=1, updated_at=datetime.now(UTC),
        )
        db.add(counter)
        try:
            await db.flush()
        except IntegrityError:
            # race condition: another transaction inserted, retry select
            await db.rollback()
            counter = (await db.execute(
                select(InvoiceCounter).where(InvoiceCounter.year == year).with_for_update()
            )).scalar_one()
            counter.last_seq += 1
            counter.updated_at = datetime.now(UTC)
            await db.flush()
        seq = counter.last_seq
    else:
        counter.last_seq += 1
        counter.updated_at = datetime.now(UTC)
        await db.flush()
        seq = counter.last_seq

    fmt: str = await get_setting(db, "invoice_number_format", "{year}{seq:04d}")
    return fmt.format(year=year, seq=seq)


# ── Snapshots ────────────────────────────────────────────────────────────────


async def build_issuer_snapshot(db: AsyncSession) -> dict[str, Any]:
    """Načte aktuální vystavovatel údaje z platform_settings."""
    keys = [
        "issuer_name", "issuer_ico", "issuer_dic",
        "issuer_address_street", "issuer_address_city", "issuer_address_zip",
        "issuer_bank_account", "issuer_bank_name", "issuer_iban", "issuer_swift",
        "issuer_email",
    ]
    snapshot: dict[str, Any] = {}
    for k in keys:
        snapshot[k] = await get_setting(db, k, "")
    snapshot["is_vat_payer"] = await get_setting(db, "is_vat_payer", False)
    snapshot["vat_rate"] = await get_setting(db, "vat_rate", 21)
    return snapshot


def build_recipient_snapshot(tenant: Tenant) -> dict[str, Any]:
    return {
        "name": tenant.billing_company_name or tenant.name,
        "ico": tenant.billing_ico or "",
        "dic": tenant.billing_dic or "",
        "address_street": tenant.billing_address_street or "",
        "address_city": tenant.billing_address_city or "",
        "address_zip": tenant.billing_address_zip or "",
        "email": tenant.billing_email or "",
        "tenant_id": str(tenant.id),
        "tenant_name": tenant.name,
    }


# ── Amount calculation ───────────────────────────────────────────────────────


async def compute_amount_for_tenant(
    db: AsyncSession,
    tenant: Tenant,
    period_from: date,
    period_to: date,
) -> tuple[Decimal, list[dict[str, Any]]]:
    """
    Vrátí (subtotal, items[]) pro daný tenant a období.
    Logika dle billing_type:
    - monthly: 1× billing_amount
    - yearly: jen pokud period obsahuje měsíc kdy tenant vznikl, jinak 0
    - per_employee: count(active employees) × billing_amount
    - custom: billing_amount (admin to nastavil ručně)
    - free / None: 0 a prázdné items
    """
    if not tenant.billing_type or tenant.billing_type == "free":
        return Decimal("0"), []

    amount = tenant.billing_amount or Decimal("0")
    period_label = f"{period_from.strftime('%-m/%Y')}"

    if tenant.billing_type == "monthly":
        items = [{
            "description": f"Předplatné OZODigi — {period_label}",
            "quantity": 1,
            "unit": "měsíc",
            "unit_price": float(amount),
            "total": float(amount),
        }]
        return amount, items

    if tenant.billing_type == "yearly":
        # Faktura jen v měsíci výročí (anniversary)
        if tenant.created_at.month != period_from.month:
            return Decimal("0"), []
        items = [{
            "description": f"Roční předplatné OZODigi — {period_from.year}",
            "quantity": 1,
            "unit": "rok",
            "unit_price": float(amount),
            "total": float(amount),
        }]
        return amount, items

    if tenant.billing_type == "per_employee":
        await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))
        count = (await db.execute(
            select(func.count(Employee.id))
            .where(Employee.tenant_id == tenant.id)
            .where(Employee.status == "active")
        )).scalar_one()
        total = amount * Decimal(count)
        items = [{
            "description": f"OZODigi za zaměstnance — {period_label}",
            "quantity": count,
            "unit": "ks",
            "unit_price": float(amount),
            "total": float(total),
        }]
        return total, items

    if tenant.billing_type == "custom":
        items = [{
            "description": (
                tenant.billing_note
                or f"Služby OZODigi — {period_label}"
            ),
            "quantity": 1,
            "unit": "ks",
            "unit_price": float(amount),
            "total": float(amount),
        }]
        return amount, items

    return Decimal("0"), []


# ── Invoice generation ───────────────────────────────────────────────────────


async def generate_invoice(
    db: AsyncSession,
    *,
    tenant: Tenant,
    period_from: date,
    period_to: date,
    issued_at: date | None = None,
    created_by: uuid.UUID | None = None,
) -> Invoice | None:
    """
    Vystaví fakturu pro tenant. Vrátí None pokud subtotal == 0
    (nepoužitý billing nebo yearly mimo anniversary).
    """
    issued = issued_at or date.today()

    subtotal, items = await compute_amount_for_tenant(db, tenant, period_from, period_to)
    if subtotal == 0:
        return None

    issuer = await build_issuer_snapshot(db)
    is_vat = bool(issuer.get("is_vat_payer", False))
    vat_rate = Decimal(str(issuer.get("vat_rate", 21))) if is_vat else Decimal("0")
    vat_amount = (subtotal * vat_rate / Decimal("100")).quantize(Decimal("0.01"))
    total = subtotal + vat_amount

    due_days = int(await get_setting(db, "invoice_due_days", 14))
    due_date = issued + timedelta(days=due_days)

    number = await next_invoice_number(db, issued.year)

    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))

    invoice = Invoice(
        tenant_id=tenant.id,
        invoice_number=number,
        issued_at=issued,
        due_date=due_date,
        period_from=period_from,
        period_to=period_to,
        status="draft",
        currency=tenant.billing_currency or "CZK",
        subtotal=subtotal,
        vat_rate=vat_rate,
        vat_amount=vat_amount,
        total=total,
        issuer_snapshot=issuer,
        recipient_snapshot=build_recipient_snapshot(tenant),
        items=items,
        created_by=created_by,
    )
    db.add(invoice)
    await db.flush()
    return invoice


async def mark_paid(
    db: AsyncSession, invoice_id: uuid.UUID, paid_at: date | None = None,
) -> Invoice:
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))
    invoice = (await db.execute(
        select(Invoice).where(Invoice.id == invoice_id)
    )).scalar_one()
    invoice.status = "paid"
    invoice.paid_at = paid_at or date.today()
    await db.flush()
    return invoice


async def cancel_invoice(db: AsyncSession, invoice_id: uuid.UUID) -> Invoice:
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))
    invoice = (await db.execute(
        select(Invoice).where(Invoice.id == invoice_id)
    )).scalar_one()
    invoice.status = "cancelled"
    await db.flush()
    return invoice


async def generate_monthly_invoices(
    db: AsyncSession,
    today: date | None = None,
) -> list[Invoice]:
    """
    Pro cron: vystaví faktury všem aktivním tenantům za předchozí kalendářní
    měsíc. Tenanti s billing_type=custom nebo free jsou přeskočeni
    (custom = admin musí ručně, free = neúčtujeme).
    """
    today = today or date.today()
    # Předchozí měsíc
    if today.month == 1:
        period_from = date(today.year - 1, 12, 1)
        period_to = date(today.year - 1, 12, 31)
    else:
        period_from = date(today.year, today.month - 1, 1)
        # last day of previous month = first of this month - 1 day
        period_to = date(today.year, today.month, 1) - timedelta(days=1)

    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))

    tenants = (await db.execute(
        select(Tenant)
        .where(Tenant.is_active.is_(True))
        .where(Tenant.name != "__PLATFORM__")
        .where(Tenant.billing_type.in_(["monthly", "yearly", "per_employee"]))
    )).scalars().all()

    invoices: list[Invoice] = []
    for tenant in tenants:
        invoice = await generate_invoice(
            db, tenant=tenant,
            period_from=period_from, period_to=period_to,
            issued_at=today,
        )
        if invoice is not None:
            invoices.append(invoice)
    return invoices
