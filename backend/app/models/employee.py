import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin

EmploymentType = str  # alias pro čitelnost


class Employee(Base, TimestampMixin):
    __tablename__ = "employees"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )

    # Vazba na auth účet (volitelná)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, unique=True
    )

    # Identifikace
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    personal_id: Mapped[str | None] = mapped_column(String(20))
    birth_date: Mapped[date | None] = mapped_column(Date)

    # Kontakt
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))

    # Pracovní zařazení (FK přidány v budoucích migracích)
    job_position_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    workplace_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    # Typ pracovního poměru
    employment_type: Mapped[str] = mapped_column(String(50), default="hpp", nullable=False)

    # Časové rozsahy
    hired_at: Mapped[date | None] = mapped_column(Date)
    terminated_at: Mapped[date | None] = mapped_column(Date)

    # Stav
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    notes: Mapped[str | None] = mapped_column(Text)

    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    # ── Computed properties ───────────────────────────────────────────────────

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def is_active(self) -> bool:
        return self.status == "active"
