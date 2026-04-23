import calendar
import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

OOPPType = Literal[
    "head_protection",          # ochrana hlavy (přilby, čepice)
    "eye_protection",           # ochrana očí a obličeje
    "hearing_protection",       # ochrana sluchu
    "respiratory_protection",   # ochrana dýchacích cest
    "hand_protection",          # ochrana rukou (rukavice)
    "foot_protection",          # ochrana nohou (obuv, kamaše)
    "fall_protection",          # ochrana proti pádu (postroje, lana)
    "body_protection",          # ochrana trupu (vesty, pláště)
    "skin_protection",          # ochrana kůže (krémy, štíty)
    "visibility",               # výstražné prostředky (reflexní vesty)
    "other",
]

OOPPStatus = Literal["active", "archived"]
ValidityStatus = Literal["no_expiry", "valid", "expiring_soon", "expired"]


class OOPPCreateRequest(BaseModel):
    employee_id: uuid.UUID | None = None
    employee_name: str = Field(..., min_length=1, max_length=255)

    item_name: str = Field(..., min_length=1, max_length=255)
    oopp_type: OOPPType = "other"

    issued_at: date
    quantity: int = Field(1, gt=0)
    size_spec: str | None = Field(None, max_length=50)
    serial_number: str | None = Field(None, max_length=100)

    valid_months: int | None = Field(None, gt=0, le=600)
    valid_until: date | None = None

    notes: str | None = None

    @model_validator(mode="after")
    def resolve_valid_until(self) -> "OOPPCreateRequest":
        """
        Pokud valid_until není zadán, vypočítá se z issued_at + valid_months.
        Explicitní valid_until má přednost.
        """
        if self.valid_until is None and self.valid_months is not None:
            month = self.issued_at.month + self.valid_months
            year = self.issued_at.year + (month - 1) // 12
            month = ((month - 1) % 12) + 1
            last_day = calendar.monthrange(year, month)[1]
            day = min(self.issued_at.day, last_day)
            self.valid_until = date(year, month, day)
        return self


class OOPPUpdateRequest(BaseModel):
    employee_id: uuid.UUID | None = None
    employee_name: str | None = Field(None, min_length=1, max_length=255)
    item_name: str | None = Field(None, min_length=1, max_length=255)
    oopp_type: OOPPType | None = None
    issued_at: date | None = None
    quantity: int | None = Field(None, gt=0)
    size_spec: str | None = Field(None, max_length=50)
    serial_number: str | None = Field(None, max_length=100)
    valid_months: int | None = Field(None, gt=0, le=600)
    valid_until: date | None = None
    notes: str | None = None
    status: OOPPStatus | None = None


class OOPPResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    employee_id: uuid.UUID | None
    employee_name: str
    item_name: str
    oopp_type: str
    issued_at: date
    quantity: int
    size_spec: str | None
    serial_number: str | None
    valid_months: int | None
    valid_until: date | None
    validity_status: str  # no_expiry | valid | expiring_soon | expired
    notes: str | None
    status: str
    created_by: uuid.UUID

    model_config = {"from_attributes": True}
