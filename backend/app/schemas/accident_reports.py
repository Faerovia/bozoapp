import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, Field, model_validator

TestResult = Literal["negative", "positive"]
AccidentReportStatus = Literal["draft", "final", "archived"]


class WitnessInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    signed_at: date | None = None


class AccidentReportCreateRequest(BaseModel):
    # Zaměstnanec
    employee_id: uuid.UUID | None = None
    employee_name: str = Field(..., min_length=1, max_length=255)
    workplace: str = Field(..., min_length=1, max_length=255)

    # Čas
    accident_date: date
    accident_time: time
    shift_start_time: time | None = None

    # Charakter zranění
    injury_type: str = Field(..., min_length=1, max_length=255)
    injured_body_part: str = Field(..., min_length=1, max_length=255)
    injury_source: str = Field(..., min_length=1, max_length=255)
    injury_cause: str = Field(..., min_length=1)
    injured_count: int = Field(default=1, ge=1)
    is_fatal: bool = False
    has_other_injuries: bool = False

    # Popis
    description: str = Field(..., min_length=1)

    # Krevní patogeny
    blood_pathogen_exposure: bool = False
    blood_pathogen_persons: str | None = None

    # Předpisy
    violated_regulations: str | None = None

    # Testy
    alcohol_test_performed: bool = False
    alcohol_test_result: TestResult | None = None
    drug_test_performed: bool = False
    drug_test_result: TestResult | None = None

    # Podpisy
    injured_signed_at: date | None = None
    witnesses: list[WitnessInput] = Field(default_factory=list)
    supervisor_name: str | None = Field(None, max_length=255)
    supervisor_signed_at: date | None = None

    # Vazba na riziko
    risk_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def validate_test_results(self) -> "AccidentReportCreateRequest":
        if self.alcohol_test_performed and self.alcohol_test_result is None:
            raise ValueError("alcohol_test_result musí být vyplněn pokud byl test proveden")
        if not self.alcohol_test_performed:
            self.alcohol_test_result = None
        if self.drug_test_performed and self.drug_test_result is None:
            raise ValueError("drug_test_result musí být vyplněn pokud byl test proveden")
        if not self.drug_test_performed:
            self.drug_test_result = None
        return self


class AccidentReportUpdateRequest(BaseModel):
    """Editace je povolena pouze ve stavu draft."""
    employee_id: uuid.UUID | None = None
    employee_name: str | None = Field(None, min_length=1, max_length=255)
    workplace: str | None = Field(None, min_length=1, max_length=255)
    accident_date: date | None = None
    accident_time: time | None = None
    shift_start_time: time | None = None
    injury_type: str | None = Field(None, min_length=1, max_length=255)
    injured_body_part: str | None = Field(None, min_length=1, max_length=255)
    injury_source: str | None = Field(None, min_length=1, max_length=255)
    injury_cause: str | None = Field(None, min_length=1)
    injured_count: int | None = Field(None, ge=1)
    is_fatal: bool | None = None
    has_other_injuries: bool | None = None
    description: str | None = Field(None, min_length=1)
    blood_pathogen_exposure: bool | None = None
    blood_pathogen_persons: str | None = None
    violated_regulations: str | None = None
    alcohol_test_performed: bool | None = None
    alcohol_test_result: TestResult | None = None
    drug_test_performed: bool | None = None
    drug_test_result: TestResult | None = None
    injured_signed_at: date | None = None
    witnesses: list[WitnessInput] | None = None
    supervisor_name: str | None = Field(None, max_length=255)
    supervisor_signed_at: date | None = None
    risk_id: uuid.UUID | None = None


class AccidentReportResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID

    employee_id: uuid.UUID | None
    employee_name: str
    workplace: str

    accident_date: date
    accident_time: time
    shift_start_time: time | None

    injury_type: str
    injured_body_part: str
    injury_source: str
    injury_cause: str
    injured_count: int
    is_fatal: bool
    has_other_injuries: bool

    description: str

    blood_pathogen_exposure: bool
    blood_pathogen_persons: str | None

    violated_regulations: str | None

    alcohol_test_performed: bool
    alcohol_test_result: str | None
    drug_test_performed: bool
    drug_test_result: str | None

    injured_signed_at: date | None
    witnesses: list  # [{name, signed_at}]
    supervisor_name: str | None
    supervisor_signed_at: date | None

    risk_id: uuid.UUID | None
    risk_review_required: bool
    risk_review_completed_at: datetime | None

    status: str
    created_by: uuid.UUID

    model_config = {"from_attributes": True}
