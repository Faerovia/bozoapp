"""
Model pro lékařské prohlídky (pracovnělékařské služby).

Legislativa: zákon 373/2011 Sb., vyhláška 79/2013 Sb.

Computed properties:
  - validity_status  – no_expiry | valid | expiring_soon | expired
  - due_status       – pending | ok | due_soon | overdue  (pro periodické prohlídky)
"""

import uuid
from datetime import date, timedelta
from typing import Literal

from sqlalchemy import CheckConstraint, Date, ForeignKey, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin

ExamType = Literal["vstupni", "periodicka", "vystupni", "mimoradna"]
ExamResult = Literal["zpusobily", "zpusobily_omezeni", "nezpusobily", "pozbyl_zpusobilosti"]

EXPIRING_SOON_DAYS = 60  # 2 měsíce před vypršením = varování


class MedicalExam(Base, TimestampMixin):
    __tablename__ = "medical_exams"
    __table_args__ = (
        CheckConstraint(
            "exam_type IN ('vstupni','periodicka','vystupni','mimoradna')",
            name="ck_me_exam_type",
        ),
        CheckConstraint(
            "result IN ('zpusobily','zpusobily_omezeni','nezpusobily','pozbyl_zpusobilosti') OR result IS NULL",  # noqa: E501
            name="ck_me_result",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    job_position_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("job_positions.id", ondelete="SET NULL"), nullable=True
    )

    exam_type: Mapped[str] = mapped_column(String(20), nullable=False)
    exam_date: Mapped[date] = mapped_column(Date, nullable=False)
    result: Mapped[str | None] = mapped_column(String(30))

    physician_name: Mapped[str | None] = mapped_column(String(255))
    valid_months: Mapped[int | None] = mapped_column(SmallInteger)
    valid_until: Mapped[date | None] = mapped_column(Date)

    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    # ── Computed properties ───────────────────────────────────────────────────

    @property
    def validity_status(self) -> str:
        """
        Stav platnosti prohlídky:
          no_expiry     – prohlídka bez stanoveného termínu platnosti
          valid         – platná
          expiring_soon – vyprší do EXPIRING_SOON_DAYS dnů
          expired       – prošlá
        """
        if self.valid_until is None:
            return "no_expiry"
        today = date.today()
        if self.valid_until < today:
            return "expired"
        if self.valid_until <= today + timedelta(days=EXPIRING_SOON_DAYS):
            return "expiring_soon"
        return "valid"

    @property
    def days_until_expiry(self) -> int | None:
        """Počet dní do vypršení. None pokud valid_until není nastaveno."""
        if self.valid_until is None:
            return None
        return (self.valid_until - date.today()).days
