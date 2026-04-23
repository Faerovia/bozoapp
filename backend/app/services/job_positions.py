import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job_position import JobPosition
from app.schemas.job_positions import JobPositionCreateRequest, JobPositionUpdateRequest


async def get_job_positions(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    status: str | None = None,
    work_category: str | None = None,
) -> list[JobPosition]:
    query = (
        select(JobPosition)
        .where(JobPosition.tenant_id == tenant_id)
        .order_by(JobPosition.name)
    )
    if status is not None:
        query = query.where(JobPosition.status == status)
    if work_category is not None:
        query = query.where(JobPosition.work_category == work_category)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_job_position_by_id(
    db: AsyncSession, jp_id: uuid.UUID, tenant_id: uuid.UUID
) -> JobPosition | None:
    result = await db.execute(
        select(JobPosition).where(
            JobPosition.id == jp_id,
            JobPosition.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def create_job_position(
    db: AsyncSession,
    data: JobPositionCreateRequest,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
) -> JobPosition:
    jp = JobPosition(
        tenant_id=tenant_id,
        created_by=created_by,
        **data.model_dump(),
    )
    db.add(jp)
    await db.flush()
    return jp


async def update_job_position(
    db: AsyncSession, jp: JobPosition, data: JobPositionUpdateRequest
) -> JobPosition:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(jp, field, value)
    await db.flush()
    return jp
