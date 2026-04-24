import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator

# Legacy široký enum (zachováme pro zpětnou kompat s existujícími daty)
RevisionType = Literal[
    "electrical",
    "pressure_vessel",
    "fire_equipment",
    "gas",
    "lifting_equipment",
    "ladder",
    "other",
]

# Striktní enum nového modelu („typ vyhrazeného zařízení")
DeviceType = Literal[
    "elektro",
    "hromosvody",
    "plyn",
    "kotle",
    "tlakove_nadoby",
    "vytahy",
    "spalinove_cesty",
]

RevisionStatus = Literal["active", "archived"]
DueStatus = Literal["no_schedule", "ok", "due_soon", "overdue"]


def _add_months(d: date, months: int) -> date:
    import calendar
    month = d.month + months
    year = d.year + (month - 1) // 12
    month = ((month - 1) % 12) + 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(d.day, last_day)
    return date(year, month, day)


class RevisionCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    # Nový model vyžaduje plant_id + device_type — validuje frontend.
    # Na API úrovni zůstávají optional kvůli zpětné kompat se staršími klienty
    # a legacy daty. Nové záznamy by měly mít obojí vyplněno.
    plant_id: uuid.UUID | None = None
    device_type: DeviceType | None = None
    device_code: str | None = Field(None, max_length=100)
    location: str | None = Field(None, max_length=255)   # upřesnění umístění

    last_revised_at: date | None = None
    valid_months: int | None = Field(None, gt=0, le=600)
    next_revision_at: date | None = None                 # dopočítá se

    technician_name: str | None = Field(None, max_length=255)
    technician_email: EmailStr | None = None
    technician_phone: str | None = Field(None, max_length=50)

    responsible_user_id: uuid.UUID | None = None
    notes: str | None = None

    # Legacy kompat — přestože schema nové, endpoint může dostat starý tvar
    revision_type: RevisionType | None = None

    @model_validator(mode="after")
    def resolve_next_revision_at(self) -> "RevisionCreateRequest":
        if (
            self.next_revision_at is None
            and self.last_revised_at is not None
            and self.valid_months is not None
        ):
            self.next_revision_at = _add_months(
                self.last_revised_at, self.valid_months
            )
        return self


class RevisionUpdateRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    plant_id: uuid.UUID | None = None
    device_type: DeviceType | None = None
    device_code: str | None = Field(None, max_length=100)
    location: str | None = Field(None, max_length=255)

    last_revised_at: date | None = None
    valid_months: int | None = Field(None, gt=0, le=600)
    next_revision_at: date | None = None

    technician_name: str | None = Field(None, max_length=255)
    technician_email: EmailStr | None = None
    technician_phone: str | None = Field(None, max_length=50)

    responsible_user_id: uuid.UUID | None = None
    notes: str | None = None
    status: RevisionStatus | None = None

    revision_type: RevisionType | None = None


class RevisionResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    title: str
    plant_id: uuid.UUID | None
    plant_name: str | None = None   # JOIN pro čitelnost v UI
    device_code: str | None
    device_type: str | None
    location: str | None
    last_revised_at: date | None
    valid_months: int | None
    next_revision_at: date | None
    due_status: str
    technician_name: str | None
    technician_email: str | None
    technician_phone: str | None
    contractor: str | None          # legacy, ponecháváme v response
    responsible_user_id: uuid.UUID | None
    qr_token: str
    notes: str | None
    status: str
    created_by: uuid.UUID
    revision_type: str

    model_config = {"from_attributes": True}


# ── Revision records (timeline) ───────────────────────────────────────────────


class RevisionRecordCreateRequest(BaseModel):
    """Zadá se přes multipart upload (date + file). Schéma pro JSON variantu
    bez souboru (jen ruční záznam)."""
    performed_at: date
    technician_name: str | None = Field(None, max_length=255)
    notes: str | None = None


class RevisionRecordResponse(BaseModel):
    id: uuid.UUID
    revision_id: uuid.UUID
    performed_at: date
    pdf_path: str | None
    image_path: str | None
    technician_name: str | None
    notes: str | None
    created_by: uuid.UUID

    model_config = {"from_attributes": True}


# ── Employee plant responsibilities ───────────────────────────────────────────


class EmployeeResponsibilitiesUpdate(BaseModel):
    """Nahradí současnou sadu provozoven zadaným seznamem."""
    plant_ids: list[uuid.UUID]


class EmployeeResponsibilitiesResponse(BaseModel):
    employee_id: uuid.UUID
    plant_ids: list[uuid.UUID]


# ── Kalendářový agregát ───────────────────────────────────────────────────────

CalendarSource = Literal["revision", "risk", "training"]


class CalendarItem(BaseModel):
    source: CalendarSource
    source_id: uuid.UUID
    title: str
    due_date: date
    due_status: str
    responsible_user_id: uuid.UUID | None
    detail_url: str
