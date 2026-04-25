import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class PlatformSettingResponse(BaseModel):
    key: str
    value: Any
    description: str | None
    updated_by: uuid.UUID | None
    updated_at: datetime

    model_config = {"from_attributes": True}


class PlatformSettingUpdateRequest(BaseModel):
    value: Any
