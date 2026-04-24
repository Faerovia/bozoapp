import secrets
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.core.validation import assert_in_tenant
from app.models.employee import Employee
from app.models.job_position import JobPosition
from app.models.user import User
from app.models.workplace import Plant, Workplace
from app.schemas.employees import EmployeeCreateRequest, EmployeeUpdateRequest


def _generate_password() -> str:
    """Generic default heslo pro nově vytvářené uživatele; OZO ho vidí jednou."""
    # 12 chars URL-safe base64 = ~72 bits entropy. Dost pro první přihlášení.
    return secrets.token_urlsafe(12)


async def _assert_workplace_in_plant(
    db: AsyncSession,
    workplace_id: uuid.UUID,
    plant_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> None:
    """Ověří, že workplace patří do daného plant + do tenantu."""
    row = (await db.execute(
        select(Workplace).where(
            Workplace.id == workplace_id,
            Workplace.plant_id == plant_id,
            Workplace.tenant_id == tenant_id,
        )
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="workplace_id nepatří do zvolené provozovny",
        )


async def get_employees(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    emp_status: str | None = None,
    employment_type: str | None = None,
) -> list[Employee]:
    query = (
        select(Employee)
        .where(Employee.tenant_id == tenant_id)
        .order_by(Employee.last_name.asc(), Employee.first_name.asc())
    )
    if emp_status is not None:
        query = query.where(Employee.status == emp_status)
    if employment_type is not None:
        query = query.where(Employee.employment_type == employment_type)

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_employee_by_user_id(
    db: AsyncSession, user_id: uuid.UUID, tenant_id: uuid.UUID
) -> Employee | None:
    """Najde HR záznam zaměstnance podle jeho auth user_id."""
    result = await db.execute(
        select(Employee).where(
            Employee.user_id == user_id,
            Employee.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def get_employee_by_id(
    db: AsyncSession, employee_id: uuid.UUID, tenant_id: uuid.UUID
) -> Employee | None:
    result = await db.execute(
        select(Employee).where(
            Employee.id == employee_id,
            Employee.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def create_employee(
    db: AsyncSession,
    data: EmployeeCreateRequest,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
) -> tuple[Employee, str | None]:
    """
    Vytvoří zaměstnance. Vrací (employee, plaintext_password).
    plaintext_password je set jen když service vytvoří nový auth User.

    Logika user account:
    - user_id zadán → propojíme s existujícím, heslo nevracíme
    - user_id NULL + (create_user_account OR is_equipment_responsible) →
      vytvoříme User s rolí employee (nebo equipment_responsible)
    - user_id NULL + ani jeden flag → zaměstnanec bez přístupu do aplikace
    """
    # FK validace
    if data.user_id is not None:
        await assert_in_tenant(db, User, data.user_id, tenant_id, field_name="user_id")
    if data.plant_id is not None:
        await assert_in_tenant(db, Plant, data.plant_id, tenant_id, field_name="plant_id")
    if data.workplace_id is not None:
        await assert_in_tenant(
            db, Workplace, data.workplace_id, tenant_id, field_name="workplace_id"
        )
        if data.plant_id is not None:
            await _assert_workplace_in_plant(
                db, data.workplace_id, data.plant_id, tenant_id
            )
    if data.job_position_id is not None:
        await assert_in_tenant(
            db, JobPosition, data.job_position_id, tenant_id, field_name="job_position_id"
        )

    # Auto-vytvoření user účtu.
    # Policy od commitu 9c: pokud je zadán email a není existující user_id,
    # service automaticky vytvoří auth účet s vygenerovaným heslem. Heslo
    # se vrátí jednou v `generated_password` (frontend ho zobrazí OZO).
    # Bez emailu (brigádník bez přístupu) se účet nevytvoří — backward compat.
    generated_password: str | None = None
    linked_user_id = data.user_id
    if data.user_id is None and data.email:
        # Duplicita emailu v rámci tenantu
        existing = (await db.execute(
            select(User).where(User.email == data.email, User.tenant_id == tenant_id)
        )).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Uživatel s emailem {data.email} již existuje v tomto tenantu",
            )

        password = data.user_password or _generate_password()
        # Pokud server heslo vygeneroval, vrátíme ho jednou přes response.
        # Pokud OZO zadal vlastní, taky ho ukážeme zpět (OZO ho může chtít
        # zkopírovat a předat zaměstnanci stejným kanálem jako generované).
        generated_password = password

        role = "equipment_responsible" if data.is_equipment_responsible else "employee"
        full_name = f"{data.first_name} {data.last_name}".strip()
        new_user = User(
            tenant_id=tenant_id,
            email=data.email,
            hashed_password=hash_password(password),
            full_name=full_name,
            role=role,
            is_active=True,
        )
        db.add(new_user)
        await db.flush()
        linked_user_id = new_user.id

    employee = Employee(
        tenant_id=tenant_id,
        created_by=created_by,
        user_id=linked_user_id,
        first_name=data.first_name,
        last_name=data.last_name,
        personal_id=data.personal_id,
        personal_number=data.personal_number,
        birth_date=data.birth_date,
        email=data.email,
        phone=data.phone,
        address_street=data.address_street,
        address_city=data.address_city,
        address_zip=data.address_zip,
        employment_type=data.employment_type,
        plant_id=data.plant_id,
        workplace_id=data.workplace_id,
        job_position_id=data.job_position_id,
        hired_at=data.hired_at,
        notes=data.notes,
    )
    db.add(employee)
    await db.flush()

    # Nastav zodpovědnosti (M:N) pokud byly zadány
    if data.responsible_plant_ids:
        from app.services.revisions import set_employee_responsibilities
        await set_employee_responsibilities(
            db, employee.id, data.responsible_plant_ids, tenant_id
        )

    return employee, generated_password


async def update_employee(
    db: AsyncSession, employee: Employee, data: EmployeeUpdateRequest
) -> Employee:
    update_fields = data.model_dump(exclude_unset=True)

    # Equipment responsible toggle — přepne roli propojeného usera
    if "is_equipment_responsible" in update_fields:
        is_resp = update_fields.pop("is_equipment_responsible")
        if employee.user_id is not None:
            linked = (await db.execute(
                select(User).where(User.id == employee.user_id)
            )).scalar_one_or_none()
            if linked is not None and linked.role in ("employee", "equipment_responsible"):
                # Měníme jen mezi těmito dvěma rolemi. OZO/HR/admin neměníme.
                linked.role = "equipment_responsible" if is_resp else "employee"

    # FK validace (stejně jako při create)
    if "user_id" in update_fields and update_fields["user_id"] is not None:
        await assert_in_tenant(
            db, User, update_fields["user_id"], employee.tenant_id, field_name="user_id"
        )
    if "plant_id" in update_fields and update_fields["plant_id"] is not None:
        await assert_in_tenant(
            db, Plant, update_fields["plant_id"], employee.tenant_id, field_name="plant_id"
        )
    if "workplace_id" in update_fields and update_fields["workplace_id"] is not None:
        await assert_in_tenant(
            db, Workplace, update_fields["workplace_id"], employee.tenant_id,
            field_name="workplace_id",
        )
        # Plant_id je ve stavu po update (pokud se měnil) nebo stávající
        effective_plant = update_fields.get("plant_id", employee.plant_id)
        if effective_plant is not None:
            await _assert_workplace_in_plant(
                db, update_fields["workplace_id"], effective_plant, employee.tenant_id
            )
    if "job_position_id" in update_fields and update_fields["job_position_id"] is not None:
        await assert_in_tenant(
            db, JobPosition, update_fields["job_position_id"], employee.tenant_id,
            field_name="job_position_id",
        )

    # Apply responsible_plant_ids separately (not a column on Employee)
    resp_plants: list[uuid.UUID] | None = update_fields.pop(
        "responsible_plant_ids", None
    )

    for field, value in update_fields.items():
        setattr(employee, field, value)

    await db.flush()

    if resp_plants is not None:
        from app.services.revisions import set_employee_responsibilities
        await set_employee_responsibilities(
            db, employee.id, resp_plants, employee.tenant_id
        )

    return employee


async def regenerate_user_password(
    db: AsyncSession, user: User
) -> str:
    """
    Vygeneruje nové heslo, uloží hash, revokuje všechny refresh tokeny
    (force re-login). Vrací plaintext heslo (jednorázově).
    """
    from app.services.refresh_tokens import revoke_user_tokens

    new_password = _generate_password()
    user.hashed_password = hash_password(new_password)
    await revoke_user_tokens(db, user.id)
    await db.flush()
    return new_password
