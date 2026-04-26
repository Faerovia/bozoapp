"""Schémata pro modul Pravidelné kontroly."""
import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

CheckKind = Literal["sanitation_kit", "spill_tray", "first_aid_kit"]
CheckStatus = Literal["active", "archived"]
DueStatus = Literal["no_schedule", "ok", "due_soon", "overdue"]
RecordResult = Literal["ok", "fixed", "issue"]


def _add_months(d: date, months: int) -> date:
    import calendar
    month = d.month + months
    year = d.year + (month - 1) // 12
    month = ((month - 1) % 12) + 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(d.day, last_day)
    return date(year, month, day)


class PeriodicCheckCreateRequest(BaseModel):
    check_kind: CheckKind
    title: str = Field(..., min_length=1, max_length=255)
    location: str | None = Field(None, max_length=255)
    plant_id: uuid.UUID | None = None
    workplace_id: uuid.UUID | None = None
    last_checked_at: date | None = None
    valid_months: int | None = Field(None, gt=0, le=600)
    next_check_at: date | None = None
    responsible_user_id: uuid.UUID | None = None
    responsible_employee_id: uuid.UUID | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def resolve_next_check(self) -> "PeriodicCheckCreateRequest":
        if (
            self.next_check_at is None
            and self.last_checked_at is not None
            and self.valid_months is not None
        ):
            self.next_check_at = _add_months(self.last_checked_at, self.valid_months)
        return self


class PeriodicCheckUpdateRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    location: str | None = Field(None, max_length=255)
    plant_id: uuid.UUID | None = None
    workplace_id: uuid.UUID | None = None
    last_checked_at: date | None = None
    valid_months: int | None = Field(None, gt=0, le=600)
    next_check_at: date | None = None
    responsible_user_id: uuid.UUID | None = None
    responsible_employee_id: uuid.UUID | None = None
    notes: str | None = None
    status: CheckStatus | None = None


class PeriodicCheckResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    check_kind: str
    title: str
    location: str | None
    plant_id: uuid.UUID | None
    plant_name: str | None = None
    workplace_id: uuid.UUID | None
    last_checked_at: date | None
    valid_months: int | None
    next_check_at: date | None
    due_status: str
    responsible_user_id: uuid.UUID | None
    responsible_employee_id: uuid.UUID | None = None
    responsible_employee_name: str | None = None
    notes: str | None
    status: str
    created_by: uuid.UUID

    model_config = {"from_attributes": True}


class PeriodicCheckRecordCreateRequest(BaseModel):
    performed_at: date
    performed_by_name: str | None = Field(None, max_length=255)
    result: RecordResult = "ok"
    notes: str | None = None


class PeriodicCheckRecordResponse(BaseModel):
    id: uuid.UUID
    periodic_check_id: uuid.UUID
    performed_at: date
    performed_by_name: str | None
    result: str
    notes: str | None
    file_path: str | None
    created_by: uuid.UUID

    model_config = {"from_attributes": True}
