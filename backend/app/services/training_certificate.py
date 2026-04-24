"""
Generátor certifikátu o absolvování školení.

Jednoduché PDF s:
- logem firmy (pokud je Tenant.logo_path)
- nadpisem „Certifikát pro školení <title>"
- řádkem „Zaměstnanec <jméno, osobní číslo> úspěšně splnil školení dne <datum>"
- informací o školiteli (OZO BOZP / OZO PO / Zaměstnavatel)
- datumem vytvoření

Volá se přes endpoint GET /trainings/assignments/{id}/certificate.pdf,
který je autenticated → user musí mít přístup k danému assignment
(zaměstnanec jen svoje, OZO/HR všechny).
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from fpdf import FPDF

from app.core.config import get_settings
from app.core.storage import file_exists

if TYPE_CHECKING:
    from app.models.employee import Employee
    from app.models.tenant import Tenant
    from app.models.training import Training, TrainingAssignment

log = logging.getLogger(__name__)

TRAINER_LABEL = {
    "ozo_bozp": "OZO BOZP",
    "ozo_po": "OZO PO",
    "employer": "Zaměstnavatel",
}


class _CertificatePdf(FPDF):
    def __init__(self) -> None:
        super().__init__(orientation="L", unit="mm", format="A4")
        self.set_auto_page_break(auto=True, margin=15)
        # fpdf2 má v sobě unicode font "helvetica" ale pro české znaky
        # potřebujeme Noto / DejaVu. Fallback na vestavěný font s latin-1
        # přepisem — pro MVP stačí, v prod nahradit DejaVuSans.ttf.


def _sanitize(text: str) -> str:
    """fpdf2 default font neumí některé znaky — escape fallback."""
    return text


def generate_certificate_pdf(
    *,
    tenant: Tenant,
    training: Training,
    assignment: TrainingAssignment,
    employee: Employee,
    issuer_name: str | None = None,
) -> bytes:
    """Vrací PDF bytes. issuer_name = jméno osoby která školení vystavila (OZO user)."""
    if assignment.last_completed_at is None:
        raise ValueError("Assignment nebyl dosud splněn")

    pdf = _CertificatePdf()
    pdf.add_page()

    # ── Logo firmy ──────────────────────────────────────────────────────────
    settings = get_settings()
    if tenant.logo_path and file_exists(tenant.logo_path):
        logo_full = Path(settings.upload_dir) / tenant.logo_path
        try:
            pdf.image(str(logo_full), x=15, y=15, h=25)
        except Exception as e:  # noqa: BLE001
            log.warning("Could not embed logo: %s", e)

    # Hlavička firmy (vpravo)
    pdf.set_xy(200, 15)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(80, 6, _sanitize(tenant.name), align="R", new_x="LMARGIN", new_y="NEXT")

    # ── Hlavní nadpis ───────────────────────────────────────────────────────
    pdf.set_y(55)
    pdf.set_font("Helvetica", "B", 26)
    pdf.cell(0, 15, "CERTIFIKÁT", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    pdf.set_font("Helvetica", "", 14)
    pdf.cell(
        0, 10,
        _sanitize(f"o absolvování školení „{training.title}"),
        align="C", new_x="LMARGIN", new_y="NEXT"
    )
    pdf.ln(12)

    # ── Hlavní text ─────────────────────────────────────────────────────────
    emp_name = f"{employee.first_name} {employee.last_name}".strip()
    personal_part = ""
    if employee.personal_number:
        personal_part = f", osobní číslo {employee.personal_number}"

    pdf.set_font("Helvetica", "", 13)
    body_lines = [
        _sanitize(f"Zaměstnanec {emp_name}{personal_part}"),
        _sanitize("úspěšně absolvoval školení"),
        _sanitize(f"„{training.title}"),
        _sanitize(f"dne {assignment.last_completed_at.date().strftime('%d. %m. %Y')}."),
    ]
    for line in body_lines:
        pdf.cell(0, 9, line, align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(15)

    # ── Detail (typ, platnost, školitel) ────────────────────────────────────
    pdf.set_font("Helvetica", "", 11)
    type_labels = {"bozp": "BOZP", "po": "Požární ochrana", "other": "Ostatní"}
    detail = [
        (
            "Typ školení:",
            type_labels.get(training.training_type, training.training_type),
        ),
        ("Platnost:", f"{training.valid_months} měsíců"),
        (
            "Platí do:",
            assignment.valid_until.strftime("%d. %m. %Y")
            if assignment.valid_until
            else "—",
        ),
        ("Školitel:", TRAINER_LABEL.get(training.trainer_kind, training.trainer_kind)),
    ]
    if issuer_name:
        detail.append(("Vystavil:", issuer_name))

    # Vykreslení jako dva sloupce zarovnané uprostřed
    pdf.set_x(60)
    for label, value in detail:
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(40, 7, _sanitize(label), align="R")
        pdf.set_font("Helvetica", "", 11)
        pdf.cell(80, 7, _sanitize(value), new_x="LMARGIN", new_y="NEXT")
        pdf.set_x(60)

    pdf.ln(10)

    # ── Podpisová oblast ────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "", 10)
    pdf.set_y(-35)
    pdf.cell(
        0, 5,
        _sanitize(f"Vystaveno v {tenant.name}"),
        align="C", new_x="LMARGIN", new_y="NEXT",
    )
    pdf.cell(
        0, 5,
        _sanitize(f"Datum vydání: {datetime.now(UTC).date().strftime('%d. %m. %Y')}"),
        align="C", new_x="LMARGIN", new_y="NEXT"
    )

    output = pdf.output()
    # fpdf2 2.x vrací bytearray, 2.7+ bytes — sjednotíme
    return bytes(output)
