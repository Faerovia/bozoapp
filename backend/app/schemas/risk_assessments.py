"""Pydantic schémata pro Risk Assessment dle ČSN ISO 45001."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

ScopeType = Literal["workplace", "position", "plant", "activity"]
RiskStatus = Literal["draft", "open", "in_progress", "mitigated", "accepted", "archived"]
ExposureFrequency = Literal["rare", "occasional", "frequent", "continuous"]
ControlType = Literal[
    "elimination", "substitution", "engineering", "administrative", "ppe",
]
MeasureStatus = Literal["planned", "in_progress", "done", "cancelled"]
RiskLevel = Literal["low", "medium", "high", "critical"]
HazardCategory = Literal[
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
]


# ── RiskAssessment ──────────────────────────────────────────────────────────


class RiskAssessmentCreateRequest(BaseModel):
    """Nové hodnocení rizika. P×Z initial povinné, residual volitelné."""

    scope_type: ScopeType
    workplace_id: uuid.UUID | None = None
    job_position_id: uuid.UUID | None = None
    plant_id: uuid.UUID | None = None
    activity_description: str | None = None

    hazard_category: HazardCategory
    hazard_description: str = Field(..., min_length=1)
    consequence_description: str = Field(..., min_length=1)
    exposed_persons: int | None = Field(None, ge=0, le=100000)
    exposure_frequency: ExposureFrequency | None = None

    initial_probability: int = Field(..., ge=1, le=5)
    initial_severity: int = Field(..., ge=1, le=5)

    existing_controls: str | None = None
    existing_oopp: str | None = None

    residual_probability: int | None = Field(None, ge=1, le=5)
    residual_severity: int | None = Field(None, ge=1, le=5)

    status: RiskStatus = "draft"
    assessed_at: date | None = None
    review_due_date: date | None = None

    related_accident_report_id: uuid.UUID | None = None
    related_revision_id: uuid.UUID | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_scope_target(self) -> RiskAssessmentCreateRequest:
        if self.scope_type == "workplace" and not self.workplace_id:
            raise ValueError("scope_type='workplace' vyžaduje workplace_id")
        if self.scope_type == "position" and not self.job_position_id:
            raise ValueError("scope_type='position' vyžaduje job_position_id")
        if self.scope_type == "plant" and not self.plant_id:
            raise ValueError("scope_type='plant' vyžaduje plant_id")
        if self.scope_type == "activity" and not (
            self.activity_description and self.activity_description.strip()
        ):
            raise ValueError(
                "scope_type='activity' vyžaduje activity_description",
            )
        return self


class RiskAssessmentUpdateRequest(BaseModel):
    """Editace existujícího rizika. Všechna pole volitelná (PATCH)."""

    scope_type: ScopeType | None = None
    workplace_id: uuid.UUID | None = None
    job_position_id: uuid.UUID | None = None
    plant_id: uuid.UUID | None = None
    activity_description: str | None = None

    hazard_category: HazardCategory | None = None
    hazard_description: str | None = Field(None, min_length=1)
    consequence_description: str | None = Field(None, min_length=1)
    exposed_persons: int | None = Field(None, ge=0, le=100000)
    exposure_frequency: ExposureFrequency | None = None

    initial_probability: int | None = Field(None, ge=1, le=5)
    initial_severity: int | None = Field(None, ge=1, le=5)

    existing_controls: str | None = None
    existing_oopp: str | None = None

    residual_probability: int | None = Field(None, ge=1, le=5)
    residual_severity: int | None = Field(None, ge=1, le=5)

    status: RiskStatus | None = None
    assessed_at: date | None = None
    review_due_date: date | None = None
    last_reviewed_at: date | None = None

    related_accident_report_id: uuid.UUID | None = None
    related_revision_id: uuid.UUID | None = None
    notes: str | None = None

    # Důvod změny — uloží se do revision snapshot
    change_reason: str | None = None


class RiskAssessmentResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID

    scope_type: str
    workplace_id: uuid.UUID | None = None
    workplace_name: str | None = None  # join helper
    job_position_id: uuid.UUID | None = None
    job_position_name: str | None = None  # join helper
    plant_id: uuid.UUID | None = None
    plant_name: str | None = None  # join helper
    activity_description: str | None = None

    hazard_category: str
    hazard_description: str
    consequence_description: str
    exposed_persons: int | None = None
    exposure_frequency: str | None = None

    initial_probability: int
    initial_severity: int
    initial_score: int | None = None
    initial_level: str | None = None

    existing_controls: str | None = None
    existing_oopp: str | None = None

    residual_probability: int | None = None
    residual_severity: int | None = None
    residual_score: int | None = None
    residual_level: str | None = None

    status: str
    assessed_at: date | None = None
    assessed_by_user_id: uuid.UUID | None = None
    review_due_date: date | None = None
    last_reviewed_at: date | None = None
    last_reviewed_by_user_id: uuid.UUID | None = None

    related_accident_report_id: uuid.UUID | None = None
    related_revision_id: uuid.UUID | None = None
    notes: str | None = None

    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    measures_count: int = 0
    measures_open_count: int = 0

    model_config = {"from_attributes": True}


# ── RiskMeasure ─────────────────────────────────────────────────────────────


class RiskMeasureCreateRequest(BaseModel):
    """Opatření. Pro 'ppe' použij position_oopp_item_id pro provázání s OOPP modulem."""

    risk_assessment_id: uuid.UUID
    order_index: int = 0
    control_type: ControlType
    description: str = Field(..., min_length=1)

    position_oopp_item_id: uuid.UUID | None = None
    training_template_id: uuid.UUID | None = None

    responsible_employee_id: uuid.UUID | None = None
    responsible_user_id: uuid.UUID | None = None
    deadline: date | None = None

    status: MeasureStatus = "planned"
    notes: str | None = None


class RiskMeasureUpdateRequest(BaseModel):
    order_index: int | None = None
    control_type: ControlType | None = None
    description: str | None = Field(None, min_length=1)

    position_oopp_item_id: uuid.UUID | None = None
    training_template_id: uuid.UUID | None = None

    responsible_employee_id: uuid.UUID | None = None
    responsible_user_id: uuid.UUID | None = None
    deadline: date | None = None

    status: MeasureStatus | None = None
    completed_at: date | None = None
    notes: str | None = None


class RiskMeasureResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    risk_assessment_id: uuid.UUID

    order_index: int
    control_type: str
    description: str

    position_oopp_item_id: uuid.UUID | None = None
    position_oopp_item_name: str | None = None  # join helper
    training_template_id: uuid.UUID | None = None
    training_template_title: str | None = None  # join helper

    responsible_employee_id: uuid.UUID | None = None
    responsible_employee_name: str | None = None  # join helper
    responsible_user_id: uuid.UUID | None = None
    deadline: date | None = None

    status: str
    completed_at: date | None = None
    completed_by_user_id: uuid.UUID | None = None
    evidence_file_path: str | None = None
    notes: str | None = None

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── RiskAssessmentRevision ───────────────────────────────────────────────────


class RiskAssessmentRevisionResponse(BaseModel):
    id: uuid.UUID
    risk_assessment_id: uuid.UUID
    revision_number: int
    snapshot: dict[str, Any]
    change_reason: str | None = None
    revised_by_user_id: uuid.UUID | None = None
    revised_at: datetime

    model_config = {"from_attributes": True}
