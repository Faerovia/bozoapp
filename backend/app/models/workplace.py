"""
Modely pro hierarchii pracovišť:
  Plant (závod) → Workplace (pracoviště)

Rizikové faktory jsou na RiskFactorAssessment (viz risk_factor_assessment.py).
"""

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class Plant(Base, TimestampMixin):
    """Závod / provozovna. Nejvyšší úroveň hierarchie pracoviště."""
    __tablename__ = "plants"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    zip_code: Mapped[str | None] = mapped_column(String(10))
    ico: Mapped[str | None] = mapped_column(String(20))
    plant_number: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


class Workplace(Base, TimestampMixin):
    """Pracoviště – konkrétní pracovní prostor v rámci závodu."""
    __tablename__ = "workplaces"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    plant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plants.id", ondelete="CASCADE"), nullable=False
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
