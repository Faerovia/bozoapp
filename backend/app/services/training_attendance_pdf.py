"""
Prezenční listina pro školení (PDF, A4 portrait).

Layout:
┌─────────────────────────────────────────────────────────────────────┐
│ [logo]   PREZENČNÍ LISTINA — <název školení>                        │
│                                                                      │
│ Firma: ABC s.r.o. (IČO: 12345678)                                   │
│ Adresa: Dlouhá 1, Praha                                             │
│ Délka školení: 2 hod          Znalosti ověřeny testem: ANO          │
│                                                                      │
│ OSNOVA / NÁPLŇ ŠKOLENÍ:                                             │
│ <multiline text z Training.outline_text>                            │
│                                                                      │
│ ┌─────────────────────────────┬──────────┬──────────┬──────────┐    │
│ │ Jméno a příjmení            │ Datum    │ Podpis   │ Podpis   │    │
│ │                             │ školení  │ školeného│ školitele│    │
│ ├─────────────────────────────┼──────────┼──────────┼──────────┤    │
│ │ Anna Nováková                │ 20.4.2026│ [PNG]   │ [PNG]    │    │
│ │ Jan Svoboda                 │ 20.4.2026│ [PNG]   │ [PNG]    │    │
│ └─────────────────────────────┴──────────┴──────────┴──────────┘    │
│                                                                      │
│ Vystavil: <OZO jméno> dne <datum>                                   │
└─────────────────────────────────────────────────────────────────────┘

Pouze podepsaní zaměstnanci (assignment.is_signed=True). Bez podpisu
školení neplatí — auditor by měl vidět jen finalizované záznamy.
"""

from __future__ import annotations

import base64
import io
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from fpdf import FPDF

from app.core.config import get_settings
from app.core.storage import file_exists
from app.services.export_pdf import _font_path

if TYPE_CHECKING:
    from app.models.employee import Employee
    from app.models.tenant import Tenant
    from app.models.training import Training, TrainingAssignment
    from app.models.user import User

log = logging.getLogger(__name__)


def _setup_fonts(pdf: FPDF) -> None:
    pdf.add_font("DejaVu", "", _font_path("DejaVuSans.ttf"))
    pdf.add_font("DejaVu", "B", _font_path("DejaVuSans-Bold.ttf"))
    pdf.set_font("DejaVu", "", 10)


def _decode_signature_image(b64: str | None) -> bytes | None:
    """Přijímá 'data:image/png;base64,...' nebo plain base64. Vrátí PNG bytes."""
    if not b64:
        return None
    if b64.startswith("data:"):
        try:
            _, b64 = b64.split(",", 1)
        except ValueError:
            return None
    try:
        return base64.b64decode(b64)
    except Exception:
        return None


def render_attendance_list_pdf(
    *,
    training: Training,
    tenant: Tenant,
    trainer: User | None,
    signed_assignments: list[tuple[TrainingAssignment, Employee]],
    issued_at: datetime,
) -> bytes:
    """
    Vyrenderuje prezenční listinu jako PDF bytes.
    `signed_assignments` musí obsahovat jen podepsané (caller ji filtruje).
    """
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    _setup_fonts(pdf)

    # ── Hlavička: logo + název ──────────────────────────────────────────────
    settings = get_settings()
    logo_y = pdf.get_y()
    if tenant.logo_path and file_exists(tenant.logo_path):
        try:
            logo_path = Path(settings.upload_dir) / tenant.logo_path
            pdf.image(str(logo_path), x=10, y=logo_y, h=15)
            pdf.set_xy(30, logo_y + 2)
        except Exception:
            log.warning("Failed to embed tenant logo: %s", tenant.logo_path)

    pdf.set_font("DejaVu", "B", 16)
    pdf.cell(0, 8, "PREZENČNÍ LISTINA", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "B", 12)
    pdf.cell(0, 7, training.title, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # ── Údaje firmy ─────────────────────────────────────────────────────────
    pdf.set_font("DejaVu", "B", 10)
    pdf.cell(0, 5, "Pořadatel školení:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "", 10)

    company_name = tenant.billing_company_name or tenant.name
    pdf.cell(0, 5, company_name, new_x="LMARGIN", new_y="NEXT")
    if tenant.billing_ico:
        pdf.cell(0, 5, f"IČO: {tenant.billing_ico}", new_x="LMARGIN", new_y="NEXT")
    addr_parts = [
        tenant.billing_address_street or "",
        " ".join(p for p in [
            tenant.billing_address_zip or "",
            tenant.billing_address_city or "",
        ] if p).strip(),
    ]
    addr_line = ", ".join(p for p in addr_parts if p)
    if addr_line:
        pdf.cell(0, 5, addr_line, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # ── Metadata školení ────────────────────────────────────────────────────
    duration_str = (
        f"{training.duration_hours:g} hod" if training.duration_hours else "—"
    )
    test_str = "ANO" if training.knowledge_test_required else "NE"
    pdf.set_font("DejaVu", "", 10)
    pdf.cell(60, 5, f"Délka školení: {duration_str}", new_x="RIGHT", new_y="TOP")
    pdf.cell(0, 5, f"Znalosti ověřeny testem: {test_str}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # ── Osnova ──────────────────────────────────────────────────────────────
    pdf.set_font("DejaVu", "B", 10)
    pdf.cell(0, 5, "Osnova / náplň školení:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "", 9)
    if training.outline_text:
        pdf.multi_cell(0, 4, training.outline_text)
    else:
        pdf.set_text_color(150, 150, 150)
        pdf.cell(0, 5, "(osnova nebyla vyplněna)", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    # ── Tabulka prezenčky ───────────────────────────────────────────────────
    col_widths = (75, 25, 40, 40)  # Jméno, Datum, Podpis školeného, Podpis školitele
    headers = (
        "Jméno a příjmení",
        "Datum školení",
        "Podpis školeného",
        "Podpis školitele",
    )

    pdf.set_font("DejaVu", "B", 10)
    pdf.set_fill_color(230, 230, 230)
    for label, w in zip(headers, col_widths, strict=True):
        pdf.cell(w, 7, label, border=1, fill=True, align="C", new_x="RIGHT", new_y="TOP")
    pdf.ln(7)

    pdf.set_font("DejaVu", "", 10)

    # Předgenerovaný image podpisu školitele (pokud má v profilu — zatím ho
    # tam nemáme, dáme jen jméno textem)
    trainer_name = (
        (trainer.full_name or trainer.email) if trainer else "—"
    )

    row_h = 18  # výška řádku — místo na canvas image
    for assignment, employee in signed_assignments:
        full_name = f"{employee.first_name} {employee.last_name}"
        date_str = (
            assignment.signed_at.strftime("%d.%m.%Y")
            if assignment.signed_at else "—"
        )

        x_start = pdf.get_x()
        y_start = pdf.get_y()

        # Jméno (text)
        pdf.cell(col_widths[0], row_h, full_name, border=1, new_x="RIGHT", new_y="TOP")
        # Datum
        pdf.cell(col_widths[1], row_h, date_str, border=1, align="C", new_x="RIGHT", new_y="TOP")
        # Podpis školeného (canvas PNG)
        sig_x = pdf.get_x()
        sig_y = pdf.get_y()
        pdf.cell(col_widths[2], row_h, "", border=1, new_x="RIGHT", new_y="TOP")
        sig_bytes = _decode_signature_image(assignment.signature_image)
        if sig_bytes:
            try:
                pdf.image(io.BytesIO(sig_bytes), x=sig_x + 1, y=sig_y + 1,
                          w=col_widths[2] - 2, h=row_h - 2,
                          keep_aspect_ratio=True)
            except Exception:
                log.warning("Failed to embed signature for assignment %s", assignment.id)
        # Podpis školitele (placeholder text — později canvas z user profilu)
        pdf.cell(col_widths[3], row_h, trainer_name, border=1,
                 align="C", new_x="LMARGIN", new_y="NEXT")
        # x_start, y_start unused (cells už pohnuly s X)
        _ = (x_start, y_start)

    # Pokud žádné podepsané — info
    if not signed_assignments:
        pdf.set_text_color(150, 150, 150)
        pdf.set_font("DejaVu", "", 10)
        pdf.cell(
            sum(col_widths), 10,
            "(zatím žádný zaměstnanec školení nepodepsal)",
            border=1, align="C", new_x="LMARGIN", new_y="NEXT",
        )
        pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    # ── Pata: vystavil / dne ────────────────────────────────────────────────
    pdf.set_font("DejaVu", "", 10)
    pdf.cell(
        0, 5,
        f"Vystavil: {trainer_name}     "
        f"Dne: {issued_at.strftime('%d.%m.%Y')}",
        new_x="LMARGIN", new_y="NEXT",
    )

    output = pdf.output()
    return bytes(output)
