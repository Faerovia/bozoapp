"""
Per-employee souhrn všech absolvovaných školení (PDF).

Layout:
┌────────────────────────────────────────────────────────────┐
│ [logo]  PŘEHLED ABSOLVOVANÝCH ŠKOLENÍ                      │
│                                                            │
│ Zaměstnanec: Anna Nováková                                │
│ Osobní číslo: 12345 (pokud je)                            │
│                                                            │
│ ┌──────────────────────────────┬────────────┬────────────┐│
│ │ Název školení                │ Datum      │ Školitel   ││
│ │                              │ absolvování│            ││
│ ├──────────────────────────────┼────────────┼────────────┤│
│ │ BOZP základní                │ 20.4.2026  │ Jan OZO    ││
│ │ Požární ochrana              │ 1.3.2026   │ Petr OZO   ││
│ └──────────────────────────────┴────────────┴────────────┘│
│                                                            │
│ Vystavil: <OZO> dne <datum>                               │
└────────────────────────────────────────────────────────────┘

Zobrazuje JEN podepsaná školení (assignment.is_signed=True).
"""

from __future__ import annotations

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


def render_employee_trainings_pdf(
    *,
    employee: Employee,
    tenant: Tenant,
    rows: list[tuple[TrainingAssignment, Training, User | None]],
    issued_by: User,
    issued_at: datetime,
) -> bytes:
    """
    `rows` = list (assignment, training, trainer_user_or_none) podepsaných
    školení zaměstnance. Caller filtruje podle is_signed.
    """
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    _setup_fonts(pdf)

    # ── Hlavička: logo + nadpis ─────────────────────────────────────────────
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
    pdf.cell(0, 8, "PŘEHLED ABSOLVOVANÝCH ŠKOLENÍ", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # ── Zaměstnanec ─────────────────────────────────────────────────────────
    pdf.set_font("DejaVu", "B", 11)
    pdf.cell(0, 6, f"{employee.first_name} {employee.last_name}",
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "", 10)
    if employee.personal_number:
        pdf.cell(0, 5, f"Osobní číslo: {employee.personal_number}",
                 new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # ── Firma ───────────────────────────────────────────────────────────────
    pdf.set_font("DejaVu", "B", 10)
    pdf.cell(0, 5, "Pořadatel:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "", 10)
    pdf.cell(
        0, 5,
        f"{tenant.billing_company_name or tenant.name}"
        + (f"  (IČO: {tenant.billing_ico})" if tenant.billing_ico else ""),
        new_x="LMARGIN", new_y="NEXT",
    )
    pdf.ln(3)

    # ── Tabulka školení ─────────────────────────────────────────────────────
    col_widths = (90, 35, 60)  # Název, Datum, Školitel
    headers = ("Název školení", "Datum absolvování", "Školitel")

    pdf.set_font("DejaVu", "B", 10)
    pdf.set_fill_color(230, 230, 230)
    for label, w in zip(headers, col_widths, strict=True):
        pdf.cell(w, 7, label, border=1, fill=True, align="C",
                 new_x="RIGHT", new_y="TOP")
    pdf.ln(7)

    pdf.set_font("DejaVu", "", 10)
    if not rows:
        pdf.set_text_color(150, 150, 150)
        pdf.cell(
            sum(col_widths), 10,
            "(zaměstnanec zatím nemá žádné platně absolvované školení)",
            border=1, align="C", new_x="LMARGIN", new_y="NEXT",
        )
        pdf.set_text_color(0, 0, 0)
    else:
        for assignment, training, trainer in rows:
            date_str = (
                assignment.signed_at.strftime("%d.%m.%Y")
                if assignment.signed_at else "—"
            )
            # Trainer může mít obě pole NULL (legacy data) → použij "—"
            if trainer is not None:
                trainer_name = trainer.full_name or trainer.email or "—"
            else:
                trainer_name = "—"
            title_text = (training.title or "")[:60]
            pdf.cell(col_widths[0], 7, title_text,
                     border=1, new_x="RIGHT", new_y="TOP")
            pdf.cell(col_widths[1], 7, date_str,
                     border=1, align="C", new_x="RIGHT", new_y="TOP")
            pdf.cell(col_widths[2], 7, trainer_name,
                     border=1, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # ── Pata ────────────────────────────────────────────────────────────────
    pdf.set_font("DejaVu", "", 10)
    issuer_name = issued_by.full_name or issued_by.email
    pdf.cell(
        0, 5,
        f"Vystavil: {issuer_name}     "
        f"Dne: {issued_at.strftime('%d.%m.%Y')}",
        new_x="LMARGIN", new_y="NEXT",
    )

    output = pdf.output()
    return bytes(output)
