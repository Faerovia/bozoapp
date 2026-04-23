import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

EmploymentType = Literal["hpp", "dpp", "dpc", "externista", "brigádník"]
EmployeeStatus = Literal["active", "terminated", "on_leave"]


class EmployeeCreateRequest(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)

    user_id: uuid.UUID | None = None
    # Propojení s auth účtem; NULL = zaměstnanec bez přístupu do aplikace

    personal_id: str | None = Field(None, max_length=20)
    # Rodné číslo – GDPR zvláštní kategorie, posílat jen pokud nutné
    birth_date: date | None = None

    email: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=50)

    employment_type: EmploymentType = "hpp"

    hired_at: date | None = None
    notes: str | None = None


class EmployeeUpdateRequest(BaseModel):
    first_name: str | None = Field(None, min_length=1, max_length=100)
    last_name: str | None = Field(None, min_length=1, max_length=100)
    user_id: uuid.UUID | None = None
    personal_id: str | None = Field(None, max_length=20)
    birth_date: date | None = None
    email: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=50)
    employment_type: EmploymentType | None = None
    hired_at: date | None = None
    terminated_at: date | None = None
    status: EmployeeStatus | None = None
    job_position_id: uuid.UUID | None = None
    workplace_id: uuid.UUID | None = None
    notes: str | None = None


class EmployeeResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID | None
    first_name: str
    last_name: str
    full_name: str
    personal_id: str | None
    birth_date: date | None
    email: str | None
    phone: str | None
    employment_type: str
    hired_at: date | None
    terminated_at: date | None
    status: str
    job_position_id: uuid.UUID | None
    workplace_id: uuid.UUID | None
    notes: str | None
    created_by: uuid.UUID

    model_config = {"from_attributes": True}
