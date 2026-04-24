import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_role
from app.models.job_position import CATEGORY_DEFAULT_EXAM_MONTHS, JobPosition
from app.models.risk_factor_assessment import RiskFactorAssessment
from app.models.user import User
from app.models.workplace import Plant, Workplace
from app.schemas.job_positions import (
    JobPositionCreateRequest,
    JobPositionResponse,
    JobPositionUpdateRequest,
)
from app.services.job_positions import (
    create_job_position,
    get_job_position_by_id,
    get_job_positions,
    update_job_position,
)

router = APIRouter()


async def _position_to_response(
    db: AsyncSession, jp: JobPosition
) -> dict[str, Any]:
    """Obohacení o workplace_name/plant_name + effective_category z RFA."""
    wp_row = (await db.execute(
        select(Workplace, Plant)
        .join(Plant, Workplace.plant_id == Plant.id)
        .where(Workplace.id == jp.workplace_id)
    )).first()
    workplace_name: str | None = None
    plant_id: uuid.UUID | None = None
    plant_name: str | None = None
    if wp_row is not None:
        wp_obj, plant_obj = wp_row
        workplace_name = wp_obj.name
        plant_id = plant_obj.id
        plant_name = plant_obj.name

    # Effective category: ruční override > RFA.category_proposed > None
    effective_category: str | None = jp.work_category
    effective_exam_period: int | None = jp.medical_exam_period_months

    if effective_category is None:
        rfa_res = await db.execute(
            select(RiskFactorAssessment).where(
                RiskFactorAssessment.job_position_id == jp.id
            )
        )
        rfa = rfa_res.scalar_one_or_none()
        if rfa is not None:
            effective_category = rfa.category_proposed

    if effective_exam_period is None and effective_category is not None:
        effective_exam_period = CATEGORY_DEFAULT_EXAM_MONTHS.get(effective_category)

    return {
        "id": jp.id,
        "tenant_id": jp.tenant_id,
        "workplace_id": jp.workplace_id,
        "workplace_name": workplace_name,
        "plant_id": plant_id,
        "plant_name": plant_name,
        "name": jp.name,
        "description": jp.description,
        "work_category": jp.work_category,
        "effective_category": effective_category,
        "medical_exam_period_months": jp.medical_exam_period_months,
        "effective_exam_period_months": effective_exam_period,
        "notes": jp.notes,
        "status": jp.status,
        "created_by": jp.created_by,
    }


@router.get("/job-positions", response_model=list[JobPositionResponse])
async def list_job_positions(
    jp_status: str | None = Query(None, pattern="^(active|archived)$"),
    work_category: str | None = Query(None, pattern="^(1|2|2R|3|4)$"),
    workplace_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(require_role("ozo", "hr_manager", "employee")),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    positions = await get_job_positions(
        db, current_user.tenant_id,
        status=jp_status, work_category=work_category, workplace_id=workplace_id,
    )
    return [await _position_to_response(db, jp) for jp in positions]


@router.post(
    "/job-positions",
    response_model=JobPositionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_job_position_endpoint(
    data: JobPositionCreateRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    jp = await create_job_position(db, data, current_user.tenant_id, current_user.id)
    return await _position_to_response(db, jp)


@router.get("/job-positions/{jp_id}", response_model=JobPositionResponse)
async def get_job_position(
    jp_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager", "employee")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    jp = await get_job_position_by_id(db, jp_id, current_user.tenant_id)
    if jp is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pozice nenalezena")
    return await _position_to_response(db, jp)


@router.patch("/job-positions/{jp_id}", response_model=JobPositionResponse)
async def update_job_position_endpoint(
    jp_id: uuid.UUID,
    data: JobPositionUpdateRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    jp = await get_job_position_by_id(db, jp_id, current_user.tenant_id)
    if jp is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pozice nenalezena")
    updated = await update_job_position(db, jp, data)
    return await _position_to_response(db, updated)


@router.delete("/job-positions/{jp_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_job_position(
    jp_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Archivuje pracovní pozici (status=archived).
    Existující zaměstnanci s touto pozicí nejsou ovlivněni (FK ON DELETE SET NULL).
    """
    jp = await get_job_position_by_id(db, jp_id, current_user.tenant_id)
    if jp is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pozice nenalezena")
    jp.status = "archived"
    await db.flush()
