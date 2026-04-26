"""
TOTP (RFC 6238) 2FA service.

Flow:
1. `begin_setup(user)` — vygeneruje base32 secret, uloží Fernet-encrypted do
   users.totp_secret (ale totp_enabled zůstává False dokud user nepotvrdí).
   Vrátí (secret_cleartext, otpauth_uri) — caller generuje QR kód pro klienta.
2. `confirm_setup(user, code)` — ověří prvni TOTP kód, pokud OK → totp_enabled=True,
   vygeneruje 10 recovery codes. Vrátí cleartext recovery codes (zobrazí uživateli
   jednou a v DB už jen jejich hash).
3. `verify(user, code)` — validuje TOTP kód nebo recovery code při loginu.
4. `disable(user)` — vymaže secret + recovery codes.

Admin override: OZO může disable 2FA jinému userovi v tenantu (viz users service).
"""
from __future__ import annotations

import hashlib
import secrets as pysecrets
import uuid

import pyotp
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import decrypt_text, encrypt_text
from app.models.recovery_code import RecoveryCode
from app.models.user import User

# Issuer ukazovaný v autentikátoru (Google Authenticator, 1Password, atd.)
TOTP_ISSUER = "OZODigi"
RECOVERY_CODE_COUNT = 10
# Délka jednoho recovery kódu (bytes před hex). 8 bytes → 16 hex chars.
RECOVERY_CODE_BYTES = 8


def _hash_recovery(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _generate_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> list[str]:
    return [pysecrets.token_hex(RECOVERY_CODE_BYTES) for _ in range(count)]


def decrypt_secret(user: User) -> str | None:
    """Vrátí dešifrovaný TOTP secret usera, nebo None."""
    if not user.totp_secret:
        return None
    return decrypt_text(user.totp_secret)


async def begin_setup(db: AsyncSession, user: User) -> tuple[str, str]:
    """
    Vygeneruje nový TOTP secret a uloží (encrypted). Vrátí (secret_cleartext,
    otpauth_uri) — otpauth://totp/... link pro klient QR renderer.

    totp_enabled zůstává FALSE dokud user nepotvrdí přes confirm_setup.
    Předchozí (nepotvrzený) secret se přepíše — re-setup je bezpečný.
    """
    secret = pyotp.random_base32()
    user.totp_secret = encrypt_text(secret)
    user.totp_enabled = False
    await db.flush()

    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=user.email, issuer_name=TOTP_ISSUER)
    return secret, uri


async def confirm_setup(
    db: AsyncSession, user: User, code: str
) -> list[str] | None:
    """
    Potvrdí setup — ověří první TOTP kód. Pokud OK:
    - totp_enabled = True
    - vygeneruje 10 recovery codes (hash v DB, cleartext vráceno volajícímu)

    Vrátí seznam cleartext recovery codes nebo None pokud kód nesedí.
    """
    secret = decrypt_secret(user)
    if secret is None:
        return None

    totp = pyotp.TOTP(secret)
    # valid_window=1 = akceptuje ±30s odchylku (clock drift)
    if not totp.verify(code, valid_window=1):
        return None

    user.totp_enabled = True

    # Vymaž případné staré recovery codes z předchozího setupu
    from sqlalchemy import delete
    await db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))

    # Vygeneruj novou sadu
    codes = _generate_recovery_codes()
    for code_plain in codes:
        db.add(RecoveryCode(
            tenant_id=user.tenant_id,
            user_id=user.id,
            code_hash=_hash_recovery(code_plain),
        ))
    await db.flush()
    return codes


async def verify(db: AsyncSession, user: User, code: str) -> bool:
    """
    Ověří TOTP kód (6 číslic) NEBO recovery code (16 hex chars).
    Recovery code se po použití označí `used_at`.

    Vrací True pokud kód prošel.
    """
    if not user.totp_enabled:
        # 2FA není zapnuté → jakýkoli kód odmítni (caller má kontrolu totp_enabled)
        return False

    # Rozlišení: 6 čísliců → TOTP, jinak recovery code
    cleaned = code.strip().replace(" ", "").lower()

    if cleaned.isdigit() and len(cleaned) == 6:
        secret = decrypt_secret(user)
        if secret is None:
            return False
        totp = pyotp.TOTP(secret)
        return bool(totp.verify(cleaned, valid_window=1))

    # Recovery code path
    code_hash = _hash_recovery(cleaned)
    row = (await db.execute(
        select(RecoveryCode).where(
            RecoveryCode.user_id == user.id,
            RecoveryCode.code_hash == code_hash,
            RecoveryCode.used_at.is_(None),
        )
    )).scalar_one_or_none()

    if row is None:
        return False

    from datetime import UTC, datetime
    row.used_at = datetime.now(UTC)
    await db.flush()
    return True


async def disable(db: AsyncSession, user: User) -> None:
    """Vypne 2FA a smaže všechny recovery codes."""
    from sqlalchemy import delete
    user.totp_secret = None
    user.totp_enabled = False
    await db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
    await db.flush()


async def regenerate_recovery_codes(db: AsyncSession, user: User) -> list[str]:
    """Vymaže staré a vytvoří novou sadu. Pro situaci kdy user ztratí codes."""
    from sqlalchemy import delete
    await db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
    codes = _generate_recovery_codes()
    for code_plain in codes:
        db.add(RecoveryCode(
            tenant_id=user.tenant_id,
            user_id=user.id,
            code_hash=_hash_recovery(code_plain),
        ))
    await db.flush()
    return codes


async def count_unused_recovery_codes(db: AsyncSession, user: User) -> int:
    from sqlalchemy import func
    result = await db.execute(
        select(func.count(RecoveryCode.id)).where(
            RecoveryCode.user_id == user.id,
            RecoveryCode.used_at.is_(None),
        )
    )
    count: int = result.scalar() or 0
    return count


async def admin_disable_for_user(
    db: AsyncSession, target_user_id: uuid.UUID
) -> bool:
    """OZO disable 2FA pro jiného usera (ztráta telefonu atd.). Volá tenantový endpoint."""
    await db.execute(
        update(User)
        .where(User.id == target_user_id)
        .values(totp_secret=None, totp_enabled=False)
    )
    from sqlalchemy import delete
    await db.execute(
        delete(RecoveryCode).where(RecoveryCode.user_id == target_user_id)
    )
    await db.flush()
    return True
