"""
Generátor žádanky o lékařskou prohlídku pro pracovnělékařské služby (PLS).

Žádanka je dokument odesílaný lékaři PLS, kterým zaměstnavatel požaduje
provedení konkrétní pracovnělékařské prohlídky daného zaměstnance.

Obsah žádanky (vyhláška 79/2013 Sb. + běžná praxe):
  - Hlavička: zaměstnavatel (název, IČO, adresa, kontaktní osoba OZO)
  - Údaje o zaměstnanci: jméno, RČ / datum narození, adresa
  - Pracovní pozice: název, kategorie práce, popis činnosti
  - Účel prohlídky: vstupní / periodická / výstupní / mimořádná / odborná (specialty)
  - Rizikové faktory práce (krátký výčet z RFA)
  - Datum vystavení, podpis OZO/zaměstnavatele
  - Místo pro razítko a podpis lékaře
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from fpdf import FPDF

if TYPE_CHECKING:
    from app.models.employee import Employee
    from app.models.job_position import JobPosition
    from app.models.medical_exam import MedicalExam


def _font_path(filename: str) -> str:
    candidates = [
        Path("/usr/share/fonts/truetype/dejavu") / filename,
        Path("/usr/share/fonts/dejavu") / filename,
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    try:
        import fpdf as _fpdf
        pkg_path = Path(_fpdf.__file__).parent / "fonts" / filename
        if pkg_path.exists():
            return str(pkg_path)
    except Exception:
        pass
    raise FileNotFoundError(
        f"Font {filename} nenalezen. apt-get install fonts-dejavu-core"
    )


_EXAM_TYPE_LABELS = {
    "vstupni": "Vstupní (před nástupem)",
    "periodicka": "Periodická",
    "vystupni": "Výstupní",
    "mimoradna": "Mimořádná",
    "odborna": "Odborná",
}


def _fmt_date(d: date | None) -> str:
    return d.strftime("%d.%m.%Y") if d else "—"


class _ReferralPDF(FPDF):
    FONT = "DejaVu"
    PAGE_W = 180

    def setup_fonts(self) -> None:
        self.add_font(self.FONT, style="", fname=_font_path("DejaVuSans.ttf"))
        self.add_font(self.FONT, style="B", fname=_font_path("DejaVuSans-Bold.ttf"))

    def section(self, text: str) -> None:
        self.set_font(self.FONT, style="B", size=10)
        self.set_fill_color(220, 230, 245)
        self.cell(self.PAGE_W, 7, text, fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def field(self, label: str, value: str, label_w: int = 60) -> None:
        self.set_font(self.FONT, style="B", size=9)
        self.cell(label_w, 6, label + ":", new_x="RIGHT", new_y="TOP")
        self.set_font(self.FONT, style="", size=9)
        self.cell(self.PAGE_W - label_w, 6, value or "—", new_x="LMARGIN", new_y="NEXT")

    def multiline(self, label: str, value: str) -> None:
        self.set_font(self.FONT, style="B", size=9)
        self.cell(self.PAGE_W, 6, label + ":", new_x="LMARGIN", new_y="NEXT")
        self.set_font(self.FONT, style="", size=9)
        self.multi_cell(self.PAGE_W, 5, value or "—")
        self.ln(1)

    def signature_box(
        self, label: str, name: str | None = None, *, with_stamp: bool = False,
    ) -> None:
        if self.get_y() + 32 > self.h - self.b_margin:
            self.add_page()
        self.set_font(self.FONT, style="B", size=9)
        self.cell(self.PAGE_W, 5, label, new_x="LMARGIN", new_y="NEXT")
        if name:
            self.set_font(self.FONT, style="", size=9)
            self.cell(self.PAGE_W, 5, name, new_x="LMARGIN", new_y="NEXT")
        # Volné místo
        self.ln(15)
        # Linka přes celou šířku
        x1 = self.l_margin
        x2 = self.l_margin + self.PAGE_W
        ly = self.get_y()
        self.set_draw_color(80, 80, 80)
        self.line(x1, ly, x2, ly)
        # Popisky pod čarou
        self.set_font(self.FONT, style="", size=7)
        self.set_text_color(120, 120, 120)
        self.cell(
            self.PAGE_W, 4,
            "Podpis a razítko" if with_stamp else "Podpis",
            align="C", new_x="LMARGIN", new_y="NEXT",
        )
        self.set_text_color(0, 0, 0)
        self.ln(4)


def generate_referral_pdf(
    exam: MedicalExam,
    employee: Employee,
    position: JobPosition | None,
    tenant_name: str,
    tenant_address: str | None = None,
    risk_factors: str | None = None,
    contact_person: str | None = None,
    specialty_label: str | None = None,
) -> bytes:
    """
    Vygeneruje žádanku o lékařskou prohlídku pro PLS.

    Args:
        exam:           záznam medical_exam (typicky čerstvě vytvořený draft)
        employee:       zaměstnanec
        position:       jeho pracovní pozice (může být None)
        tenant_name:    název zaměstnavatele
        tenant_address: adresa zaměstnavatele (volitelné)
        risk_factors:   stručný popis rizik z RFA (volitelné)
        contact_person: jméno OZO / kontaktní osoby
        specialty_label: lidsky čitelný název odborné prohlídky
    """
    pdf = _ReferralPDF(format="A4")
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.setup_fonts()
    pdf.add_page()

    # Hlavička
    pdf.set_font(_ReferralPDF.FONT, style="B", size=15)
    pdf.cell(
        _ReferralPDF.PAGE_W, 9,
        "ŽÁDANKA O LÉKAŘSKOU PROHLÍDKU",
        align="C", new_x="LMARGIN", new_y="NEXT",
    )
    pdf.set_font(_ReferralPDF.FONT, style="", size=8)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(
        _ReferralPDF.PAGE_W, 4,
        "(podle zákona č. 373/2011 Sb. a vyhlášky č. 79/2013 Sb.)",
        align="C", new_x="LMARGIN", new_y="NEXT",
    )
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    # 1. Zaměstnavatel
    pdf.section("1.  ZAMĚSTNAVATEL")
    pdf.field("Název", tenant_name)
    if tenant_address:
        pdf.field("Adresa", tenant_address)
    if contact_person:
        pdf.field("Kontaktní osoba", contact_person)
    pdf.field("Datum vystavení", _fmt_date(date.today()))
    pdf.ln(3)

    # 2. Zaměstnanec
    pdf.section("2.  ÚDAJE O ZAMĚSTNANCI")
    pdf.field("Jméno a příjmení", f"{employee.first_name} {employee.last_name}".strip())
    if employee.personal_id:
        pdf.field("Rodné číslo", employee.personal_id)
    addr_parts = [
        employee.address_street, employee.address_zip, employee.address_city,
    ]
    addr = ", ".join(p for p in addr_parts if p)
    if addr:
        pdf.field("Adresa", addr)
    pdf.ln(3)

    # 3. Pracovní pozice
    pdf.section("3.  PRACOVNÍ POZICE A PODMÍNKY")
    if position:
        pdf.field("Název pozice", position.name)
        if position.work_category:
            pdf.field("Kategorie práce", position.work_category)
        if position.description:
            pdf.multiline("Popis činnosti", position.description)
    else:
        pdf.field("Pozice", "neuvedeno")
    if risk_factors:
        pdf.multiline("Rizikové faktory práce", risk_factors)
    pdf.ln(2)

    # 4. Účel prohlídky
    pdf.section("4.  ÚČEL PROHLÍDKY")
    purpose = _EXAM_TYPE_LABELS.get(exam.exam_type, exam.exam_type)
    pdf.field("Typ prohlídky", purpose)
    if exam.exam_category == "odborna":
        pdf.field("Specializace", specialty_label or (exam.specialty or "—"))
    if exam.notes:
        pdf.multiline("Doplňující informace", exam.notes)
    pdf.ln(4)

    # 5. Žádost
    pdf.set_font(_ReferralPDF.FONT, style="", size=9)
    pdf.multi_cell(
        _ReferralPDF.PAGE_W, 5,
        "Žádáme o provedení výše uvedené pracovnělékařské prohlídky a vystavení "
        "lékařského posudku o zdravotní způsobilosti zaměstnance k práci.",
    )
    pdf.ln(6)

    # Podpisy
    pdf.signature_box("Za zaměstnavatele:", contact_person)
    pdf.signature_box("Posuzující lékař:", with_stamp=True)

    # Patička
    pdf.set_font(_ReferralPDF.FONT, style="", size=7)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(
        _ReferralPDF.PAGE_W, 5,
        f"Vystaveno: {datetime.now().strftime('%d.%m.%Y %H:%M')}  |  ID prohlídky: {exam.id}",
        align="C", new_x="LMARGIN", new_y="NEXT",
    )

    return bytes(pdf.output())
