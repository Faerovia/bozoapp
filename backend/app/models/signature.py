"""Univerzální podpisová infrastruktura — append-only s hash chain + TSA kotvy.

Slouží pro digitální podpisy zaměstnanců napříč moduly:
- OOPP výdej (potvrzení převzetí)
- Pracovní úraz (postižený + svědci + vedoucí)
- Školení (od přechodu z TrainingSignatureOTP)

Tamper-evidence:
1. payload_hash = SHA-256(canonical_json) — detekuje změnu obsahu dokumentu
2. chain_hash = SHA-256(prev_hash || payload_hash || seq) — detekuje úpravu
   historického záznamu (kaskáda po seq)
3. signature_anchors = denní RFC 3161 TSA kotva (cron) — externí důkaz
   nezměnitelnosti hashe k danému datu

DB triggery zakazují UPDATE/DELETE na signatures (append-only enforcement).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    SmallInteger,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# Doc types — odpovídají CHECK constraintu v migraci 057.
DOC_TYPE_OOPP_ISSUE = "oopp_issue"
DOC_TYPE_ACCIDENT_REPORT = "accident_report"
DOC_TYPE_TRAINING_ATTEMPT = "training_attempt"
DOC_TYPE_TRAINING_CONTENT = "training_content"  # autor + OZO podpis obsahu
ALL_DOC_TYPES = (
    DOC_TYPE_OOPP_ISSUE,
    DOC_TYPE_ACCIDENT_REPORT,
    DOC_TYPE_TRAINING_ATTEMPT,
    DOC_TYPE_TRAINING_CONTENT,
)

AUTH_METHOD_PASSWORD = "password"
AUTH_METHOD_SMS_OTP = "sms_otp"

# Initial prev_hash pro první řádek v chainu
GENESIS_HASH = "0" * 64


class Signature(Base):
    __tablename__ = "signatures"
    __table_args__ = (
        CheckConstraint(
            "doc_type IN ('oopp_issue', 'accident_report', "
            "'training_attempt', 'training_content')",
            name="ck_sig_doc_type",
        ),
        CheckConstraint(
            "auth_method IN ('password', 'sms_otp')",
            name="ck_sig_auth_method",
        ),
        Index("ix_signatures_doc", "doc_type", "doc_id"),
        Index("ix_signatures_tenant", "tenant_id", "signed_at"),
        Index("ix_signatures_employee", "employee_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False,
    )
    doc_type: Mapped[str] = mapped_column(String(50), nullable=False)
    doc_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    employee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False,
    )
    employee_full_name_snapshot: Mapped[str] = mapped_column(
        String(255), nullable=False,
    )
    payload_canonical: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    auth_method: Mapped[str] = mapped_column(String(20), nullable=False)
    auth_proof: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict,
    )
    seq: Mapped[int] = mapped_column(
        BigInteger, nullable=False, unique=True, autoincrement=True,
    )
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    chain_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    signed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )


class SignatureAnchor(Base):
    """Denní RFC 3161 TSA kotva pro celý chain (cross-tenant)."""

    __tablename__ = "signature_anchors"
    __table_args__ = (
        CheckConstraint(
            "tsa_provider IN ('freetsa', 'postsignum', 'ica', 'mock')",
            name="ck_anchor_provider",
        ),
        Index("ix_anchors_seq", "last_seq"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    anchored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    last_seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_chain_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    tsa_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    tsa_token: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    tsa_serial: Mapped[str | None] = mapped_column(String(100))


class SmsOtpCode(Base):
    """OTP kód pro autentizaci podpisu přes SMS.

    Životní cyklus:
    1. /signatures/initiate s auth_method='sms_otp' → vygeneruje 6místný kód,
       hash uloží sem, plain text pošle SMS gateway (v dev mode mock = '111111').
    2. /signatures/verify s code → kontrola hash + attempts + expiry.
    3. Po úspěšném ověření verified_at = now, vytvoří se signature řádek
       v `signatures` tabulce.
    """

    __tablename__ = "sms_otp_codes"
    __table_args__ = (
        CheckConstraint(
            "doc_type IN ('oopp_issue', 'accident_report', "
            "'training_attempt', 'training_content')",
            name="ck_sms_otp_doc_type",
        ),
        Index(
            "ix_sms_otp_pending",
            "employee_id", "doc_type", "doc_id",
            postgresql_where="verified_at IS NULL",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False,
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False,
    )
    doc_type: Mapped[str] = mapped_column(String(50), nullable=False)
    doc_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    sent_to: Mapped[str] = mapped_column(String(50), nullable=False)
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )


# Suppression: Boolean import — používá se v úpravách acccident_report.py
_ = Boolean
