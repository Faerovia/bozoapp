import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_role
from app.models.user import User
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


@router.get("/job-positions", response_model=list[JobPositionResponse])
async def list_job_positions(
    jp_status: str | None = Query(None, pattern="^(active|archived)$"),
    work_category: str | None = Query(None, pattern="^(1|2|2R|3|4)$"),
    current_user: User = Depends(require_role("ozo", "manager", "employee")),
    db: AsyncSession = Depends(get_db),
) -> list:
    return await get_job_positions(
        db, current_user.tenant_id, status=jp_status, work_category=work_category
    )


@router.post(
    "/job-positions",
    response_model=JobPositionResponse,
    status_code=status.HTTP_201_CREATED,
)  # noqa: E501
async def create_job_position_endpoint(
    data: JobPositionCreateRequest,
    current_user: User = Depends(require_role("ozo", "manager")),
    db: AsyncSession = Depends(get_db),
) -> object:
    return await create_job_position(db, data, current_user.tenant_id, current_user.id)


@router.get("/job-positions/{jp_id}", response_model=JobPositionResponse)
async def get_job_position(
    jp_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "manager", "employee")),
    db: AsyncSession = Depends(get_db),
) -> object:
    jp = await get_job_position_by_id(db, jp_id, current_user.tenant_id)
    if jp is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pozice nenalezena")
    return jp


@router.patch("/job-positions/{jp_id}", response_model=JobPositionResponse)
async def update_job_position_endpoint(
    jp_id: uuid.UUID,
    data: JobPositionUpdateRequest,
    current_user: User = Depends(require_role("ozo", "manager")),
    db: AsyncSession = Depends(get_db),
) -> object:
    jp = await get_job_position_by_id(db, jp_id, current_user.tenant_id)
    if jp is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pozice nenalezena")
    return await update_job_position(db, jp, data)


@router.delete("/job-positions/{jp_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_job_position(
    jp_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "manager")),
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
