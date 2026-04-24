import uuid
from datetime import date

from pydantic import BaseModel, Field, model_validator


class MedicalExamCreateRequest(BaseModel):
    employee_id: uuid.UUID
    job_position_id: uuid.UUID | None = None
    exam_type: str = Field(..., pattern="^(vstupni|periodicka|vystupni|mimoradna)$")
    exam_date: date
    result: str | None = Field(
        None,
        pattern="^(zpusobily|zpusobily_omezeni|nezpusobily|pozbyl_zpusobilosti)$",
    )
    physician_name: str | None = Field(None, max_length=255)
    valid_months: int | None = Field(None, gt=0, le=120)
    valid_until: date | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def compute_valid_until(self) -> "MedicalExamCreateRequest":
        """Pokud valid_until není zadáno, vypočítá ho z exam_date + valid_months."""
        if self.valid_until is None and self.valid_months is not None:
            import calendar
            d = self.exam_date
            month = d.month + self.valid_months
            year = d.year + (month - 1) // 12
            month = ((month - 1) % 12) + 1
            last_day = calendar.monthrange(year, month)[1]
            self.valid_until = date(year, month, min(d.day, last_day))
        return self


class MedicalExamUpdateRequest(BaseModel):
    job_position_id: uuid.UUID | None = None
    exam_type: str | None = Field(
        None, pattern="^(vstupni|periodicka|vystupni|mimoradna)$"
    )
    exam_date: date | None = None
    result: str | None = Field(
        None,
        pattern="^(zpusobily|zpusobily_omezeni|nezpusobily|pozbyl_zpusobilosti)$",
    )
    physician_name: str | None = Field(None, max_length=255)
    valid_months: int | None = Field(None, gt=0, le=120)
    valid_until: date | None = None
    notes: str | None = None
    status: str | None = Field(None, pattern="^(active|archived)$")


class MedicalExamResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    employee_id: uuid.UUID
    job_position_id: uuid.UUID | None
    exam_type: str
    exam_date: date
    result: str | None
    physician_name: str | None
    valid_months: int | None
    valid_until: date | None
    validity_status: str   # computed property z modelu
    days_until_expiry: int | None  # computed property z modelu
    notes: str | None
    status: str
    created_by: uuid.UUID

    model_config = {"from_attributes": True}
