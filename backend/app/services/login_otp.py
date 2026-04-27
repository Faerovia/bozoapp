"""Login OTP service — passwordless login přes SMS kód.

Liší se od signature SMS OTP (services/signatures.py) tím, že:
- Není vázaný na document — vrátí jen JWT.
- Neřeší tenant kontext, ale identifuje User napříč tenanty.
- Telefonní číslo se hledá z Employee.user_id (User sám phone nemá).

Životní cyklus:
1. request_login_otp(identifier) → najde User, jeho Employee.phone, pošle
   SMS s 6-místným kódem (v dev mode '111111').
2. verify_login_otp(identifier, code) → ověří hash, vrátí User.

Bezpečnost:
- Argon2id hash kódu (stejně jako signature OTP)
- TTL 5 minut, max 3 pokusy
- Anti-enumeration: request_login_otp NEPROZRAZUJE jestli identifier
  existuje. Vrací 204 vždy. Pokud neexistuje, OTP se prostě nepošle.
- Rate limit (slowapi) na endpoint úrovni — 5/hod per IP.
- Při dev mode (žádný real SMS provider) se kód neposílá — frontend
  musí uživatele upozornit, že má zadat 111111.
"""
from __future__ import annotations

import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from passlib.context import CryptContext
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.login_otp import LoginSmsOtpCode
from app.models.user import User
from app.services.sms import SmsMessage, get_sms_sender, is_dev_mode

log = logging.getLogger("login_otp")

OTP_LENGTH = 6
OTP_TTL_MINUTES = 5
OTP_MAX_ATTEMPTS = 3
DEV_OTP_CODE = "111111"

_otp_pwd = CryptContext(schemes=["argon2"], deprecated="auto")


def _generate_code() -> str:
    if is_dev_mode():
        return DEV_OTP_CODE
    return f"{secrets.randbelow(10 ** OTP_LENGTH):0{OTP_LENGTH}d}"


def _normalize_phone(raw: str) -> str:
    """Odstraní mezery a hyphens. '+420 728 319 744' → '+420728319744'."""
    return "".join(c for c in raw.strip() if c.isdigit() or c == "+")


async def _find_user_by_identifier(
    db: AsyncSession,
    identifier: str,
    *,
    tenant_id: uuid.UUID | None = None,
) -> User | None:
    """Najde User podle emailu, telefonu, personal_number nebo username.

    Priorita rozhodování:
    1. obsahuje '@' → email
    2. začíná '+' nebo je telefonní číslo → Employee.phone → user_id
    3. tenant_id daný a identifier není telefon → personal_number v tenantu
    4. fallback → username (platform admin)

    RLS bypass: hledáme napříč tenanty (login je pre-tenant).
    """
    await db.execute(
        text("SELECT set_config('app.is_superadmin', 'true', true)"),
    )

    if "@" in identifier:
        # Email
        query = select(User).where(
            User.email == identifier,
            User.is_active == True,  # noqa: E712
        )
        if tenant_id is not None:
            query = query.where(User.tenant_id == tenant_id)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    is_phone = identifier.startswith("+") or (
        identifier.replace(" ", "").isdigit() and len(identifier) >= 9
    )
    if is_phone:
        # Telefon — najdi přes Employee.phone, pak User
        phone = _normalize_phone(identifier)
        query = select(Employee).where(
            Employee.phone == phone,
            Employee.user_id.is_not(None),
        ).limit(1)
        if tenant_id is not None:
            query = query.where(Employee.tenant_id == tenant_id)
        emp = (await db.execute(query)).scalar_one_or_none()
        if emp is None or emp.user_id is None:
            return None
        return (await db.execute(
            select(User).where(
                User.id == emp.user_id,
                User.is_active == True,  # noqa: E712
            ),
        )).scalar_one_or_none()

    if tenant_id is not None:
        # Personal number v rámci tenantu
        emp = (await db.execute(
            select(Employee).where(
                Employee.tenant_id == tenant_id,
                Employee.personal_number == identifier,
                Employee.user_id.is_not(None),
            ).limit(1),
        )).scalar_one_or_none()
        if emp is not None and emp.user_id is not None:
            return (await db.execute(
                select(User).where(
                    User.id == emp.user_id,
                    User.is_active == True,  # noqa: E712
                ),
            )).scalar_one_or_none()

    # Username (platform admin)
    result = await db.execute(
        select(User).where(
            User.username == identifier,
            User.is_active == True,  # noqa: E712
        ),
    )
    return result.scalar_one_or_none()


async def _resolve_user_phone(
    db: AsyncSession, user: User,
) -> str | None:
    """Najde telefonní číslo pro uživatele.

    User sám phone nemá — bere se z Employee napojeného přes user_id.
    Vezme první nalezený (může být víc tenantů pro OZO multi-client).
    """
    result = await db.execute(
        select(Employee.phone).where(
            Employee.user_id == user.id,
            Employee.phone.is_not(None),
        ).limit(1),
    )
    phone = result.scalar_one_or_none()
    return phone if phone else None


async def request_login_otp(
    db: AsyncSession,
    identifier: str,
    *,
    tenant_id: uuid.UUID | None = None,
) -> bool:
    """Vygeneruje OTP pro daný identifier a pošle SMS.

    Vrací True pokud SMS byla odeslána, False pokud user neexistuje
    nebo nemá telefon. Caller by měl vždy odpovědět HTTP 204 ať tak,
    či tak (anti-enumeration).
    """
    user = await _find_user_by_identifier(db, identifier, tenant_id=tenant_id)
    if user is None:
        log.info("Login OTP: identifier=%s neexistuje", identifier[:30])
        return False

    phone = await _resolve_user_phone(db, user)
    if phone is None:
        log.warning(
            "Login OTP: user=%s nemá telefon (žádný Employee.phone)", user.id,
        )
        return False

    code = _generate_code()
    code_hash = _otp_pwd.hash(code)
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=OTP_TTL_MINUTES)

    otp_row = LoginSmsOtpCode(
        id=uuid.uuid4(),
        user_id=user.id,
        code_hash=code_hash,
        sent_to=phone,
        attempts=0,
        verified_at=None,
        expires_at=expires,
        created_at=now,
    )
    db.add(otp_row)
    await db.flush()

    sender = get_sms_sender()
    body = (
        f"DigitalOZO: přihlašovací kód {code}. "
        f"Platnost {OTP_TTL_MINUTES} min."
    )
    await sender.send(SmsMessage(to=phone, body=body))

    log.info("Login OTP sent: user=%s expires=%s", user.id, expires)
    return True


async def verify_login_otp(
    db: AsyncSession,
    identifier: str,
    code: str,
    *,
    tenant_id: uuid.UUID | None = None,
) -> User | None:
    """Ověří OTP. Vrací User při úspěchu, None jinak.

    Důvody selhání jsou v logu — UI dostane jen 401.
    """
    user = await _find_user_by_identifier(db, identifier, tenant_id=tenant_id)
    if user is None:
        return None

    now = datetime.now(UTC)
    otp = (
        await db.execute(
            select(LoginSmsOtpCode)
            .where(
                LoginSmsOtpCode.user_id == user.id,
                LoginSmsOtpCode.verified_at.is_(None),
            )
            .order_by(LoginSmsOtpCode.created_at.desc())
            .limit(1),
        )
    ).scalar_one_or_none()

    if otp is None:
        log.info("Login OTP verify: user=%s — žádný pending OTP", user.id)
        return None
    if otp.expires_at < now:
        log.info("Login OTP verify: user=%s — vypršel", user.id)
        return None
    if otp.attempts >= OTP_MAX_ATTEMPTS:
        log.warning(
            "Login OTP verify: user=%s — překročen limit pokusů", user.id,
        )
        return None

    otp.attempts = otp.attempts + 1
    if not _otp_pwd.verify(code, otp.code_hash):
        await db.flush()
        log.info(
            "Login OTP verify: user=%s — nesprávný kód (attempt %d)",
            user.id, otp.attempts,
        )
        return None

    otp.verified_at = now
    await db.flush()
    return user
