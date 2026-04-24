import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

EmploymentType = Literal["hpp", "dpp", "dpc", "externista", "brigádník"]
EmployeeStatus = Literal["active", "terminated", "on_leave"]


class EmployeeCreateRequest(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)

    # Existující user_id pro propojení. Pokud NULL a zároveň create_user_account=True
    # nebo is_equipment_responsible=True → service vytvoří nový User.
    user_id: uuid.UUID | None = None
    # Flag: vytvořit auth účet pro přihlášení do aplikace.
    # Implicit True pokud is_equipment_responsible=True (potřebuje login).
    create_user_account: bool = False
    # Pokud vytváříme účet: heslo (plaintext) které uživatel dostane. Když
    # nevyplněno, server vygeneruje a vrátí v responsu (jednorázově).
    user_password: str | None = Field(None, min_length=8, max_length=128)
    # Zodpovědnost za vyhrazená technická zařízení — pokud zaškrtnuto, user
    # dostane role `equipment_responsible` místo defaultního `employee`.
    is_equipment_responsible: bool = False
    # Seznam provozoven, za které je zaměstnanec zodpovědný (M:N).
    # Pokud prázdný seznam + is_equipment_responsible=True → role se nastaví,
    # ale notifikace nedostává (musí admin doplnit přes PUT responsibilities).
    responsible_plant_ids: list[uuid.UUID] = Field(default_factory=list)

    personal_id: str | None = Field(None, max_length=20)
    # Rodné číslo — GDPR zvláštní kategorie, ukládáno Fernet-encrypted.
    personal_number: str | None = Field(None, max_length=50)
    # Osobní číslo u zaměstnavatele (unikátní v tenantu).
    birth_date: date | None = None

    email: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=50)

    # Trvalé bydliště
    address_street: str | None = Field(None, max_length=200)
    address_city: str | None = Field(None, max_length=100)
    address_zip: str | None = Field(None, max_length=10)

    employment_type: EmploymentType = "hpp"

    # Pracovní zařazení
    plant_id: uuid.UUID | None = None
    workplace_id: uuid.UUID | None = None
    job_position_id: uuid.UUID | None = None

    hired_at: date | None = None
    notes: str | None = None


class EmployeeUpdateRequest(BaseModel):
    first_name: str | None = Field(None, min_length=1, max_length=100)
    last_name: str | None = Field(None, min_length=1, max_length=100)
    user_id: uuid.UUID | None = None
    personal_id: str | None = Field(None, max_length=20)
    personal_number: str | None = Field(None, max_length=50)
    birth_date: date | None = None
    email: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=50)
    address_street: str | None = Field(None, max_length=200)
    address_city: str | None = Field(None, max_length=100)
    address_zip: str | None = Field(None, max_length=10)
    employment_type: EmploymentType | None = None
    hired_at: date | None = None
    terminated_at: date | None = None
    status: EmployeeStatus | None = None
    job_position_id: uuid.UUID | None = None
    plant_id: uuid.UUID | None = None
    workplace_id: uuid.UUID | None = None
    notes: str | None = None
    # Equipment responsible toggle — přepne roli linked usera mezi
    # equipment_responsible ↔ employee.
    is_equipment_responsible: bool | None = None
    # Volitelné: nahradí aktuální seznam zodpovědných provozoven. Pokud je
    # pole vynechané, M:N vazba se nemění.
    responsible_plant_ids: list[uuid.UUID] | None = None


class EmployeeResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID | None
    first_name: str
    last_name: str
    full_name: str
    personal_id: str | None
    personal_number: str | None
    birth_date: date | None
    email: str | None
    phone: str | None
    address_street: str | None
    address_city: str | None
    address_zip: str | None
    employment_type: str
    hired_at: date | None
    terminated_at: date | None
    status: str
    plant_id: uuid.UUID | None
    workplace_id: uuid.UUID | None
    job_position_id: uuid.UUID | None
    notes: str | None
    created_by: uuid.UUID

    # Jednorázově vrácené plaintext heslo, pokud při create service vygeneroval
    # nový auth account. Jen v response, do DB jde Argon2 hash. V response
    # `GET /employees` je vždy None (heslo nikdy nezobrazujeme retrospektivně).
    generated_password: str | None = None

    model_config = {"from_attributes": True}


class PasswordRegenerateResponse(BaseModel):
    """Pro POST /users/{id}/regenerate-password — nové heslo vrácené jednou."""
    new_password: str
