"""Risk Assessment dle ČSN ISO 45001 + Zákoník práce §102.

Tři tabulky:
- RiskAssessment           — hodnocení nebezpečí + P×Z + status workflow
- RiskMeasure              — opatření 1:N, hierarchie ISO controls
- RiskAssessmentRevision   — audit trail snapshot per revize

Liší se od RiskFactorAssessment (RFA) — RFA = NV 361/2007 kategorizace prací
podle expozice (hluk, prach...). RiskAssessment = strukturované hodnocení
konkrétních nebezpečných situací (pád z výšky, popálení, uklouznutí...).

Score = P × S (1–25). Level se odvozuje (low/medium/high/critical) v Pythonu
nebo přes platform_setting `risk.level_thresholds` (per-tenant override).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Computed,
    Date,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin

# ── Score → Level mapping (default; tenant může override v platform_settings)
DEFAULT_LEVEL_THRESHOLDS: dict[str, tuple[int, int]] = {
    "low":      (1, 4),
    "medium":   (5, 9),
    "high":     (10, 15),
    "critical": (16, 25),
}


def score_to_level(score: int | None) -> str | None:
    """Standardní mapping P×S na úroveň. Pro per-tenant override použít settings."""
    if score is None:
        return None
    for level, (lo, hi) in DEFAULT_LEVEL_THRESHOLDS.items():
        if lo <= score <= hi:
            return level
    return None


# Hierarchie kontrol dle ISO 45001 — preferují se vyšší úrovně
CONTROL_TYPES = ("elimination", "substitution", "engineering", "administrative", "ppe")
CONTROL_TYPE_LABELS_CS = {
    "elimination":     "Eliminace",
    "substitution":    "Substituce",
    "engineering":     "Inženýrské opatření",
    "administrative":  "Administrativní opatření",
    "ppe":             "OOPP",
}

HAZARD_CATEGORIES = (
    "slip_trip",
    "splash_flying_particles",
    "hot_surfaces",
    "manual_handling",
    "chemical_splash",
    "dust",
    "gas",
    "falling_object",
    "pressure_release",
    "working_at_height",
    "cutting",
    "low_clearance",
    "tool_drop",
    "electrical",
    "forklift",
    "machine_entanglement",
    "noise",
    "fire_explosion",
    "confined_space",
    "crane",
    "other",
)


class RiskAssessment(Base, TimestampMixin):
    """Strukturované hodnocení nebezpečí (4 scope + 5×5 P×Z + workflow)."""

    __tablename__ = "risk_assessments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False,
    )

    # Scope: čeho se týká (workplace|position|plant|activity)
    scope_type: Mapped[str] = mapped_column(String(20), nullable=False)
    workplace_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workplaces.id", ondelete="SET NULL"),
    )
    job_position_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("job_positions.id", ondelete="SET NULL"),
    )
    plant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("plants.id", ondelete="SET NULL"),
    )
    activity_description: Mapped[str | None] = mapped_column(Text)

    # Identifikace nebezpečí
    hazard_category: Mapped[str] = mapped_column(String(50), nullable=False)
    # oopp_risk_column = sloupec 1..26 dle NV 390/2021 Příloha 2 (standardizovaný
    # slovník sjednocující RA s OOPP gridem). Pro nové RA povinné v Pydantic
    # schématu, v DB nullable kvůli historickým záznamům před migrací 067.
    oopp_risk_column: Mapped[int | None] = mapped_column(SmallInteger)
    hazard_description: Mapped[str] = mapped_column(Text, nullable=False)
    consequence_description: Mapped[str] = mapped_column(Text, nullable=False)
    exposed_persons: Mapped[int | None] = mapped_column(SmallInteger)
    exposure_frequency: Mapped[str | None] = mapped_column(String(20))

    # Initial assessment
    initial_probability: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    initial_severity: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # initial_score je GENERATED v DB (P × S) — Computed říká SQLAlchemy, ať to vynechá z INSERT
    initial_score: Mapped[int | None] = mapped_column(
        SmallInteger,
        Computed("initial_probability * initial_severity", persisted=True),
    )
    initial_level: Mapped[str | None] = mapped_column(String(20))

    # Stávající kontroly
    existing_controls: Mapped[str | None] = mapped_column(Text)
    existing_oopp: Mapped[str | None] = mapped_column(Text)

    # Residual (po opatřeních)
    residual_probability: Mapped[int | None] = mapped_column(SmallInteger)
    residual_severity: Mapped[int | None] = mapped_column(SmallInteger)
    residual_score: Mapped[int | None] = mapped_column(
        SmallInteger,
        Computed(
            "COALESCE(residual_probability, initial_probability) * "
            "COALESCE(residual_severity, initial_severity)",
            persisted=True,
        ),
    )
    residual_level: Mapped[str | None] = mapped_column(String(20))

    # Workflow
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    assessed_at: Mapped[date | None] = mapped_column(Date)
    assessed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    review_due_date: Mapped[date | None] = mapped_column(Date)
    last_reviewed_at: Mapped[date | None] = mapped_column(Date)
    last_reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
    )

    # Provázanost s ostatními moduly
    related_accident_report_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("accident_reports.id", ondelete="SET NULL"),
    )
    related_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("revisions.id", ondelete="SET NULL"),
    )

    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False,
    )


class RiskMeasure(Base):
    """Opatření per riziko. Hierarchie ISO 45001 controls.

    Provázanost:
    - position_oopp_item_id: PPE measure → odkaz na konkrétní OOPP položku.
      Service při uložení zařadí OOPP do pozice + spustí výdej.
    - training_template_id:  administrative measure → školení template,
      které se přiřadí dotčeným zaměstnancům.
    """

    __tablename__ = "risk_measures"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False,
    )
    risk_assessment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("risk_assessments.id", ondelete="CASCADE"), nullable=False,
    )

    order_index: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    control_type: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Provázanost
    position_oopp_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("position_oopp_items.id", ondelete="SET NULL"),
    )
    training_template_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("trainings.id", ondelete="SET NULL"),
    )

    responsible_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"),
    )
    responsible_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    deadline: Mapped[date | None] = mapped_column(Date)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="planned")
    completed_at: Mapped[date | None] = mapped_column(Date)
    completed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    evidence_file_path: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow,
    )


class RiskAssessmentRevision(Base):
    """Audit trail — snapshot RiskAssessment per revize."""

    __tablename__ = "risk_assessment_revisions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False,
    )
    risk_assessment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("risk_assessments.id", ondelete="CASCADE"), nullable=False,
    )
    revision_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    change_reason: Mapped[str | None] = mapped_column(Text)
    revised_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    revised_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow,
    )
