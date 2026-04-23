import uuid
from typing import Annotated

from pydantic import BaseModel, Field

WorkCategory = Annotated[
    str | None,
    Field(pattern=r"^(1|2|2R|3|4)$", default=None),
]


class JobPositionCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    work_category: WorkCategory = None
    medical_exam_period_months: int | None = Field(None, gt=0, le=120)
    notes: str | None = None


class JobPositionUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    work_category: WorkCategory = None
    medical_exam_period_months: int | None = Field(None, gt=0, le=120)
    notes: str | None = None
    status: str | None = Field(None, pattern="^(active|archived)$")


class JobPositionResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    description: str | None
    work_category: str | None
    medical_exam_period_months: int | None
    effective_exam_period_months: int | None  # computed property z modelu
    notes: str | None
    status: str
    created_by: uuid.UUID

    model_config = {"from_attributes": True}
