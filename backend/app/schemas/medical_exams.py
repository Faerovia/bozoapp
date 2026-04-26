import uuid
from datetime import date

from pydantic import BaseModel, Field, model_validator

EXAM_TYPE_PATTERN = "^(vstupni|periodicka|vystupni|mimoradna|odborna)$"
EXAM_CATEGORY_PATTERN = "^(preventivni|odborna)$"


class MedicalExamCreateRequest(BaseModel):
    employee_id: uuid.UUID
    job_position_id: uuid.UUID | None = None
    exam_category: str = Field("preventivni", pattern=EXAM_CATEGORY_PATTERN)
    exam_type: str = Field(..., pattern=EXAM_TYPE_PATTERN)
    specialty: str | None = Field(None, max_length=50)
    # NULL = prohlídka byla naplánována ale neproběhla (auto-gen z RFA)
    exam_date: date | None = None
    result: str | None = Field(
        None,
        pattern="^(zpusobily|zpusobily_omezeni|nezpusobily|pozbyl_zpusobilosti)$",
    )
    physician_name: str | None = Field(None, max_length=255)
    valid_months: int | None = Field(None, gt=0, le=120)
    valid_until: date | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_and_compute(self) -> "MedicalExamCreateRequest":
        # Konzistence kategorie a typu
        if self.exam_category == "odborna":
            if not self.specialty:
                raise ValueError(
                    "U odborné prohlídky je nutné uvést specialty (typ vyšetření).",
                )
            if self.exam_type != "odborna":
                self.exam_type = "odborna"
        else:
            # preventivni — specialty nedává smysl
            self.specialty = None
            if self.exam_type == "odborna":
                raise ValueError(
                    "exam_type='odborna' není platný pro exam_category='preventivni'.",
                )

        # Auto-výpočet valid_until z valid_months (jen pokud je exam_date)
        if (
            self.valid_until is None
            and self.valid_months is not None
            and self.exam_date is not None
        ):
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
    exam_category: str | None = Field(None, pattern=EXAM_CATEGORY_PATTERN)
    exam_type: str | None = Field(None, pattern=EXAM_TYPE_PATTERN)
    specialty: str | None = Field(None, max_length=50)
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
    employee_name: str | None = None      # naplněno servicem (manuálně)
    employee_personal_id: str | None = None  # rodné číslo (jen pro ozo/hr_manager)
    job_position_id: uuid.UUID | None
    job_position_name: str | None = None
    work_category: str | None = None      # 1/2/2R/3/4 (z position)
    exam_category: str
    exam_type: str
    specialty: str | None
    specialty_label: str | None = None    # lidsky čitelné z catalogu
    exam_date: date | None
    result: str | None
    physician_name: str | None
    valid_months: int | None
    valid_until: date | None
    validity_status: str   # computed property z modelu
    days_until_expiry: int | None  # computed property z modelu
    has_report: bool = False              # je nahraná zpráva?
    notes: str | None
    status: str
    created_by: uuid.UUID

    model_config = {"from_attributes": True}


class GenerateInitialExamsRequest(BaseModel):
    employee_id: uuid.UUID


class TriggeredSpecialty(BaseModel):
    specialty: str
    factor: str       # rf_hluk, rf_prach, ...
    rating: str       # 2, 2R, 3, 4


class GenerateInitialExamsResponse(BaseModel):
    created: int
    exam_ids: list[uuid.UUID]
    skipped_specialties: list[str]      # už existující prohlídky stejného typu
    work_category: str | None           # max kategorie pozice (informativně)
    triggered_by_factors: list[TriggeredSpecialty] = Field(default_factory=list)
    rfa_present: bool = False           # má pozice vyplněné RFA?
