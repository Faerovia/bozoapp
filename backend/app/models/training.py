import uuid
from datetime import date, datetime, timezone

from sqlalchemy import CheckConstraint, Date, ForeignKey, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin

# Počet dní před expirací kdy se zobrazí varování
EXPIRING_SOON_DAYS = 30

TrainingType = str  # alias pro čitelnost


class Training(Base, TimestampMixin):
    __tablename__ = "trainings"
    __table_args__ = (
        CheckConstraint("valid_months > 0", name="ck_trainings_valid_months"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    training_type: Mapped[str] = mapped_column(String(50), default="other", nullable=False)

    trained_at: Mapped[date] = mapped_column(Date, nullable=False)

    valid_months: Mapped[int | None] = mapped_column(SmallInteger)
    valid_until: Mapped[date | None] = mapped_column(Date)

    trainer_name: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)

    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    # ── Computed properties ───────────────────────────────────────────────────

    @property
    def validity_status(self) -> str:
        """
        Odvozený stav platnosti záznamu.
        - 'no_expiry'      – valid_until je NULL (školení bez expiry)
        - 'valid'          – platí, expiry je dál než EXPIRING_SOON_DAYS
        - 'expiring_soon'  – platí, ale expiruje do EXPIRING_SOON_DAYS
        - 'expired'        – platnost vypršela
        """
        if self.valid_until is None:
            return "no_expiry"
        today = datetime.now(timezone.utc).date()
        delta = (self.valid_until - today).days
        if delta < 0:
            return "expired"
        if delta <= EXPIRING_SOON_DAYS:
            return "expiring_soon"
        return "valid"
