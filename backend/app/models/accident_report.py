import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    SmallInteger,
    String,
    Text,
    Time,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class AccidentReport(Base, TimestampMixin):
    __tablename__ = "accident_reports"
    __table_args__ = (
        CheckConstraint("injured_count >= 1", name="ck_accident_reports_injured_count"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )

    # Zaměstnanec
    employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL")
    )
    employee_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Snapshot názvu pracoviště pro PDF (vyplňuje service podle workplace_id
    # nebo workplace_external_description). Zachováno NOT NULL pro backward compat.
    workplace: Mapped[str] = mapped_column(String(255), nullable=False)
    # FK na konkrétní pracoviště v tenantu. NULL → úraz se stal mimo provozovnu
    # (typicky externí montáž, doprava, terén) — viz `workplace_external_description`.
    workplace_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workplaces.id", ondelete="SET NULL"),
    )
    # Když workplace_id IS NULL: textový popis místa úrazu mimo provozovnu.
    # (např. „Stavba Olomouc, ulice Wolkerova 5, lešení 3. patro").
    workplace_external_description: Mapped[str | None] = mapped_column(Text)

    # Čas
    accident_date: Mapped[date] = mapped_column(Date, nullable=False)
    accident_time: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)
    shift_start_time: Mapped[time | None] = mapped_column(Time(timezone=False))

    # Charakter zranění
    injury_type: Mapped[str] = mapped_column(String(255), nullable=False)
    injured_body_part: Mapped[str] = mapped_column(String(255), nullable=False)
    injury_source: Mapped[str] = mapped_column(String(255), nullable=False)
    injury_cause: Mapped[str] = mapped_column(Text, nullable=False)
    injured_count: Mapped[int] = mapped_column(SmallInteger, default=1, nullable=False)
    is_fatal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_other_injuries: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Popis
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Krevní patogeny
    blood_pathogen_exposure: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    blood_pathogen_persons: Mapped[str | None] = mapped_column(Text)

    # Předpisy
    violated_regulations: Mapped[str | None] = mapped_column(Text)

    # Testy
    alcohol_test_performed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    alcohol_test_result: Mapped[str | None] = mapped_column(String(20))
    alcohol_test_value: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))  # promile
    drug_test_performed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    drug_test_result: Mapped[str | None] = mapped_column(String(20))

    # Podpisy
    injured_signed_at: Mapped[date | None] = mapped_column(Date)
    # Postižený externí (brigádník bez evidence). Pokud True, digitální
    # podpis nelze a celý formulář vyžaduje fyzický tisk. Migrace 058.
    injured_external: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )
    # JSONB: list dictů {name: str, employee_id: uuid | None, signed_at: date | None}
    # Pokud witness.employee_id is None → externí svědek (digi podpis nelze).
    witnesses: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    supervisor_name: Mapped[str | None] = mapped_column(String(255))
    # Vedoucí pracovník z evidence. Pokud None ale supervisor_name je
    # vyplněný, je to externí vedoucí. Migrace 058.
    supervisor_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL")
    )
    supervisor_signed_at: Mapped[date | None] = mapped_column(Date)

    # Vazba na riziko
    risk_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("risks.id", ondelete="SET NULL")
    )

    # Risk review workflow
    risk_review_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    risk_review_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Workflow
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)

    # Podepsaný papírový záznam (sken / PDF)
    signed_document_path: Mapped[str | None] = mapped_column(String(500))

    # Univerzální digitální podpis (#105). Migrace 057.
    # signature_required: True pokud všichni účastníci jsou interní zaměstnanci.
    # False pokud kdokoliv je externí → vyžaduje fyzický tisk.
    signature_required: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
    )
    # Pole employee UUID, kteří musí podepsat (postižený + svědci + vedoucí,
    # všichni jen interní). Stringy v JSONB kvůli serializaci UUID.
    required_signer_employee_ids: Mapped[list[Any]] = mapped_column(
        JSONB, default=list, nullable=False,
    )

    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
