import uuid
from datetime import date, datetime, timezone

from sqlalchemy import CheckConstraint, Date, ForeignKey, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin

DUE_SOON_DAYS = 30


class Revision(Base, TimestampMixin):
    __tablename__ = "revisions"
    __table_args__ = (
        CheckConstraint("valid_months > 0", name="ck_revisions_valid_months"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    revision_type: Mapped[str] = mapped_column(String(50), default="other", nullable=False)
    location: Mapped[str | None] = mapped_column(String(255))

    last_revised_at: Mapped[date | None] = mapped_column(Date)
    valid_months: Mapped[int | None] = mapped_column(SmallInteger)
    next_revision_at: Mapped[date | None] = mapped_column(Date)

    contractor: Mapped[str | None] = mapped_column(String(255))
    responsible_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    @property
    def due_status(self) -> str:
        """
        - 'no_schedule'  – next_revision_at není zadán
        - 'ok'           – termín je dál než DUE_SOON_DAYS
        - 'due_soon'     – termín je do DUE_SOON_DAYS
        - 'overdue'      – termín je v minulosti
        """
        if self.next_revision_at is None:
            return "no_schedule"
        today = datetime.now(timezone.utc).date()
        delta = (self.next_revision_at - today).days
        if delta < 0:
            return "overdue"
        if delta <= DUE_SOON_DAYS:
            return "due_soon"
        return "ok"
