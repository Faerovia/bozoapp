import uuid

from pydantic import BaseModel, field_validator


class TenantResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    is_active: bool
    external_login_enabled: bool = False

    model_config = {"from_attributes": True}


class TenantUpdateRequest(BaseModel):
    name: str | None = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("Název firmy nesmí být prázdný")
        return v.strip() if v else v
