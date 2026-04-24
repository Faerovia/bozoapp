import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.validation import assert_in_tenant
from app.models.risk import Risk
from app.models.user import User
from app.schemas.risks import RiskCreateRequest, RiskUpdateRequest


async def get_risks(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    status: str | None = None,
) -> list[Risk]:
    query = select(Risk).where(Risk.tenant_id == tenant_id)
    if status:
        query = query.where(Risk.status == status)
    query = query.order_by(Risk.created_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_risk_by_id(
    db: AsyncSession, risk_id: uuid.UUID, tenant_id: uuid.UUID
) -> Risk | None:
    result = await db.execute(
        select(Risk).where(Risk.id == risk_id, Risk.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


async def create_risk(
    db: AsyncSession,
    data: RiskCreateRequest,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
) -> Risk:
    if data.responsible_user_id is not None:
        await assert_in_tenant(
            db, User, data.responsible_user_id, tenant_id, field_name="responsible_user_id"
        )
    risk = Risk(
        tenant_id=tenant_id,
        created_by=created_by,
        title=data.title,
        description=data.description,
        location=data.location,
        activity=data.activity,
        hazard_type=data.hazard_type,
        probability=data.probability,
        severity=data.severity,
        control_measures=data.control_measures,
        residual_probability=data.residual_probability,
        residual_severity=data.residual_severity,
        responsible_user_id=data.responsible_user_id,
        review_date=data.review_date,
    )
    db.add(risk)
    await db.flush()
    return risk


async def update_risk(
    db: AsyncSession, risk: Risk, data: RiskUpdateRequest
) -> Risk:
    update_fields = data.model_dump(exclude_unset=True)
    if (
        "responsible_user_id" in update_fields
        and update_fields["responsible_user_id"] is not None
    ):
        await assert_in_tenant(
            db, User, update_fields["responsible_user_id"], risk.tenant_id,
            field_name="responsible_user_id",
        )
    for field, value in update_fields.items():
        setattr(risk, field, value)
    await db.flush()
    return risk
