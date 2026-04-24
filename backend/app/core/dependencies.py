import uuid

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_token
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

    # Nastav RLS kontext pro tuto transakci.
    # UUID z JWT je bezpečný vstup (validován výše).
    await db.execute(text(f"SET LOCAL app.current_tenant_id = '{tenant_id}'"))

    result = await db.execute(
        select(User).where(User.id == user_id, User.is_active == True)  # noqa: E712
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise exc

    return user
