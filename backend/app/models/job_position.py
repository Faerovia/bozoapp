"""
Model pro pracovní pozice (kategorizace prací dle NV 361/2007 Sb.).

Každý záznam = typ pracovního zařazení v rámci tenantu.
Slouží jako reference pro:
  - Lékařské prohlídky (periodicita dle kategorie práce)
  - Zaměstnanci (employee.job_position_id)
  - BOZP dokumentace

Výchozí lhůty periodické prohlídky (vyhláška 79/2013 Sb. §11):
  Kategorie 1:  72 měsíců (věk < 50), 48 měsíců (věk ≥ 50)
  Kategorie 2:  48 měsíců (věk < 50), 24 měsíců (věk ≥ 50)
  Kategorie 2R: 24 měsíců
  Kategorie 3:  24 měsíců
  Kategorie 4:  12 měsíců
"""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin

# Výchozí lhůty periodické prohlídky v měsících dle kategorie (věk < 50)
# OZO může přepsat na konkrétní pozici přes medical_exam_period_months
CATEGORY_DEFAULT_EXAM_MONTHS: dict[str, int] = {
    "1": 72,
    "2": 48,
    "2R": 24,
    "3": 24,
    "4": 12,
}


class JobPosition(Base, TimestampMixin):
    __tablename__ = "job_positions"
    __table_args__ = (
        CheckConstraint(
            "work_category IN ('1','2','2R','3','4') OR work_category IS NULL",
            name="ck_jp_category",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Kategorie práce dle NV 361/2007 Sb.
    work_category: Mapped[str | None] = mapped_column(String(3))

    # Přepsatelná lhůta periodické prohlídky
    # NULL → použij CATEGORY_DEFAULT_EXAM_MONTHS[work_category]
    medical_exam_period_months: Mapped[int | None] = mapped_column(SmallInteger)

    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    # ── Computed properties ───────────────────────────────────────────────────

    @property
    def effective_exam_period_months(self) -> int | None:
        """
        Efektivní lhůta periodické prohlídky.
        Priorita: ruční override > výchozí z kategorie > None (není určeno).
        """
        if self.medical_exam_period_months is not None:
            return self.medical_exam_period_months
        if self.work_category is not None:
            return CATEGORY_DEFAULT_EXAM_MONTHS.get(self.work_category)
        return None
