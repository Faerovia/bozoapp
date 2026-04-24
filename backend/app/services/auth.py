import re

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import (
    apply_login_delay,
    record_login_failure,
    record_login_success,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import RegisterRequest

# Pre-computed Argon2 hash libovolné hodnoty. Používáme ho v login flow,
# pokud uživatel neexistuje — `verify_password` musí stejně proběhnout
# (stejná CPU/time cost) aby útočník nedokázal rozlišit "neexistující email"
# od "existující email, špatné heslo" podle timing.
_DUMMY_PASSWORD_HASH = hash_password("dummy-password-not-used-for-login")


def _slugify(name: str) -> str:
    """Převede název firmy na URL-friendly slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug[:100]


async def register_user(
    db: AsyncSession, data: RegisterRequest
) -> tuple[User, str, str]:
    """
    Vytvoří tenant + prvního uživatele (role=ozo).
    Vrátí (user, access_token, refresh_token).

    RLS bypass: při registraci ještě nemáme tenant_id, takže
    dočasně nastavíme superadmin flag aby INSERT prošel přes RLS.
    """
    await db.execute(
        text("SELECT set_config('app.is_superadmin', 'true', true)")
    )

    tenant = Tenant(name=data.tenant_name, slug=_slugify(data.tenant_name))
    db.add(tenant)
    await db.flush()  # Získáme tenant.id bez commitu

    user = User(
        tenant_id=tenant.id,
        email=data.email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        role="ozo",  # První uživatel v tenantu je vždy OZO
    )
    db.add(user)
    await db.flush()

    access_token = create_access_token(user.id, tenant.id, user.role)
    refresh_token = create_refresh_token(user.id, tenant.id)

    return user, access_token, refresh_token


async def login_user(
    db: AsyncSession,
    email: str,
    password: str,
    *,
    totp_code: str | None = None,
) -> tuple[User, str, str] | None:
    """
    Ověří přihlašovací údaje.
    Vrátí (user, access_token, refresh_token) nebo None.

    Ochrany:
    - **Progressive delay**: před ověřením spi úměrně počtu fail pokusů
      pro daný email (Redis counter). Nad prahem → 429.
    - **Timing attack resistance**: při neexistujícím emailu voláme
      verify_password proti dummy hashi, aby celkový čas byl stejný jako
      pro existujícího uživatele se špatným heslem.

    RLS bypass: hledáme uživatele podle emailu napříč tenanty,
    tenant_id ještě neznáme.
    """
    # 1) Progressive delay podle fail countu. Volá se PŘED jakýmkoli DB/crypto
    #    dotazem, aby attacker platil čas i kdyby o email nic nevěděl.
    can_proceed = await apply_login_delay(email)
    if not can_proceed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Účet je dočasně zablokován pro příliš mnoho neúspěšných pokusů.",
        )

    await db.execute(
        text("SELECT set_config('app.is_superadmin', 'true', true)")
    )

    result = await db.execute(
        select(User).where(User.email == email, User.is_active == True)  # noqa: E712
    )
    user = result.scalar_one_or_none()

    # 2) Timing attack ochrana: pokud user neexistuje, ověřujeme dummy hash,
    #    abychom spotřebovali stejný Argon2 time jako legit login.
    if user is None:
        verify_password(password, _DUMMY_PASSWORD_HASH)
        await record_login_failure(email)
        return None

    if not verify_password(password, user.hashed_password):
        await record_login_failure(email)
        return None

    # 2FA gate — pokud je zapnuté, musí přijít platný TOTP nebo recovery code
    if user.totp_enabled:
        from app.services import totp as totp_svc
        if totp_code is None:
            # Signál: heslo OK, ale chybí kód. Endpoint rozliší přes
            # HTTPException s detail="TOTP_REQUIRED".
            raise _TotpRequired()
        if not await totp_svc.verify(db, user, totp_code):
            await record_login_failure(email)
            return None

    await record_login_success(email)

    access_token = create_access_token(user.id, user.tenant_id, user.role)
    refresh_token = create_refresh_token(user.id, user.tenant_id)

    return user, access_token, refresh_token


class _TotpRequired(Exception):
    """Interní signál: password OK, ale potřebujeme TOTP kód."""
    pass
