"""
File storage pro uploads (PDF obsah školení, loga firem).

Zatím lokální filesystem v `settings.upload_dir`. Do budoucna lze snadno
přepnout na S3-kompatibilní backend přes Protocol (viz email sender pattern).

Cesty v DB jsou RELATIVNÍ vzhledem k upload_dir, např:
  "trainings/{tid}/{training_id}/content.pdf"
  "tenants/{tid}/logo.png"

To umožní migrovat storage bez přepisu DB.
"""
from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

from app.core.config import get_settings

log = logging.getLogger(__name__)

MAX_TRAINING_PDF_BYTES = 3 * 1024 * 1024   # 3 MB
MAX_LOGO_BYTES = 1 * 1024 * 1024           # 1 MB
MAX_TEST_CSV_BYTES = 500 * 1024            # 500 KB
MAX_REVISION_FILE_BYTES = 5 * 1024 * 1024  # 5 MB (PDF nebo foto z terénu)
_ALLOWED_PDF_MIME = "application/pdf"
_ALLOWED_LOGO_EXTENSIONS = {".png", ".jpg", ".jpeg"}
_ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".heic"}


def _upload_root() -> Path:
    return Path(get_settings().upload_dir)


def _safe_join(*parts: str) -> Path:
    """Join cesta vůči upload_root s ochranou proti ../ escape."""
    root = _upload_root().resolve()
    candidate = root.joinpath(*parts).resolve()
    # Ochrana proti traversal
    try:
        candidate.relative_to(root)
    except ValueError as e:
        raise ValueError(f"Path traversal attempt: {candidate}") from e
    return candidate


def save_training_pdf(
    tenant_id: uuid.UUID, training_id: uuid.UUID, content: bytes
) -> str:
    """Uloží PDF obsahu školení a vrátí relativní cestu pro DB."""
    if len(content) > MAX_TRAINING_PDF_BYTES:
        raise ValueError(
            f"PDF je příliš velké (max {MAX_TRAINING_PDF_BYTES // 1024 // 1024} MB)"
        )
    if not content.startswith(b"%PDF"):
        raise ValueError("Soubor není platné PDF")

    rel_path = f"trainings/{tenant_id}/{training_id}/content.pdf"
    full = _safe_join(rel_path)
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_bytes(content)
    return rel_path


def save_tenant_logo(
    tenant_id: uuid.UUID, content: bytes, filename: str
) -> str:
    """Uloží logo firmy. Vrací relativní cestu."""
    if len(content) > MAX_LOGO_BYTES:
        raise ValueError(
            f"Logo je příliš velké (max {MAX_LOGO_BYTES // 1024} KB)"
        )
    ext = Path(filename).suffix.lower()
    if ext not in _ALLOWED_LOGO_EXTENSIONS:
        raise ValueError(f"Nepodporovaný formát loga (povoleno: {_ALLOWED_LOGO_EXTENSIONS})")

    rel_path = f"tenants/{tenant_id}/logo{ext}"
    full = _safe_join(rel_path)
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_bytes(content)
    return rel_path


def save_rfa_factor_pdf(
    tenant_id: uuid.UUID,
    rfa_id: uuid.UUID,
    factor_key: str,
    content: bytes,
) -> str:
    """
    Uloží PDF příloh k rizikovému faktoru (měření hygieny / protokol).
    factor_key je jeden z RF_FIELDS (rf_prach, rf_chem, …).
    """
    if len(content) > MAX_TRAINING_PDF_BYTES:  # stejný 3 MB limit jako u tréninku
        raise ValueError(
            f"PDF je příliš velké (max {MAX_TRAINING_PDF_BYTES // 1024 // 1024} MB)"
        )
    if not content.startswith(b"%PDF"):
        raise ValueError("Soubor není platné PDF")

    # Validace factor_key proti whitelistu — ochrana proti injection do cesty
    if not factor_key.startswith("rf_") or not factor_key.replace("_", "").isalnum():
        raise ValueError(f"Neplatný factor_key: {factor_key}")

    rel_path = f"rfa/{tenant_id}/{rfa_id}/{factor_key}.pdf"
    full = _safe_join(rel_path)
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_bytes(content)
    return rel_path


def save_accident_signed_document(
    tenant_id: uuid.UUID,
    accident_id: uuid.UUID,
    content: bytes,
    filename: str,
) -> str:
    """
    Uloží podepsaný papírový záznam o úrazu (PDF nebo obrázek skenu).
    Per úraz může existovat pouze jeden — předchozí přepíše.
    """
    if len(content) > MAX_REVISION_FILE_BYTES:
        raise ValueError(
            f"Soubor je příliš velký (max {MAX_REVISION_FILE_BYTES // 1024 // 1024} MB)"
        )

    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        if not content.startswith(b"%PDF"):
            raise ValueError("Soubor má příponu .pdf ale není platné PDF")
    elif ext not in _ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError(
            "Nepodporovaný formát (povoleno: PDF, PNG, JPG, JPEG, WEBP, HEIC)"
        )

    rel_path = f"accidents/{tenant_id}/{accident_id}/signed_document{ext}"
    full = _safe_join(rel_path)
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_bytes(content)
    return rel_path


def save_accident_photo(
    tenant_id: uuid.UUID,
    accident_id: uuid.UUID,
    photo_id: uuid.UUID,
    content: bytes,
    filename: str,
) -> str:
    """Uloží fotku úrazu (max 5 MB, image/* extension). Vrací relativní cestu."""
    if len(content) > MAX_REVISION_FILE_BYTES:
        raise ValueError(
            f"Fotka je příliš velká (max {MAX_REVISION_FILE_BYTES // 1024 // 1024} MB)"
        )

    ext = Path(filename).suffix.lower()
    if ext not in _ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError(
            "Nepodporovaný formát fotky (povoleno: PNG, JPG, JPEG, WEBP, HEIC)"
        )

    rel_path = f"accidents/{tenant_id}/{accident_id}/{photo_id}{ext}"
    full = _safe_join(rel_path)
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_bytes(content)
    return rel_path


def save_revision_record_file(
    tenant_id: uuid.UUID,
    revision_id: uuid.UUID,
    record_id: uuid.UUID,
    content: bytes,
    filename: str,
) -> tuple[str | None, str | None]:
    """
    Uloží přílohu k záznamu revize — PDF nebo obrázek.
    Vrací (pdf_path, image_path), z toho právě jedno je None.
    """
    if len(content) > MAX_REVISION_FILE_BYTES:
        raise ValueError(
            f"Soubor je příliš velký (max {MAX_REVISION_FILE_BYTES // 1024 // 1024} MB)"
        )

    ext = Path(filename).suffix.lower()

    # PDF větev
    if ext == ".pdf":
        if not content.startswith(b"%PDF"):
            raise ValueError("Soubor má příponu .pdf ale není platné PDF")
        rel_path = f"revisions/{tenant_id}/{revision_id}/{record_id}.pdf"
        full = _safe_join(rel_path)
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(content)
        return rel_path, None

    # Obrázková větev
    if ext in _ALLOWED_IMAGE_EXTENSIONS:
        rel_path = f"revisions/{tenant_id}/{revision_id}/{record_id}{ext}"
        full = _safe_join(rel_path)
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(content)
        return None, rel_path

    raise ValueError(
        "Nepodporovaný formát (povoleno: PDF, PNG, JPG, JPEG, WEBP, HEIC)"
    )


def read_file(rel_path: str) -> bytes:
    """Načte soubor podle relativní cesty. Raises FileNotFoundError."""
    full = _safe_join(rel_path)
    return full.read_bytes()


def file_exists(rel_path: str | None) -> bool:
    if not rel_path:
        return False
    try:
        return _safe_join(rel_path).is_file()
    except ValueError:
        return False


def delete_file(rel_path: str | None) -> None:
    if not rel_path:
        return
    try:
        full = _safe_join(rel_path)
        if full.is_file():
            full.unlink()
    except (ValueError, OSError) as e:
        log.warning("Could not delete file %s: %s", rel_path, e)


def ensure_upload_dir_exists() -> None:
    """Volat při startupu. Vytvoří root adresář pokud chybí."""
    root = _upload_root()
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        log.warning("Could not create upload dir %s: %s", root, e)


# For tests — reset helper
def _reset_for_tests() -> None:
    """Pouze pro testy — vyčistí obsah upload_dir."""
    root = _upload_root()
    if root.exists():
        for p in root.rglob("*"):
            if p.is_file():
                os.remove(p)
