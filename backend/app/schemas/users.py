import uuid
from typing import Literal

from pydantic import BaseModel, EmailStr, field_validator

RoleType = Literal[
    "admin",                  # platform-level (SaaS operator, is_platform_admin=True)
    "ozo",                    # tenant-level full rights
    "hr_manager",             # tenant-level full rights (budoucí split od ozo)
    "equipment_responsible",  # employee + správa revizí/zařízení (scope TBD)
    "employee",               # self-access only
]


class UserCreateRequest(BaseModel):
    """OZO zve nového uživatele do tenantu."""

    email: EmailStr
    password: str
    full_name: str | None = None
    role: RoleType = "employee"

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Heslo musí mít alespoň 8 znaků")
        return v


class UserUpdateRequest(BaseModel):
    """
    Aktualizace uživatele. Oprávnění se řeší v endpointu:
    - full_name, password: může měnit každý sám sobě
    - role, is_active: pouze OZO
    """

    full_name: str | None = None
    role: RoleType | None = None
    is_active: bool | None = None
    password: str | None = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str | None) -> str | None:
        if v is not None and len(v) < 8:
            raise ValueError("Heslo musí mít alespoň 8 znaků")
        return v


class UserResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    full_name: str | None
    role: str
    is_active: bool

    model_config = {"from_attributes": True}
