import uuid
from typing import Annotated

from pydantic import BaseModel, Field

WorkCategory = Annotated[
    str | None,
    Field(pattern=r"^(1|2|2R|3|4)$", default=None),
]


class JobPositionCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    # Workplace (pracoviště) — povinné v novém modelu. Pozice je per-workplace.
    workplace_id: uuid.UUID
    description: str | None = None
    # Manuální override kategorie práce. Pokud None, derivuje se z RFA.
    work_category: WorkCategory = None
    medical_exam_period_months: int | None = Field(None, gt=0, le=120)
    notes: str | None = None


class JobPositionUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    workplace_id: uuid.UUID | None = None
    description: str | None = None
    work_category: WorkCategory = None
    medical_exam_period_months: int | None = Field(None, gt=0, le=120)
    notes: str | None = None
    status: str | None = Field(None, pattern="^(active|archived)$")


class JobPositionResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    workplace_id: uuid.UUID
    workplace_name: str | None = None   # JOIN pro UI
    plant_id: uuid.UUID | None = None   # odvozené z workplace
    plant_name: str | None = None
    name: str
    description: str | None
    work_category: str | None           # manuální override (legacy)
    effective_category: str | None      # derived: override nebo RFA.category_proposed
    medical_exam_period_months: int | None
    effective_exam_period_months: int | None
    notes: str | None
    status: str
    created_by: uuid.UUID

    model_config = {"from_attributes": True}
