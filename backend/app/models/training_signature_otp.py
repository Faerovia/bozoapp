"""
OTP pro ZES (kvalifikovaný elektronický podpis) školení.

Při requires_qes=True musí zaměstnanec před canvas podpisem zadat 6-místný
kód z emailu (později i SMS). Tabulka je ephemeral — záznamy se mažou
po expires_at (TTL ~10 min) nebo po úspěšném verify.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TrainingSignatureOTP(Base):
    __tablename__ = "training_signature_otps"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False,
    )
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("training_assignments.id", ondelete="CASCADE"), nullable=False,
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False,
    )
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    sent_to: Mapped[str] = mapped_column(String(255), nullable=False)
    channel: Mapped[str] = mapped_column(String(10), nullable=False, default="email")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
