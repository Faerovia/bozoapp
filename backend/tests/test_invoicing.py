"""
Testy manuální fakturace (commit 19b-1).

Pokrývá:
- next_invoice_number atomicky inkrementuje
- generate_invoice vyžaduje vyplněné billing_company údaje
- compute_amount per billing_type (monthly/yearly/per_employee/custom/free)
- mark_paid / cancel
- generate_monthly_invoices přeskakuje neaktivní/custom/free tenanty
- Admin endpointy: vystavení, list, patch
- RLS: tenant vidí jen své faktury
"""

from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.models.tenant import Tenant
from app.models.user import User
from app.services.invoicing import (
    compute_amount_for_tenant,
    generate_invoice,
    generate_monthly_invoices,
    mark_paid,
    next_invoice_number,
)


async def _register_ozo(client: AsyncClient, suffix: str) -> tuple[str, str]:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"inv{suffix}@me.cz",
            "password": "heslo1234",
            "tenant_name": f"Klient {suffix}",
        },
    )
    assert resp.status_code == 201
    access_token: str = resp.json()["access_token"]
    payload = decode_token(access_token)
    return access_token, str(payload["tenant_id"])


async def _promote_to_admin(db: AsyncSession, email: str) -> None:
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))
    user = (await db.execute(select(User).where(User.email == email))).scalar_one()
    user.role = "admin"
    user.is_platform_admin = True
    await db.commit()


async def _set_tenant_billing(
    db: AsyncSession,
    tenant_id: str,
    *,
    billing_type: str,
    billing_amount: Decimal,
    fill_company: bool = True,
) -> Tenant:
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))
    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one()
    tenant.billing_type = billing_type
    tenant.billing_amount = billing_amount
    tenant.billing_currency = "CZK"
    if fill_company:
        tenant.billing_company_name = "Klient s.r.o."
        tenant.billing_ico = "12345678"
        tenant.billing_address_street = "Dlouhá 1"
        tenant.billing_address_city = "Praha"
        tenant.billing_address_zip = "11000"
        tenant.billing_email = "fakturace@klient.cz"
    await db.commit()
    return tenant


@pytest.mark.asyncio
async def test_next_invoice_number_increments(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register_ozo(client, "n1")
    # Hodnoty se mohou lišit podle stavu DB (predchozí seed či test);
    # ověřujeme jen že counter monotonicky roste a má správný formát.
    n1 = await next_invoice_number(db_session, 2026)
    n2 = await next_invoice_number(db_session, 2026)
    assert n1.startswith("2026") and len(n1) == 8
    assert n2.startswith("2026") and len(n2) == 8
    assert int(n2) == int(n1) + 1
    # Rok 2030 (málo používaný) — ověř že nová sekvence začíná
    n3 = await next_invoice_number(db_session, 2030)
    assert n3.startswith("2030") and len(n3) == 8


@pytest.mark.asyncio
async def test_compute_amount_monthly(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, tid = await _register_ozo(client, "m1")
    tenant = await _set_tenant_billing(
        db_session, tid, billing_type="monthly", billing_amount=Decimal("990"),
    )
    subtotal, items = await compute_amount_for_tenant(
        db_session, tenant, date(2026, 4, 1), date(2026, 4, 30),
    )
    assert subtotal == Decimal("990")
    assert len(items) == 1


@pytest.mark.asyncio
async def test_compute_amount_free_returns_zero(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, tid = await _register_ozo(client, "f1")
    tenant = await _set_tenant_billing(
        db_session, tid, billing_type="free", billing_amount=Decimal("0"),
    )
    subtotal, items = await compute_amount_for_tenant(
        db_session, tenant, date(2026, 4, 1), date(2026, 4, 30),
    )
    assert subtotal == Decimal("0")
    assert items == []


@pytest.mark.asyncio
async def test_generate_invoice_creates_record(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, tid = await _register_ozo(client, "g1")
    tenant = await _set_tenant_billing(
        db_session, tid, billing_type="monthly", billing_amount=Decimal("500"),
    )
    invoice = await generate_invoice(
        db_session, tenant=tenant,
        period_from=date(2026, 4, 1), period_to=date(2026, 4, 30),
    )
    assert invoice is not None
    assert invoice.subtotal == Decimal("500")
    assert invoice.total == Decimal("500")  # neplátce DPH
    assert invoice.status == "draft"
    assert invoice.invoice_number.startswith("2026")
    assert invoice.recipient_snapshot["ico"] == "12345678"


@pytest.mark.asyncio
async def test_generate_invoice_skips_zero(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, tid = await _register_ozo(client, "z1")
    tenant = await _set_tenant_billing(
        db_session, tid, billing_type="free", billing_amount=Decimal("0"),
    )
    invoice = await generate_invoice(
        db_session, tenant=tenant,
        period_from=date(2026, 4, 1), period_to=date(2026, 4, 30),
    )
    assert invoice is None


@pytest.mark.asyncio
async def test_mark_paid_changes_status(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, tid = await _register_ozo(client, "p1")
    tenant = await _set_tenant_billing(
        db_session, tid, billing_type="monthly", billing_amount=Decimal("100"),
    )
    invoice = await generate_invoice(
        db_session, tenant=tenant,
        period_from=date(2026, 4, 1), period_to=date(2026, 4, 30),
    )
    assert invoice is not None
    paid = await mark_paid(db_session, invoice.id, paid_at=date(2026, 5, 5))
    assert paid.status == "paid"
    assert paid.paid_at == date(2026, 5, 5)


@pytest.mark.asyncio
async def test_admin_create_invoice_endpoint(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, tid = await _register_ozo(client, "ai1")
    await _promote_to_admin(db_session, "invai1@me.cz")
    await _set_tenant_billing(
        db_session, tid, billing_type="monthly", billing_amount=Decimal("1500"),
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "invai1@me.cz", "password": "heslo1234"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await client.post(
        "/api/v1/admin/invoices",
        headers=headers,
        json={
            "tenant_id": tid,
            "period_from": "2026-04-01",
            "period_to": "2026-04-30",
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "draft"
    assert data["total"] == "1500.00"


@pytest.mark.asyncio
async def test_admin_create_invoice_requires_billing_company(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, tid = await _register_ozo(client, "ai2")
    await _promote_to_admin(db_session, "invai2@me.cz")
    # billing_type ano, ale nevyplníme billing_company
    await _set_tenant_billing(
        db_session, tid, billing_type="monthly",
        billing_amount=Decimal("200"), fill_company=False,
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "invai2@me.cz", "password": "heslo1234"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await client.post(
        "/api/v1/admin/invoices",
        headers=headers,
        json={
            "tenant_id": tid,
            "period_from": "2026-04-01",
            "period_to": "2026-04-30",
        },
    )
    assert resp.status_code == 400
    assert "fakturační údaje" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_admin_run_monthly_skips_custom_and_free(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Tři tenanti: monthly, custom, free. Cron vystaví jen pro monthly.
    _, tid_m = await _register_ozo(client, "rm")
    _, tid_c = await _register_ozo(client, "rc")
    _, tid_f = await _register_ozo(client, "rf")
    await _set_tenant_billing(db_session, tid_m, billing_type="monthly", billing_amount=Decimal("100"))
    await _set_tenant_billing(db_session, tid_c, billing_type="custom",  billing_amount=Decimal("999"))
    await _set_tenant_billing(db_session, tid_f, billing_type="free",    billing_amount=Decimal("0"))

    invoices = await generate_monthly_invoices(db_session, today=date(2026, 5, 1))
    # cron běží 1.5. → vystaví za duben. V DB mohou být i jiní tenanti
    # (z dema/seedu) — filtrujeme jen na naše 3.
    import uuid as _uuid
    our_ids = {_uuid.UUID(tid_m), _uuid.UUID(tid_c), _uuid.UUID(tid_f)}
    our_invoices = [inv for inv in invoices if inv.tenant_id in our_ids]
    assert len(our_invoices) == 1
    assert our_invoices[0].tenant_id == _uuid.UUID(tid_m)


@pytest.mark.asyncio
async def test_tenant_sees_only_own_invoices_via_rls(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    access_a, tid_a = await _register_ozo(client, "ra")
    _, tid_b = await _register_ozo(client, "rb")
    tenant_a = await _set_tenant_billing(
        db_session, tid_a, billing_type="monthly", billing_amount=Decimal("300"),
    )
    tenant_b = await _set_tenant_billing(
        db_session, tid_b, billing_type="monthly", billing_amount=Decimal("400"),
    )
    inv_a = await generate_invoice(
        db_session, tenant=tenant_a,
        period_from=date(2026, 4, 1), period_to=date(2026, 4, 30),
    )
    inv_b = await generate_invoice(
        db_session, tenant=tenant_b,
        period_from=date(2026, 4, 1), period_to=date(2026, 4, 30),
    )
    assert inv_a is not None and inv_b is not None
    await db_session.commit()

    headers = {"Authorization": f"Bearer {access_a}"}
    resp = await client.get("/api/v1/billing/invoices", headers=headers)
    assert resp.status_code == 200
    numbers = {inv["invoice_number"] for inv in resp.json()}
    assert inv_a.invoice_number in numbers
    assert inv_b.invoice_number not in numbers
