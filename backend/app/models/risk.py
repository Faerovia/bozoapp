import uuid
from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin

# Hranice skóre rizika dle české metodiky (pravděpodobnost × závažnost)
RISK_SCORE_LOW_MAX = 6      # přijatelné riziko
RISK_SCORE_MEDIUM_MAX = 12  # střední riziko
# > 12 = vysoké riziko


def compute_risk_level(score: int) -> str:
    if score <= RISK_SCORE_LOW_MAX:
        return "low"
    elif score <= RISK_SCORE_MEDIUM_MAX:
        return "medium"
    return "high"


class Risk(Base, TimestampMixin):
    __tablename__ = "risks"
    __table_args__ = (
        CheckConstraint("probability BETWEEN 1 AND 5", name="ck_risks_probability"),
        CheckConstraint("severity BETWEEN 1 AND 5", name="ck_risks_severity"),
        CheckConstraint(
            "residual_probability IS NULL OR residual_probability BETWEEN 1 AND 5",
            name="ck_risks_residual_probability",
        ),
        CheckConstraint(
            "residual_severity IS NULL OR residual_severity BETWEEN 1 AND 5",
            name="ck_risks_residual_severity",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(255))
    activity: Mapped[str | None] = mapped_column(String(255))
    hazard_type: Mapped[str] = mapped_column(String(50), default="other", nullable=False)

    probability: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    severity: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    control_measures: Mapped[str | None] = mapped_column(Text)

    residual_probability: Mapped[int | None] = mapped_column(SmallInteger)
    residual_severity: Mapped[int | None] = mapped_column(SmallInteger)

    responsible_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    review_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    # ── Computed properties ───────────────────────────────────────────────────

    @property
    def risk_score(self) -> int:
        return self.probability * self.severity

    @property
    def risk_level(self) -> str:
        return compute_risk_level(self.risk_score)

    @property
    def residual_risk_score(self) -> int | None:
        if self.residual_probability is None or self.residual_severity is None:
            return None
        return self.residual_probability * self.residual_severity

    @property
    def residual_risk_level(self) -> str | None:
        score = self.residual_risk_score
        if score is None:
            return None
        return compute_risk_level(score)
