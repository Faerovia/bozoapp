"""
Testy pro PDF generování + email delivery + monthly cron task (commit 19b-2).
"""

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.email import EmailMessage
from app.core.security import decode_token
from app.models.tenant import Tenant
from app.models.user import User
from app.services.invoice_delivery import (
    deliver_invoice,
    render_and_save_pdf,
    send_invoice_email,
)
from app.services.invoice_pdf import build_spayd_string, render_invoice_pdf
from app.services.invoicing import generate_invoice


async def _register_ozo(client: AsyncClient, suffix: str) -> tuple[str, str]:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"d{suffix}@me.cz",
            "password": "heslo1234",
            "tenant_name": f"Klient {suffix}",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    payload = decode_token(body["access_token"])
    return body["access_token"], str(payload["tenant_id"])


async def _promote_to_admin(db: AsyncSession, email: str) -> None:
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))
    user = (await db.execute(select(User).where(User.email == email))).scalar_one()
    user.role = "admin"
    user.is_platform_admin = True
    await db.commit()


async def _set_billing(
    db: AsyncSession, tenant_id: str, *, amount: Decimal = Decimal("500"),
) -> Tenant:
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))
    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one()
    tenant.billing_type = "monthly"
    tenant.billing_amount = amount
    tenant.billing_currency = "CZK"
    tenant.billing_company_name = "Klient s.r.o."
    tenant.billing_ico = "12345678"
    tenant.billing_address_street = "Dlouhá 1"
    tenant.billing_address_city = "Praha"
    tenant.billing_address_zip = "11000"
    tenant.billing_email = "fakturace@klient.cz"
    await db.commit()
    return tenant


# ── SPAYD ────────────────────────────────────────────────────────────────────


def test_spayd_string_format() -> None:
    s = build_spayd_string(
        iban="CZ6508000000192000145399",
        amount=990.0,
        currency="CZK",
        variable_symbol="20260001",
        message="Faktura 20260001",
    )
    assert s.startswith("SPD*1.0*")
    assert "ACC:CZ6508000000192000145399" in s
    assert "AM:990.00" in s
    assert "CC:CZK" in s
    assert "X-VS:20260001" in s
    assert "MSG:Faktura+20260001" in s


def test_spayd_strips_iban_spaces() -> None:
    s = build_spayd_string(
        iban="CZ65 0800 0000 1920 0014 5399",
        amount=10,
        currency="CZK",
        variable_symbol="1",
        message="",
    )
    assert "ACC:CZ6508000000192000145399" in s
    assert "MSG:" not in s  # prázdná zpráva neodejde


# ── PDF rendering ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_render_invoice_pdf_returns_pdf_bytes(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, tid = await _register_ozo(client, "pdf1")
    tenant = await _set_billing(db_session, tid)
    invoice = await generate_invoice(
        db_session, tenant=tenant,
        period_from=date(2026, 4, 1), period_to=date(2026, 4, 30),
    )
    assert invoice is not None

    pdf_bytes = render_invoice_pdf(invoice)
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 1000  # rozumná velikost


@pytest.mark.asyncio
async def test_render_and_save_pdf_writes_to_disk(
    client: AsyncClient, db_session: AsyncSession, tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    # Reset settings cache
    from app.core.config import get_settings
    get_settings.cache_clear()

    _, tid = await _register_ozo(client, "pdf2")
    tenant = await _set_billing(db_session, tid)
    invoice = await generate_invoice(
        db_session, tenant=tenant,
        period_from=date(2026, 4, 1), period_to=date(2026, 4, 30),
    )
    assert invoice is not None

    pdf_bytes, rel_path = render_and_save_pdf(invoice)
    assert pdf_bytes.startswith(b"%PDF-")
    assert rel_path.endswith(f"{invoice.invoice_number}.pdf")
    assert (tmp_path / rel_path).exists()

    get_settings.cache_clear()


# ── Email delivery ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_invoice_email_updates_status(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    _, tid = await _register_ozo(client, "se1")
    tenant = await _set_billing(db_session, tid)
    invoice = await generate_invoice(
        db_session, tenant=tenant,
        period_from=date(2026, 4, 1), period_to=date(2026, 4, 30),
    )
    assert invoice is not None

    # Mock sender — chytíme zaslaný EmailMessage a ověříme přílohu
    captured: list[EmailMessage] = []

    class _CapturingSender:
        async def send(self, message: EmailMessage) -> None:
            captured.append(message)

    with patch(
        "app.services.invoice_delivery.get_email_sender",
        return_value=_CapturingSender(),
    ):
        await send_invoice_email(db_session, invoice, b"%PDF-fake")

    assert len(captured) == 1
    msg = captured[0]
    assert msg.to == "fakturace@klient.cz"
    assert invoice.invoice_number in msg.subject
    assert msg.attachments is not None and len(msg.attachments) == 1
    assert msg.attachments[0].filename.endswith(".pdf")
    assert invoice.status == "sent"
    assert invoice.sent_at is not None


@pytest.mark.asyncio
async def test_send_invoice_email_skips_when_no_recipient(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    _, tid = await _register_ozo(client, "se2")
    tenant = await _set_billing(db_session, tid)
    # smaž recipient email
    tenant.billing_email = None
    await db_session.commit()
    invoice = await generate_invoice(
        db_session, tenant=tenant,
        period_from=date(2026, 4, 1), period_to=date(2026, 4, 30),
    )
    assert invoice is not None

    sender_mock = AsyncMock()
    with patch(
        "app.services.invoice_delivery.get_email_sender",
        return_value=sender_mock,
    ):
        await send_invoice_email(db_session, invoice, b"x")

    sender_mock.send.assert_not_called()
    assert invoice.status == "draft"


# ── Admin endpointy: PDF download + send ────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_pdf_endpoint_returns_pdf(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, tid = await _register_ozo(client, "ap1")
    await _promote_to_admin(db_session, "dap1@me.cz")
    tenant = await _set_billing(db_session, tid)
    invoice = await generate_invoice(
        db_session, tenant=tenant,
        period_from=date(2026, 4, 1), period_to=date(2026, 4, 30),
    )
    assert invoice is not None
    await db_session.commit()

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "dap1@me.cz", "password": "heslo1234"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await client.get(f"/api/v1/admin/invoices/{invoice.id}/pdf", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF-")


@pytest.mark.asyncio
async def test_admin_send_endpoint_renders_and_emails(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, tid = await _register_ozo(client, "as1")
    await _promote_to_admin(db_session, "das1@me.cz")
    tenant = await _set_billing(db_session, tid)
    invoice = await generate_invoice(
        db_session, tenant=tenant,
        period_from=date(2026, 4, 1), period_to=date(2026, 4, 30),
    )
    assert invoice is not None
    await db_session.commit()

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "das1@me.cz", "password": "heslo1234"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    captured: list[EmailMessage] = []

    class _Capturing:
        async def send(self, message: EmailMessage) -> None:
            captured.append(message)

    with patch(
        "app.services.invoice_delivery.get_email_sender",
        return_value=_Capturing(),
    ):
        resp = await client.post(
            f"/api/v1/admin/invoices/{invoice.id}/send", headers=headers,
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["sent_to"] == "fakturace@klient.cz"
    assert len(captured) == 1


@pytest.mark.asyncio
async def test_tenant_pdf_endpoint_works(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    access, tid = await _register_ozo(client, "tp1")
    tenant = await _set_billing(db_session, tid)
    invoice = await generate_invoice(
        db_session, tenant=tenant,
        period_from=date(2026, 4, 1), period_to=date(2026, 4, 30),
    )
    assert invoice is not None
    await db_session.commit()

    headers = {"Authorization": f"Bearer {access}"}
    resp = await client.get(f"/api/v1/billing/invoices/{invoice.id}/pdf", headers=headers)
    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF-")


# ── Cron / deliver_invoice plný flow ────────────────────────────────────────


@pytest.mark.asyncio
async def test_deliver_invoice_full_flow(
    client: AsyncClient, db_session: AsyncSession, tmp_path, monkeypatch,
) -> None:
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    from app.core.config import get_settings
    get_settings.cache_clear()

    _, tid = await _register_ozo(client, "dl1")
    tenant = await _set_billing(db_session, tid)
    invoice = await generate_invoice(
        db_session, tenant=tenant,
        period_from=date(2026, 4, 1), period_to=date(2026, 4, 30),
    )
    assert invoice is not None

    captured: list[EmailMessage] = []

    class _Capturing:
        async def send(self, message: EmailMessage) -> None:
            captured.append(message)

    with patch(
        "app.services.invoice_delivery.get_email_sender",
        return_value=_Capturing(),
    ):
        await deliver_invoice(db_session, invoice)

    assert invoice.pdf_path is not None
    assert (tmp_path / invoice.pdf_path).exists()
    assert len(captured) == 1
    assert invoice.status == "sent"

    get_settings.cache_clear()
