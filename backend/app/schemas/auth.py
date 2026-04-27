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
    """Login podporuje 3 typy identifierů (priorita podle obsahu):

    1. **Email** (obsahuje '@') — per-tenant unique. Backend zjistí tenant
       podle subdomain (X-Tenant-Slug header / Host) NEBO podle pole
       `tenant_slug` v body. Bez tenantu se email hledá globálně.
    2. **Username** (krátký řetězec, jen pro platform admina) — globálně unikát.
    3. **Personal_number** (osobní číslo zaměstnance) — vyžaduje tenant_slug.

    Backwards compat: `email` a `username` pole pořád fungují (deprecated,
    nový kód má posílat `identifier`).
    """
    # Nový sjednocený identifier (email, username, nebo personal_number).
    identifier: str | None = None
    # Tenant slug ze subdomény nebo formuláře. Vyžadováno pro personal_number,
    # volitelné pro email (kde rozlišení per-tenant pomáhá).
    tenant_slug: str | None = None
    # Legacy pole — pokud klient pošle email/username, převedeme na identifier
    email: EmailStr | None = None
    username: str | None = None
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
    username: str | None = None
    full_name: str | None
    role: str
    is_active: bool
    is_platform_admin: bool = False

    model_config = {"from_attributes": True}


class MembershipResponse(BaseModel):
    """Klient × role pro current_user. Pro client switcher."""
    tenant_id: uuid.UUID
    tenant_slug: str
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


class SmsLoginRequest(BaseModel):
    """Identifier pro request OTP. Email, username, personal_number nebo telefon.

    `tenant_slug` je volitelný — když chybí, backend se pokusí najít z
    Host hlavičky (subdomain). Pro personal_number je tenant_slug povinný
    (jinak nelze zjistit, který tenant — různí lidi mohou mít stejný
    personal_number v různých firmách).
    """
    identifier: str
    tenant_slug: str | None = None


class SmsLoginVerifyRequest(BaseModel):
    """Identifier + 6-místný OTP kód + volitelný tenant_slug."""
    identifier: str
    code: str
    tenant_slug: str | None = None


class ChangePasswordRequest(BaseModel):
    """Self-service změna hesla. Vyžaduje staré heslo pro ověření."""
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Nové heslo musí mít alespoň 8 znaků")
        return v
