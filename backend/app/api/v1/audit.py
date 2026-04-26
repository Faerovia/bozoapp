"""Audit log API — read-only **pouze pro platform admina**.

Žádné write endpointy — audit_log je append-only (zapisuje SQLAlchemy
event listener v app.core.audit). Platform admin vidí napříč všemi tenanty
(přístup k cross-tenant audit trailu pro compliance / incident response);
běžný OZO ani HR manager k auditu přístup nemají.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_platform_admin
from app.models.audit_log import AuditLog
from app.models.user import User

router = APIRouter()


class AuditLogItem(BaseModel):
    id: int
    tenant_id: uuid.UUID
    user_id: uuid.UUID | None
    user_email: str | None = None
    user_full_name: str | None = None
    action: str
    resource_type: str
    resource_id: str | None
    ip_address: str | None
    created_at: datetime
    has_diff: bool

    model_config = {"from_attributes": True}


class AuditLogDetail(AuditLogItem):
    old_values: dict[str, Any] | None
    new_values: dict[str, Any] | None
    user_agent: str | None


@router.get("/audit", response_model=list[AuditLogItem])
async def list_audit_endpoint(
    action: str | None = Query(None, pattern="^(CREATE|UPDATE|DELETE|VIEW|EXPORT)$"),
    resource_type: str | None = Query(None, max_length=100),
    user_id: uuid.UUID | None = Query(None),
    tenant_id: uuid.UUID | None = Query(
        None, description="Filter by tenant (cross-tenant je default)",
    ),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _current_user: User = Depends(require_platform_admin()),
    db: AsyncSession = Depends(get_db),
) -> list[Any]:
    """Vrátí poslední audit log entries napříč všemi tenanty (platform admin)."""
    # Platform admin musí mít is_platform_admin GUC v DB session pro RLS bypass
    await db.execute(
        text("SELECT set_config('app.is_platform_admin', 'true', true)")
    )
    q = (
        select(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if tenant_id is not None:
        q = q.where(AuditLog.tenant_id == tenant_id)
    if action:
        q = q.where(AuditLog.action == action)
    if resource_type:
        q = q.where(AuditLog.resource_type == resource_type)
    if user_id is not None:
        q = q.where(AuditLog.user_id == user_id)

    rows = list((await db.execute(q)).scalars().all())

    # Doplň user info (email, full_name) pro UI
    user_ids = {r.user_id for r in rows if r.user_id is not None}
    user_map: dict[uuid.UUID, User] = {}
    if user_ids:
        u_res = await db.execute(
            select(User).where(User.id.in_(user_ids))
        )
        user_map = {u.id: u for u in u_res.scalars()}

    out = []
    for r in rows:
        u = user_map.get(r.user_id) if r.user_id else None
        item = AuditLogItem(
            id=r.id,
            tenant_id=r.tenant_id,
            user_id=r.user_id,
            user_email=u.email if u else None,
            user_full_name=u.full_name if u else None,
            action=r.action,
            resource_type=r.resource_type,
            resource_id=r.resource_id,
            ip_address=str(r.ip_address) if r.ip_address else None,
            created_at=r.created_at,
            has_diff=bool(r.old_values or r.new_values),
        )
        out.append(item)
    return out


@router.get("/audit/{audit_id}", response_model=AuditLogDetail)
async def get_audit_detail_endpoint(
    audit_id: int,
    _current_user: User = Depends(require_platform_admin()),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Vrátí kompletní audit záznam včetně old_values/new_values pro diff zobrazení."""
    await db.execute(
        text("SELECT set_config('app.is_platform_admin', 'true', true)")
    )
    res = await db.execute(
        select(AuditLog).where(AuditLog.id == audit_id)
    )
    row = res.scalar_one_or_none()
    if row is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Záznam nenalezen")

    user_obj = None
    if row.user_id is not None:
        user_obj = (await db.execute(
            select(User).where(User.id == row.user_id)
        )).scalar_one_or_none()

    return AuditLogDetail(
        id=row.id,
        tenant_id=row.tenant_id,
        user_id=row.user_id,
        user_email=user_obj.email if user_obj else None,
        user_full_name=user_obj.full_name if user_obj else None,
        action=row.action,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        ip_address=str(row.ip_address) if row.ip_address else None,
        created_at=row.created_at,
        has_diff=bool(row.old_values or row.new_values),
        old_values=row.old_values,
        new_values=row.new_values,
        user_agent=row.user_agent,
    )
