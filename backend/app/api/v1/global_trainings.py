"""
API pro globální (marketplace) školení.

Endpointy:
  - Platform admin:
      POST   /admin/global-trainings           — vytvoří globální šablonu
      GET    /admin/global-trainings           — list všech globálních šablon
      PATCH  /admin/global-trainings/{id}      — edituje
      DELETE /admin/global-trainings/{id}      — smaže

  - Tenant uživatel (OZO/HR):
      GET    /global-trainings/marketplace     — list dostupných šablon
      POST   /global-trainings/{id}/activate   — vytvoří kopii šablony do tenantu
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_platform_admin, require_role
from app.models.training import Training
from app.models.user import User

router = APIRouter()


# ── Schémata ────────────────────────────────────────────────────────────────


class GlobalTrainingCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    training_type: str = Field(..., pattern="^(bozp|po|other)$")
    trainer_kind: str = Field("employer", pattern="^(ozo_bozp|ozo_po|employer)$")
    valid_months: int = Field(..., ge=1, le=120)
    notes: str | None = None
    test_questions: list[dict[str, Any]] | None = None
    pass_percentage: int | None = Field(None, ge=0, le=100)


class GlobalTrainingUpdateRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    training_type: str | None = Field(None, pattern="^(bozp|po|other)$")
    trainer_kind: str | None = Field(None, pattern="^(ozo_bozp|ozo_po|employer)$")
    valid_months: int | None = Field(None, ge=1, le=120)
    notes: str | None = None
    test_questions: list[dict[str, Any]] | None = None
    pass_percentage: int | None = Field(None, ge=0, le=100)


class GlobalTrainingResponse(BaseModel):
    id: uuid.UUID
    title: str
    training_type: str
    trainer_kind: str
    valid_months: int
    notes: str | None
    has_test: bool
    question_count: int
    pass_percentage: int | None
    is_global: bool
    created_at: datetime
    created_by: uuid.UUID

    model_config = {"from_attributes": True}


# ── Admin: CRUD ──────────────────────────────────────────────────────────────


@router.get("/admin/global-trainings", response_model=list[GlobalTrainingResponse])
async def admin_list_global_trainings(
    _admin: User = Depends(require_platform_admin()),
    db: AsyncSession = Depends(get_db),
) -> list[Any]:
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))
    rows = (await db.execute(
        select(Training)
        .where(Training.is_global.is_(True))
        .order_by(Training.created_at.desc())
    )).scalars().all()
    return list(rows)


@router.post(
    "/admin/global-trainings",
    response_model=GlobalTrainingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def admin_create_global_training(
    data: GlobalTrainingCreateRequest,
    admin: User = Depends(require_platform_admin()),
    db: AsyncSession = Depends(get_db),
) -> Any:
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))
    training = Training(
        tenant_id=None,
        is_global=True,
        title=data.title,
        training_type=data.training_type,
        trainer_kind=data.trainer_kind,
        valid_months=data.valid_months,
        notes=data.notes,
        test_questions=data.test_questions,
        pass_percentage=data.pass_percentage,
        created_by=admin.id,
    )
    db.add(training)
    await db.flush()
    return training


@router.patch(
    "/admin/global-trainings/{training_id}",
    response_model=GlobalTrainingResponse,
)
async def admin_update_global_training(
    training_id: uuid.UUID,
    data: GlobalTrainingUpdateRequest,
    _admin: User = Depends(require_platform_admin()),
    db: AsyncSession = Depends(get_db),
) -> Any:
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))
    training = (await db.execute(
        select(Training).where(
            Training.id == training_id, Training.is_global.is_(True),
        )
    )).scalar_one_or_none()
    if training is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Globální školení nenalezeno",
        )
    update_fields = data.model_dump(exclude_unset=True)
    for k, v in update_fields.items():
        setattr(training, k, v)
    await db.flush()
    return training


@router.delete(
    "/admin/global-trainings/{training_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def admin_delete_global_training(
    training_id: uuid.UUID,
    _admin: User = Depends(require_platform_admin()),
    db: AsyncSession = Depends(get_db),
) -> None:
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))
    training = (await db.execute(
        select(Training).where(
            Training.id == training_id, Training.is_global.is_(True),
        )
    )).scalar_one_or_none()
    if training is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Globální školení nenalezeno",
        )
    await db.delete(training)
    await db.flush()


# ── Tenant: marketplace + aktivace ──────────────────────────────────────────


@router.get(
    "/global-trainings/marketplace",
    response_model=list[GlobalTrainingResponse],
)
async def list_marketplace(
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> list[Any]:
    """Seznam všech aktivních globálních šablon dostupných k aktivaci."""
    _ = current_user
    rows = (await db.execute(
        select(Training)
        .where(Training.is_global.is_(True))
        .order_by(Training.created_at.desc())
    )).scalars().all()
    return list(rows)


class ActivateResponse(BaseModel):
    training_id: uuid.UUID
    source_id: uuid.UUID


@router.post(
    "/global-trainings/{training_id}/activate",
    response_model=ActivateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def activate_global_training(
    training_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> ActivateResponse:
    """
    Aktivuje globální školení v aktuálním tenantu — vytvoří jeho kopii s
    tenant_id=current_user.tenant_id a global_source_id=originál.

    Pokud už existuje aktivace stejného source v tenantu, vrátí stávající
    (idempotentní).
    """
    # Najdi globální šablonu
    src = (await db.execute(
        select(Training).where(
            Training.id == training_id, Training.is_global.is_(True),
        )
    )).scalar_one_or_none()
    if src is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Globální školení nenalezeno",
        )

    # Existuje už aktivace v tenantu?
    existing = (await db.execute(
        select(Training).where(
            Training.tenant_id == current_user.tenant_id,
            Training.global_source_id == src.id,
        )
    )).scalar_one_or_none()
    if existing is not None:
        return ActivateResponse(training_id=existing.id, source_id=src.id)

    # Vytvoř kopii do tenantu
    copy = Training(
        tenant_id=current_user.tenant_id,
        is_global=False,
        global_source_id=src.id,
        title=src.title,
        training_type=src.training_type,
        trainer_kind=src.trainer_kind,
        valid_months=src.valid_months,
        content_pdf_path=src.content_pdf_path,
        test_questions=src.test_questions,
        pass_percentage=src.pass_percentage,
        notes=src.notes,
        created_by=current_user.id,
        created_at=datetime.now(UTC),
    )
    db.add(copy)
    await db.flush()
    return ActivateResponse(training_id=copy.id, source_id=src.id)
