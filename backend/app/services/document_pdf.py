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
from typing import Any

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
    def __init__(
        self, tenant_name: str, doc_title: str, orientation: str = "P",
    ) -> None:
        super().__init__(orientation=orientation, unit="mm", format="A4")
        self.set_auto_page_break(auto=True, margin=18)
        self._tenant_name = tenant_name
        self._doc_title = doc_title
        # Unicode font pro českou diakritiku + em-dashe / typografické uvozovky.
        # `fonts-dejavu-core` má jen Sans + Bold; Oblique a BoldOblique chybí
        # — pro italic / bold-italic fallback na regular / bold.
        self.add_font(FONT, style="", fname=_font_path("DejaVuSans.ttf"))
        self.add_font(FONT, style="B", fname=_font_path("DejaVuSans-Bold.ttf"))
        try:
            self.add_font(FONT, style="I", fname=_font_path("DejaVuSans-Oblique.ttf"))
        except FileNotFoundError:
            self.add_font(FONT, style="I", fname=_font_path("DejaVuSans.ttf"))
        try:
            self.add_font(FONT, style="BI", fname=_font_path("DejaVuSans-BoldOblique.ttf"))
        except FileNotFoundError:
            self.add_font(FONT, style="BI", fname=_font_path("DejaVuSans-Bold.ttf"))

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


# ── Inline styled text rendering ────────────────────────────────────────────


def _tokenize_inline(text: str) -> list[tuple[str, str]]:
    """
    Rozparsuje řádek na seznam (style, text) tokenů, kde style je
    prázdný řetězec, "B" (bold), "I" (italic) nebo "BI" (bold-italic).

    Podporuje:
      **bold**
      *italic*
      ***bold-italic***
      [text](url) → vrátí jen text
      `code` → vrátí jen code (bez stylů)
    """
    # Nejprve nahradíme odkazy a inline kód za prostý text
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", text)
    text = _INLINE_CODE_RE.sub(r"\1", text)

    tokens: list[tuple[str, str]] = []
    i = 0
    n = len(text)
    while i < n:
        # ***bold-italic***
        if text.startswith("***", i):
            end = text.find("***", i + 3)
            if end != -1:
                tokens.append(("BI", text[i + 3 : end]))
                i = end + 3
                continue
        # **bold**
        if text.startswith("**", i):
            end = text.find("**", i + 2)
            if end != -1:
                tokens.append(("B", text[i + 2 : end]))
                i = end + 2
                continue
        # *italic*
        if text[i] == "*" and (i + 1 < n and text[i + 1] != "*"):
            end = text.find("*", i + 1)
            if end != -1 and (end + 1 >= n or text[end + 1] != "*"):
                tokens.append(("I", text[i + 1 : end]))
                i = end + 1
                continue
        # plain char
        # Najdi nejbližší marker
        next_marker = n
        for m in ("**", "*"):
            idx = text.find(m, i)
            if idx != -1 and idx < next_marker:
                next_marker = idx
        tokens.append(("", text[i:next_marker]))
        i = next_marker

    # Slouč po sobě jdoucí stejně-stylované tokeny
    merged: list[tuple[str, str]] = []
    for style, txt in tokens:
        if not txt:
            continue
        if merged and merged[-1][0] == style:
            merged[-1] = (style, merged[-1][1] + txt)
        else:
            merged.append((style, txt))
    return merged


def _render_inline_tokens(
    pdf: FPDF, tokens: list[tuple[str, str]], size: int = 11,
    line_height: float = 6.0,
) -> None:
    """
    Vykreslí styled inline tokens jako jeden flow paragraph s wrap.
    Použije pdf.write() — automatic line break.
    """
    for style, txt in tokens:
        if "B" in style and "I" in style:
            pdf.set_font(FONT, "BI" if "BI" in style else "B", size)
        elif "B" in style:
            pdf.set_font(FONT, "B", size)
        elif "I" in style:
            pdf.set_font(FONT, "I", size)
        else:
            pdf.set_font(FONT, "", size)
        pdf.write(line_height, txt)
    pdf.ln(line_height)


def _parse_table_row(line: str) -> list[str]:
    """`| a | b | c |` → ['a', 'b', 'c']"""
    parts = line.strip().strip("|").split("|")
    return [p.strip() for p in parts]


def _render_paragraph(pdf: FPDF, text: str) -> None:
    """Render paragraph s inline bold/italic + wrap."""
    pdf.set_text_color(40, 40, 40)
    tokens = _tokenize_inline(text)
    _render_inline_tokens(pdf, tokens, size=11, line_height=6.0)
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
    pdf.set_text_color(40, 40, 40)
    bullet = f"{idx}." if ordered else "•"
    pdf.set_font(FONT, "", 11)
    # 6mm indent + 5mm bullet column
    pdf.cell(6, 6, "")
    pdf.cell(5, 6, bullet)
    tokens = _tokenize_inline(text)
    _render_inline_tokens(pdf, tokens, size=11, line_height=6.0)


def _calc_col_widths(headers: list[str], rows: list[list[str]],
                     total_width: float) -> list[float]:
    """Heuristika: šířka sloupce úměrná průměrné délce obsahu (clamped 8-50%)."""
    n = len(headers)
    if n == 0:
        return []

    # Spočítej max délku obsahu per column
    col_max: list[int] = []
    for col_idx in range(n):
        max_len = len(headers[col_idx])
        for row in rows:
            if col_idx < len(row):
                max_len = max(max_len, len(str(row[col_idx])))
        col_max.append(max(max_len, 5))  # min 5 chars

    total = sum(col_max)
    # Proporcionálně + clamp aby žádný sloupec nebyl extrémně úzký/široký
    min_pct = 0.08
    max_pct = 0.50
    widths = []
    for ml in col_max:
        pct = ml / total
        pct = max(min_pct, min(max_pct, pct))
        widths.append(pct)
    # Re-normalize na 1.0
    s = sum(widths)
    return [(w / s) * total_width for w in widths]


def _render_table(pdf: FPDF, headers: list[str], rows: list[list[str]]) -> None:
    """Manuální table renderer — explicitně používá DejaVu font v každé buňce.

    fpdf2 native pdf.table() v některých případech nedrží set_font kontext
    a fallbackuje na core (Helvetica), který nepodporuje českou diakritiku.
    Proto všechny buňky kreslíme přes set_font + multi_cell.
    """
    if not headers:
        return
    pdf.ln(2)
    total_width = pdf.w - pdf.l_margin - pdf.r_margin
    col_widths = _calc_col_widths(headers, rows, total_width)
    n = len(headers)

    line_h = 5.0
    pad = 1.0

    def _cell_lines(text: str, width: float, font_size: int) -> int:
        """Spočítá počet řádků, které text zabere v buňce dané šířky."""
        pdf.set_font(FONT, "", font_size)
        # split_only=True vrátí list zalomených řádků bez tisku;
        # fpdf2 ji ale typuje jako Union — přijmeme Any a sami zkontrolujeme.
        try:
            wrapped: Any = pdf.multi_cell(
                width - 2 * pad, line_h, text, split_only=True,
            )
            if isinstance(wrapped, list):
                return max(1, len(wrapped))
        except Exception:  # noqa: BLE001
            pass
        # Fallback heuristika dle počtu znaků
        char_w = font_size * 0.45 / 2
        chars_per_line = max(1, int((width - 2 * pad) / char_w))
        return max(1, (len(text) + chars_per_line - 1) // chars_per_line)

    def _draw_row(
        cells: list[str], font_size: int,
        bold: bool = False, fill: tuple[int, int, int] | None = None,
    ) -> None:
        """Vykreslí jeden řádek tabulky s text wrap a borders."""
        # Spočti výšku řádku = max počet zalomených řádků × line_h
        max_lines = 1
        for i, txt in enumerate(cells[:n]):
            lines = _cell_lines(txt, col_widths[i], font_size)
            if lines > max_lines:
                max_lines = lines
        row_h = max_lines * line_h + 2 * pad

        # Page break pokud se nevejde
        if pdf.get_y() + row_h > pdf.h - pdf.b_margin:
            pdf.add_page()

        x_start = pdf.l_margin
        y_start = pdf.get_y()

        # Pozadí
        if fill is not None:
            pdf.set_fill_color(*fill)
        else:
            pdf.set_fill_color(255, 255, 255)

        # Vykresli každou buňku jako multi_cell se správným fontem
        x = x_start
        pdf.set_font(FONT, "B" if bold else "", font_size)
        for i, txt in enumerate(cells[:n]):
            pdf.set_xy(x, y_start)
            # Detekce **bold** markeru — uvnitř buňky
            display = txt
            cell_bold = bold
            if not bold and txt.startswith("**") and txt.endswith("**") and len(txt) >= 4:
                display = txt[2:-2]
                cell_bold = True
                pdf.set_font(FONT, "B", font_size)
            else:
                pdf.set_font(FONT, "B" if bold else "", font_size)

            pdf.multi_cell(
                col_widths[i], line_h, display,
                border=0, align="L", fill=fill is not None,
                new_x="RIGHT", new_y="TOP",
                max_line_height=line_h,
            )
            if cell_bold and not bold:
                pdf.set_font(FONT, "", font_size)
            x += col_widths[i]

        # Vykresli ohraničení celého řádku přes set_draw + line/rect
        pdf.set_draw_color(180, 180, 180)
        pdf.set_line_width(0.1)
        x = x_start
        for i in range(n):
            pdf.rect(x, y_start, col_widths[i], row_h)
            x += col_widths[i]

        # Posuň kurzor pod řádek
        pdf.set_xy(x_start, y_start + row_h)

    header_size = 8
    body_size = 8

    # Header
    _draw_row(
        [_strip_inline(h) for h in headers],
        font_size=header_size, bold=True,
        fill=(220, 230, 245),
    )

    # Body
    for ridx, r in enumerate(rows):
        cells = [_strip_inline(str(c)) if c is not None else "—" for c in r]
        cells += [""] * max(0, n - len(cells))
        shade = (248, 250, 252) if ridx % 2 == 1 else None
        _draw_row(cells, font_size=body_size, bold=False, fill=shade)

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
    # Wide-table dokumenty (RFA seznam) renderujeme na landscape A4,
    # aby se vešlo 13 sloupců rizikových faktorů + identifikace + kat.
    wide_layout = doc.document_type == "risk_categorization"
    orientation = "L" if wide_layout else "P"
    pdf = _DocumentPdf(tenant.name, doc.title, orientation=orientation)
    pdf.add_page()

    # Logo firmy (vlevo nahoře) — pokud tenant má upload
    from app.services.pdf_logo import embed_tenant_logo
    logo_y_start = pdf.get_y()
    has_logo = embed_tenant_logo(pdf, tenant, x=pdf.l_margin, y=logo_y_start, h=14)
    if has_logo:
        # Odsadíme nadpis vpravo od loga aby se nepřekrývaly
        pdf.set_xy(pdf.l_margin + 30, logo_y_start)

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
