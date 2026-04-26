"""
Doručení faktury — uložení PDF na disk + odeslání emailem příjemci.

Workflow:
1. `render_and_save_pdf(invoice)` — vyrenderuje PDF a uloží do
   UPLOAD_DIR/invoices/{year}/{number}.pdf, vrátí relativní cestu.
2. `send_invoice_email(invoice, pdf_bytes)` — pošle email s PDF přílohou
   na recipient_snapshot.email (fallback: tenant.billing_email).

Obě operace jsou idempotentní — opakované volání přepíše PDF / pošle nový email.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.email import EmailAttachment, EmailMessage, get_email_sender
from app.core.storage import save_invoice_pdf
from app.models.invoice import Invoice
from app.services.invoice_pdf import render_invoice_pdf


def render_and_save_pdf(invoice: Invoice) -> tuple[bytes, str]:
    """
    Vyrenderuje PDF a uloží jej přes storage backend (Local nebo S3) na cestu
    `invoices/{year}/{number}.pdf`. Vrátí (pdf_bytes, relative_path).
    """
    pdf_bytes = render_invoice_pdf(invoice)
    rel_path = save_invoice_pdf(
        invoice_year=invoice.issued_at.year,
        invoice_number=invoice.invoice_number,
        content=pdf_bytes,
    )
    return pdf_bytes, rel_path


def _build_email_text(invoice: Invoice) -> str:
    issuer_name = invoice.issuer_snapshot.get("issuer_name", "")
    return (
        f"Dobrý den,\n\n"
        f"v příloze posíláme fakturu č. {invoice.invoice_number} "
        f"za období "
        f"{invoice.period_from.strftime('%d.%m.%Y')}–"
        f"{invoice.period_to.strftime('%d.%m.%Y')}.\n\n"
        f"Splatnost: {invoice.due_date.strftime('%d.%m.%Y')}\n"
        f"Částka:    {float(invoice.total):,.2f} {invoice.currency} "
        f"(VS: {invoice.invoice_number})\n\n"
        f"Děkujeme za spolupráci.\n\n"
        f"{issuer_name}"
    ).replace(",", " ")


async def send_invoice_email(
    db: AsyncSession,
    invoice: Invoice,
    pdf_bytes: bytes,
) -> None:
    """
    Odešle email s fakturou. Aktualizuje invoice.sent_at + status='sent'.
    """
    recipient = (
        invoice.recipient_snapshot.get("email")
        or invoice.issuer_snapshot.get("issuer_email")
    )
    if not recipient:
        # Bez emailu nemáme kam poslat — necháme draft
        return

    sender = get_email_sender()
    await sender.send(EmailMessage(
        to=recipient,
        subject=f"Faktura {invoice.invoice_number}",
        body_text=_build_email_text(invoice),
        attachments=[EmailAttachment(
            filename=f"faktura_{invoice.invoice_number}.pdf",
            content=pdf_bytes,
            mime_type="application/pdf",
        )],
    ))

    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))
    invoice.sent_at = datetime.now(UTC)
    if invoice.status == "draft":
        invoice.status = "sent"
    await db.flush()


async def deliver_invoice(db: AsyncSession, invoice: Invoice) -> None:
    """Plný flow: render PDF → ulož → email."""
    pdf_bytes, rel_path = render_and_save_pdf(invoice)
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))
    invoice.pdf_path = rel_path
    await db.flush()
    await send_invoice_email(db, invoice, pdf_bytes)
