"""
PDF exporty pro tisk a archivaci BOZP dokumentace.

Čtyři typy exportů:
  - Registr rizik
  - Přehled školení
  - Harmonogram revizí
  - Kniha úrazů

Všechny používají stejnou infrastrukturu: fpdf2 + DejaVu fonty (češtiny).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

from fpdf import FPDF

if TYPE_CHECKING:
    from app.models.accident_report import AccidentReport
    from app.models.oopp import OOPPAssignment
    from app.models.revision import Revision
    from app.models.risk import Risk
    from app.models.risk_factor_assessment import RiskFactorAssessment
    from app.models.training import Training
    from app.models.workplace import Plant, Workplace


# ── Sdílené utility ───────────────────────────────────────────────────────────

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
        pkg = Path(_fpdf.__file__).parent / "fonts" / filename
        if pkg.exists():
            return str(pkg)
    except Exception:
        pass
    raise FileNotFoundError(f"Font {filename} nenalezen – nainstalujte fonts-dejavu-core")


def _fmt_date(d: object) -> str:
    from datetime import date
    if isinstance(d, date):
        return d.strftime("%d.%m.%Y")
    return "—"


def _fmt_bool(b: bool) -> str:
    return "Ano" if b else "Ne"


FONT = "DejaVu"
PAGE_W = 277  # landscape A4 obsah při margin 10mm


class _ExportPDF(FPDF):
    def __init__(self, title: str, tenant_name: str, orientation: str = "L") -> None:
        super().__init__(orientation=orientation, format="A4")
        self._doc_title = title
        self._tenant_name = tenant_name
        self.set_margins(10, 10, 10)
        self.set_auto_page_break(auto=True, margin=15)
        self.add_font(FONT, style="", fname=_font_path("DejaVuSans.ttf"))
        self.add_font(FONT, style="B", fname=_font_path("DejaVuSans-Bold.ttf"))
        self.add_page()
        self._render_header()

    def _render_header(self) -> None:
        self.set_font(FONT, style="B", size=13)
        self.cell(PAGE_W, 8, self._doc_title, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font(FONT, style="", size=8)
        now = datetime.now().strftime("%d.%m.%Y %H:%M")
        self.cell(
            PAGE_W, 5,
            f"{self._tenant_name}   |   Vygenerováno: {now}",
            align="C", new_x="LMARGIN", new_y="NEXT",
        )
        self.ln(3)

    def table_header(self, cols: list[tuple[str, int]]) -> None:
        """Vykreslí záhlaví tabulky. cols = [(label, šířka_mm), ...]"""
        self.set_font(FONT, style="B", size=8)
        self.set_fill_color(210, 225, 240)
        for label, w in cols:
            self.cell(w, 7, label, border=1, fill=True, new_x="RIGHT", new_y="TOP")
        self.ln()

    def table_row(self, values: list[tuple[str, int]], shade: bool = False) -> None:
        """Vykreslí jeden řádek tabulky."""
        self.set_font(FONT, style="", size=7)
        if shade:
            self.set_fill_color(245, 248, 252)
        else:
            self.set_fill_color(255, 255, 255)
        for text, w in values:
            self.cell(w, 6, str(text)[:60] if text else "—", border=1, fill=True, new_x="RIGHT", new_y="TOP")
        self.ln()

    def section_note(self, text: str) -> None:
        self.set_font(FONT, style="", size=7)
        self.set_text_color(100, 100, 100)
        self.cell(PAGE_W, 5, text, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.ln(1)


# ── 1. Registr rizik ──────────────────────────────────────────────────────────

RISK_LEVEL_CS = {"low": "Nízké", "medium": "Střední", "high": "Vysoké"}

def generate_risks_pdf(risks: Sequence["Risk"], tenant_name: str) -> bytes:
    pdf = _ExportPDF("REGISTR RIZIK", tenant_name)

    cols = [
        ("Název rizika", 60),
        ("Typ nebezpečí", 28),
        ("Pracoviště", 30),
        ("P", 8),
        ("Z", 8),
        ("Skóre", 12),
        ("Úroveň", 16),
        ("Zbytk. skóre", 16),
        ("Zbytk. úroveň", 18),
        ("Datum revize", 22),
        ("Status", 16),
        ("Opatření", 45),  # zkráceno na 60 znaků v table_row
    ]
    pdf.table_header(cols)

    for i, r in enumerate(risks):
        res_score = str(r.residual_risk_score) if r.residual_risk_score else "—"
        res_level = RISK_LEVEL_CS.get(r.residual_risk_level or "", "—") if r.residual_risk_level else "—"
        pdf.table_row([
            (r.title, 60),
            (r.hazard_type, 28),
            (r.location or "—", 30),
            (str(r.probability), 8),
            (str(r.severity), 8),
            (str(r.risk_score), 12),
            (RISK_LEVEL_CS.get(r.risk_level, r.risk_level), 16),
            (res_score, 16),
            (res_level, 18),
            (_fmt_date(r.review_date), 22),
            ("Aktivní" if r.status == "active" else "Archiv.", 16),
            (r.control_measures or "—", 45),
        ], shade=i % 2 == 1)

    pdf.section_note(f"Celkem záznamů: {len(risks)}   |   P = Pravděpodobnost, Z = Závažnost (1–5)")
    return bytes(pdf.output())


# ── 2. Přehled školení ────────────────────────────────────────────────────────

VALIDITY_CS = {
    "no_expiry": "Bez expiry",
    "valid": "Platné",
    "expiring_soon": "Brzy vyprší",
    "expired": "Prošlé",
}

TRAINING_TYPE_CS = {
    "bozp_initial": "BOZP vstupní",
    "bozp_periodic": "BOZP periodické",
    "fire_protection": "PO",
    "first_aid": "První pomoc",
    "equipment": "Obsluha zař.",
    "other": "Ostatní",
}

def generate_trainings_pdf(trainings: Sequence["Training"], tenant_name: str) -> bytes:
    pdf = _ExportPDF("PŘEHLED ŠKOLENÍ BOZP/PO", tenant_name)

    cols = [
        ("Název školení", 70),
        ("Typ", 28),
        ("Datum školení", 26),
        ("Platnost do", 24),
        ("Stav platnosti", 28),
        ("Lektor/Školitel", 40),
        ("Platnost (měs.)", 24),
        ("Status", 18),
        ("Poznámky", 39),
    ]
    pdf.table_header(cols)

    for i, t in enumerate(trainings):
        pdf.table_row([
            (t.title, 70),
            (TRAINING_TYPE_CS.get(t.training_type, t.training_type), 28),
            (_fmt_date(t.trained_at), 26),
            (_fmt_date(t.valid_until), 24),
            (VALIDITY_CS.get(t.validity_status, t.validity_status), 28),
            (t.trainer_name or "—", 40),
            (str(t.valid_months) if t.valid_months else "—", 24),
            ("Aktivní" if t.status == "active" else "Archiv.", 18),
            (t.notes or "—", 39),
        ], shade=i % 2 == 1)

    pdf.section_note(f"Celkem záznamů: {len(trainings)}")
    return bytes(pdf.output())


# ── 3. Harmonogram revizí ─────────────────────────────────────────────────────

DUE_STATUS_CS = {
    "no_schedule": "Bez termínu",
    "ok": "V pořádku",
    "due_soon": "Blíží se",
    "overdue": "PO TERMÍNU",
}

REVISION_TYPE_CS = {
    "electrical": "Elektrorevize",
    "pressure_vessel": "Tlakové nádoby",
    "fire_equipment": "Hasicí přístroje",
    "gas": "Plynové zař.",
    "lifting_equipment": "Zdvihací zař.",
    "ladder": "Žebříky",
    "other": "Ostatní",
}

def generate_revisions_pdf(revisions: Sequence["Revision"], tenant_name: str) -> bytes:
    pdf = _ExportPDF("HARMONOGRAM REVIZÍ ZAŘÍZENÍ", tenant_name)

    cols = [
        ("Název / Zařízení", 70),
        ("Typ revize", 30),
        ("Umístění", 35),
        ("Poslední revize", 28),
        ("Platnost (měs.)", 24),
        ("Příští revize", 28),
        ("Stav termínu", 24),
        ("Zhotovitel", 38),
    ]
    pdf.table_header(cols)

    for i, r in enumerate(revisions):
        due = DUE_STATUS_CS.get(r.due_status, r.due_status)
        pdf.table_row([
            (r.title, 70),
            (REVISION_TYPE_CS.get(r.revision_type, r.revision_type), 30),
            (r.location or "—", 35),
            (_fmt_date(r.last_revised_at), 28),
            (str(r.valid_months) if r.valid_months else "—", 24),
            (_fmt_date(r.next_revision_at), 28),
            (due, 24),
            (r.contractor or "—", 38),
        ], shade=i % 2 == 1)

    overdue_count = sum(1 for r in revisions if r.due_status == "overdue")
    due_soon_count = sum(1 for r in revisions if r.due_status == "due_soon")
    pdf.section_note(
        f"Celkem záznamů: {len(revisions)}   |   "
        f"Po termínu: {overdue_count}   |   Blíží se termín: {due_soon_count}"
    )
    return bytes(pdf.output())


# ── 4. Kniha úrazů ────────────────────────────────────────────────────────────

def generate_accident_log_pdf(reports: Sequence["AccidentReport"], tenant_name: str) -> bytes:
    pdf = _ExportPDF("KNIHA ÚRAZŮ", tenant_name)

    cols = [
        ("Datum úrazu", 24),
        ("Čas", 14),
        ("Jméno zaměstnance", 50),
        ("Pracoviště", 40),
        ("Druh zranění", 35),
        ("Zraněná část těla", 35),
        ("Počet zraněných", 20),
        ("Smrtelný", 16),
        ("Status záznamu", 24),
        ("Revize rizik", 19),
    ]
    pdf.table_header(cols)

    for i, r in enumerate(reports):
        risk_review = "Dokončena" if r.risk_review_completed_at else (
            "Čeká" if r.risk_review_required else "—"
        )
        pdf.table_row([
            (_fmt_date(r.accident_date), 24),
            (r.accident_time.strftime("%H:%M") if r.accident_time else "—", 14),
            (r.employee_name, 50),
            (r.workplace, 40),
            (r.injury_type, 35),
            (r.injured_body_part, 35),
            (str(r.injured_count), 20),
            (_fmt_bool(r.is_fatal), 16),
            ({"draft": "Rozpracovaný", "final": "Finální", "archived": "Archivovaný"}.get(r.status, r.status), 24),
            (risk_review, 19),
        ], shade=i % 2 == 1)

    fatal_count = sum(1 for r in reports if r.is_fatal)
    pending_review = sum(1 for r in reports if r.risk_review_required and not r.risk_review_completed_at)
    pdf.section_note(
        f"Celkem úrazů: {len(reports)}   |   "
        f"Smrtelných: {fatal_count}   |   "
        f"Čeká na revizi rizik: {pending_review}"
    )
    return bytes(pdf.output())


# ── 5. Evidence OOPP ──────────────────────────────────────────────────────────

OOPP_TYPE_CS = {
    "head_protection": "Ochrana hlavy",
    "eye_protection": "Ochrana očí",
    "hearing_protection": "Ochrana sluchu",
    "respiratory_protection": "Ochrana dýchání",
    "hand_protection": "Ochrana rukou",
    "foot_protection": "Ochrana nohou",
    "fall_protection": "Ochrana pádu",
    "body_protection": "Ochrana trupu",
    "skin_protection": "Ochrana kůže",
    "visibility": "Výstražné",
    "other": "Ostatní",
}


def generate_medical_exams_pdf(exams: Sequence["MedicalExam"], tenant_name: str) -> bytes:
    """Přehled lékařských prohlídek pro tisk a archivaci."""
    EXAM_TYPE_CS = {
        "vstupni": "Vstupní",
        "periodicka": "Periodická",
        "vystupni": "Výstupní",
        "mimoradna": "Mimořádná",
    }
    RESULT_CS = {
        "zpusobilyý": "Způsobilý",
        "zpusobilyý_omezeni": "Způsobilý s omez.",
        "nezpusobilyý": "Nezpůsobilý",
        "pozbyl_zpusobilosti": "Pozbyl způsob.",
    }

    pdf = _ExportPDF("PŘEHLED LÉKAŘSKÝCH PROHLÍDEK", tenant_name)

    cols = [
        ("Zaměstnanec (ID)", 40),
        ("Druh prohlídky", 28),
        ("Datum", 24),
        ("Výsledek", 34),
        ("Lékař", 44),
        ("Platnost do", 24),
        ("Stav platnosti", 30),
        ("Zbývá dní", 18),
        ("Status", 15),
        ("Poznámky", 20),
    ]
    pdf.table_header(cols)

    for i, e in enumerate(exams):
        days = e.days_until_expiry
        days_str = str(days) if days is not None else "—"
        pdf.table_row([
            (str(e.employee_id)[:8] + "…", 40),
            (EXAM_TYPE_CS.get(e.exam_type, e.exam_type), 28),
            (_fmt_date(e.exam_date), 24),
            (RESULT_CS.get(e.result or "", "—") if e.result else "—", 34),
            (e.physician_name or "—", 44),
            (_fmt_date(e.valid_until), 24),
            (VALIDITY_CS.get(e.validity_status, e.validity_status), 30),
            (days_str, 18),
            ("Akt." if e.status == "active" else "Arch.", 15),
            (e.notes or "—", 20),
        ], shade=i % 2 == 1)

    expired_count = sum(1 for e in exams if e.validity_status == "expired")
    expiring_count = sum(1 for e in exams if e.validity_status == "expiring_soon")
    pdf.section_note(
        f"Celkem záznamů: {len(exams)}   |   "
        f"Prošlé: {expired_count}   |   Brzy vyprší: {expiring_count}"
    )
    return bytes(pdf.output())


def generate_risk_factor_list_pdf(
    grouped: list[tuple["Plant", list[tuple["Workplace", list["RiskFactorAssessment"]]]]],
    tenant_name: str,
) -> bytes:
    """
    Generuje 'Seznam rizikových faktorů pracovního prostředí' dle NV 361/2007.

    grouped = [(plant, [(workplace, [rfa, ...]), ...]), ...]
    Orientace: landscape A4.
    """
    from app.models.risk_factor_assessment import RF_FIELDS, RF_LABELS

    # Zkratky pro záhlaví tabulky (sloupce 7mm – musí být velmi krátké)
    RF_SHORT = {
        "rf_prach":       "Prach",
        "rf_chem":        "Chem.",
        "rf_hluk":        "Hluk",
        "rf_vibrace":     "Vibr.",
        "rf_zareni":      "Záření",
        "rf_tlak":        "Tlak",
        "rf_fyz_zatez":   "Fyz.z.",
        "rf_prac_poloha": "Prac.p.",
        "rf_teplo":       "Teplo",
        "rf_chlad":       "Chlad",
        "rf_psych":       "Psych.",
        "rf_zrak":        "Zrak",
        "rf_bio":         "Bio",
    }

    # Šířky sloupců (mm), součet musí být ≤ PAGE_W (277)
    W_WORKPLACE = 40
    W_PROFESE = 52
    W_WORKERS = 11
    W_WOMEN = 11
    W_RF = 8          # 13 × 8 = 104
    W_CAT = 14
    # Součet: 40+52+11+11+104+14 = 232 mm (bezpečná rezerva)

    pdf = _ExportPDF("SEZNAM RIZIKOVÝCH FAKTORŮ PRACOVNÍHO PROSTŘEDÍ", tenant_name)

    def _table_header() -> None:
        pdf.set_font(FONT, style="B", size=6)
        pdf.set_fill_color(210, 225, 240)
        pdf.cell(W_WORKPLACE, 8, "Pracoviště", border=1, fill=True, new_x="RIGHT", new_y="TOP")
        pdf.cell(W_PROFESE, 8, "Profese / Pracovní zařazení", border=1, fill=True, new_x="RIGHT", new_y="TOP")
        pdf.cell(W_WORKERS, 8, "Poč.", border=1, fill=True, new_x="RIGHT", new_y="TOP", align="C")
        pdf.cell(W_WOMEN, 8, "Ženy", border=1, fill=True, new_x="RIGHT", new_y="TOP", align="C")
        for f in RF_FIELDS:
            pdf.cell(W_RF, 8, RF_SHORT[f], border=1, fill=True, new_x="RIGHT", new_y="TOP", align="C")
        pdf.cell(W_CAT, 8, "Kat.", border=1, fill=True, new_x="LMARGIN", new_y="NEXT", align="C")

    def _rfa_row(workplace_name: str, rfa: "RiskFactorAssessment", shade: bool) -> None:
        pdf.set_font(FONT, style="", size=7)
        fill_color = (245, 248, 252) if shade else (255, 255, 255)
        pdf.set_fill_color(*fill_color)

        pdf.cell(W_WORKPLACE, 6, workplace_name[:35], border=1, fill=True, new_x="RIGHT", new_y="TOP")
        pdf.cell(W_PROFESE, 6, rfa.profese[:45], border=1, fill=True, new_x="RIGHT", new_y="TOP")
        pdf.cell(W_WORKERS, 6, str(rfa.worker_count), border=1, fill=True, new_x="RIGHT", new_y="TOP", align="C")
        pdf.cell(W_WOMEN, 6, str(rfa.women_count), border=1, fill=True, new_x="RIGHT", new_y="TOP", align="C")

        for f in RF_FIELDS:
            val = getattr(rfa, f) or ""
            # Vizuální zvýraznění kategorií 3 a 4
            if val in ("3", "4"):
                pdf.set_fill_color(255, 220, 220)  # světle červená
            elif val == "2R":
                pdf.set_fill_color(255, 245, 180)  # světle žlutá
            else:
                pdf.set_fill_color(*fill_color)
            pdf.cell(W_RF, 6, val, border=1, fill=True, new_x="RIGHT", new_y="TOP", align="C")

        cat = rfa.category_proposed
        if cat in ("3", "4"):
            pdf.set_fill_color(255, 180, 180)
        elif cat == "2R":
            pdf.set_fill_color(255, 245, 100)
        else:
            pdf.set_fill_color(*fill_color)
        pdf.cell(W_CAT, 6, cat, border=1, fill=True, new_x="LMARGIN", new_y="NEXT", align="C")

    total_rows = 0
    cat3_plus = 0

    for plant, wp_list in grouped:
        # Záhlaví závodu
        pdf.set_font(FONT, style="B", size=9)
        pdf.set_fill_color(180, 200, 230)
        plant_label = f"Závod: {plant.name}"
        if plant.address:
            plant_label += f"  |  {plant.address}"
            if plant.city:
                plant_label += f", {plant.city}"
        pdf.cell(232, 7, plant_label[:100], border=1, fill=True, new_x="LMARGIN", new_y="NEXT")

        _table_header()

        row_idx = 0
        for workplace, rfas in wp_list:
            for rfa in rfas:
                _rfa_row(workplace.name, rfa, shade=row_idx % 2 == 1)
                row_idx += 1
                total_rows += 1
                if rfa.category_proposed in ("3", "4"):
                    cat3_plus += 1

        pdf.ln(2)

    # Záhlaví s legendou rizikových faktorů na konci dokumentu
    pdf.set_font(FONT, style="B", size=7)
    pdf.cell(232, 5, "Legenda rizikových faktorů (NV 361/2007 Sb.):", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(FONT, style="", size=6.5)
    legend_parts = [f"{RF_SHORT[f]} = {RF_LABELS[f]}" for f in RF_FIELDS]
    # Dva sloupce
    half = len(legend_parts) // 2 + len(legend_parts) % 2
    for i in range(half):
        left = legend_parts[i]
        right = legend_parts[i + half] if i + half < len(legend_parts) else ""
        pdf.cell(116, 4, left, new_x="RIGHT", new_y="TOP")
        pdf.cell(116, 4, right, new_x="LMARGIN", new_y="NEXT")

    pdf.ln(2)
    pdf.set_font(FONT, style="", size=7)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(
        232, 5,
        f"Celkem záznamů: {total_rows}   |   Kategorie 3 a vyšší: {cat3_plus}   |   "
        f"Hodnocení: 1=nejnižší riziko, 2=přijatelné, 2R=kategorie 2 riziková, 3=zvýšené, 4=vysoké",
        new_x="LMARGIN", new_y="NEXT",
    )
    pdf.set_text_color(0, 0, 0)

    return bytes(pdf.output())


def generate_oopp_pdf(assignments: Sequence["OOPPAssignment"], tenant_name: str) -> bytes:
    pdf = _ExportPDF("EVIDENCE OSOBNÍCH OCHRANNÝCH PRACOVNÍCH PROSTŘEDKŮ", tenant_name)

    cols = [
        ("Zaměstnanec", 50),
        ("Název OOPP", 55),
        ("Kategorie", 30),
        ("Datum vydání", 24),
        ("Počet ks", 14),
        ("Velikost", 18),
        ("Platnost do", 24),
        ("Stav platnosti", 28),
        ("Výr. číslo", 24),
        ("Status", 10),
    ]
    pdf.table_header(cols)

    for i, a in enumerate(assignments):
        pdf.table_row([
            (a.employee_name, 50),
            (a.item_name, 55),
            (OOPP_TYPE_CS.get(a.oopp_type, a.oopp_type), 30),
            (_fmt_date(a.issued_at), 24),
            (str(a.quantity), 14),
            (a.size_spec or "—", 18),
            (_fmt_date(a.valid_until), 24),
            (VALIDITY_CS.get(a.validity_status, a.validity_status), 28),
            (a.serial_number or "—", 24),
            ("Akt." if a.status == "active" else "Arch.", 10),
        ], shade=i % 2 == 1)

    expired_count = sum(1 for a in assignments if a.validity_status == "expired")
    expiring_count = sum(1 for a in assignments if a.validity_status == "expiring_soon")
    pdf.section_note(
        f"Celkem výdejů: {len(assignments)}   |   "
        f"Prošlé: {expired_count}   |   Brzy vyprší: {expiring_count}"
    )
    return bytes(pdf.output())
