"""Schémata pro modul Provozní deníky."""
import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

DeviceCategory = Literal[
    "vzv", "kotelna", "tlakova_nadoba", "jerab", "eps", "sprinklery",
    "cov", "diesel", "regaly_sklad", "vytah", "stroje_riziko", "other",
]
Period = Literal["daily", "weekly", "monthly", "shift", "other"]
DeviceStatus = Literal["active", "archived"]


class DeviceCreateRequest(BaseModel):
    category: DeviceCategory
    title: str = Field(..., min_length=1, max_length=255)
    device_code: str | None = Field(None, max_length=100)
    location: str | None = Field(None, max_length=255)
    plant_id: uuid.UUID | None = None
    workplace_id: uuid.UUID | None = None
    check_items: list[str] = Field(..., min_length=1, max_length=20)
    period: Period = "daily"
    period_note: str | None = Field(None, max_length=255)
    notes: str | None = None


class DeviceUpdateRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    device_code: str | None = Field(None, max_length=100)
    location: str | None = Field(None, max_length=255)
    plant_id: uuid.UUID | None = None
    workplace_id: uuid.UUID | None = None
    check_items: list[str] | None = Field(None, min_length=1, max_length=20)
    period: Period | None = None
    period_note: str | None = Field(None, max_length=255)
    notes: str | None = None
    status: DeviceStatus | None = None


class DeviceResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    category: str
    title: str
    device_code: str | None
    location: str | None
    plant_id: uuid.UUID | None
    plant_name: str | None = None
    workplace_id: uuid.UUID | None
    check_items: list[str]
    period: str
    period_note: str | None
    qr_token: str
    notes: str | None
    status: str
    created_by: uuid.UUID

    model_config = {"from_attributes": True}


class EntryCreateRequest(BaseModel):
    performed_at: date
    performed_by_name: str = Field(..., min_length=1, max_length=255)
    # Pole bool paralelní s device.check_items. Délka musí odpovídat.
    capable_items: list[bool] = Field(..., min_length=1, max_length=20)
    overall_capable: bool = True
    notes: str | None = None


class EntryResponse(BaseModel):
    id: uuid.UUID
    device_id: uuid.UUID
    performed_at: date
    performed_by_name: str
    capable_items: list[bool]
    overall_capable: bool
    notes: str | None
    created_by: uuid.UUID

    model_config = {"from_attributes": True}
