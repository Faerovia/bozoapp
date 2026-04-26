"""Univerzální signature service.

Architektura:
- canonical_json(payload) — deterministická serializace pro hashování.
- compute_payload_hash(canonical_bytes) — SHA-256 obsahu dokumentu.
- compute_chain_hash(prev_hash, payload_hash, seq) — hash řetězec.
- create_signature(...) — vytvoří append-only řádek v `signatures`.
- verify_chain(tenant_id, since_seq) — projde chain a ověří integritu.

Atomicita:
Vytvoření podpisu je v transakci s SELECT FOR UPDATE na posledním řádku
chain — zabraňuje race condition když dva podpisy jdou současně.
Backend musí mít POSTGRES advisory lock NEBO serializovatelný režim.
Pro MVP používáme advisory lock (jeden globální pro signatures chain).
"""
from __future__ import annotations

import hashlib
import json
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from passlib.context import CryptContext
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password
from app.models.employee import Employee
from app.models.signature import (
    GENESIS_HASH,
    Signature,
    SmsOtpCode,
)
from app.models.user import User
from app.services.sms import SmsMessage, get_sms_sender

log = logging.getLogger("signatures")

# Postgres advisory lock ID pro signature chain (32-bit signed int).
# Konstantní, sdílený napříč celým systémem — serializuje vytváření podpisů
# tak, aby chain_hash byl konzistentní.
SIGNATURE_CHAIN_LOCK_ID = 824571392  # arbitrary fixed int

# OTP konstanty
OTP_LENGTH = 6
OTP_TTL_MINUTES = 5
OTP_MAX_ATTEMPTS = 3
DEV_OTP_CODE = "111111"  # v dev/mock SMS módu vždy tento kód

_otp_pwd = CryptContext(schemes=["argon2"], deprecated="auto")


# ── Canonical JSON & hashing ────────────────────────────────────────────────

def canonical_json(payload: dict[str, Any]) -> bytes:
    """Deterministická JSON serializace pro hashování.

    - Klíče seřazené abecedně (sort_keys=True).
    - Žádné mezery (separators=(",", ":")).
    - UTF-8 (ensure_ascii=False) — české znaky se hashují přímo.
    - JSON-serializable typy: str, int, float, bool, None, list, dict.
      Datumy/UUID musí být převedené na string před voláním.
    """
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def compute_payload_hash(canonical_bytes: bytes) -> str:
    """SHA-256 hex digest payloadu."""
    return hashlib.sha256(canonical_bytes).hexdigest()


def compute_chain_hash(prev_hash: str, payload_hash: str, seq: int) -> str:
    """Hash řetězec: SHA-256(prev_hash || payload_hash || seq)."""
    h = hashlib.sha256()
    h.update(prev_hash.encode("ascii"))
    h.update(payload_hash.encode("ascii"))
    h.update(str(seq).encode("ascii"))
    return h.hexdigest()


# ── Chain creation (atomic) ─────────────────────────────────────────────────

async def create_signature(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    doc_type: str,
    doc_id: uuid.UUID,
    employee: Employee,
    payload: dict[str, Any],
    auth_method: str,
    auth_proof: dict[str, Any],
) -> Signature:
    """Vytvoří podpis v append-only chainu. Atomicky pod advisory lockem."""
    # Advisory lock — serializuje všechny insertery napříč procesy.
    # Lock se uvolní při commit/rollback transakce.
    await db.execute(
        text(f"SELECT pg_advisory_xact_lock({SIGNATURE_CHAIN_LOCK_ID})"),
    )

    # Najdi poslední řádek
    last = (
        await db.execute(
            select(Signature).order_by(Signature.seq.desc()).limit(1),
        )
    ).scalar_one_or_none()

    if last is None:
        prev_hash = GENESIS_HASH
        next_seq = 1
    else:
        prev_hash = last.chain_hash
        next_seq = int(last.seq) + 1

    canonical = canonical_json(payload)
    payload_hash = compute_payload_hash(canonical)
    chain_hash = compute_chain_hash(prev_hash, payload_hash, next_seq)

    sig = Signature(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        doc_type=doc_type,
        doc_id=doc_id,
        employee_id=employee.id,
        employee_full_name_snapshot=employee.full_name,
        payload_canonical=payload,
        payload_hash=payload_hash,
        auth_method=auth_method,
        auth_proof=auth_proof,
        seq=next_seq,
        prev_hash=prev_hash,
        chain_hash=chain_hash,
        signed_at=datetime.now(UTC),
    )
    db.add(sig)
    await db.flush()
    log.info(
        "Signature created: doc_type=%s doc_id=%s emp=%s seq=%d hash=%s",
        doc_type, doc_id, employee.id, next_seq, chain_hash[:16],
    )
    return sig


# ── Chain verification ──────────────────────────────────────────────────────

async def verify_chain(
    db: AsyncSession,
    *,
    since_seq: int = 0,
    until_seq: int | None = None,
) -> dict[str, Any]:
    """Ověří hash chain v rozsahu [since_seq, until_seq].

    Vrací:
        {
            "ok": bool,
            "checked": int,
            "first_seq": int | None,
            "last_seq": int | None,
            "first_failure_seq": int | None,
            "first_failure_reason": str | None,
        }
    """
    q = select(Signature).order_by(Signature.seq.asc())
    if since_seq > 0:
        q = q.where(Signature.seq > since_seq)
    if until_seq is not None:
        q = q.where(Signature.seq <= until_seq)

    rows = (await db.execute(q)).scalars().all()
    if not rows:
        return {
            "ok": True,
            "checked": 0,
            "first_seq": None,
            "last_seq": None,
            "first_failure_seq": None,
            "first_failure_reason": None,
        }

    # Načti prev_hash pro první řádek — pokud since_seq>0, je to chain_hash
    # předchozího řádku (musí existovat).
    expected_prev: str
    if since_seq == 0:
        expected_prev = GENESIS_HASH
    else:
        prev_row = (
            await db.execute(
                select(Signature).where(Signature.seq == since_seq),
            )
        ).scalar_one_or_none()
        if prev_row is None:
            return {
                "ok": False,
                "checked": 0,
                "first_seq": None,
                "last_seq": None,
                "first_failure_seq": since_seq,
                "first_failure_reason": (
                    f"Předchozí řádek seq={since_seq} chybí — chain rozbitý"
                ),
            }
        expected_prev = prev_row.chain_hash

    failure_seq: int | None = None
    failure_reason: str | None = None

    for row in rows:
        # 1) prev_hash musí odpovídat chain_hash předchozího řádku
        if row.prev_hash != expected_prev:
            failure_seq = int(row.seq)
            failure_reason = (
                f"prev_hash mismatch: očekávaný={expected_prev[:16]}, "
                f"uložený={row.prev_hash[:16]}"
            )
            break

        # 2) payload_hash musí odpovídat aktuálnímu payload_canonical
        recomputed_payload = compute_payload_hash(
            canonical_json(row.payload_canonical),
        )
        if recomputed_payload != row.payload_hash:
            failure_seq = int(row.seq)
            failure_reason = (
                "payload_hash mismatch: payload byl změněn po podpisu"
            )
            break

        # 3) chain_hash musí odpovídat
        recomputed_chain = compute_chain_hash(
            row.prev_hash, row.payload_hash, int(row.seq),
        )
        if recomputed_chain != row.chain_hash:
            failure_seq = int(row.seq)
            failure_reason = (
                "chain_hash mismatch: chain byl tampered"
            )
            break

        expected_prev = row.chain_hash

    return {
        "ok": failure_seq is None,
        "checked": len(rows),
        "first_seq": int(rows[0].seq),
        "last_seq": int(rows[-1].seq),
        "first_failure_seq": failure_seq,
        "first_failure_reason": failure_reason,
    }


# ── SMS OTP flow ────────────────────────────────────────────────────────────

def _generate_otp() -> str:
    """Vygeneruje 6místný OTP. V dev mode vrací '111111' (z services/sms.py)."""
    from app.services.sms import is_dev_mode
    if is_dev_mode():
        return DEV_OTP_CODE
    # Production: cryptograficky bezpečný 6-digit
    return f"{secrets.randbelow(10 ** OTP_LENGTH):0{OTP_LENGTH}d}"


async def initiate_sms_otp(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    employee: Employee,
    doc_type: str,
    doc_id: uuid.UUID,
) -> SmsOtpCode:
    """Vygeneruje OTP, pošle SMS, uloží hash do DB."""
    if not employee.phone:
        raise ValueError(
            "Zaměstnanec nemá uložené telefonní číslo — nelze poslat SMS",
        )

    code = _generate_otp()
    code_hash = _otp_pwd.hash(code)
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=OTP_TTL_MINUTES)

    otp_row = SmsOtpCode(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=employee.id,
        doc_type=doc_type,
        doc_id=doc_id,
        code_hash=code_hash,
        sent_to=employee.phone,
        attempts=0,
        verified_at=None,
        expires_at=expires,
        created_at=now,
    )
    db.add(otp_row)
    await db.flush()

    sender = get_sms_sender()
    body = (
        f"DigitalOZO: kód pro podpis dokumentu: {code}. "
        f"Platnost {OTP_TTL_MINUTES} min."
    )
    await sender.send(SmsMessage(to=employee.phone, body=body))

    log.info(
        "SMS OTP sent: emp=%s doc=%s/%s expires=%s",
        employee.id, doc_type, doc_id, expires,
    )
    return otp_row


async def verify_sms_otp(
    db: AsyncSession,
    *,
    employee: Employee,
    doc_type: str,
    doc_id: uuid.UUID,
    code: str,
) -> SmsOtpCode:
    """Ověří OTP. Vyhazuje ValueError při neúspěchu (různé důvody).

    Po úspěšném ověření nastaví verified_at = now.
    """
    now = datetime.now(UTC)

    # Pokud je víc pending OTP pro tuto kombinaci, vezmi ten poslední
    # (předchozí byly nahrazeny novým).
    otp = (
        await db.execute(
            select(SmsOtpCode)
            .where(
                SmsOtpCode.employee_id == employee.id,
                SmsOtpCode.doc_type == doc_type,
                SmsOtpCode.doc_id == doc_id,
                SmsOtpCode.verified_at.is_(None),
            )
            .order_by(SmsOtpCode.created_at.desc())
            .limit(1),
        )
    ).scalar_one_or_none()

    if otp is None:
        raise ValueError(
            "Žádný aktivní OTP — vygeneruj nový kód přes /signatures/initiate",
        )
    if otp.expires_at < now:
        raise ValueError("OTP kód vypršel (5 min). Vygeneruj nový kód.")
    if otp.attempts >= OTP_MAX_ATTEMPTS:
        raise ValueError(
            f"Překročen limit pokusů ({OTP_MAX_ATTEMPTS}). "
            f"Vygeneruj nový kód.",
        )

    otp.attempts = otp.attempts + 1
    if not _otp_pwd.verify(code, otp.code_hash):
        await db.flush()
        remaining = OTP_MAX_ATTEMPTS - otp.attempts
        raise ValueError(
            f"Nesprávný kód. Zbývá {remaining} pokusů.",
        )

    otp.verified_at = now
    await db.flush()
    return otp


# ── Password verification (= login password) ───────────────────────────────

async def verify_employee_password(
    db: AsyncSession,
    *,
    employee: Employee,
    password: str,
) -> bool:
    """Ověří, že password odpovídá hash zaměstnancova auth user accountu.

    Pokud zaměstnanec nemá user account, vyhazuje ValueError — caller musí
    forcovat sms_otp.
    """
    if employee.user_id is None:
        raise ValueError(
            "Zaměstnanec nemá login účet — použij SMS OTP místo hesla",
        )
    user = (
        await db.execute(
            select(User).where(User.id == employee.user_id),
        )
    ).scalar_one_or_none()
    if user is None or not user.hashed_password:
        raise ValueError("User account nedostupný")
    return verify_password(password, user.hashed_password)
