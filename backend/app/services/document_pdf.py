"""
Markdown → PDF renderer pro generated_documents.

Jednoduchý parser, který umí:
- # / ## / ### nadpisy
- paragrafy
- - / * unordered list
- 1. / 2. ordered list
- **bold**, *italic* (jen jako prostý text — fpdf2 styles náročné)
- | a | b |  | --- | tabulky (Markdown)
- horizontální čáry ---

Pokročilejší elements (kód, blockquotes, embedded HTML) nejsou podporované.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from fpdf import FPDF

from app.models.generated_document import GeneratedDocument
from app.models.tenant import Tenant

FONT = "DejaVu"


def _font_path(filename: str) -> str:
    """Najde DejaVu font v systému / fpdf2 packageu (stejná logika jako export_pdf)."""
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
    except Exception:  # noqa: BLE001
        pass
    raise FileNotFoundError(
        f"Font {filename} nenalezen — nainstalujte fonts-dejavu-core"
    )


class _DocumentPdf(FPDF):
    def __init__(self, tenant_name: str, doc_title: str) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_auto_page_break(auto=True, margin=18)
        self._tenant_name = tenant_name
        self._doc_title = doc_title
        # Unicode font pro českou diakritiku + em-dashe / typografické uvozovky.
        # `fonts-dejavu-core` má jen Sans + Bold; Oblique chybí — pro italic
        # falbeck na regular (vizuálně jen header/footer, není kritické).
        self.add_font(FONT, style="", fname=_font_path("DejaVuSans.ttf"))
        self.add_font(FONT, style="B", fname=_font_path("DejaVuSans-Bold.ttf"))
        try:
            self.add_font(FONT, style="I", fname=_font_path("DejaVuSans-Oblique.ttf"))
        except FileNotFoundError:
            self.add_font(FONT, style="I", fname=_font_path("DejaVuSans.ttf"))

    def header(self) -> None:
        # Hlavička jen na první stránce — fpdf volá pre každou stránku
        # ale pro úspory uděláme jen tenkou linku.
        if self.page_no() == 1:
            return
        self.set_font(FONT, "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 6, self._tenant_name + " — " + self._doc_title,
                  align="L", new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.ln(2)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font(FONT, "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 8, f"Strana {self.page_no()}", align="C")
        self.set_text_color(0, 0, 0)


# ── Markdown parser ─────────────────────────────────────────────────────────


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$")
_LIST_UL_RE = re.compile(r"^(\s*)[-*+]\s+(.+)$")
_LIST_OL_RE = re.compile(r"^(\s*)\d+\.\s+(.+)$")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")


def _strip_inline(text: str) -> str:
    """Odstraní markdown inline syntax (bold/italic/code) — pro plain output."""
    text = _BOLD_RE.sub(r"\1", text)
    text = _ITALIC_RE.sub(r"\1", text)
    text = _INLINE_CODE_RE.sub(r"\1", text)
    # Odkazy [text](url) → text
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", text)
    return text


def _parse_table_row(line: str) -> list[str]:
    """`| a | b | c |` → ['a', 'b', 'c']"""
    parts = line.strip().strip("|").split("|")
    return [p.strip() for p in parts]


def _render_paragraph(pdf: FPDF, text: str) -> None:
    """Render plain paragraph s wrap."""
    pdf.set_font(FONT, "", 11)
    pdf.set_text_color(40, 40, 40)
    pdf.multi_cell(0, 6, _strip_inline(text), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)


def _render_heading(pdf: FPDF, level: int, text: str) -> None:
    sizes = {1: 18, 2: 14, 3: 12}
    spacing = {1: 5, 2: 4, 3: 3}
    pdf.ln(spacing.get(level, 2))
    pdf.set_font(FONT, "B", sizes.get(level, 11))
    pdf.set_text_color(0, 0, 100) if level == 1 else pdf.set_text_color(0, 0, 0)
    pdf.multi_cell(0, sizes.get(level, 11) * 0.6,
                   _strip_inline(text), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)


def _render_list_item(pdf: FPDF, text: str, ordered: bool, idx: int) -> None:
    pdf.set_font(FONT, "", 11)
    pdf.set_text_color(40, 40, 40)
    bullet = f"{idx}." if ordered else "•"
    # 6mm indent + 5mm bullet column
    x = pdf.get_x()
    pdf.cell(6, 6, "")
    pdf.cell(5, 6, bullet)
    pdf.multi_cell(0, 6, _strip_inline(text), new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(x)


def _render_table(pdf: FPDF, headers: list[str], rows: list[list[str]]) -> None:
    if not headers:
        return
    pdf.ln(2)
    page_width = pdf.w - 2 * pdf.l_margin
    col_width = page_width / len(headers)

    # Header
    pdf.set_font(FONT, "B", 9)
    pdf.set_fill_color(230, 235, 245)
    pdf.set_text_color(0, 0, 100)
    for h in headers:
        pdf.cell(col_width, 7, _strip_inline(h)[:60], border=1, align="L", fill=True)
    pdf.ln()
    pdf.set_text_color(0, 0, 0)

    # Rows
    pdf.set_font(FONT, "", 9)
    for i, row in enumerate(rows):
        # Pad row pokud chybí buňky
        cells = list(row) + [""] * max(0, len(headers) - len(row))
        if i % 2 == 1:
            pdf.set_fill_color(248, 248, 252)
            fill = True
        else:
            fill = False
        for c in cells[: len(headers)]:
            pdf.cell(col_width, 6, _strip_inline(str(c))[:60],
                     border=1, align="L", fill=fill)
        pdf.ln()
    pdf.ln(2)


def _render_markdown(pdf: FPDF, md: str) -> None:
    """Hlavní parser — řádek po řádku."""
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Prázdný řádek
        if not stripped:
            pdf.ln(1)
            i += 1
            continue

        # Horizontální čára
        if stripped == "---" or stripped == "***":
            pdf.ln(2)
            pdf.set_draw_color(200, 200, 200)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.ln(3)
            i += 1
            continue

        # Tabulka — detekce: tento řádek obsahuje | a další řádek je separátor
        if "|" in stripped and i + 1 < len(lines) and _TABLE_SEP_RE.match(lines[i + 1]):
            headers = _parse_table_row(stripped)
            rows: list[list[str]] = []
            j = i + 2
            while j < len(lines) and "|" in lines[j].strip():
                rows.append(_parse_table_row(lines[j]))
                j += 1
            _render_table(pdf, headers, rows)
            i = j
            continue

        # Nadpis
        m = _HEADING_RE.match(stripped)
        if m:
            level = len(m.group(1))
            _render_heading(pdf, level, m.group(2))
            i += 1
            continue

        # Unordered list
        m = _LIST_UL_RE.match(line)
        if m:
            _render_list_item(pdf, m.group(2), ordered=False, idx=0)
            i += 1
            continue

        # Ordered list — kontinuální numbering pomocí counter
        m = _LIST_OL_RE.match(line)
        if m:
            # Najdi run consecutive ordered items
            idx = 1
            while i < len(lines):
                m2 = _LIST_OL_RE.match(lines[i])
                if not m2:
                    break
                _render_list_item(pdf, m2.group(2), ordered=True, idx=idx)
                idx += 1
                i += 1
            continue

        # Default: paragraph (sloučí konsekutivní non-empty řádky)
        para_lines = [stripped]
        i += 1
        while i < len(lines) and lines[i].strip() and not _HEADING_RE.match(lines[i]) \
                and not _LIST_UL_RE.match(lines[i]) and not _LIST_OL_RE.match(lines[i]) \
                and "|" not in lines[i] and lines[i].strip() not in ("---", "***"):
            para_lines.append(lines[i].strip())
            i += 1
        _render_paragraph(pdf, " ".join(para_lines))


# ── Public API ──────────────────────────────────────────────────────────────


def render_document_pdf(doc: GeneratedDocument, tenant: Tenant) -> bytes:
    """Vrátí PDF bytes pro daný GeneratedDocument."""
    pdf = _DocumentPdf(tenant.name, doc.title)
    pdf.add_page()

    # Hlavička dokumentu na první stránce
    pdf.set_font(FONT, "B", 22)
    pdf.set_text_color(0, 0, 100)
    pdf.multi_cell(0, 11, doc.title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(1)

    pdf.set_font(FONT, "", 10)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 5, tenant.name, new_x="LMARGIN", new_y="NEXT")
    today = datetime.now(UTC).date().strftime("%d. %m. %Y")
    pdf.cell(0, 5, f"Vystaveno: {today}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)
    pdf.set_draw_color(200, 200, 200)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(4)

    # Render Markdown obsahu
    _render_markdown(pdf, doc.content_md)

    output = pdf.output()
    return bytes(output)
