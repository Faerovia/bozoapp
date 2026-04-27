"""LoginSmsOtpCode — OTP kód pro alternativní login přes SMS.

Viz migrace 061. Liší se od signature SMS OTP (sms_otp_codes):
- Není vázaný na document (žádný doc_type/doc_id)
- Není vázaný na tenant (login je cross-tenant pro platform admina)
- Vázaný přímo na users.id, ne employees.id
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LoginSmsOtpCode(Base):
    __tablename__ = "login_sms_otp_codes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
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
