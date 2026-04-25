import uuid

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import JWTError, decode_token
from app.models.user import User

# HTTPBearer s auto_error=False → nevyhodí 403 pokud header chybí,
# umožní nám zkusit cookie jako fallback.
bearer_scheme = HTTPBearer(auto_error=False)


def _extract_token(
    credentials: HTTPAuthorizationCredentials | None,
    access_token_cookie: str | None,
) -> str:
    """
    Vrátí JWT token z dostupného zdroje:
    1. Authorization: Bearer header – explicitní, prioritní (API klienti, testy)
    2. httpOnly cookie access_token – implicitní (browser, neposílá Bearer)

    Bearer má prioritu: browser nikdy neposílá custom Authorization header
    bez explicitní instrukce → neexistuje konflikt v produkci. V testech
    httpx AsyncClient ukládá cookies, takže Bearer priority zabraňuje
    cross-contamination mezi requesty různých uživatelů.
    """
    if credentials and credentials.credentials:
        return credentials.credentials
    if access_token_cookie:
        return access_token_cookie
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    access_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Validates JWT (cookie nebo Bearer), sets RLS tenant context, returns current user.

    Dvě věci najednou záměrně:
    1. Ověření JWT → kdo jsi
    2. SET LOCAL app.current_tenant_id → PostgreSQL RLS izolace tenantu
    """
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = _extract_token(credentials, access_token)

    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise exc
        user_id = uuid.UUID(payload["sub"])
        tenant_id = uuid.UUID(payload["tenant_id"])
    except (JWTError, KeyError, ValueError):
        raise exc

    # User lookup obejde RLS — JWT je už ověřený. Po multi-tenant refaktoru
    # user.tenant_id (primární) může být jiný než aktuální tenant z JWT
    # (OZO přepnul na klienta), a RLS by lookup zablokovala.
    await db.execute(
        text("SELECT set_config('app.is_superadmin', 'true', true)")
    )
    result = await db.execute(
        select(User).where(User.id == user_id, User.is_active == True)  # noqa: E712
    )
    user = result.scalar_one_or_none()
    # Po lookupu superadmin reset — dál už jedeme s normálním kontextem
    await db.execute(
        text("SELECT set_config('app.is_superadmin', 'false', true)")
    )

    if user is None:
        raise exc

    # Ověř, že user má membership na tenant_id z JWT (revoke ochrana).
    # Platform admin tuto kontrolu obchází (může být všude).
    if not user.is_platform_admin:
        from app.models.membership import UserTenantMembership
        m_res = await db.execute(
            select(UserTenantMembership).where(
                UserTenantMembership.user_id == user_id,
                UserTenantMembership.tenant_id == tenant_id,
            )
        )
        if m_res.scalar_one_or_none() is None:
            raise exc

    # Nastav RLS kontext pro tuto transakci. Pokud platform admin, nasadíme
    # ještě bypass (níže) — pro normálního usera jen current_tenant_id.
    await db.execute(
        text("SELECT set_config('app.current_tenant_id', :tid, true)"),
        {"tid": str(tenant_id)},
    )

    # Platform admin → aktivuj cross-tenant bypass pro zbytek requestu.
    # RLS policy `platform_admin_bypass` na všech tabulkách (viz migrace 019)
    # propustí SELECT/INSERT/UPDATE/DELETE napříč tenanty.
    if user.is_platform_admin:
        await db.execute(
            text("SELECT set_config('app.is_platform_admin', 'true', true)")
        )

    # OZO multi-client: response /auth/me musí ukazovat AKTIVNÍ tenant
    # (z JWT), ne primární z DB. Frontend ClientSwitcher to potřebuje.
    # Mutace nemá efekt na DB (commit nevolán).
    user.tenant_id = tenant_id
    return user
