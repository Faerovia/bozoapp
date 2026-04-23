import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

TrainingType = Literal[
    "bozp_initial",      # BOZP vstupní školení (§37 ZP)
    "bozp_periodic",     # BOZP periodické opakování
    "fire_protection",   # Školení PO (zákon 133/1985 Sb.)
    "first_aid",         # První pomoc
    "equipment",         # Obsluha zařízení (jeřáby, VZV, tlakové nádoby...)
    "other",             # Ostatní
]

TrainingStatus = Literal["active", "archived"]

ValidityStatus = Literal["no_expiry", "valid", "expiring_soon", "expired"]


class TrainingCreateRequest(BaseModel):
    employee_id: uuid.UUID

    title: str = Field(..., min_length=1, max_length=255)
    training_type: TrainingType = "other"

    trained_at: date

    # Platnost: buď valid_months (vypočítá valid_until), nebo valid_until přímo,
    # nebo ani jedno (trvalé školení bez expiry).
    valid_months: int | None = Field(None, gt=0, le=600)  # max 50 let
    valid_until: date | None = None

    trainer_name: str | None = Field(None, max_length=255)
    notes: str | None = None

    @model_validator(mode="after")
    def resolve_valid_until(self) -> "TrainingCreateRequest":
        """
        Pokud je zadán valid_months a valid_until není explicitně nastaven,
        vypočítá valid_until = trained_at + valid_months měsíců.
        Pokud je zadán valid_until přímo, valid_months se ignoruje pro výpočet.
        """
        if self.valid_until is None and self.valid_months is not None:
            # Výpočet: přidat měsíce k trained_at
            month = self.trained_at.month + self.valid_months
            year = self.trained_at.year + (month - 1) // 12
            month = ((month - 1) % 12) + 1
            # Ošetři přetečení dnů (e.g. 31. jan + 1 měsíc = 28/29 feb)
            import calendar
            last_day = calendar.monthrange(year, month)[1]
            day = min(self.trained_at.day, last_day)
            from datetime import date as date_type
            self.valid_until = date_type(year, month, day)
        return self


class TrainingUpdateRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    training_type: TrainingType | None = None
    trained_at: date | None = None
    valid_months: int | None = Field(None, gt=0, le=600)
    valid_until: date | None = None
    trainer_name: str | None = Field(None, max_length=255)
    notes: str | None = None
    status: TrainingStatus | None = None


class TrainingResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    employee_id: uuid.UUID

    title: str
    training_type: str

    trained_at: date
    valid_months: int | None
    valid_until: date | None
    validity_status: str  # no_expiry | valid | expiring_soon | expired

    trainer_name: str | None
    notes: str | None
    status: str
    created_by: uuid.UUID

    model_config = {"from_attributes": True}
