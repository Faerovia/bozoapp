import uuid
from typing import Any

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
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MembershipResponse,
    RegisterRequest,
    ResetPasswordRequest,
    SelectTenantRequest,
    SmsLoginRequest,
    SmsLoginVerifyRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth import _TotpRequiredError, login_user, register_user
from app.services.login_otp import (
    request_login_otp as svc_login_otp_request,
)
from app.services.login_otp import (
    verify_login_otp as svc_login_otp_verify,
)
from app.services.memberships import (
    get_user_memberships,
    has_membership,
)
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
    """Nastaví httpOnly cookies s JWT tokeny + non-httpOnly CSRF cookie.

    Cookie scope: pokud settings.cookie_domain je nastavený (např.
    '.digitalozo.cz' v prod), cookie platí pro všechny subdomény →
    OZO multi-client switcher může jen redirect bez re-login.
    """
    is_prod = settings.is_production
    domain = settings.cookie_domain or None
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=_ACCESS_MAX_AGE,
        httponly=True,
        secure=is_prod,
        samesite="lax",
        path="/",
        domain=domain,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=_REFRESH_MAX_AGE,
        httponly=True,
        secure=is_prod,
        samesite="lax",
        path="/api/v1/auth/refresh",
        domain=domain,
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
    # Self-signup je v produkci typicky zakázán — tenanty vytváří platform admin
    # přes POST /admin/tenants. Nastav ALLOW_SELF_SIGNUP=false v prod .env.
    if not settings.allow_self_signup:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Self-signup je zakázán. Kontaktujte správce pro vytvoření účtu.",
        )
    user, access_token, _legacy_refresh = await register_user(db, data)
    # Vydej první token v nové family (rotation-aware)
    refresh_token = await issue_family(db, user.id, user.tenant_id)
    _set_auth_cookies(response, access_token, refresh_token)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/auth/login", response_model=TokenResponse)
@limiter.limit("20/minute")
async def login(
    request: Request,
    data: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    # Sjednocení identifieru: nový API přijímá `identifier`, legacy klienti
    # posílají `email` nebo `username` — oba sjednoceně do `identifier`.
    identifier = data.identifier or data.email or data.username
    if not identifier:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Pošlete identifier (email, osobní číslo nebo přihlašovací jméno)",
        )

    # Tenant kontext: priorita 1) explicit pole tenant_slug v body,
    # 2) subdomain (request.state.tenant_from_subdomain).
    tenant_id = None
    if data.tenant_slug:
        from app.core.tenant_subdomain import _resolve_slug
        resolved = await _resolve_slug(data.tenant_slug)
        if resolved:
            tenant_id = resolved[0]
    if tenant_id is None:
        tenant_id = getattr(request.state, "tenant_from_subdomain", None)

    try:
        result = await login_user(
            db, identifier, data.password,
            tenant_id=tenant_id,
            totp_code=data.totp_code,
        )
    except _TotpRequiredError:
        # Password OK, 2FA zapnuté, ale kód nepřišel. Klient pošle znovu s totp_code.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="TOTP_REQUIRED",
        ) from None

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nesprávné přihlašovací údaje",
        )
    user, _legacy_access, _legacy_refresh = result

    # Subdomain scope: pokud je login na tenant subdoméně (jiné než user.tenant_id),
    # zvalidujeme že user má v té tenantě membership a vystavíme JWT s tím
    # tenant_id (a rolí z membership). Bez tohoto by OZO multi-client nemohl
    # přihlásit na sekundární tenant subdoménu.
    effective_tenant_id = user.tenant_id
    effective_role = user.role
    if tenant_id is not None and tenant_id != user.tenant_id:
        # Platform admin se může přihlásit kamkoli (s jeho role 'admin')
        if not user.is_platform_admin:
            membership = await has_membership(db, user.id, tenant_id)
            if membership is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Nemáš přístup k tomuto klientovi",
                )
            effective_tenant_id = tenant_id
            effective_role = membership.role
        else:
            effective_tenant_id = tenant_id

    access_token = create_access_token(user.id, effective_tenant_id, effective_role)
    refresh_token = await issue_family(db, user.id, effective_tenant_id)
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
    domain = settings.cookie_domain or None
    response.delete_cookie(
        "access_token",
        path="/",
        httponly=True,
        secure=is_prod,
        samesite="lax",
        domain=domain,
    )
    response.delete_cookie(
        "refresh_token",
        path="/api/v1/auth/refresh",
        httponly=True,
        secure=is_prod,
        samesite="lax",
        domain=domain,
    )
    response.delete_cookie(
        "csrf_token",
        path="/",
        httponly=False,
        secure=is_prod,
        samesite="lax",
        domain=domain,
    )


@router.get("/auth/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.get("/auth/me/employee")
async def me_employee(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Vrátí Employee record napojený na current_user (přes user_id).

    Slouží pro signature flows — UI potřebuje employee_id pro
    /signatures/initiate. Pokud user nemá employee record (typicky
    platform admin nebo HR uživatel bez personálního záznamu), vrátí
    employee_id=None.
    """
    from app.services.employees import get_employee_by_user_id
    emp = await get_employee_by_user_id(db, current_user.id, current_user.tenant_id)
    if emp is None:
        return {
            "employee_id": None,
            "full_name": current_user.full_name or current_user.email,
            "has_login_account": True,
            "has_phone": False,
        }
    return {
        "employee_id": str(emp.id),
        "full_name": emp.full_name,
        "has_login_account": emp.user_id is not None,
        "has_phone": bool(emp.phone),
    }


# ── Multi-tenant membership endpoints ───────────────────────────────────────


@router.get("/auth/memberships", response_model=list[MembershipResponse])
async def list_memberships(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MembershipResponse]:
    """Vrátí list klientů (tenantů), kam má current user přístup."""
    rows = await get_user_memberships(db, current_user.id)
    return [MembershipResponse.model_validate(r) for r in rows]


@router.post("/auth/select-tenant", response_model=TokenResponse)
async def select_tenant(
    data: SelectTenantRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Přepne aktivní tenant. Vystaví nový access token s vybraným tenant_id
    a rolí z membership. Cookie `access_token` se přepíše (httpOnly,
    JS ji nemůže měnit). Refresh token zůstává platný s původním tenant_id.
    """
    membership = await has_membership(db, current_user.id, data.tenant_id)
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nemáš přístup k tomuto klientovi",
        )

    new_access = create_access_token(
        current_user.id, data.tenant_id, membership.role
    )

    # Přepiš HTTP-only cookie aby browser používal nový token
    is_prod = settings.is_production
    response.set_cookie(
        key="access_token",
        value=new_access,
        max_age=_ACCESS_MAX_AGE,
        httponly=True,
        secure=is_prod,
        samesite="lax",
        path="/",
    )

    return TokenResponse(
        access_token=new_access,
        # Refresh netvoříme — používá se stávající.
        refresh_token="",
        token_type="bearer",
    )


# ── Password reset ────────────────────────────────────────────────────────────

# ── Public tenant info pro branded login UI ─────────────────────────────────

@router.get("/auth/tenant-info")
async def auth_tenant_info(request: Request) -> dict[str, str | None]:
    """Vrátí název tenantu z aktuální subdomény (pro login page branding).

    Response:
        {"slug": "strojirny-abc-s-r-o", "name": "Strojírny ABC s.r.o.",
         "is_admin": false}

    Pokud subdomain neodpovídá tenantu (root, neznámý slug), vrátí None
    pole — frontend pak ukáže generic login.
    """
    return {
        "slug": getattr(request.state, "tenant_slug", None),
        "name": getattr(request.state, "tenant_name", None),
        "is_admin": str(getattr(request.state, "is_admin_subdomain", False)).lower(),
    }


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


# ── SMS OTP login (passwordless) ─────────────────────────────────────────────

async def _resolve_tenant_for_login(
    request: Request, body_slug: str | None,
) -> uuid.UUID | None:
    """Vyřeší tenant_id pro login (priorita: body slug > subdomain)."""
    if body_slug:
        from app.core.tenant_subdomain import _resolve_slug
        resolved = await _resolve_slug(body_slug)
        if resolved:
            return resolved[0]
    return getattr(request.state, "tenant_from_subdomain", None)


@router.post("/auth/sms/request", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("5/hour")
async def sms_login_request(
    request: Request,  # noqa: ARG001  # required by slowapi
    data: SmsLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Pošle 6-místný OTP kód SMS na telefon zaměstnance napojeného
    na uživatele s daným identifierem (email/username/personal_number/telefon).

    Anti-enumeration: vrací 204 vždy (i když identifier neexistuje).
    """
    tenant_id = await _resolve_tenant_for_login(request, data.tenant_slug)
    await svc_login_otp_request(db, data.identifier, tenant_id=tenant_id)


@router.post("/auth/sms/verify", response_model=TokenResponse)
@limiter.limit("20/minute")
async def sms_login_verify(
    request: Request,
    data: SmsLoginVerifyRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Ověří OTP kód a vystaví JWT (access + refresh) cookies."""
    tenant_id = await _resolve_tenant_for_login(request, data.tenant_slug)
    user = await svc_login_otp_verify(
        db, data.identifier, data.code, tenant_id=tenant_id,
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nesprávný nebo expirovaný kód",
        )
    access_token = create_access_token(user.id, user.tenant_id, user.role)
    refresh_token = await issue_family(db, user.id, user.tenant_id)
    _set_auth_cookies(response, access_token, refresh_token)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


# ── Self-service změna hesla ─────────────────────────────────────────────────

@router.post("/auth/change-password", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/hour")
async def change_password(
    request: Request,  # noqa: ARG001  # required by slowapi
    data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Změna vlastního hesla. Vyžaduje současné heslo pro ověření.

    Po změně revokuje všechny refresh tokeny mimo aktuální session
    (current session zůstává, jiná zařízení musí re-login).
    """
    from app.core.security import hash_password, verify_password

    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Současné heslo je nesprávné",
        )
    if data.current_password == data.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nové heslo se musí lišit od současného",
        )

    current_user.hashed_password = hash_password(data.new_password)
    await db.flush()
    # Force re-login na ostatních zařízeních.
    await revoke_user_tokens(db, current_user.id)
