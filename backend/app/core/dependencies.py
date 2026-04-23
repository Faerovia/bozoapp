import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User

bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Validates Bearer token, sets RLS tenant context, returns the current user.

    Dvě věci najednou záměrně:
    1. Ověření JWT → kdo jsi
    2. SET LOCAL app.current_tenant_id → PostgreSQL RLS izolace tenantu

    Všechny endpointy které závisí na tomto dependency automaticky
    získají tenant-izolovanou DB session.
    """
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise exc
        user_id = uuid.UUID(payload["sub"])
        tenant_id = uuid.UUID(payload["tenant_id"])
    except (JWTError, KeyError, ValueError):
        raise exc

    # Nastav RLS kontext pro tuto transakci.
    # Pozor: SET LOCAL nepodporuje parameterized queries ($1),
    # proto používáme string interpolaci. UUID z JWT je bezpečný vstup.
    await db.execute(text(f"SET LOCAL app.current_tenant_id = '{tenant_id}'"))

    result = await db.execute(
        select(User).where(User.id == user_id, User.is_active == True)  # noqa: E712
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise exc

    return user
