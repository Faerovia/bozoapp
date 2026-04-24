import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

RevisionType = Literal[
    "electrical",         # elektrorevize (vyhl. 50/1978, NV 194/2022)
    "pressure_vessel",    # tlakové nádoby (NV 26/2003)
    "fire_equipment",     # hasicí přístroje (vyhl. 246/2001)
    "gas",                # plynová zařízení
    "lifting_equipment",  # zdvihací zařízení (NV 378/2001)
    "ladder",             # žebříky (ČSN EN 131)
    "other",
]

RevisionStatus = Literal["active", "archived"]
DueStatus = Literal["no_schedule", "ok", "due_soon", "overdue"]


class RevisionCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    revision_type: RevisionType = "other"
    location: str | None = Field(None, max_length=255)

    last_revised_at: date | None = None
    valid_months: int | None = Field(None, gt=0, le=600)
    next_revision_at: date | None = None

    contractor: str | None = Field(None, max_length=255)
    responsible_user_id: uuid.UUID | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def resolve_next_revision_at(self) -> "RevisionCreateRequest":
        """
        Pokud next_revision_at není zadán, vypočítá se z last_revised_at + valid_months.
        Explicitní next_revision_at má přednost.
        """
        if (
            self.next_revision_at is None
            and self.last_revised_at is not None
            and self.valid_months is not None
        ):
            import calendar
            month = self.last_revised_at.month + self.valid_months
            year = self.last_revised_at.year + (month - 1) // 12
            month = ((month - 1) % 12) + 1
            last_day = calendar.monthrange(year, month)[1]
            day = min(self.last_revised_at.day, last_day)
            from datetime import date as date_type
            self.next_revision_at = date_type(year, month, day)
        return self


class RevisionUpdateRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    revision_type: RevisionType | None = None
    location: str | None = Field(None, max_length=255)
    last_revised_at: date | None = None
    valid_months: int | None = Field(None, gt=0, le=600)
    next_revision_at: date | None = None
    contractor: str | None = Field(None, max_length=255)
    responsible_user_id: uuid.UUID | None = None
    notes: str | None = None
    status: RevisionStatus | None = None


class RevisionResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    title: str
    revision_type: str
    location: str | None
    last_revised_at: date | None
    valid_months: int | None
    next_revision_at: date | None
    due_status: str  # no_schedule | ok | due_soon | overdue
    contractor: str | None
    responsible_user_id: uuid.UUID | None
    notes: str | None
    status: str
    created_by: uuid.UUID

    model_config = {"from_attributes": True}


# ── Kalendářový agregát ───────────────────────────────────────────────────────

CalendarSource = Literal["revision", "risk", "training"]


class CalendarItem(BaseModel):
    """Unified položka v agregovaném kalendáři termínů."""
    source: CalendarSource          # odkud položka pochází
    source_id: uuid.UUID            # id záznamu ve zdrojové tabulce
    title: str
    due_date: date                  # termín: next_revision_at / review_date / valid_until
    due_status: str                 # overdue | due_soon | ok
    responsible_user_id: uuid.UUID | None
    detail_url: str                 # relativní URL pro přechod na detail (/api/v1/risks/uuid)
