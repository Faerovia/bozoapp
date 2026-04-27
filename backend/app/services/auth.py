import re
import uuid

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
from app.models.employee import Employee
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import RegisterRequest


async def _find_user_by_identifier(
    db: AsyncSession,
    identifier: str,
    *,
    tenant_id: uuid.UUID | None = None,
) -> User | None:
    """Najde User podle identifieru (email/personal_number/username).

    Důležité (subdomain login):
    - **Email**: hledá se GLOBÁLNĚ, ne per-tenant. Důvod: OZO multi-client
      má User.tenant_id na primárním tenantu, ale potřebuje se přihlásit
      i na subdoménách jiných tenantů, kde má jen membership. Per-tenant
      lookup by ho zde nenašel. Kontrola, že uživatel má v subdoméně
      membership, se dělá až v login endpointu (po nalezení usera).
    - **Personal_number**: per-tenant (vyžaduje tenant_id). Bez tenantu
      nelze rozlišit různé lidi se stejným osobním číslem.
    - **Username**: globálně unikát (platform admin).
    """
    is_email = "@" in identifier

    if is_email:
        result = await db.execute(
            select(User).where(
                User.email == identifier,
                User.is_active == True,  # noqa: E712
            ),
        )
        return result.scalar_one_or_none()

    if tenant_id is not None:
        # Personal number v rámci tenantu — Employee.personal_number → user_id
        emp_result = await db.execute(
            select(Employee).where(
                Employee.tenant_id == tenant_id,
                Employee.personal_number == identifier,
                Employee.user_id.is_not(None),
            ).limit(1),
        )
        emp = emp_result.scalar_one_or_none()
        if emp is not None and emp.user_id is not None:
            return (await db.execute(
                select(User).where(
                    User.id == emp.user_id,
                    User.is_active == True,  # noqa: E712
                ),
            )).scalar_one_or_none()

    # Fallback: username (platform admin, globálně unikát)
    result = await db.execute(
        select(User).where(
            User.username == identifier,
            User.is_active == True,  # noqa: E712
        ),
    )
    return result.scalar_one_or_none()

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

    # Vytvoř i M:N membership (default), aby fungoval client switcher.
    from app.models.membership import UserTenantMembership
    db.add(UserTenantMembership(
        user_id=user.id,
        tenant_id=tenant.id,
        role="ozo",
        is_default=True,
    ))
    await db.flush()

    access_token = create_access_token(user.id, tenant.id, user.role)
    refresh_token = create_refresh_token(user.id, tenant.id)

    return user, access_token, refresh_token


async def login_user(
    db: AsyncSession,
    identifier: str,
    password: str,
    *,
    tenant_id: uuid.UUID | None = None,
    totp_code: str | None = None,
) -> tuple[User, str, str] | None:
    """
    Ověří přihlašovací údaje. `identifier` může být:

    1. Email (obsahuje '@') — najde User.email. Pokud `tenant_id` je dán,
       hledá per-tenant; jinak globálně.
    2. Personal_number — vyžaduje `tenant_id`. Najde Employee přes
       (tenant_id, personal_number) → user_id → User.
    3. Username — globálně unikátní (platform admin).

    Vrátí (user, access_token, refresh_token) nebo None.

    Ochrany:
    - **Progressive delay**: před ověřením spi úměrně počtu fail pokusů.
    - **Timing attack resistance**: dummy hash check pro neexistující user.

    RLS bypass: hledáme uživatele napříč tenanty (tenant_id ještě neznáme).
    """
    # 1) Progressive delay podle fail countu. Volá se PŘED jakýmkoli DB/crypto
    #    dotazem, aby attacker platil čas i kdyby o identifier nic nevěděl.
    can_proceed = await apply_login_delay(identifier)
    if not can_proceed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Účet je dočasně zablokován pro příliš mnoho neúspěšných pokusů.",
        )

    await db.execute(
        text("SELECT set_config('app.is_superadmin', 'true', true)")
    )

    user = await _find_user_by_identifier(db, identifier, tenant_id=tenant_id)

    # 2) Timing attack ochrana: pokud user neexistuje, ověřujeme dummy hash,
    #    abychom spotřebovali stejný Argon2 time jako legit login.
    if user is None:
        verify_password(password, _DUMMY_PASSWORD_HASH)
        await record_login_failure(identifier)
        return None

    if not verify_password(password, user.hashed_password):
        await record_login_failure(identifier)
        return None

    # 2FA gate — pokud je zapnuté, musí přijít platný TOTP nebo recovery code
    if user.totp_enabled:
        from app.services import totp as totp_svc
        if totp_code is None:
            # Signál: heslo OK, ale chybí kód. Endpoint rozliší přes
            # HTTPException s detail="TOTP_REQUIRED".
            raise _TotpRequiredError()
        if not await totp_svc.verify(db, user, totp_code):
            await record_login_failure(identifier)
            return None

    await record_login_success(identifier)

    access_token = create_access_token(user.id, user.tenant_id, user.role)
    refresh_token = create_refresh_token(user.id, user.tenant_id)

    return user, access_token, refresh_token


class _TotpRequiredError(Exception):
    """Interní signál: password OK, ale potřebujeme TOTP kód."""
    pass
