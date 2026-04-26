"""Modul Pravidelné kontroly — sanační sady, záchytné vany, lékárničky."""
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin

DUE_SOON_DAYS = 30

CHECK_KINDS = (
    "sanitation_kit",   # Sanační sady (vyhl. 432/2003 Sb. — únik chem. látek)
    "spill_tray",       # Záchytné vany (NV 11/2002 Sb. — chem. skladování)
    "first_aid_kit",    # Lékárničky (vyhl. 296/2022 Sb. — pracoviště)
)


class PeriodicCheck(Base, TimestampMixin):
    __tablename__ = "periodic_checks"
    __table_args__ = (
        CheckConstraint(
            "check_kind IN ('sanitation_kit', 'spill_tray', 'first_aid_kit')",
            name="ck_periodic_check_kind",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )

    check_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255))

    plant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("plants.id", ondelete="RESTRICT")
    )
    workplace_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workplaces.id", ondelete="SET NULL")
    )

    last_checked_at: Mapped[date | None] = mapped_column(Date)
    valid_months: Mapped[int | None] = mapped_column(SmallInteger)
    next_check_at: Mapped[date | None] = mapped_column(Date)

    responsible_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    # Zodpovědný zaměstnanec — preferovaný kanál pro due/overdue alerty.
    # Pokud je nastaven, cron posílá email tomuto zaměstnanci místo
    # responsible_user_id. Migrace 056.
    responsible_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL")
    )

    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    @property
    def due_status(self) -> str:
        if self.next_check_at is None:
            return "no_schedule"
        today = datetime.now(UTC).date()
        delta = (self.next_check_at - today).days
        if delta < 0:
            return "overdue"
        if delta <= DUE_SOON_DAYS:
            return "due_soon"
        return "ok"


class PeriodicCheckRecord(Base):
    __tablename__ = "periodic_check_records"
    __table_args__ = (
        CheckConstraint(
            "result IN ('ok', 'fixed', 'issue')",
            name="ck_periodic_record_result",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    periodic_check_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("periodic_checks.id", ondelete="CASCADE"), nullable=False
    )

    performed_at: Mapped[date] = mapped_column(Date, nullable=False)
    performed_by_name: Mapped[str | None] = mapped_column(String(255))
    result: Mapped[str] = mapped_column(String(20), default="ok", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(String(500))

    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC),
    )
