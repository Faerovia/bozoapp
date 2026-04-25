import uuid

from pydantic import BaseModel, EmailStr, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None
    tenant_name: str  # Vytvoří nový tenant pro tohoto uživatele

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Heslo musí mít alespoň 8 znaků")
        return v

    @field_validator("tenant_name")
    @classmethod
    def tenant_name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Název firmy nesmí být prázdný")
        return v.strip()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    # Pokud má user zapnuté 2FA, musí přiložit TOTP kód nebo recovery code.
    # Klient neví dopředu, jestli user má 2FA — pošle nejdřív login bez kódu,
    # při 403 TOTP_REQUIRED pošle znovu s kódem.
    totp_code: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    full_name: str | None
    role: str
    is_active: bool

    model_config = {"from_attributes": True}


class MembershipResponse(BaseModel):
    """Klient × role pro current_user. Pro client switcher."""
    tenant_id: uuid.UUID
    tenant_name: str
    role: str
    is_default: bool

    model_config = {"from_attributes": True}


class SelectTenantRequest(BaseModel):
    tenant_id: uuid.UUID


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Heslo musí mít alespoň 8 znaků")
        return v
