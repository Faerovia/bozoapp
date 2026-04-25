"""
Extrakce textu z různých formátů pro import existujícího dokumentu.

Podporuje:
  - .md / .txt        → naprázdno (jen decode)
  - .pdf              → pypdf (text-only, bez OCR)
  - .docx             → python-docx

Pokud se nepodaří extrahovat, vrátí ValueError s vysvětlením.
Maximální velikost vstupu MAX_IMPORT_BYTES.
"""

from __future__ import annotations

import io
from pathlib import Path

MAX_IMPORT_BYTES = 10 * 1024 * 1024   # 10 MB
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".md", ".txt"}


def extract_text(content: bytes, filename: str) -> str:
    """
    Vrátí extrahovaný text jako Markdown řetězec.
    PDF a DOCX se převádí na plain text se zachovaným odsazováním odstavců.
    """
    if len(content) > MAX_IMPORT_BYTES:
        raise ValueError(
            f"Soubor je příliš velký (max {MAX_IMPORT_BYTES // 1024 // 1024} MB)"
        )

    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Nepodporovaný formát {ext}. Povoleno: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    if ext in (".md", ".txt"):
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return content.decode("cp1250")
            except UnicodeDecodeError as e:
                raise ValueError("Soubor není v UTF-8 ani CP1250") from e

    if ext == ".pdf":
        if not content.startswith(b"%PDF"):
            raise ValueError("Soubor má příponu .pdf, ale není platné PDF")
        return _extract_pdf(content)

    if ext == ".docx":
        return _extract_docx(content)

    # neměli bychom se sem dostat
    raise ValueError(f"Neznámý formát: {ext}")


def _extract_pdf(content: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise ValueError(
            "Pro import PDF je potřeba balíček pypdf — kontaktujte administrátora"
        ) from e

    try:
        reader = PdfReader(io.BytesIO(content))
    except Exception as e:
        raise ValueError(f"Nelze otevřít PDF: {e}") from e

    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    text = "\n\n".join(p.strip() for p in parts if p and p.strip())
    if not text.strip():
        raise ValueError(
            "PDF neobsahuje extrahovatelný text (může to být sken — použijte OCR)"
        )
    return text


def _extract_docx(content: bytes) -> str:
    try:
        import docx  # python-docx
    except ImportError as e:
        raise ValueError(
            "Pro import DOCX je potřeba balíček python-docx — kontaktujte administrátora"
        ) from e

    try:
        document = docx.Document(io.BytesIO(content))
    except Exception as e:
        raise ValueError(f"Nelze otevřít DOCX: {e}") from e

    paragraphs = [p.text for p in document.paragraphs if p.text and p.text.strip()]
    text = "\n\n".join(paragraphs)
    if not text.strip():
        raise ValueError("DOCX dokument je prázdný")
    return text
