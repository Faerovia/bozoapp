"""
Refresh token lifecycle — issue, rotate, revoke family.

Flow:
1. **issue_family()** — login/register: vygeneruje nový family_id,
   vydá první refresh token s tímto family_id. Vrátí (jti, family_id, token_str).
2. **rotate()** — /refresh: přijme starý token, označí ho `used_at`,
   vystaví nový s SAMÝM family_id. Nový dostane nový jti.
3. **detect_reuse_and_revoke()** — pokud starý token má `used_at IS NOT NULL`
   nebo `revoked_at IS NOT NULL`, znamená to reuse. Revoke celou family.

V celém flow se token string (JWT) generuje `create_refresh_token(jti, family_id)`
aby klient nemusel znát strukturu; DB track je interní.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import create_refresh_token
from app.models.refresh_token import RefreshToken

settings = get_settings()


def _expires_at() -> datetime:
    return datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)


async def issue_family(
    db: AsyncSession,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> str:
    """Založí novou token family a vrátí JWT string prvního refresh tokenu."""
    jti = uuid.uuid4()
    family_id = uuid.uuid4()
    row = RefreshToken(
        jti=jti,
        tenant_id=tenant_id,
        user_id=user_id,
        family_id=family_id,
        expires_at=_expires_at(),
    )
    db.add(row)
    await db.flush()
    return create_refresh_token(user_id, tenant_id, jti=str(jti), family_id=str(family_id))


async def rotate(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    jti: uuid.UUID,
    family_id: uuid.UUID,
) -> str | None:
    """
    Vymění starý token za nový ve stejné family.

    Vrátí nový JWT string, nebo None pokud:
    - starý token neexistuje / již použit / revoked / expired → reuse detected,
      zneplatní celou family
    """
    # Načti starý token (query přes RLS projde, tenant_id je nastaven middlewarem)
    old = (await db.execute(
        select(RefreshToken).where(
            RefreshToken.jti == jti,
            RefreshToken.user_id == user_id,
            RefreshToken.tenant_id == tenant_id,
        )
    )).scalar_one_or_none()

    now = datetime.now(UTC)

    if old is None:
        # Token neznámý — pravděpodobně už smazaný / z jiné family po revoce.
        # Revoke celou family pro jistotu, pokud je family_id validní.
        await _revoke_family(db, family_id, reason="reuse_detected")
        return None

    # Kontroly životnosti
    if old.revoked_at is not None or old.used_at is not None:
        # Reuse detekovaný — revoke celou family
        await _revoke_family(db, old.family_id, reason="reuse_detected")
        return None

    if old.expires_at < now:
        # Expired — jen označ, ale nevyvolej family-wide revocation
        old.revoked_at = now
        old.revoked_reason = "expired"
        await db.flush()
        return None

    # OK, rotate
    old.used_at = now

    new_jti = uuid.uuid4()
    new_row = RefreshToken(
        jti=new_jti,
        tenant_id=tenant_id,
        user_id=user_id,
        family_id=old.family_id,
        expires_at=_expires_at(),
    )
    db.add(new_row)
    await db.flush()

    return create_refresh_token(
        user_id, tenant_id, jti=str(new_jti), family_id=str(old.family_id)
    )


async def _revoke_family(
    db: AsyncSession, family_id: uuid.UUID, *, reason: str
) -> None:
    now = datetime.now(UTC)
    await db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.family_id == family_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=now, revoked_reason=reason)
    )
    await db.flush()


async def revoke_user_tokens(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Pro logout-all / password-reset / deactivation: zruš všechny aktivní refresh tokeny usera."""
    now = datetime.now(UTC)
    await db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=now, revoked_reason="logout")
    )
    await db.flush()
