import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.permissions import require_role
from app.models.user import User
from app.schemas.employees import EmployeeCreateRequest, EmployeeResponse, EmployeeUpdateRequest
from app.services.employees import (
    create_employee,
    get_employee_by_id,
    get_employees,
    update_employee,
)

router = APIRouter()


@router.get("/employees", response_model=list[EmployeeResponse])
async def list_employees(
    emp_status: str | None = Query(None, pattern="^(active|terminated|on_leave)$"),
    employment_type: str | None = Query(None),
    current_user: User = Depends(require_role("ozo", "manager")),
    db: AsyncSession = Depends(get_db),
) -> list:
    """
    Vrátí seznam zaměstnanců tenantu.
    Filtry: ?emp_status=active|terminated|on_leave, ?employment_type=hpp|dpp|...
    Přístup: ozo, manager.
    """
    return await get_employees(
        db, current_user.tenant_id,
        emp_status=emp_status,
        employment_type=employment_type,
    )


@router.post("/employees", response_model=EmployeeResponse, status_code=status.HTTP_201_CREATED)
async def create_employee_endpoint(
    data: EmployeeCreateRequest,
    current_user: User = Depends(require_role("ozo", "manager")),
    db: AsyncSession = Depends(get_db),
) -> object:
    """
    Vytvoří nový záznam zaměstnance.
    user_id je volitelné – zaměstnanec nemusí mít přístup do aplikace.
    Přístup: ozo, manager.
    """
    return await create_employee(db, data, current_user.tenant_id, current_user.id)


@router.get("/employees/{employee_id}", response_model=EmployeeResponse)
async def get_employee(
    employee_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> object:
    """
    Vrátí detail zaměstnance.
    Employee může vidět pouze svůj vlastní záznam.
    Přístup: všechny role (employee = jen vlastní).
    """
    employee = await get_employee_by_id(db, employee_id, current_user.tenant_id)
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zaměstnanec nenalezen")

    # Employee vidí jen sebe – ověříme přes user_id
    if current_user.role == "employee" and employee.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Přístup odepřen")

    return employee


@router.patch("/employees/{employee_id}", response_model=EmployeeResponse)
async def update_employee_endpoint(
    employee_id: uuid.UUID,
    data: EmployeeUpdateRequest,
    current_user: User = Depends(require_role("ozo", "manager")),
    db: AsyncSession = Depends(get_db),
) -> object:
    """Aktualizuje zaměstnance. Přístup: ozo, manager."""
    employee = await get_employee_by_id(db, employee_id, current_user.tenant_id)
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zaměstnanec nenalezen")
    return await update_employee(db, employee, data)


@router.delete("/employees/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
async def terminate_employee(
    employee_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "manager")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Označí zaměstnance jako terminated (status=terminated).
    Fyzické smazání není povoleno – BOZP záznamy musí být dohledatelné.
    """
    employee = await get_employee_by_id(db, employee_id, current_user.tenant_id)
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zaměstnanec nenalezen")
    employee.status = "terminated"
    await db.flush()
