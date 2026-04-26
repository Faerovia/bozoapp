"""
Service pro digitální podpis školení.

Workflow:
1. Standard podpis (Training.requires_qes=False):
   - klient pošle base64 canvas PNG → sign_assignment() uloží + audit
2. ZES podpis (Training.requires_qes=True):
   - klient zavolá request_otp() → server vygeneruje 6-místný kód, pošle emailem
   - klient zavolá verify_otp(code) → server označí OTP jako verified
   - klient pošle base64 canvas PNG → sign_assignment(qes=True) ověří verified OTP

Bezpečnost:
- timestamp je VŽDY server-side (klientskému času nevěříme)
- IP a user agent ukládáme do signature_meta (audit trail)
- OTP kódy: hash (Argon2) + max 5 attempts + 10 min TTL
- Bez verified OTP nelze podepsat ZES školení
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.email import EmailMessage, get_email_sender
from app.core.security import hash_password, verify_password
from app.core.sms import SmsMessage, get_sms_sender
from app.models.employee import Employee
from app.models.training import Training, TrainingAssignment
from app.models.training_signature_otp import TrainingSignatureOTP

OTP_LIFETIME_MINUTES = 10
OTP_MAX_ATTEMPTS = 5


class SigningError(Exception):
    """Aplikační chyba při podpisu (špatný OTP, expirovaný OTP, atd.)."""


# ── Standard signing (canvas only) ───────────────────────────────────────────


async def sign_assignment(
    db: AsyncSession,
    *,
    assignment: TrainingAssignment,
    signature_image_b64: str,
    method: str = "simple",
    request_ip: str | None = None,
    user_agent: str | None = None,
    otp_id: uuid.UUID | None = None,
) -> TrainingAssignment:
    """
    Uloží podpis na assignment. Pokud assignment.training.requires_qes=True,
    volající MUSÍ předat otp_id z verified OTP — jinak SigningError.
    """
    if not signature_image_b64.startswith("data:image/png;base64,"):
        raise SigningError("Podpis musí být PNG v data URL formátu")

    # Načti training kvůli requires_qes flagu
    training = (await db.execute(
        select(Training).where(Training.id == assignment.training_id)
    )).scalar_one()

    if training.requires_qes:
        if method != "qes":
            raise SigningError(
                "Toto školení vyžaduje ZES — použij requires_qes flow",
            )
        if otp_id is None:
            raise SigningError("ZES podpis vyžaduje verified OTP")
        otp = (await db.execute(
            select(TrainingSignatureOTP).where(TrainingSignatureOTP.id == otp_id)
        )).scalar_one_or_none()
        if otp is None or otp.verified_at is None:
            raise SigningError("OTP nebyl ověřen")
        if otp.assignment_id != assignment.id:
            raise SigningError("OTP patří jinému assignmentu")

    now = datetime.now(UTC)
    assignment.signature_image = signature_image_b64
    assignment.signed_at = now
    assignment.signature_method = method
    assignment.signature_meta = {
        "ip": request_ip,
        "user_agent": user_agent,
        "server_signed_at": now.isoformat(),
        "otp_id": str(otp_id) if otp_id else None,
    }
    await db.flush()
    return assignment


# ── OTP flow pro ZES ─────────────────────────────────────────────────────────


def _generate_otp_code() -> str:
    """6-místný numerický kód."""
    return f"{secrets.randbelow(1_000_000):06d}"


async def request_otp(
    db: AsyncSession,
    *,
    assignment: TrainingAssignment,
    employee: Employee,
    channel: str | None = None,
) -> TrainingSignatureOTP:
    """
    Vygeneruje OTP kód, uloží jeho hash, pošle plaintext kód.

    Kanál:
    - channel="email" → nutí email; pokud chybí → SigningError
    - channel="sms"   → nutí SMS; pokud chybí phone → SigningError
    - channel=None    → auto: preferuje email, fallback SMS, jinak SigningError

    Vrátí OTP řádek (id se použije v verify a sign).
    """
    has_email = bool(employee.email)
    has_phone = bool(employee.phone)

    if channel is None:
        if has_email:
            channel = "email"
        elif has_phone:
            channel = "sms"
        else:
            raise SigningError(
                "Zaměstnanec nemá email ani telefon — ZES podpis nelze "
                "provést. Doplň kontakt v profilu zaměstnance nebo přepni "
                "školení na simple podpis.",
            )

    if channel == "email" and not has_email:
        raise SigningError("Zaměstnanec nemá email")
    if channel == "sms" and not has_phone:
        raise SigningError("Zaměstnanec nemá telefon")

    sent_to: str = employee.email if channel == "email" else employee.phone  # type: ignore[assignment]

    code = _generate_otp_code()
    code_hash = hash_password(code)
    now = datetime.now(UTC)

    otp = TrainingSignatureOTP(
        tenant_id=assignment.tenant_id,
        assignment_id=assignment.id,
        employee_id=employee.id,
        code_hash=code_hash,
        sent_to=sent_to,
        channel=channel,
        expires_at=now + timedelta(minutes=OTP_LIFETIME_MINUTES),
        created_at=now,
    )
    db.add(otp)
    await db.flush()

    # Pošli kód podle kanálu
    body_text = (
        f"Váš kód pro podpis školení: {code} "
        f"(platí {OTP_LIFETIME_MINUTES} min). OZODigi"
    )
    if channel == "email":
        await get_email_sender().send(EmailMessage(
            to=sent_to,
            subject="OZODigi — kód pro podpis školení",
            body_text=(
                f"Dobrý den,\n\n"
                f"váš kód pro podpis školení je:  {code}\n\n"
                f"Kód platí {OTP_LIFETIME_MINUTES} minut. Pokud jste podpis "
                f"nezahájili, ignorujte tento email.\n\n"
                f"OZODigi"
            ),
        ))
    else:  # sms
        await get_sms_sender().send(SmsMessage(to=sent_to, body=body_text))

    return otp


async def verify_otp(
    db: AsyncSession,
    *,
    otp_id: uuid.UUID,
    code: str,
) -> TrainingSignatureOTP:
    """Ověří kód. Increment attempts. Po MAX_ATTEMPTS → invalidate."""
    otp = (await db.execute(
        select(TrainingSignatureOTP).where(TrainingSignatureOTP.id == otp_id)
    )).scalar_one_or_none()

    if otp is None:
        raise SigningError("OTP nenalezen")
    if otp.verified_at is not None:
        raise SigningError("OTP už byl použit")
    if otp.expires_at < datetime.now(UTC):
        raise SigningError("OTP vypršel — vyžádej si nový")
    if otp.attempts >= OTP_MAX_ATTEMPTS:
        raise SigningError("Překročen limit pokusů — vyžádej si nový OTP")

    otp.attempts += 1
    if not verify_password(code, otp.code_hash):
        await db.flush()
        raise SigningError("Nesprávný kód")

    otp.verified_at = datetime.now(UTC)
    await db.flush()
    return otp


async def cleanup_expired_otps(db: AsyncSession) -> int:
    """Smaže expirované / použité OTP (pro periodicý cleanup)."""
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))
    now = datetime.now(UTC)
    result = await db.execute(
        text(
            """DELETE FROM training_signature_otps
               WHERE expires_at < :now OR verified_at IS NOT NULL"""
        ),
        {"now": now},
    )
    rowcount: int = getattr(result, "rowcount", 0) or 0
    return rowcount


# ── Helper pro audit trail ───────────────────────────────────────────────────


def signature_audit_summary(assignment: TrainingAssignment) -> dict[str, Any]:
    """Vrátí kompaktní summary pro audit log / admin UI."""
    if not assignment.is_signed:
        return {"signed": False}
    meta = assignment.signature_meta or {}
    return {
        "signed": True,
        "signed_at": assignment.signed_at.isoformat() if assignment.signed_at else None,
        "method": assignment.signature_method,
        "ip": meta.get("ip"),
        "user_agent": meta.get("user_agent"),
        "otp_id": meta.get("otp_id"),
    }
