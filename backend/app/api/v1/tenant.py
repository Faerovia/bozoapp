import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.permissions import require_role
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.tenant import TenantResponse, TenantUpdateRequest

router = APIRouter()


@router.get("/tenant", response_model=TenantResponse)
async def get_tenant(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Tenant:
    """Vrátí info o aktuálním tenantu. Přístup: všechny role."""
    result = await db.execute(
        select(Tenant).where(Tenant.id == current_user.tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant nenalezen")
    return tenant


@router.patch("/tenant", response_model=TenantResponse)
async def update_tenant(
    data: TenantUpdateRequest,
    current_user: User = Depends(require_role("ozo")),
    db: AsyncSession = Depends(get_db),
) -> Tenant:
    """Aktualizuje název tenantu. Přístup: pouze ozo."""
    result = await db.execute(
        select(Tenant).where(Tenant.id == current_user.tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant nenalezen")

    if data.name is not None:
        tenant.name = data.name
        # Aktualizuj slug dle nového názvu
        slug = data.name.lower().strip()
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"[\s_-]+", "-", slug)
        tenant.slug = slug[:100]

    await db.flush()
    return tenant
