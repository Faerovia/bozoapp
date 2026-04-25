"""
Generování faktury jako PDF (fpdf2) s QR Pay-by-Square (CZ standard SPAYD).

Layout (A4):
┌─────────────────────────────────────────────────────────────┐
│ Vystavovatel (logo+adresa)         FAKTURA č. 20260001     │
│                                                             │
│ Odběratel:                          Vystavena: 01.05.2026   │
│   Klient s.r.o.                     Splatná:  15.05.2026   │
│   Dlouhá 1, Praha                   Období:   04/2026      │
│   IČO: 12345678                                             │
│                                                             │
│ ┌──────────────────────────────────────────────────────┐   │
│ │ Popis             | Mn. | Cena j. | Celkem           │   │
│ │ Předplatné 04/26  | 1   | 990     | 990 Kč           │   │
│ └──────────────────────────────────────────────────────┘   │
│                              Celkem k úhradě: 990 Kč        │
│                                                             │
│ Bankovní spojení: 123/0100        ┌──────┐                  │
│ Variabilní symbol: 20260001       │ QR   │ ← Pay-by-Square │
│                                   └──────┘                  │
└─────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import io
from typing import Any

from fpdf import FPDF

from app.models.invoice import Invoice
from app.services.export_pdf import _font_path  # reuse DejaVu finder


# ── Pay-by-Square SPAYD generator ────────────────────────────────────────────


def build_spayd_string(
    *,
    iban: str,
    amount: float,
    currency: str,
    variable_symbol: str,
    message: str,
) -> str:
    """
    Vrátí SPAYD řetězec pro QR platbu (česká norma Short Payment Descriptor).
    Příklad: SPD*1.0*ACC:CZ65...*AM:990.00*CC:CZK*X-VS:20260001*MSG:Faktura
    """
    parts = [
        "SPD*1.0",
        f"ACC:{iban.replace(' ', '')}",
        f"AM:{amount:.2f}",
        f"CC:{currency}",
        f"X-VS:{variable_symbol}",
    ]
    if message:
        # SPAYD MSG max 60 chars, ASCII-only, '+' místo mezer
        cleaned = message.replace(" ", "+")[:60]
        parts.append(f"MSG:{cleaned}")
    return "*".join(parts)


def render_qr_png(spayd: str) -> bytes:
    """Vrátí PNG bytes s QR kódem dané SPAYD platby."""
    import qrcode

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8, border=2,
    )
    qr.add_data(spayd)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ── PDF rendering ────────────────────────────────────────────────────────────


class _InvoicePDF(FPDF):
    def header(self) -> None:
        # bez globálního headeru — vykreslíme manuálně
        return

    def footer(self) -> None:
        # ani footer
        return


def _setup_fonts(pdf: FPDF) -> None:
    pdf.add_font("DejaVu", "", _font_path("DejaVuSans.ttf"))
    pdf.add_font("DejaVu", "B", _font_path("DejaVuSans-Bold.ttf"))
    pdf.set_font("DejaVu", "", 10)


def _addr_lines(snap: dict[str, Any], *, prefix_name: bool) -> list[str]:
    lines: list[str] = []
    if prefix_name and snap.get("name"):
        lines.append(str(snap["name"]))
    if snap.get("issuer_name") and not prefix_name:
        lines.append(str(snap["issuer_name"]))
    street = snap.get("address_street") or snap.get("issuer_address_street") or ""
    city = snap.get("address_city") or snap.get("issuer_address_city") or ""
    zip_ = snap.get("address_zip") or snap.get("issuer_address_zip") or ""
    if street:
        lines.append(str(street))
    city_line = " ".join(p for p in [str(zip_), str(city)] if p).strip()
    if city_line:
        lines.append(city_line)
    ico = snap.get("ico") or snap.get("issuer_ico") or ""
    dic = snap.get("dic") or snap.get("issuer_dic") or ""
    if ico:
        lines.append(f"IČO: {ico}")
    if dic:
        lines.append(f"DIČ: {dic}")
    return lines


def render_invoice_pdf(invoice: Invoice) -> bytes:
    """Vrátí PDF faktury jako bytes."""
    pdf = _InvoicePDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    _setup_fonts(pdf)

    issuer = invoice.issuer_snapshot
    recipient = invoice.recipient_snapshot
    is_vat_payer = bool(issuer.get("is_vat_payer"))

    # ── Hlavička: vystavovatel + číslo faktury ───────────────────────────────
    pdf.set_font("DejaVu", "B", 16)
    title = "FAKTURA – DAŇOVÝ DOKLAD" if is_vat_payer else "FAKTURA"
    pdf.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("DejaVu", "B", 12)
    pdf.cell(0, 8, f"č. {invoice.invoice_number}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # ── Vystavovatel + Příjemce vedle sebe ──────────────────────────────────
    col_w = 90
    y_start = pdf.get_y()

    pdf.set_font("DejaVu", "B", 10)
    pdf.cell(col_w, 6, "Vystavovatel:", new_x="RIGHT", new_y="TOP")
    pdf.cell(col_w, 6, "Odběratel:", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("DejaVu", "", 10)
    issuer_lines = _addr_lines(issuer, prefix_name=False)
    recipient_lines = _addr_lines(recipient, prefix_name=True)
    max_lines = max(len(issuer_lines), len(recipient_lines))

    for i in range(max_lines):
        x_left = pdf.l_margin
        pdf.set_xy(x_left, y_start + 6 + i * 5)
        if i < len(issuer_lines):
            pdf.cell(col_w, 5, issuer_lines[i], new_x="RIGHT", new_y="TOP")
        else:
            pdf.cell(col_w, 5, "", new_x="RIGHT", new_y="TOP")
        if i < len(recipient_lines):
            pdf.cell(col_w, 5, recipient_lines[i], new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.cell(col_w, 5, "", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # ── Datumy ───────────────────────────────────────────────────────────────
    def _row(label: str, value: str) -> None:
        pdf.set_font("DejaVu", "B", 10)
        pdf.cell(45, 6, label, new_x="RIGHT", new_y="TOP")
        pdf.set_font("DejaVu", "", 10)
        pdf.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")

    _row("Datum vystavení:", invoice.issued_at.strftime("%d.%m.%Y"))
    if is_vat_payer:
        _row("DUZP:", invoice.issued_at.strftime("%d.%m.%Y"))
    _row("Datum splatnosti:", invoice.due_date.strftime("%d.%m.%Y"))
    _row(
        "Fakturační období:",
        f"{invoice.period_from.strftime('%d.%m.%Y')} – "
        f"{invoice.period_to.strftime('%d.%m.%Y')}",
    )
    _row("Variabilní symbol:", invoice.invoice_number)
    pdf.ln(4)

    # ── Tabulka položek ─────────────────────────────────────────────────────
    pdf.set_font("DejaVu", "B", 10)
    pdf.set_fill_color(230, 230, 230)
    headers = [("Popis", 95), ("Mn.", 15), ("Cena j.", 35), ("Celkem", 35)]
    for label, w in headers:
        pdf.cell(w, 7, label, border=1, fill=True, new_x="RIGHT", new_y="TOP")
    pdf.ln(7)

    pdf.set_font("DejaVu", "", 10)
    for item in invoice.items:
        desc = str(item.get("description", ""))
        qty = item.get("quantity", 1)
        unit_price = float(item.get("unit_price", 0))
        total = float(item.get("total", 0))
        pdf.cell(95, 6, desc[:55], border=1, new_x="RIGHT", new_y="TOP")
        pdf.cell(15, 6, str(qty), border=1, align="R", new_x="RIGHT", new_y="TOP")
        pdf.cell(
            35, 6, f"{unit_price:,.2f} {invoice.currency}".replace(",", " "),
            border=1, align="R", new_x="RIGHT", new_y="TOP",
        )
        pdf.cell(
            35, 6, f"{total:,.2f} {invoice.currency}".replace(",", " "),
            border=1, align="R", new_x="LMARGIN", new_y="NEXT",
        )
    pdf.ln(2)

    # ── Součty ───────────────────────────────────────────────────────────────
    if is_vat_payer:
        _row("Základ:", f"{float(invoice.subtotal):,.2f} {invoice.currency}".replace(",", " "))
        _row(
            f"DPH {float(invoice.vat_rate):.0f} %:",
            f"{float(invoice.vat_amount):,.2f} {invoice.currency}".replace(",", " "),
        )
    pdf.set_font("DejaVu", "B", 12)
    pdf.cell(45, 8, "Celkem k úhradě:", new_x="RIGHT", new_y="TOP")
    pdf.cell(
        0, 8,
        f"{float(invoice.total):,.2f} {invoice.currency}".replace(",", " "),
        new_x="LMARGIN", new_y="NEXT",
    )
    pdf.ln(6)

    # ── Bankovní spojení + QR ───────────────────────────────────────────────
    pdf.set_font("DejaVu", "B", 10)
    pdf.cell(0, 6, "Platba převodem:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "", 10)

    bank_account = str(issuer.get("issuer_bank_account") or "")
    bank_name = str(issuer.get("issuer_bank_name") or "")
    iban = str(issuer.get("issuer_iban") or "")
    if bank_account:
        _row("Číslo účtu:", f"{bank_account}{f' ({bank_name})' if bank_name else ''}")
    if iban:
        _row("IBAN:", iban)
    _row("Variabilní symbol:", invoice.invoice_number)

    # QR Pay-by-Square
    if iban:
        spayd = build_spayd_string(
            iban=iban,
            amount=float(invoice.total),
            currency=invoice.currency,
            variable_symbol=invoice.invoice_number,
            message=f"Faktura {invoice.invoice_number}",
        )
        try:
            qr_png = render_qr_png(spayd)
            qr_buf = io.BytesIO(qr_png)
            pdf.image(qr_buf, x=160, y=pdf.get_y() - 24, w=35, h=35)
        except Exception:
            pass  # QR je nice-to-have; selhání nesmí shodit fakturu

    pdf.ln(8)

    # ── Pata ─────────────────────────────────────────────────────────────────
    if invoice.notes:
        pdf.set_font("DejaVu", "", 9)
        pdf.multi_cell(0, 5, str(invoice.notes))
        pdf.ln(2)

    if not is_vat_payer:
        pdf.set_font("DejaVu", "", 9)
        pdf.cell(
            0, 5,
            "Nejsem plátcem DPH.",
            new_x="LMARGIN", new_y="NEXT",
        )
    pdf.set_font("DejaVu", "", 9)
    pdf.cell(0, 5, "Děkujeme za spolupráci.", new_x="LMARGIN", new_y="NEXT")

    output: Any = pdf.output()
    return bytes(output)
