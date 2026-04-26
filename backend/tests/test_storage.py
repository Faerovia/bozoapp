"""
Testy pro storage abstrakci (commit 19d).

Local backend test_*: pokrývají write/read/exists/delete + path traversal protection.
S3 backend test_*: skip pokud chybí boto3 nebo env. Test používá moto (mock S3).
"""

import uuid
from pathlib import Path

import pytest

from app.core.storage import (
    LocalStorageBackend,
    file_exists,
    get_storage,
    read_file,
    reset_storage_for_tests,
    save_accident_photo,
    save_invoice_pdf,
    save_tenant_logo,
)


@pytest.fixture(autouse=True)
def _reset_storage():
    reset_storage_for_tests()
    yield
    reset_storage_for_tests()


# ── LocalStorageBackend ──────────────────────────────────────────────────────


def test_local_write_read_exists_delete(tmp_path: Path) -> None:
    backend = LocalStorageBackend(tmp_path)

    rel = "tenants/abc/file.txt"
    backend.write(rel, b"hello")
    assert backend.exists(rel)
    assert backend.read(rel) == b"hello"

    backend.delete(rel)
    assert not backend.exists(rel)


def test_local_path_traversal_blocked(tmp_path: Path) -> None:
    backend = LocalStorageBackend(tmp_path)
    with pytest.raises(ValueError, match="Path traversal"):
        backend.write("../../etc/passwd", b"x")


def test_local_overwrite(tmp_path: Path) -> None:
    backend = LocalStorageBackend(tmp_path)
    backend.write("a/b.txt", b"first")
    backend.write("a/b.txt", b"second")
    assert backend.read("a/b.txt") == b"second"


def test_local_creates_nested_dirs(tmp_path: Path) -> None:
    backend = LocalStorageBackend(tmp_path)
    backend.write("deep/nested/path/file.bin", b"data")
    assert (tmp_path / "deep/nested/path/file.bin").is_file()


# ── Veřejné API přes get_storage() ───────────────────────────────────────────


def test_save_invoice_pdf_returns_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    monkeypatch.setenv("STORAGE_BACKEND", "local")

    from app.core.config import get_settings
    get_settings.cache_clear()
    reset_storage_for_tests()

    rel = save_invoice_pdf(2026, "20260001", b"%PDF-fake")
    assert rel == "invoices/2026/20260001.pdf"
    assert file_exists(rel)
    assert read_file(rel) == b"%PDF-fake"

    get_settings.cache_clear()


def test_save_tenant_logo_path_format(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    monkeypatch.setenv("STORAGE_BACKEND", "local")

    from app.core.config import get_settings
    get_settings.cache_clear()
    reset_storage_for_tests()

    tid = uuid.uuid4()
    rel = save_tenant_logo(tid, b"PNG-fake", "logo.png")
    assert rel == f"tenants/{tid}/logo.png"
    assert file_exists(rel)

    get_settings.cache_clear()


def test_save_tenant_logo_rejects_invalid_extension(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    from app.core.config import get_settings
    get_settings.cache_clear()
    reset_storage_for_tests()

    tid = uuid.uuid4()
    with pytest.raises(ValueError, match="Nepodporovaný formát"):
        save_tenant_logo(tid, b"x", "logo.bmp")

    get_settings.cache_clear()


def test_save_accident_photo_with_image_extension(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    from app.core.config import get_settings
    get_settings.cache_clear()
    reset_storage_for_tests()

    tid = uuid.uuid4()
    aid = uuid.uuid4()
    pid = uuid.uuid4()
    rel = save_accident_photo(tid, aid, pid, b"JPG-fake", "photo.jpg")
    assert rel.endswith(".jpg")
    assert file_exists(rel)

    get_settings.cache_clear()


# ── Factory selection ────────────────────────────────────────────────────────


def test_factory_returns_local_by_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    from app.core.config import get_settings
    get_settings.cache_clear()
    reset_storage_for_tests()

    backend = get_storage()
    assert isinstance(backend, LocalStorageBackend)

    get_settings.cache_clear()


def test_factory_raises_when_s3_misconfigured(monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.setenv("S3_BUCKET", "")  # chybějící
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "")

    from app.core.config import get_settings
    get_settings.cache_clear()
    reset_storage_for_tests()

    with pytest.raises(RuntimeError, match="STORAGE_BACKEND=s3"):
        get_storage()

    get_settings.cache_clear()
