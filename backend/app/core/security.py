import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


# PyJWT exception alias pro jednotné použití napříč codebasem.
# Původně bylo `jose.JWTError` — po migraci na PyJWT zachytíme
# PyJWTError (base exception pro všechny JWT chyby včetně expirace).
JWTError = jwt.PyJWTError


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: uuid.UUID, tenant_id: uuid.UUID, role: str) -> str:
    expire = datetime.now(UTC) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": role,
        "type": "access",
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_refresh_token(
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    *,
    jti: str | None = None,
    family_id: str | None = None,
) -> str:
    """
    jti a family_id jsou volitelné — použijí se při aktivovaném rotation flow
    (Commit 4). Bez nich zůstává chování zpětně kompatibilní.
    """
    expire = datetime.now(UTC) + timedelta(
        days=settings.refresh_token_expire_days
    )
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "type": "refresh",
        "exp": expire,
    }
    if jti is not None:
        payload["jti"] = jti
    if family_id is not None:
        payload["family_id"] = family_id
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> dict[str, Any]:
    """Raises jwt.PyJWTError (alias JWTError) pokud je token invalid nebo expired."""
    decoded: dict[str, Any] = jwt.decode(
        token, settings.secret_key, algorithms=[settings.algorithm]
    )
    return decoded
