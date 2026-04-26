"""
File storage pro uploads (PDF obsah školení, loga firem, fotky úrazů, ...).

Architektura:
- `StorageBackend` Protocol — minimální rozhraní (read / write / delete / exists)
- `LocalStorageBackend` — zápis do `settings.upload_dir`
- `S3StorageBackend` — Hetzner Object Storage / jakýkoliv S3-kompat. (boto3)
- `get_storage()` — singleton podle `settings.storage_backend`

Veřejné funkce nahoře (`save_*`, `read_file`, `delete_file`, ...) zůstávají
beze změny rozhraní — interně volají aktivní backend. Cesty v DB jsou
RELATIVNÍ (např. `tenants/{id}/logo.png`) a fungují stejně pro local i S3.
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any, Protocol

from app.core.config import get_settings

log = logging.getLogger(__name__)

MAX_TRAINING_PDF_BYTES = 3 * 1024 * 1024   # 3 MB
MAX_LOGO_BYTES = 1 * 1024 * 1024           # 1 MB
MAX_TEST_CSV_BYTES = 500 * 1024            # 500 KB
MAX_REVISION_FILE_BYTES = 5 * 1024 * 1024  # 5 MB
_ALLOWED_PDF_MIME = "application/pdf"
_ALLOWED_LOGO_EXTENSIONS = {".png", ".jpg", ".jpeg"}
_ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".heic"}


# ── Backend protocol ─────────────────────────────────────────────────────────


class StorageBackend(Protocol):
    def write(self, rel_path: str, content: bytes) -> None: ...
    def read(self, rel_path: str) -> bytes: ...
    def exists(self, rel_path: str) -> bool: ...
    def delete(self, rel_path: str) -> None: ...


# ── Local backend ────────────────────────────────────────────────────────────


class LocalStorageBackend:
    """Zápis na lokální filesystem v `settings.upload_dir`. Default pro dev."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        try:
            self._root.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            log.warning("Could not create upload dir %s: %s", self._root, e)

    def _safe_join(self, rel_path: str) -> Path:
        candidate = (self._root / rel_path).resolve()
        try:
            candidate.relative_to(self._root)
        except ValueError as e:
            raise ValueError(f"Path traversal attempt: {candidate}") from e
        return candidate

    def write(self, rel_path: str, content: bytes) -> None:
        full = self._safe_join(rel_path)
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(content)

    def read(self, rel_path: str) -> bytes:
        return self._safe_join(rel_path).read_bytes()

    def exists(self, rel_path: str) -> bool:
        try:
            return self._safe_join(rel_path).is_file()
        except ValueError:
            return False

    def delete(self, rel_path: str) -> None:
        try:
            full = self._safe_join(rel_path)
            if full.is_file():
                full.unlink()
        except (ValueError, OSError) as e:
            log.warning("Could not delete file %s: %s", rel_path, e)


# ── S3 backend (Hetzner Object Storage / AWS S3 / minio) ─────────────────────


class S3StorageBackend:
    """
    S3-kompatibilní backend (Hetzner Object Storage, AWS S3, MinIO, Wasabi…).
    Vyžaduje `boto3` a env: `STORAGE_BACKEND=s3` + `S3_ENDPOINT_URL`,
    `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`.

    Note: každá instance drží lazy-initialized `boto3` client. boto3 je
    importováno až při použití, aby ho dev/test nemuseli mít nainstalovaný.
    """

    def __init__(
        self,
        *,
        endpoint_url: str,
        bucket: str,
        access_key_id: str,
        secret_access_key: str,
        region: str,
    ) -> None:
        self._endpoint_url = endpoint_url
        self._bucket = bucket
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._region = region
        self._client: Any = None  # boto3 S3 client, lazy init

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3
            self._client = boto3.client(
                "s3",
                endpoint_url=self._endpoint_url,
                aws_access_key_id=self._access_key_id,
                aws_secret_access_key=self._secret_access_key,
                region_name=self._region,
            )
        return self._client

    def write(self, rel_path: str, content: bytes) -> None:
        self._get_client().put_object(
            Bucket=self._bucket,
            Key=rel_path,
            Body=content,
        )

    def read(self, rel_path: str) -> bytes:
        try:
            resp = self._get_client().get_object(Bucket=self._bucket, Key=rel_path)
            data: bytes = resp["Body"].read()
            return data
        except Exception as e:
            # AWS NoSuchKey → překlad na FileNotFoundError pro stejné API jako Local
            response = getattr(e, "response", None)
            err_code = ""
            if isinstance(response, dict):
                error_obj = response.get("Error", {})
                if isinstance(error_obj, dict):
                    err_code = str(error_obj.get("Code", ""))
            if err_code in ("NoSuchKey", "404"):
                raise FileNotFoundError(rel_path) from e
            raise

    def exists(self, rel_path: str) -> bool:
        try:
            self._get_client().head_object(Bucket=self._bucket, Key=rel_path)
            return True
        except Exception:
            return False

    def delete(self, rel_path: str) -> None:
        try:
            self._get_client().delete_object(Bucket=self._bucket, Key=rel_path)
        except Exception as e:
            log.warning("S3 delete failed for %s: %s", rel_path, e)


# ── Factory ──────────────────────────────────────────────────────────────────


_backend: StorageBackend | None = None


def get_storage() -> StorageBackend:
    """Singleton storage backend dle `settings.storage_backend`."""
    global _backend
    if _backend is not None:
        return _backend

    settings = get_settings()
    if settings.storage_backend == "s3":
        if not (
            settings.s3_endpoint_url
            and settings.s3_bucket
            and settings.s3_access_key_id
            and settings.s3_secret_access_key
        ):
            raise RuntimeError(
                "STORAGE_BACKEND=s3 ale chybí S3_ENDPOINT_URL/BUCKET/"
                "ACCESS_KEY_ID/SECRET_ACCESS_KEY",
            )
        _backend = S3StorageBackend(
            endpoint_url=settings.s3_endpoint_url,
            bucket=settings.s3_bucket,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key,
            region=settings.s3_region,
        )
    else:
        _backend = LocalStorageBackend(Path(settings.upload_dir))
    return _backend


def reset_storage_for_tests() -> None:
    """Pro testy — resetne singleton aby se znovu vytvořil podle nových env."""
    global _backend
    _backend = None


# ── Veřejné API (volá refactored funkce → StorageBackend) ────────────────────


def save_training_pdf(
    tenant_id: uuid.UUID, training_id: uuid.UUID, content: bytes
) -> str:
    if len(content) > MAX_TRAINING_PDF_BYTES:
        raise ValueError(
            f"PDF je příliš velké (max {MAX_TRAINING_PDF_BYTES // 1024 // 1024} MB)"
        )
    if not content.startswith(b"%PDF"):
        raise ValueError("Soubor není platné PDF")

    rel_path = f"trainings/{tenant_id}/{training_id}/content.pdf"
    get_storage().write(rel_path, content)
    return rel_path


def save_tenant_logo(
    tenant_id: uuid.UUID, content: bytes, filename: str
) -> str:
    if len(content) > MAX_LOGO_BYTES:
        raise ValueError(
            f"Logo je příliš velké (max {MAX_LOGO_BYTES // 1024} KB)"
        )
    ext = Path(filename).suffix.lower()
    if ext not in _ALLOWED_LOGO_EXTENSIONS:
        raise ValueError(f"Nepodporovaný formát loga (povoleno: {_ALLOWED_LOGO_EXTENSIONS})")

    rel_path = f"tenants/{tenant_id}/logo{ext}"
    get_storage().write(rel_path, content)
    return rel_path


def save_rfa_factor_pdf(
    tenant_id: uuid.UUID,
    rfa_id: uuid.UUID,
    factor_key: str,
    content: bytes,
) -> str:
    if len(content) > MAX_TRAINING_PDF_BYTES:
        raise ValueError(
            f"PDF je příliš velké (max {MAX_TRAINING_PDF_BYTES // 1024 // 1024} MB)"
        )
    if not content.startswith(b"%PDF"):
        raise ValueError("Soubor není platné PDF")
    if not factor_key.startswith("rf_") or not factor_key.replace("_", "").isalnum():
        raise ValueError(f"Neplatný factor_key: {factor_key}")

    rel_path = f"rfa/{tenant_id}/{rfa_id}/{factor_key}.pdf"
    get_storage().write(rel_path, content)
    return rel_path


def save_medical_exam_report(
    tenant_id: uuid.UUID,
    exam_id: uuid.UUID,
    content: bytes,
    filename: str,
) -> str:
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

    rel_path = f"medical_exams/{tenant_id}/{exam_id}/report{ext}"
    get_storage().write(rel_path, content)
    return rel_path


def save_accident_signed_document(
    tenant_id: uuid.UUID,
    accident_id: uuid.UUID,
    content: bytes,
    filename: str,
) -> str:
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
    get_storage().write(rel_path, content)
    return rel_path


def save_accident_photo(
    tenant_id: uuid.UUID,
    accident_id: uuid.UUID,
    photo_id: uuid.UUID,
    content: bytes,
    filename: str,
) -> str:
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
    get_storage().write(rel_path, content)
    return rel_path


def save_revision_record_file(
    tenant_id: uuid.UUID,
    revision_id: uuid.UUID,
    record_id: uuid.UUID,
    content: bytes,
    filename: str,
) -> tuple[str | None, str | None]:
    if len(content) > MAX_REVISION_FILE_BYTES:
        raise ValueError(
            f"Soubor je příliš velký (max {MAX_REVISION_FILE_BYTES // 1024 // 1024} MB)"
        )

    ext = Path(filename).suffix.lower()

    if ext == ".pdf":
        if not content.startswith(b"%PDF"):
            raise ValueError("Soubor má příponu .pdf ale není platné PDF")
        rel_path = f"revisions/{tenant_id}/{revision_id}/{record_id}.pdf"
        get_storage().write(rel_path, content)
        return rel_path, None

    if ext in _ALLOWED_IMAGE_EXTENSIONS:
        rel_path = f"revisions/{tenant_id}/{revision_id}/{record_id}{ext}"
        get_storage().write(rel_path, content)
        return None, rel_path

    raise ValueError(
        "Nepodporovaný formát (povoleno: PDF, PNG, JPG, JPEG, WEBP, HEIC)"
    )


def save_invoice_pdf(invoice_year: int, invoice_number: str, content: bytes) -> str:
    """Uloží PDF faktury — používá invoice_delivery."""
    rel_path = f"invoices/{invoice_year}/{invoice_number}.pdf"
    get_storage().write(rel_path, content)
    return rel_path


def read_file(rel_path: str) -> bytes:
    """Načte soubor podle relativní cesty. Raises FileNotFoundError."""
    return get_storage().read(rel_path)


def file_exists(rel_path: str | None) -> bool:
    if not rel_path:
        return False
    return get_storage().exists(rel_path)


def delete_file(rel_path: str | None) -> None:
    if not rel_path:
        return
    get_storage().delete(rel_path)


def ensure_upload_dir_exists() -> None:
    """No-op pro S3, vytvoří root pro Local. Volat při startupu."""
    backend = get_storage()
    if isinstance(backend, LocalStorageBackend):
        return  # __init__ už mkdir udělal


# For tests — reset helper
def _reset_for_tests() -> None:
    """Pouze pro testy — vyčistí obsah upload_dir (jen LocalStorage)."""
    import os

    settings = get_settings()
    root = Path(settings.upload_dir)
    if root.exists():
        for p in root.rglob("*"):
            if p.is_file():
                os.remove(p)
    reset_storage_for_tests()
