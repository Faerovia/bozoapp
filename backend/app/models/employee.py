import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.encryption import EncryptedString
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
    # Rodné číslo — GDPR Čl. 9 zvláštní kategorie. Fernet-encrypted at rest.
    # V DB je to ciphertext (~150 chars), aplikace vidí plaintext transparentně.
    personal_id: Mapped[str | None] = mapped_column(EncryptedString(256))
    # Osobní číslo (employee ID u zaměstnavatele) — unikátní v rámci tenantu,
    # volitelné (brigádníci ho nemusí mít).
    personal_number: Mapped[str | None] = mapped_column(String(50))
    birth_date: Mapped[date | None] = mapped_column(Date)
    # Pohlaví (NV 361/2007 ženy na rizikových pracovištích, statistiky)
    # M = muž, F = žena, X = jiné / neuvedeno. NULL = nevyplněno.
    gender: Mapped[str | None] = mapped_column(String(1))

    # Kontakt
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))

    # Trvalé bydliště
    address_street: Mapped[str | None] = mapped_column(String(200))
    address_city: Mapped[str | None] = mapped_column(String(100))
    address_zip: Mapped[str | None] = mapped_column(String(10))

    # Pracovní zařazení (FK na plants/workplaces/job_positions)
    job_position_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    plant_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    workplace_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    # Typ pracovního poměru
    employment_type: Mapped[str] = mapped_column(String(50), default="hpp", nullable=False)

    # Časové rozsahy
    hired_at: Mapped[date | None] = mapped_column(Date)
    terminated_at: Mapped[date | None] = mapped_column(Date)

    # Stav
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    # Throttling pro auto-generaci lékařských prohlídek
    # Po každé úspěšné generaci se aktualizuje. Manuální tlačítko
    # „Generovat prohlídky" projde jen ty zaměstnance, kteří byli zkontrolováni
    # před více než 30 minutami (nebo ještě nikdy).
    last_exam_auto_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

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
