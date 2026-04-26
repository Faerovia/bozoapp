"""
PDF generátor pro Záznam o pracovním úrazu.

Používá fpdf2 s DejaVu fonty (součást balíčku) pro podporu češtiny.
Formát A4, strukturovaný do sekcí odpovídajících NV 201/2010 Sb.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from fpdf import FPDF

if TYPE_CHECKING:
    from app.models.accident_report import AccidentReport


def _font_path(filename: str) -> str:
    """
    Najde DejaVu TTF font. Prohledává v pořadí:
    1. Systémové fonty Ubuntu/Debian (fonts-dejavu-core)
    2. Fallback na FPDF_FONT_DIR (starší verze fpdf2 fonty bundlují)
    """
    candidates = [
        Path("/usr/share/fonts/truetype/dejavu") / filename,
        Path("/usr/share/fonts/dejavu") / filename,
    ]
    for path in candidates:
        if path.exists():
            return str(path)

    # Fallback: fpdf2 package (starší verze bundlují DejaVu)
    try:
        import fpdf as _fpdf
        pkg_path = Path(_fpdf.__file__).parent / "fonts" / filename
        if pkg_path.exists():
            return str(pkg_path)
    except Exception:
        pass

    raise FileNotFoundError(
        f"Font {filename} nenalezen. "
        "Nainstalujte: apt-get install fonts-dejavu-core"
    )


def _fmt_date(d: date | None) -> str:
    return d.strftime("%d.%m.%Y") if d else "—"


def _fmt_bool(b: bool) -> str:
    return "Ano" if b else "Ne"


def _fmt_test_result(result: str | None) -> str:
    if result is None:
        return "—"
    return "Negativní" if result == "negative" else "Pozitivní"


class _ReportPDF(FPDF):
    """FPDF subclass se sdíleným formátováním."""

    FONT = "DejaVu"
    PAGE_W = 180  # šířka obsahu při margin 15mm

    def setup_fonts(self) -> None:
        self.add_font(self.FONT, style="", fname=_font_path("DejaVuSans.ttf"))
        self.add_font(self.FONT, style="B", fname=_font_path("DejaVuSans-Bold.ttf"))

    def section_heading(self, text: str) -> None:
        self.set_font(self.FONT, style="B", size=10)
        self.set_fill_color(210, 225, 240)
        self.cell(self.PAGE_W, 7, text, fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def field_row(self, label: str, value: str, label_w: int = 65) -> None:
        """
        Label vlevo (single line) + value vpravo s automatickým zalamováním
        přes multi_cell. Pokud se value vejde na jeden řádek, výška = 6 mm.
        Pokud se zalomí, výška se přizpůsobí.
        """
        self.set_font(self.FONT, style="B", size=9)
        # Záznam start Y
        start_y = self.get_y()
        start_x = self.get_x()
        # Label (single line)
        self.cell(label_w, 6, label + ":", new_x="RIGHT", new_y="TOP")
        # Value — multi_cell pro automatické zalamování
        self.set_font(self.FONT, style="", size=9)
        value_x = self.get_x()
        value_w = self.PAGE_W - label_w
        self.multi_cell(value_w, 6, value or "—",
                        new_x="LMARGIN", new_y="NEXT")
        # Pokud multi_cell vykreslil víc řádků, kurzor je už pod value.
        # Zarovnáme na začátek dalšího řádku.
        end_y = self.get_y()
        # Pro single-line value se chování nemění (end_y = start_y + 6)
        _ = (start_y, start_x, value_x, end_y)

    def multiline_field(self, label: str, value: str) -> None:
        self.set_font(self.FONT, style="B", size=9)
        self.cell(self.PAGE_W, 6, label + ":", new_x="LMARGIN", new_y="NEXT")
        self.set_font(self.FONT, style="", size=9)
        self.multi_cell(self.PAGE_W, 5, value or "—")
        self.ln(1)

    def signature_block(self, label: str, name: str | None, signed_at: date | None) -> None:
        """
        Vykreslí blok pro podpis s velkým prostorem (~22 mm na výšku).
        Layout:
          [Role:           ] [Jméno:                       ] [Datum: DD.MM.RRRR]
          .................................................................. ← podpisová linka
          (prostor ~16 mm pro vlastní rukopisný podpis)
        """
        # Pokud by se nový blok rozdělil přes konec stránky, nejdřív přejdi na novou
        if self.get_y() + 28 > self.h - self.b_margin:
            self.add_page()

        # Hlavička bloku — role, jméno, datum
        self.set_font(self.FONT, style="B", size=9)
        self.cell(55, 6, label + ":", new_x="RIGHT", new_y="TOP")
        self.set_font(self.FONT, style="", size=9)
        self.cell(85, 6, name or "—", new_x="RIGHT", new_y="TOP")
        self.cell(40, 6, "Datum: " + _fmt_date(signed_at), new_x="LMARGIN", new_y="NEXT")

        # Prázdný prostor pro podpis (~16 mm)
        sig_top = self.get_y() + 1
        self.ln(16)

        # Podpisová linka přes celou šířku obsahu
        x1 = self.l_margin
        x2 = self.l_margin + self.PAGE_W
        line_y = self.get_y()
        self.set_draw_color(80, 80, 80)
        self.line(x1, line_y, x2, line_y)

        # Popisek pod čarou
        self.set_font(self.FONT, style="", size=7)
        self.set_text_color(120, 120, 120)
        self.ln(0.5)
        self.cell(self.PAGE_W, 4, "Podpis", align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        # Padding mezi bloky
        self.ln(3)
        # sig_top je deklarován pro budoucí rozšíření (např. razítko)
        _ = sig_top


def generate_accident_report_pdf(report: AccidentReport, tenant_name: str) -> bytes:
    """
    Vygeneruje PDF záznamu o pracovním úrazu.

    Args:
        report:       ORM objekt AccidentReport
        tenant_name:  Název tenanta (zaměstnavatele) pro hlavičku

    Returns:
        PDF jako bytes
    """
    pdf = _ReportPDF(format="A4")
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.setup_fonts()
    pdf.add_page()

    # ── Hlavička ─────────────────────────────────────────────────────────────
    pdf.set_font(_ReportPDF.FONT, style="B", size=15)
    pdf.cell(
        _ReportPDF.PAGE_W, 10,
        "ZÁZNAM O PRACOVNÍM ÚRAZU",
        align="C", new_x="LMARGIN", new_y="NEXT",
    )
    pdf.set_font(_ReportPDF.FONT, style="", size=9)
    pdf.cell(
        _ReportPDF.PAGE_W, 5,
        f"Zaměstnavatel: {tenant_name}",
        align="C", new_x="LMARGIN", new_y="NEXT",
    )

    from datetime import datetime
    pdf.cell(
        _ReportPDF.PAGE_W, 5,
        f"Datum sestavení záznamu: {datetime.now().strftime('%d.%m.%Y')}",
        align="C", new_x="LMARGIN", new_y="NEXT",
    )
    pdf.ln(5)

    # ── 1. Zaměstnanec ────────────────────────────────────────────────────────
    pdf.section_heading("1.  ZAMĚSTNANEC A PRACOVIŠTĚ")
    pdf.field_row("Jméno a příjmení", report.employee_name)
    pdf.field_row("Pracoviště", report.workplace)
    pdf.ln(3)

    # ── 2. Datum a čas ────────────────────────────────────────────────────────
    pdf.section_heading("2.  DATUM A ČAS ÚRAZU")
    pdf.field_row("Datum úrazu", _fmt_date(report.accident_date))
    pdf.field_row(
        "Čas úrazu",
        report.accident_time.strftime("%H:%M") if report.accident_time else "—",
    )
    pdf.field_row(
        "Začátek pracovní směny",
        report.shift_start_time.strftime("%H:%M") if report.shift_start_time else "—",
    )
    pdf.ln(3)

    # ── 3. Charakter zranění ──────────────────────────────────────────────────
    pdf.section_heading("3.  CHARAKTER ZRANĚNÍ")
    pdf.field_row("Druh zranění", report.injury_type)
    pdf.field_row("Zraněná část těla", report.injured_body_part)
    pdf.field_row("Zdroj úrazu", report.injury_source)
    pdf.field_row("Příčina úrazu", report.injury_cause)
    pdf.field_row("Počet současně zraněných osob", str(report.injured_count))
    pdf.field_row("Smrtelný úraz", _fmt_bool(report.is_fatal))
    pdf.field_row("Ostatní úrazy", _fmt_bool(report.has_other_injuries))
    pdf.ln(3)

    # ── 4. Popis okolností ────────────────────────────────────────────────────
    pdf.section_heading("4.  POPIS PŘÍČINY A OKOLNOSTÍ ÚRAZU")
    pdf.multiline_field("Popis", report.description)
    pdf.ln(2)

    # ── 5. Krevní patogeny (jen pokud relevantní) ─────────────────────────────
    if report.blood_pathogen_exposure:
        pdf.section_heading("5.  EXPOZICE KREVNÍMI PATOGENY")
        pdf.field_row("Expozice krevními patogeny", "Ano")
        pdf.multiline_field("Jména postižených osob", report.blood_pathogen_persons or "—")
        pdf.ln(2)

    # ── 6. Porušené předpisy ──────────────────────────────────────────────────
    pdf.section_heading("6.  PORUŠENÉ PŘEDPISY A OPATŘENÍ")
    pdf.multiline_field("Porušené předpisy", report.violated_regulations or "—")
    pdf.ln(2)

    # ── 7. Testy ──────────────────────────────────────────────────────────────
    pdf.section_heading("7.  VÝSLEDKY TESTŮ")
    pdf.field_row("Test na alkohol proveden", _fmt_bool(report.alcohol_test_performed))
    if report.alcohol_test_performed:
        pdf.field_row("Výsledek testu na alkohol", _fmt_test_result(report.alcohol_test_result))
        if report.alcohol_test_result == "positive" and report.alcohol_test_value is not None:
            pdf.field_row(
                "Naměřená hodnota alkoholu",
                f"{report.alcohol_test_value} ‰",
            )
    pdf.field_row("Test na návykové látky proveden", _fmt_bool(report.drug_test_performed))
    if report.drug_test_performed:
        pdf.field_row("Výsledek testu na návykové látky", _fmt_test_result(report.drug_test_result))
    pdf.ln(3)

    # ── 8. Podpisy ────────────────────────────────────────────────────────────
    pdf.section_heading("8.  PODPISY")
    pdf.ln(2)

    pdf.set_font(_ReportPDF.FONT, style="", size=8)
    pdf.cell(
        _ReportPDF.PAGE_W, 5,
        "Svým podpisem potvrzuji správnost výše uvedených údajů.",
        new_x="LMARGIN", new_y="NEXT",
    )
    pdf.ln(3)

    # Postižený
    pdf.signature_block(
        "Postižený zaměstnanec",
        report.employee_name,
        report.injured_signed_at,
    )

    # Svědci
    witnesses = report.witnesses or []
    for i, w in enumerate(witnesses, 1):
        signed_raw = w.get("signed_at")
        signed_dt: date | None = None
        if signed_raw:
            from datetime import date as date_type
            try:
                signed_dt = date_type.fromisoformat(signed_raw)
            except (ValueError, TypeError):
                signed_dt = None
        pdf.signature_block(f"Svědek {i}", w.get("name"), signed_dt)

    # Nadřízený
    pdf.signature_block(
        "Nadřízený zaměstnanec",
        report.supervisor_name,
        report.supervisor_signed_at,
    )

    # ── Patička ───────────────────────────────────────────────────────────────
    pdf.ln(5)
    pdf.set_font(_ReportPDF.FONT, style="", size=7)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(
        _ReportPDF.PAGE_W, 5,
        f"Záznam vyhotoven v souladu s NV 201/2010 Sb.  |  ID záznamu: {report.id}",
        align="C", new_x="LMARGIN", new_y="NEXT",
    )

    return bytes(pdf.output())
