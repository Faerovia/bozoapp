import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.permissions import require_role
from app.models.user import User
from app.schemas.trainings import (
    TrainingCreateRequest,
    TrainingResponse,
    TrainingUpdateRequest,
)
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

    Přístup:
    - employee: vidí pouze vlastní záznamy (employee_id filtr je vynucený)
    - ozo / manager: vidí všechny záznamy tenantu, volitelně filtrovat po employee_id

    Filtry: ?employee_id=, ?training_type=, ?status=active|archived,
            ?validity_status=valid|expiring_soon|expired|no_expiry
    """
    # Employee smí vidět jen vlastní záznamy
    if current_user.role == "employee":
        employee_id = current_user.id

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
    """
    Zaznamená absolvování školení zaměstnancem.
    Přístup: ozo, manager.
    """
    return await create_training(db, data, current_user.tenant_id, current_user.id)


@router.get("/trainings/{training_id}", response_model=TrainingResponse)
async def get_training(
    training_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> object:
    """
    Vrátí detail záznamu o školení.

    Přístup:
    - employee: pouze pokud je záznam jejich vlastní
    - ozo / manager: jakýkoli záznam tenantu
    """
    training = await get_training_by_id(db, training_id, current_user.tenant_id)
    if training is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Záznam nenalezen")

    if current_user.role == "employee" and training.employee_id != current_user.id:
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
    """
    Archivuje záznam o školení (status=archived).
    Fyzické smazání není povoleno – záznamy jsou součástí BOZP dokumentace.
    """
    training = await get_training_by_id(db, training_id, current_user.tenant_id)
    if training is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Záznam nenalezen")
    training.status = "archived"
    await db.flush()
