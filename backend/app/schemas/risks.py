import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

HazardType = Literal[
    "physical",     # fyzické (hluk, vibrace, záření, teplota)
    "chemical",     # chemické (látky, prašnost)
    "biological",   # biologické (viry, bakterie)
    "mechanical",   # mechanické (stroje, nářadí)
    "electrical",   # elektrické
    "ergonomic",    # ergonomické (poloha, zvedání břemen)
    "psychosocial", # psychosociální (stres, pracovní zátěž)
    "fire",         # požární
    "other",        # ostatní
]

RiskStatus = Literal["active", "archived"]


class RiskCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    location: str | None = Field(None, max_length=255)
    activity: str | None = Field(None, max_length=255)
    hazard_type: HazardType = "other"

    probability: int = Field(..., ge=1, le=5)
    severity: int = Field(..., ge=1, le=5)

    control_measures: str | None = None

    residual_probability: int | None = Field(None, ge=1, le=5)
    residual_severity: int | None = Field(None, ge=1, le=5)

    responsible_user_id: uuid.UUID | None = None
    review_date: date | None = None

    @model_validator(mode="after")
    def residual_both_or_none(self) -> "RiskCreateRequest":
        rp = self.residual_probability
        rs = self.residual_severity
        if (rp is None) != (rs is None):
            raise ValueError(
                "residual_probability a residual_severity musí být vyplněny oba nebo ani jeden"
            )
        return self


class RiskUpdateRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    location: str | None = Field(None, max_length=255)
    activity: str | None = Field(None, max_length=255)
    hazard_type: HazardType | None = None

    probability: int | None = Field(None, ge=1, le=5)
    severity: int | None = Field(None, ge=1, le=5)

    control_measures: str | None = None

    residual_probability: int | None = Field(None, ge=1, le=5)
    residual_severity: int | None = Field(None, ge=1, le=5)

    responsible_user_id: uuid.UUID | None = None
    review_date: date | None = None
    status: RiskStatus | None = None


class RiskResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    title: str
    description: str | None
    location: str | None
    activity: str | None
    hazard_type: str

    probability: int
    severity: int
    risk_score: int
    risk_level: str  # low | medium | high

    control_measures: str | None

    residual_probability: int | None
    residual_severity: int | None
    residual_risk_score: int | None
    residual_risk_level: str | None

    responsible_user_id: uuid.UUID | None
    review_date: date | None
    status: str
    created_by: uuid.UUID

    model_config = {"from_attributes": True}
