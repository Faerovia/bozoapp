import uuid

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.csrf import generate_csrf_token, set_csrf_cookie
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.rate_limit import limiter
from app.core.security import (
    JWTError,
    create_access_token,
    decode_token,
)
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth import login_user, register_user
from app.services.password_reset import (
    request_reset as svc_request_reset,
)
from app.services.password_reset import (
    reset_password as svc_reset_password,
)
from app.services.refresh_tokens import issue_family, revoke_user_tokens, rotate

router = APIRouter()
settings = get_settings()

# Délky platnosti v sekundách (pro cookie max_age)
_ACCESS_MAX_AGE = settings.access_token_expire_minutes * 60
_REFRESH_MAX_AGE = settings.refresh_token_expire_days * 86400


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """Nastaví httpOnly cookies s JWT tokeny + non-httpOnly CSRF cookie."""
    is_prod = settings.is_production
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=_ACCESS_MAX_AGE,
        httponly=True,
        secure=is_prod,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=_REFRESH_MAX_AGE,
        httponly=True,
        secure=is_prod,
        samesite="lax",
        path="/api/v1/auth/refresh",
    )
    # CSRF double-submit cookie. Frontend si ji přečte z JS a pošle
    # v X-CSRF-Token hlavičce pro každý state-changing request.
    set_csrf_cookie(response, generate_csrf_token(), is_production=is_prod)


@router.post("/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/hour")
async def register(
    request: Request,  # noqa: ARG001  # required by slowapi
    data: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    user, access_token, _legacy_refresh = await register_user(db, data)
    # Vydej první token v nové family (rotation-aware)
    refresh_token = await issue_family(db, user.id, user.tenant_id)
    _set_auth_cookies(response, access_token, refresh_token)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/auth/login", response_model=TokenResponse)
@limiter.limit("20/minute")
async def login(
    request: Request,  # noqa: ARG001  # required by slowapi
    data: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    result = await login_user(db, data.email, data.password)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nesprávný email nebo heslo",
        )
    user, access_token, _legacy_refresh = result
    refresh_token = await issue_family(db, user.id, user.tenant_id)
    _set_auth_cookies(response, access_token, refresh_token)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/auth/refresh", response_model=TokenResponse)
@limiter.limit("60/minute")
async def refresh(
    request: Request,  # noqa: ARG001  # required by slowapi
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Obnoví access token pomocí refresh tokenu z httpOnly cookie.
    Cookie je omezena na path=/api/v1/auth/refresh – browser ji posílá jen sem.
    """
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Neplatný nebo expirovaný refresh token",
    )
    if refresh_token is None:
        raise exc
    try:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise exc
        user_id = uuid.UUID(payload["sub"])
        tenant_id = uuid.UUID(payload["tenant_id"])
        # jti + family_id jsou povinné u rotation-aware tokenů.
        # Staré tokeny bez nich jsou z před migrace 013 → považuj za neplatné.
        jti = uuid.UUID(payload["jti"])
        family_id = uuid.UUID(payload["family_id"])
    except (JWTError, KeyError, ValueError):
        raise exc

    # Nastav RLS kontext aby SELECT User / RefreshToken prošel přes FORCE RLS
    await db.execute(
        text("SELECT set_config('app.current_tenant_id', :tid, true)"),
        {"tid": str(tenant_id)},
    )

    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.tenant_id == tenant_id,
            User.is_active == True,  # noqa: E712
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise exc

    new_refresh = await rotate(
        db,
        user_id=user_id,
        tenant_id=tenant_id,
        jti=jti,
        family_id=family_id,
    )
    if new_refresh is None:
        # Reuse / expired / revoked — klient musí re-loginovat
        raise exc

    new_access = create_access_token(user.id, tenant_id, user.role)
    _set_auth_cookies(response, new_access, new_refresh)
    return TokenResponse(access_token=new_access, refresh_token=new_refresh)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Smaže auth cookies + revoke všechny aktivní refresh tokeny usera.

    Pro správné smazání musí delete_cookie mít stejné atributy (secure,
    samesite, path) jako originální set_cookie; jinak některé browsery
    cookie nezruší.
    """
    await revoke_user_tokens(db, current_user.id)

    is_prod = settings.is_production
    response.delete_cookie(
        "access_token",
        path="/",
        httponly=True,
        secure=is_prod,
        samesite="lax",
    )
    response.delete_cookie(
        "refresh_token",
        path="/api/v1/auth/refresh",
        httponly=True,
        secure=is_prod,
        samesite="lax",
    )
    response.delete_cookie(
        "csrf_token",
        path="/",
        httponly=False,
        secure=is_prod,
        samesite="lax",
    )


@router.get("/auth/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


# ── Password reset ────────────────────────────────────────────────────────────

@router.post("/auth/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("5/hour")
async def forgot_password(
    request: Request,
    data: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Iniciuje password reset. VŽDY vrací 204 (bez ohledu na existenci emailu)
    aby nešlo enumerovat uživatele.
    """
    ip = request.client.host if request.client else None
    await svc_request_reset(db, data.email, request_ip=ip)


@router.post("/auth/reset-password", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/hour")
async def reset_password(
    request: Request,  # noqa: ARG001  # required by slowapi
    data: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> None:
    ok = await svc_reset_password(db, data.token, data.new_password)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Neplatný nebo expirovaný token",
        )
