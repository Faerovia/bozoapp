"""
Schémata pro OOPP modul (NV 390/2021 Sb.).

Struktura:
  PositionRiskGrid    — vyhodnocení rizik per pozice (matrix 14×26)
  PositionOoppItem    — co je pozice povinná dostat
  EmployeeOoppIssue   — záznam výdeje
"""

import calendar
import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

# ── Risk grid ────────────────────────────────────────────────────────────────


class RiskGridUpdateRequest(BaseModel):
    """Replace strategie: client posílá kompletní novou matrix."""
    grid: dict[str, list[int]] = Field(default_factory=dict)


class RiskGridResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    job_position_id: uuid.UUID
    grid: dict[str, list[int]]
    has_any_risk: bool
    created_by: uuid.UUID

    model_config = {"from_attributes": True}


# ── Position OOPP item ───────────────────────────────────────────────────────

BodyPartLetter = Literal[
    "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N",
]


class OoppItemCreateRequest(BaseModel):
    job_position_id: uuid.UUID
    body_part: BodyPartLetter
    name: str = Field(..., min_length=1, max_length=255)
    valid_months: int | None = Field(None, gt=0, le=600)
    notes: str | None = None


class OoppItemUpdateRequest(BaseModel):
    body_part: BodyPartLetter | None = None
    name: str | None = Field(None, min_length=1, max_length=255)
    valid_months: int | None = Field(None, gt=0, le=600)
    notes: str | None = None
    status: Literal["active", "archived"] | None = None


class OoppItemResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    job_position_id: uuid.UUID
    body_part: str
    name: str
    valid_months: int | None
    notes: str | None
    status: str
    created_by: uuid.UUID

    model_config = {"from_attributes": True}


# ── Employee OOPP issue ──────────────────────────────────────────────────────

ValidityStatus = Literal["no_expiry", "valid", "expiring_soon", "expired"]


class IssueCreateRequest(BaseModel):
    employee_id: uuid.UUID
    position_oopp_item_id: uuid.UUID

    issued_at: date
    valid_until: date | None = None
    quantity: int = Field(1, gt=0)
    size_spec: str | None = Field(None, max_length=50)
    serial_number: str | None = Field(None, max_length=100)
    notes: str | None = None

    @model_validator(mode="after")
    def resolve_valid_until(self) -> "IssueCreateRequest":
        # Server dopočítá valid_until z item.valid_months v service vrstvě
        # (potřebujeme přístup k DB). Tady jen necháme zadanou hodnotu.
        return self


class IssueUpdateRequest(BaseModel):
    issued_at: date | None = None
    valid_until: date | None = None
    quantity: int | None = Field(None, gt=0)
    size_spec: str | None = Field(None, max_length=50)
    serial_number: str | None = Field(None, max_length=100)
    notes: str | None = None
    status: Literal["active", "returned", "discarded"] | None = None


class IssueResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str | None = None        # JOIN pro UI
    position_oopp_item_id: uuid.UUID
    item_name: str | None = None            # JOIN: position_oopp_item.name
    body_part: str | None = None            # JOIN: position_oopp_item.body_part
    issued_at: date
    valid_until: date | None
    validity_status: str
    quantity: int
    size_spec: str | None
    serial_number: str | None
    notes: str | None
    status: str
    created_by: uuid.UUID

    model_config = {"from_attributes": True}


# ── Konstanty ekvivalentní backend modelu — exporty pro UI ──────────────────

class BodyPartInfo(BaseModel):
    key: str
    label: str
    group: str | None


class RiskColumnInfo(BaseModel):
    col: int
    label: str
    subgroup: str | None
    group: str


class OoppCatalogResponse(BaseModel):
    """Statický popis tabulky NV 390/2021 — UI je z toho vykreslí."""
    body_parts: list[BodyPartInfo]
    risk_columns: list[RiskColumnInfo]


def _add_months(d: date, months: int) -> date:
    month = d.month + months
    year = d.year + (month - 1) // 12
    month = ((month - 1) % 12) + 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(d.day, last_day)
    return date(year, month, day)
