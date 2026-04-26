"""
Password reset service.

Flow:
1. `request_reset(email)` — vytvoří token (pokud user existuje), pošle email.
   Vrací VŽDY success aby útočník nerozlišil existující/neexistující email.
2. `reset_password(token, new_password)` — validuje token, změní heslo,
   označí token used, revoke všechny refresh tokeny usera.

Bezpečnost:
- Token má dvě části: cleartext (v emailu) a hash (v DB).
- TOKEN_TTL_HOURS = 1
- Při úspěšném resetu: revoke_user_tokens → force re-login na všech zařízeních
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.email import EmailMessage, get_email_sender
from app.core.security import hash_password
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User
from app.services.refresh_tokens import revoke_user_tokens

TOKEN_TTL_HOURS = 1


def _hash_token(cleartext: str) -> str:
    """SHA-256 hex. Dostatečné pro lookup; cleartext má plnou entropii z secrets."""
    return hashlib.sha256(cleartext.encode("utf-8")).hexdigest()


async def request_reset(
    db: AsyncSession,
    email: str,
    *,
    request_ip: str | None = None,
    reset_url_template: str = "/reset-password?token={token}",
) -> None:
    """
    Vytvoří reset token pokud email odpovídá aktivnímu uživateli. Vždy return
    None — volající endpoint vrací vždy 204 (enumeration resistance).
    """
    # Cross-tenant lookup — bypass RLS (email je unique jen v rámci tenanta,
    # ale v praxi bude user jen v jednom tenantu)
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))

    user = (await db.execute(
        select(User).where(User.email == email, User.is_active == True)  # noqa: E712
    )).scalar_one_or_none()

    if user is None:
        return

    cleartext_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(cleartext_token)

    row = PasswordResetToken(
        tenant_id=user.tenant_id,
        user_id=user.id,
        token_hash=token_hash,
        expires_at=datetime.now(UTC) + timedelta(hours=TOKEN_TTL_HOURS),
        request_ip=request_ip,
    )
    db.add(row)
    await db.flush()

    reset_url = reset_url_template.format(token=cleartext_token)
    sender = get_email_sender()
    await sender.send(EmailMessage(
        to=user.email,
        subject="OZODigi – obnova hesla",
        body_text=(
            f"Pro obnovení hesla klikni na následující odkaz:\n\n{reset_url}\n\n"
            f"Odkaz vyprší za {TOKEN_TTL_HOURS} hodinu.\n"
            "Pokud jsi o obnovu nepožádal/a, ignoruj tento email."
        ),
    ))


async def reset_password(
    db: AsyncSession,
    cleartext_token: str,
    new_password: str,
) -> bool:
    """
    Vrací True pokud reset uspěl, False jinak (token invalid/expired/used).
    """
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))

    token_hash = _hash_token(cleartext_token)
    now = datetime.now(UTC)

    row = (await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        )
    )).scalar_one_or_none()

    if row is None:
        return False

    user = (await db.execute(
        select(User).where(User.id == row.user_id)
    )).scalar_one_or_none()

    if user is None or not user.is_active:
        return False

    user.hashed_password = hash_password(new_password)
    row.used_at = now

    # Revoke všechny aktivní refresh tokeny — force re-login na všech zařízeních
    await revoke_user_tokens(db, user.id)

    await db.flush()
    return True


async def cleanup_expired(db: AsyncSession) -> int:
    """Administrativa — smaže row. Volat z cronu / scheduled task."""
    from sqlalchemy import CursorResult, delete
    now = datetime.now(UTC)
    # Pro DML vrací AsyncSession.execute CursorResult, který má .rowcount.
    # Typový signature je Result[Any], proto explicit cast pro mypy strict.
    result = cast(
        CursorResult[Any],
        await db.execute(
            delete(PasswordResetToken).where(PasswordResetToken.expires_at < now)
        ),
    )
    await db.flush()
    return result.rowcount or 0


# Placeholder — pro budoucí use: pojmenovat parametr aby se nechoval jako unused
_ = uuid.UUID  # keep import for future use
