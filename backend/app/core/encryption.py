"""
Symmetric encryption pro citlivá pole (personal_id, totp_secret, atd.).

Fernet (cryptography) = AES-128-CBC + HMAC-SHA256 s timestampem. Klíč je
32-byte URL-safe base64 string v `FERNET_KEY` env proměnné.

Použití:
    enc = encrypt_text("6908040345")   # → "gAAAAABh..."
    raw = decrypt_text(enc)            # → "6908040345"

V testech / dev bez FERNET_KEY vracíme plaintext (pass-through) aby se app
rozběhla bez extra konfigurace. Produkční SECRET_KEY validator odmítne start
bez FERNET_KEY.

Rotace klíčů: zatím neřešíme. Až přijde čas, MultiFernet s historií klíčů
umí postupné re-encryption bez downtime.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import String
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

from app.core.config import get_settings

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _fernet() -> Fernet | None:
    settings = get_settings()
    if not settings.fernet_key:
        log.warning(
            "FERNET_KEY not set — encryption disabled (plaintext passthrough). "
            "OK for dev/test. MUST be set in production."
        )
        return None
    try:
        return Fernet(settings.fernet_key.encode("utf-8"))
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(
            f"FERNET_KEY is invalid (must be 32-byte URL-safe base64): {e}"
        ) from e


def encrypt_text(plaintext: str | None) -> str | None:
    """Šifruje string. None/empty → passthrough (pro nullable columny)."""
    if plaintext is None or plaintext == "":
        return plaintext
    f = _fernet()
    if f is None:
        return plaintext  # dev/test passthrough
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_text(ciphertext: str | None) -> str | None:
    """Dešifruje string. None/empty → passthrough. Invalid token → log+as-is."""
    if ciphertext is None or ciphertext == "":
        return ciphertext
    f = _fernet()
    if f is None:
        return ciphertext  # dev/test passthrough
    try:
        return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        # Možná data uložená před zapnutím encryption (plaintext). Vrátíme jak je.
        # Alternativně: error — záleží na toleranci pro legacy data.
        log.warning("decrypt_text: InvalidToken, returning as-is (legacy plaintext?)")
        return ciphertext


class EncryptedString(TypeDecorator[str]):
    """
    SQLAlchemy type: sloupce deklarované `EncryptedString(length)` se:
    - při INSERT/UPDATE automaticky Fernet-encrypt-ují
    - při SELECT automaticky dešifrují

    `length` je maximální velikost SHIFROVANÉHO textu (Fernet ~100B overhead +
    base64 overhead → pro plaintext 20 chars je safe 256).

    Legacy plaintext data (před zapnutím encryption) se vrátí beze změny
    (InvalidToken fallback v decrypt_text).
    """

    impl = String
    cache_ok = True

    def __init__(self, length: int = 256, **kwargs: Any) -> None:
        super().__init__(length, **kwargs)

    def process_bind_param(
        self, value: str | None, dialect: Dialect
    ) -> str | None:
        return encrypt_text(value)

    def process_result_value(
        self, value: str | None, dialect: Dialect
    ) -> str | None:
        return decrypt_text(value)
