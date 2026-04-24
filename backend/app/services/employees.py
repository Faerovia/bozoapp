import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.schemas.employees import EmployeeCreateRequest, EmployeeUpdateRequest


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
) -> Employee:
    # Pokud je zadáno user_id, ověříme že user existuje ve stejném tenantu
    if data.user_id is not None:
        from app.models.user import User
        user = (
            await db.execute(
                select(User).where(User.id == data.user_id, User.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="user_id neexistuje v tomto tenantu",
            )

    employee = Employee(
        tenant_id=tenant_id,
        created_by=created_by,
        user_id=data.user_id,
        first_name=data.first_name,
        last_name=data.last_name,
        personal_id=data.personal_id,
        birth_date=data.birth_date,
        email=data.email,
        phone=data.phone,
        employment_type=data.employment_type,
        hired_at=data.hired_at,
        notes=data.notes,
    )
    db.add(employee)
    await db.flush()
    return employee


async def update_employee(
    db: AsyncSession, employee: Employee, data: EmployeeUpdateRequest
) -> Employee:
    update_fields = data.model_dump(exclude_unset=True)

    # Pokud se mění user_id, ověříme tenant příslušnost
    if "user_id" in update_fields and update_fields["user_id"] is not None:
        from app.models.user import User
        user = (
            await db.execute(
                select(User).where(
                    User.id == update_fields["user_id"],
                    User.tenant_id == employee.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="user_id neexistuje v tomto tenantu",
            )

    for field, value in update_fields.items():
        setattr(employee, field, value)

    await db.flush()
    return employee
