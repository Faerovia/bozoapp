import uuid
from datetime import UTC, date, datetime

from sqlalchemy import CheckConstraint, Date, ForeignKey, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin

# Počet dní před expirací kdy se zobrazí varování
OOPP_EXPIRING_SOON_DAYS = 30


class OOPPAssignment(Base, TimestampMixin):
    __tablename__ = "oopp_assignments"
    __table_args__ = (
        CheckConstraint("valid_months > 0", name="ck_oopp_valid_months"),
        CheckConstraint("quantity > 0", name="ck_oopp_quantity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )

    employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id", ondelete="RESTRICT"), nullable=True
    )
    employee_name: Mapped[str] = mapped_column(String(255), nullable=False)

    item_name: Mapped[str] = mapped_column(String(255), nullable=False)
    oopp_type: Mapped[str] = mapped_column(String(50), default="other", nullable=False)

    issued_at: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[int] = mapped_column(SmallInteger, default=1, nullable=False)
    size_spec: Mapped[str | None] = mapped_column(String(50))
    serial_number: Mapped[str | None] = mapped_column(String(100))

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
        Odvozený stav platnosti OOPP.
        - 'no_expiry'      – valid_until je NULL
        - 'valid'          – platí, expiry je dál než OOPP_EXPIRING_SOON_DAYS
        - 'expiring_soon'  – platí, ale expiruje do OOPP_EXPIRING_SOON_DAYS
        - 'expired'        – platnost vypršela
        """
        if self.valid_until is None:
            return "no_expiry"
        today = datetime.now(UTC).date()
        delta = (self.valid_until - today).days
        if delta < 0:
            return "expired"
        if delta <= OOPP_EXPIRING_SOON_DAYS:
            return "expiring_soon"
        return "valid"
