"""
Training šablona + přiřazení zaměstnancům + pokusy o test.

Training (šablona)
    ↓ 1:N
TrainingAssignment (přiřazení konkrétnímu zaměstnanci)
    ↓ 1:N
TrainingAttempt (pokusy o test)

Staré 1:1 schéma (Training.employee_id) bylo dropnuto v migraci 022.
"""
import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin

# Dní předem, kdy se přiřazení zobrazí jako "expiring_soon"
EXPIRING_SOON_DAYS = 30


class Training(Base, TimestampMixin):
    """Šablona školení. Jedna Training → N TrainingAssignment přes employee."""
    __tablename__ = "trainings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # tenant_id je NULL pro globální (marketplace) školení, jinak povinný.
    # Konzistence vynucená CHECK constraint v migraci 036.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
    )
    # Globální šablona vytvořená platform adminem (zobrazí se na marketplace).
    is_global: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )
    # Pokud je tato šablona kopií globální (po aktivaci tenantem), odkazuje
    # na původní zdroj. Slouží pro audit a budoucí auto-update obsahu.
    global_source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("trainings.id", ondelete="SET NULL"),
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # training_type: bozp | po | other
    training_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # trainer_kind: ozo_bozp | ozo_po | employer
    trainer_kind: Mapped[str] = mapped_column(String(20), nullable=False, default="employer")
    valid_months: Mapped[int] = mapped_column(Integer, nullable=False)

    # Cesta na PDF s obsahem školení. NULL = bez PDF (jen instrukce v title).
    content_pdf_path: Mapped[str | None] = mapped_column(String(500))

    # Test — pokud NULL, zaměstnanec absolvuje jen "potvrzením přečtení".
    # Struktura: [{"question": str, "correct_answer": str, "wrong_answers": [str,str,str]}]
    test_questions: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    pass_percentage: Mapped[int | None] = mapped_column(Integer)

    notes: Mapped[str | None] = mapped_column(Text)

    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    @property
    def has_test(self) -> bool:
        return self.test_questions is not None and len(self.test_questions) > 0

    @property
    def question_count(self) -> int:
        return len(self.test_questions) if self.test_questions else 0


class TrainingAssignment(Base, TimestampMixin):
    """Přiřazení šablony konkrétnímu zaměstnanci + jeho aktuální stav."""
    __tablename__ = "training_assignments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    training_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("trainings.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )

    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="NOW()"
    )
    # Deadline pro první absolvování = assigned_at + 7 dní.
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Datum poslední úspěšné absolvace; NULL dokud nedokončil poprvé.
    last_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Do kdy platí aktuální absolvování (last_completed + training.valid_months).
    valid_until: Mapped[date | None] = mapped_column(Date)

    # pending | completed | expired | revoked
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")

    assigned_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    @property
    def validity_status(self) -> str:
        """
        - 'pending'        – dosud nesplněno, v deadline
        - 'overdue'        – dosud nesplněno, po deadline
        - 'valid'          – splněno, do expirace > EXPIRING_SOON_DAYS
        - 'expiring_soon'  – splněno, expirace < 30 dní
        - 'expired'        – splněno ale valid_until < dnes
        """
        today = datetime.now(UTC).date()
        if self.last_completed_at is None:
            return "overdue" if self.deadline.date() < today else "pending"
        if self.valid_until is None:
            return "valid"
        delta = (self.valid_until - today).days
        if delta < 0:
            return "expired"
        if delta <= EXPIRING_SOON_DAYS:
            return "expiring_soon"
        return "valid"


class TrainingAttempt(Base):
    """
    Jeden pokus zaměstnance o test. Každý pokus je ostrý — uloží se skóre
    + passed flag. Passed=True triggeruje update TrainingAssignment.
    """
    __tablename__ = "training_attempts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("training_assignments.id", ondelete="CASCADE"), nullable=False
    )

    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="NOW()"
    )
    score_percentage: Mapped[int] = mapped_column(Integer, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # Serializované odpovědi uživatele: [{"question_index", "chosen", "correct"}]
    answers: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
