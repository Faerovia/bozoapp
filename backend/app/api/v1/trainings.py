import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.permissions import require_role
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.trainings import (
    TrainingCreateRequest,
    TrainingResponse,
    TrainingUpdateRequest,
)
from app.services.employees import get_employee_by_user_id
from app.services.export_pdf import generate_trainings_pdf
from app.services.trainings import (
    create_training,
    get_training_by_id,
    get_trainings,
    update_training,
)

router = APIRouter()


@router.get("/trainings", response_model=list[TrainingResponse])
async def list_trainings(
    employee_id: uuid.UUID | None = Query(None),
    training_type: str | None = Query(None),
    status: str | None = Query(None, pattern="^(active|archived)$"),
    validity_status: str | None = Query(
        None, pattern="^(no_expiry|valid|expiring_soon|expired)$"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list:
    """
    Vrátí záznamy o školeních.
    Employee vidí pouze vlastní záznamy (server-side enforce přes employees.user_id).
    Filtry: ?employee_id=, ?training_type=, ?status=, ?validity_status=
    """
    if current_user.role == "employee":
        emp = await get_employee_by_user_id(db, current_user.id, current_user.tenant_id)
        if emp is None:
            return []
        employee_id = emp.id

    return await get_trainings(
        db,
        current_user.tenant_id,
        employee_id=employee_id,
        training_type=training_type,
        status=status,
        validity_status=validity_status,
    )


@router.post("/trainings", response_model=TrainingResponse, status_code=status.HTTP_201_CREATED)
async def create_training_endpoint(
    data: TrainingCreateRequest,
    current_user: User = Depends(require_role("ozo", "manager")),
    db: AsyncSession = Depends(get_db),
) -> object:
    """Zaznamená absolvování školení zaměstnancem. Přístup: ozo, manager."""
    return await create_training(db, data, current_user.tenant_id, current_user.id)


# DŮLEŽITÉ: /trainings/export/pdf musí být před /trainings/{training_id}
@router.get("/trainings/export/pdf")
async def export_trainings_pdf(
    training_type: str | None = Query(None),
    training_status: str | None = Query(None, pattern="^(active|archived)$"),
    validity_status: str | None = Query(None, pattern="^(no_expiry|valid|expiring_soon|expired)$"),
    download: bool = Query(False),
    current_user: User = Depends(require_role("ozo", "manager")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Exportuje přehled školení jako PDF.
    Filtry: ?training_type=, ?training_status=, ?validity_status=
    """
    tenant = (await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))).scalar_one_or_none()
    tenant_name = tenant.name if tenant else str(current_user.tenant_id)

    records = await get_trainings(
        db, current_user.tenant_id,
        training_type=training_type,
        status=training_status,
        validity_status=validity_status,
    )
    pdf_bytes = generate_trainings_pdf(records, tenant_name)

    disposition = "attachment" if download else "inline"
    filename = f"prehled_skoleni_{date.today()}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


@router.get("/trainings/{training_id}", response_model=TrainingResponse)
async def get_training(
    training_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> object:
    """
    Vrátí detail záznamu o školení.
    Employee může vidět pouze vlastní záznamy.
    """
    training = await get_training_by_id(db, training_id, current_user.tenant_id)
    if training is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Záznam nenalezen")
    if current_user.role == "employee":
        emp = await get_employee_by_user_id(db, current_user.id, current_user.tenant_id)
        if emp is None or training.employee_id != emp.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Přístup odepřen")
    return training


@router.patch("/trainings/{training_id}", response_model=TrainingResponse)
async def update_training_endpoint(
    training_id: uuid.UUID,
    data: TrainingUpdateRequest,
    current_user: User = Depends(require_role("ozo", "manager")),
    db: AsyncSession = Depends(get_db),
) -> object:
    """Aktualizuje záznam o školení. Přístup: ozo, manager."""
    training = await get_training_by_id(db, training_id, current_user.tenant_id)
    if training is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Záznam nenalezen")
    return await update_training(db, training, data)


@router.delete("/trainings/{training_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_training(
    training_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "manager")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Archivuje záznam o školení. Fyzické smazání není povoleno."""
    training = await get_training_by_id(db, training_id, current_user.tenant_id)
    if training is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Záznam nenalezen")
    training.status = "archived"
    await db.flush()
