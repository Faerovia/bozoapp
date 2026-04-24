"""
2FA (TOTP) endpointy.

- POST /auth/2fa/setup — začne setup; vrátí secret + otpauth URI + base64 QR image
- POST /auth/2fa/confirm — potvrdí první kód, zapne 2FA, vrátí recovery codes
- POST /auth/2fa/disable — vypne (vyžaduje current password)
- POST /auth/2fa/recovery-codes — regenerate recovery codes (vyžaduje current password)
- GET  /auth/2fa/status — is_enabled + count remaining recovery codes
- POST /auth/2fa/admin-disable/{user_id} — OZO disable pro jiného usera

Login flow (implementovaný v auth.py) přijme `totp_code` pokud je 2FA enabled.
"""
import base64
import io
import uuid

import pyotp
import qrcode
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.permissions import require_role
from app.core.rate_limit import limiter
from app.core.security import verify_password
from app.models.user import User
from app.services import totp as totp_svc
from app.services.users import get_user_by_id

router = APIRouter()


# ── Schémata ─────────────────────────────────────────────────────────────────

class TotpSetupResponse(BaseModel):
    secret: str = Field(..., description="Base32 secret pro manuální setup")
    otpauth_uri: str = Field(..., description="otpauth:// URI pro QR")
    qr_png_base64: str = Field(..., description="Base64 PNG obrázek QR kódu")


class TotpConfirmRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=8)


class TotpConfirmResponse(BaseModel):
    recovery_codes: list[str] = Field(
        ...,
        description=(
            "Jednorázové recovery codes. Zobrazte uživateli a uložte bezpečně — "
            "zobrazí se jen teď."
        ),
    )


class TotpPasswordConfirm(BaseModel):
    password: str


class TotpStatusResponse(BaseModel):
    enabled: bool
    recovery_codes_remaining: int


# ── Helpers ──────────────────────────────────────────────────────────────────

def _qr_to_base64_png(data: str) -> str:
    img = qrcode.make(data)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


# ── Endpointy ────────────────────────────────────────────────────────────────

@router.post("/auth/2fa/setup", response_model=TotpSetupResponse)
@limiter.limit("10/hour")
async def totp_setup(
    request: Request,  # noqa: ARG001  # required by slowapi
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TotpSetupResponse:
    """Vygeneruje TOTP secret a vrátí ho spolu s QR kódem. 2FA se zapne až po confirm."""
    secret, uri = await totp_svc.begin_setup(db, current_user)
    return TotpSetupResponse(
        secret=secret,
        otpauth_uri=uri,
        qr_png_base64=_qr_to_base64_png(uri),
    )


@router.post("/auth/2fa/confirm", response_model=TotpConfirmResponse)
@limiter.limit("10/minute")
async def totp_confirm(
    request: Request,  # noqa: ARG001
    data: TotpConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TotpConfirmResponse:
    codes = await totp_svc.confirm_setup(db, current_user, data.code)
    if codes is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kód nesouhlasí. Zkus to znovu.",
        )
    return TotpConfirmResponse(recovery_codes=codes)


@router.post("/auth/2fa/disable", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("5/minute")
async def totp_disable(
    request: Request,  # noqa: ARG001
    data: TotpPasswordConfirm,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Vypnutí vyžaduje aktuální heslo — chrání před ukradením session."""
    if not verify_password(data.password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Heslo nesouhlasí",
        )
    await totp_svc.disable(db, current_user)


@router.post("/auth/2fa/recovery-codes", response_model=TotpConfirmResponse)
@limiter.limit("3/hour")
async def totp_regenerate(
    request: Request,  # noqa: ARG001
    data: TotpPasswordConfirm,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TotpConfirmResponse:
    """Nové recovery codes. Staré se zneplatní. Vyžaduje aktuální heslo."""
    if not verify_password(data.password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Heslo nesouhlasí",
        )
    if not current_user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA není zapnuté",
        )
    codes = await totp_svc.regenerate_recovery_codes(db, current_user)
    return TotpConfirmResponse(recovery_codes=codes)


@router.get("/auth/2fa/status", response_model=TotpStatusResponse)
async def totp_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TotpStatusResponse:
    remaining = await totp_svc.count_unused_recovery_codes(db, current_user)
    return TotpStatusResponse(
        enabled=current_user.totp_enabled,
        recovery_codes_remaining=remaining,
    )


@router.post(
    "/auth/2fa/admin-disable/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def totp_admin_disable(
    user_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """OZO může vypnout 2FA jinému uživateli v tenantu (ztráta telefonu)."""
    target = await get_user_by_id(db, user_id, current_user.tenant_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Uživatel nenalezen")
    if target.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pro vlastní účet použij /auth/2fa/disable",
        )
    await totp_svc.admin_disable_for_user(db, target.id)


# Re-export pro register v main.py
__all__ = ["router"]

# Nepoužito, jen pro pyotp import validaci v mypy
_ = pyotp.TOTP
