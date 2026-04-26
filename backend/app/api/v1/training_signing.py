"""
API pro digitální podpis školení.

- POST /trainings/assignments/{id}/sign         — uložit podpis (canvas)
- POST /trainings/assignments/{id}/request-otp  — pošle OTP pro ZES
- POST /trainings/assignments/{id}/verify-otp   — ověří OTP (vrátí otp_id)
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.employee import Employee
from app.models.training import TrainingAssignment
from app.models.user import User
from app.services.training_signing import (
    SigningError,
    request_otp,
    sign_assignment,
    verify_otp,
)

router = APIRouter()


# ── Request/response schemas ─────────────────────────────────────────────────


class SignRequest(BaseModel):
    signature_image_b64: str = Field(..., min_length=100)
    method: str = Field(default="simple", pattern="^(simple|qes)$")
    otp_id: uuid.UUID | None = None


class SignResponse(BaseModel):
    assignment_id: uuid.UUID
    signed_at: str
    method: str


class RequestOtpRequest(BaseModel):
    """Volitelně lze vynutit kanál; jinak server zvolí podle dostupnosti."""
    channel: str | None = Field(None, pattern="^(email|sms)$")


class RequestOtpResponse(BaseModel):
    otp_id: uuid.UUID
    sent_to: str
    channel: str
    expires_in_minutes: int = 10


class VerifyOtpRequest(BaseModel):
    otp_id: uuid.UUID
    code: str = Field(..., min_length=6, max_length=6)


class VerifyOtpResponse(BaseModel):
    otp_id: uuid.UUID
    verified: bool


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _load_assignment_for_user(
    db: AsyncSession,
    assignment_id: uuid.UUID,
    user: User,
) -> tuple[TrainingAssignment, Employee]:
    """
    Načte assignment + ověří, že buď:
      - assignment patří aktuálnímu user (přes Employee.user_id) — self-service
      - aktuální user je manager (OZO/HR) v tenantu — shared tablet flow
    Vrátí (assignment, employee).
    """
    assignment = (await db.execute(
        select(TrainingAssignment).where(TrainingAssignment.id == assignment_id)
    )).scalar_one_or_none()
    if assignment is None:
        raise HTTPException(status_code=404, detail="Přiřazení nenalezeno")

    employee = (await db.execute(
        select(Employee).where(Employee.id == assignment.employee_id)
    )).scalar_one_or_none()
    if employee is None:
        raise HTTPException(status_code=404, detail="Zaměstnanec nenalezen")

    # Self-service: zaměstnanec podepisuje vlastní školení
    if employee.user_id == user.id:
        return assignment, employee

    # Shared tablet: OZO/HR může spustit podpis pro kteréhokoli zaměstnance
    if user.role in ("ozo", "hr_manager"):
        return assignment, employee

    raise HTTPException(
        status_code=403,
        detail="Nemáš oprávnění podepsat toto školení",
    )


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.post(
    "/trainings/assignments/{assignment_id}/sign",
    response_model=SignResponse,
)
async def sign_training_assignment(
    assignment_id: uuid.UUID,
    data: SignRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Uloží podpis na assignment. Pro ZES školení vyžaduje verified otp_id."""
    assignment, _ = await _load_assignment_for_user(db, assignment_id, user)

    try:
        result = await sign_assignment(
            db,
            assignment=assignment,
            signature_image_b64=data.signature_image_b64,
            method=data.method,
            request_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            otp_id=data.otp_id,
        )
    except SigningError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    assert result.signed_at is not None  # pro mypy
    return SignResponse(
        assignment_id=result.id,
        signed_at=result.signed_at.isoformat(),
        method=result.signature_method or "simple",
    )


@router.post(
    "/trainings/assignments/{assignment_id}/request-otp",
    response_model=RequestOtpResponse,
)
async def request_signing_otp(
    assignment_id: uuid.UUID,
    data: RequestOtpRequest = RequestOtpRequest(),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Vygeneruje 6-místný OTP. Default: email (pokud má) → SMS (pokud má) →
    chyba. Klient může vynutit channel=email|sms.
    """
    assignment, employee = await _load_assignment_for_user(db, assignment_id, user)

    try:
        otp = await request_otp(
            db, assignment=assignment, employee=employee, channel=data.channel,
        )
    except SigningError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return RequestOtpResponse(
        otp_id=otp.id,
        sent_to=otp.sent_to,
        channel=otp.channel,
    )


@router.post(
    "/trainings/assignments/{assignment_id}/verify-otp",
    response_model=VerifyOtpResponse,
)
async def verify_signing_otp(
    assignment_id: uuid.UUID,
    data: VerifyOtpRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    await _load_assignment_for_user(db, assignment_id, user)

    try:
        otp = await verify_otp(db, otp_id=data.otp_id, code=data.code)
    except SigningError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return VerifyOtpResponse(otp_id=otp.id, verified=otp.verified_at is not None)
