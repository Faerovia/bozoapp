"""Univerzální API pro digitální podpisy.

Endpointy:
- POST   /signatures/initiate   — zahájí podpisový flow (volba auth_method)
- POST   /signatures/verify     — ověří OTP/heslo a vytvoří signature
- GET    /signatures/by-doc/{doc_type}/{doc_id} — vrátí podpisy pro dokument
- GET    /admin/signatures/verify-chain — admin ověří integritu chainu

Podpis vytváří zaměstnanec (current_user musí být shodný nebo OZO/HR).
Pro OOPP a training si caller dohraje validaci přístupu.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_platform_admin, require_role
from app.models.employee import Employee
from app.models.signature import (
    ALL_DOC_TYPES,
    AUTH_METHOD_PASSWORD,
    AUTH_METHOD_SMS_OTP,
    Signature,
)
from app.models.user import User
from app.services.signatures import (
    create_signature,
    initiate_sms_otp,
    verify_chain,
    verify_employee_password,
    verify_sms_otp,
)

log = logging.getLogger("api.signatures")

router = APIRouter()

DocType = Literal[
    "oopp_issue", "accident_report", "training_attempt", "training_content",
]
AuthMethod = Literal["password", "sms_otp"]


class InitiateRequest(BaseModel):
    doc_type: DocType
    doc_id: uuid.UUID
    employee_id: uuid.UUID
    auth_method: AuthMethod


class InitiateResponse(BaseModel):
    ok: bool
    auth_method: str
    sms_sent_to: str | None = None  # masked phone (např. "+420***456")
    expires_in_seconds: int | None = None
    message: str


class VerifyRequest(BaseModel):
    doc_type: DocType
    doc_id: uuid.UUID
    employee_id: uuid.UUID
    auth_method: AuthMethod
    code_or_password: str = Field(..., min_length=1, max_length=200)


class SignatureResponse(BaseModel):
    id: uuid.UUID
    doc_type: str
    doc_id: uuid.UUID
    employee_id: uuid.UUID
    employee_full_name_snapshot: str
    auth_method: str
    payload_hash: str
    seq: int
    chain_hash: str
    signed_at: str  # ISO 8601

    model_config = {"from_attributes": True}


def _redact_phone(phone: str) -> str:
    if len(phone) <= 6:
        return phone
    return phone[:-4] + "****"


async def _get_employee_in_tenant(
    db: AsyncSession, employee_id: uuid.UUID, tenant_id: uuid.UUID,
) -> Employee:
    emp = (
        await db.execute(
            select(Employee).where(
                Employee.id == employee_id,
                Employee.tenant_id == tenant_id,
            ),
        )
    ).scalar_one_or_none()
    if emp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Zaměstnanec nenalezen v tenantu",
        )
    return emp


@router.post("/signatures/initiate", response_model=InitiateResponse)
async def initiate_endpoint(
    data: InitiateRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager", "employee")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Zahájí podpisový flow.

    - Pro 'sms_otp' vygeneruje kód a pošle SMS na employee.phone.
    - Pro 'password' jen vrátí ack — verify pak ověří heslo.
    """
    emp = await _get_employee_in_tenant(db, data.employee_id, current_user.tenant_id)

    if data.auth_method == AUTH_METHOD_SMS_OTP:
        try:
            otp = await initiate_sms_otp(
                db,
                tenant_id=current_user.tenant_id,
                employee=emp,
                doc_type=data.doc_type,
                doc_id=data.doc_id,
            )
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(e),
            ) from e
        return InitiateResponse(
            ok=True,
            auth_method=AUTH_METHOD_SMS_OTP,
            sms_sent_to=_redact_phone(otp.sent_to),
            expires_in_seconds=300,  # 5 min
            message=f"SMS kód byl odeslán na {_redact_phone(otp.sent_to)}",
        )

    # password — žádná akce na backendu, ack
    if emp.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Zaměstnanec nemá login účet — pro podpis použij SMS kód."
            ),
        )
    return InitiateResponse(
        ok=True,
        auth_method=AUTH_METHOD_PASSWORD,
        sms_sent_to=None,
        expires_in_seconds=None,
        message="Zadej heslo, kterým se zaměstnanec přihlašuje do aplikace.",
    )


@router.post("/signatures/verify", response_model=SignatureResponse)
async def verify_endpoint(
    data: VerifyRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager", "employee")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Ověří OTP/heslo a vytvoří signature řádek (append-only).

    Po úspěšném verify:
    1. Vytvoří signature v `signatures`.
    2. Caller (OOPP, accident_reports, ...) musí zachytit response a uložit
       signature_id do svého modelu (pokud má dedikovaný FK).
    """
    emp = await _get_employee_in_tenant(db, data.employee_id, current_user.tenant_id)

    auth_proof: dict[str, Any] = {"verified_by_user_id": str(current_user.id)}

    if data.auth_method == AUTH_METHOD_SMS_OTP:
        try:
            otp = await verify_sms_otp(
                db,
                employee=emp,
                doc_type=data.doc_type,
                doc_id=data.doc_id,
                code=data.code_or_password,
            )
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(e),
            ) from e
        auth_proof["otp_id"] = str(otp.id)
        auth_proof["sent_to_redacted"] = _redact_phone(otp.sent_to)
    elif data.auth_method == AUTH_METHOD_PASSWORD:
        try:
            ok = await verify_employee_password(
                db, employee=emp, password=data.code_or_password,
            )
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(e),
            ) from e
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Nesprávné heslo",
            )
        auth_proof["password_verified"] = True
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Neznámý auth_method: {data.auth_method}",
        )

    # Sestav payload pro hash. Pro každý doc_type by měl mít builder svou
    # canonical formu — pro generic endpoint zatím sestavíme minimální payload.
    payload = {
        "doc_type": data.doc_type,
        "doc_id": str(data.doc_id),
        "tenant_id": str(current_user.tenant_id),
        "employee_id": str(emp.id),
        "employee_full_name": emp.full_name,
        "action": "sign",
    }

    sig = await create_signature(
        db,
        tenant_id=current_user.tenant_id,
        doc_type=data.doc_type,
        doc_id=data.doc_id,
        employee=emp,
        payload=payload,
        auth_method=data.auth_method,
        auth_proof=auth_proof,
    )

    # Propagace signed_at do AccidentReport — pro UX (PDF + záznam o úrazu)
    # potřebujeme `injured_signed_at` / `supervisor_signed_at` resp. položku
    # ve `witnesses[].signed_at`. Datum se bere z signature.signed_at, takže
    # uživatel ho už nemusí psát ručně. Pro externí zraněné se datum nesetuje
    # (digitální podpis tam není možný; tisk + ruční podpis na papíře).
    if data.doc_type == "accident_report":
        from app.models.accident_report import AccidentReport
        report = (await db.execute(
            select(AccidentReport).where(
                AccidentReport.id == data.doc_id,
                AccidentReport.tenant_id == current_user.tenant_id,
            ),
        )).scalar_one_or_none()
        if report is not None:
            sig_date = sig.signed_at.date()
            if report.employee_id == emp.id and not report.injured_external:
                report.injured_signed_at = sig_date
            if report.supervisor_employee_id == emp.id:
                report.supervisor_signed_at = sig_date
            # Svědci — najdi v JSONB list a doplň signed_at
            if report.witnesses:
                updated_witnesses = []
                for w in report.witnesses:
                    if (
                        w.get("employee_id")
                        and str(w["employee_id"]) == str(emp.id)
                        and not w.get("signed_at")
                    ):
                        w = {**w, "signed_at": sig_date.isoformat()}
                    updated_witnesses.append(w)
                report.witnesses = updated_witnesses
            await db.flush()

    return SignatureResponse(
        id=sig.id,
        doc_type=sig.doc_type,
        doc_id=sig.doc_id,
        employee_id=sig.employee_id,
        employee_full_name_snapshot=sig.employee_full_name_snapshot,
        auth_method=sig.auth_method,
        payload_hash=sig.payload_hash,
        seq=int(sig.seq),
        chain_hash=sig.chain_hash,
        signed_at=sig.signed_at.isoformat(),
    )


@router.get(
    "/signatures/by-doc/{doc_type}/{doc_id}",
    response_model=list[SignatureResponse],
)
async def list_by_doc(
    doc_type: str,
    doc_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager", "employee")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    if doc_type not in ALL_DOC_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Neplatný doc_type: {doc_type}",
        )
    rows = (
        await db.execute(
            select(Signature)
            .where(
                Signature.tenant_id == current_user.tenant_id,
                Signature.doc_type == doc_type,
                Signature.doc_id == doc_id,
            )
            .order_by(Signature.seq.asc()),
        )
    ).scalars().all()
    return [
        SignatureResponse(
            id=s.id,
            doc_type=s.doc_type,
            doc_id=s.doc_id,
            employee_id=s.employee_id,
            employee_full_name_snapshot=s.employee_full_name_snapshot,
            auth_method=s.auth_method,
            payload_hash=s.payload_hash,
            seq=int(s.seq),
            chain_hash=s.chain_hash,
            signed_at=s.signed_at.isoformat(),
        )
        for s in rows
    ]


@router.get("/admin/signatures/verify-chain")
async def admin_verify_chain(
    _admin: User = Depends(require_platform_admin()),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Admin endpoint: prochází kompletní chain a ověří integritu.

    Pomalé pro velké chains — pro běžnou kontrolu raději používat denní
    TSA kotvy (signature_anchors).
    """
    return await verify_chain(db)
