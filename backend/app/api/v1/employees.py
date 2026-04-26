import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.permissions import require_role
from app.models.user import User
from app.schemas.employees import (
    EmployeeCreateRequest,
    EmployeeResponse,
    EmployeeUpdateRequest,
)
from app.services.employee_import import (
    generate_template_csv,
    import_from_csv,
)
from app.services.employees import (
    create_employee,
    get_employee_by_id,
    get_employees,
    update_employee,
)

router = APIRouter()


# ── Import schémata ──────────────────────────────────────────────────────────

class ImportSuccessRow(BaseModel):
    row: int
    employee_id: uuid.UUID
    full_name: str
    email: str | None = None
    generated_password: str | None = None


class ImportErrorRow(BaseModel):
    row: int
    error: str
    raw: dict[str, Any]


class ImportResponse(BaseModel):
    total_rows: int
    created_count: int
    error_count: int
    created: list[ImportSuccessRow]
    errors: list[ImportErrorRow]


@router.get("/employees", response_model=list[EmployeeResponse])
async def list_employees(
    emp_status: str | None = Query(None, pattern="^(active|terminated|on_leave)$"),
    employment_type: str | None = Query(None),
    plant_id: uuid.UUID | None = Query(None),
    workplace_id: uuid.UUID | None = Query(None),
    job_position_id: uuid.UUID | None = Query(None),
    gender: str | None = Query(None, pattern="^(M|F|X)$"),
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> list[Any]:
    """
    Vrátí seznam zaměstnanců tenantu.
    Filtry: emp_status, employment_type, plant_id, workplace_id, job_position_id, gender (M/F/X).
    Přístup: ozo, manager.
    """
    return await get_employees(
        db, current_user.tenant_id,
        emp_status=emp_status,
        employment_type=employment_type,
        plant_id=plant_id,
        workplace_id=workplace_id,
        job_position_id=job_position_id,
        gender=gender,
    )


@router.post(
    "/employees",
    response_model=EmployeeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_employee_endpoint(
    data: EmployeeCreateRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> EmployeeResponse:
    """
    Vytvoří nový záznam zaměstnance.

    Pokud data.create_user_account=True nebo data.is_equipment_responsible=True
    a zároveň user_id nezadáno, service vytvoří propojený auth User účet.
    Heslo (pokud se vygenerovalo) je vráceno v response.generated_password
    jednorázově — OZO ho předá uživateli, do DB už jde jen Argon2 hash.
    """
    employee, generated_password = await create_employee(
        db, data, current_user.tenant_id, current_user.id
    )
    response = EmployeeResponse.model_validate(employee)
    response.generated_password = generated_password
    return response


# ── CSV import ────────────────────────────────────────────────────────────────
# POZOR: cesty /employees/import/* musí být REGISTROVÁNY DŘÍV než
# /employees/{employee_id} — FastAPI matchuje v pořadí, jinak by
# "import" vyhodnotil jako UUID parametr a 422 validace selhala.

@router.get("/employees/import/template")
async def download_import_template(
    current_user: User = Depends(require_role("admin", "ozo", "hr_manager")),  # noqa: ARG001
) -> Response:
    """
    Stáhne vzorový CSV soubor s hlavičkou a jedním řádkem vzoru.
    OZO ho otevře v Excelu, vyplní data a nahraje přes POST /employees/import.
    """
    content = generate_template_csv()
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="zamestnanci_vzor.csv"',
        },
    )


@router.post("/employees/import", response_model=ImportResponse)
async def import_employees(
    file: UploadFile = File(...),
    current_user: User = Depends(require_role("admin", "ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> ImportResponse:
    """
    Hromadný import zaměstnanců z CSV souboru.

    Formát: UTF-8, delimiter "," nebo ";" (auto-detect). Hlavička musí
    obsahovat sloupce dle GET /employees/import/template.

    Partial import: řádky které selžou na validaci nebo DB constraint
    se přeskočí (savepoint rollback), ostatní se commitnou. Response
    obsahuje rich report — OZO vidí přesně které řádky selhaly a proč.

    Vygenerovaná hesla (pro řádky s create_user_account=true) jsou
    vrácena jen v této response — OZO je musí zapsat hned.
    """
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Očekávám soubor .csv",
        )

    raw = await file.read()
    if len(raw) > 5 * 1024 * 1024:  # 5 MB limit
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Soubor je příliš velký (max 5 MB)",
        )

    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            content = raw.decode("cp1250")  # starý Excel/Windows CZ export
        except UnicodeDecodeError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    f"Nepodařilo se dekódovat soubor ({e.__class__.__name__}). "
                    "Uložte jako UTF-8."
                ),
            ) from None

    result = await import_from_csv(db, content, current_user.tenant_id, current_user.id)

    return ImportResponse(
        total_rows=result.total_rows,
        created_count=len(result.created),
        error_count=len(result.errors),
        created=[
            ImportSuccessRow(
                row=r.row,
                employee_id=r.employee_id,
                full_name=r.full_name,
                email=r.email,
                generated_password=r.generated_password,
            )
            for r in result.created
        ],
        errors=[
            ImportErrorRow(row=e.row, error=e.error, raw=e.raw)
            for e in result.errors
        ],
    )


# ── Detail / update / delete (musí být PO /import/* kvůli route matchingu) ──

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
    current_user: User = Depends(require_role("ozo", "hr_manager")),
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
    current_user: User = Depends(require_role("ozo", "hr_manager")),
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
