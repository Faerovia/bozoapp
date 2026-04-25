"""
Platform admin endpoints — cross-tenant správa. Přístup: is_platform_admin=True.

Endpointy:
- POST   /admin/tenants              — vytvoří tenant + OZO + pošle onboarding email
- GET    /admin/tenants              — list všech tenantů
- GET    /admin/tenants/{id}         — detail
- PATCH  /admin/tenants/{id}         — pozastavit/reaktivovat, měnit jméno

Všechny endpointy vyžadují `require_platform_admin()`. Platform admin bypass
RLS je nastaven v `get_current_user` automaticky pro users s flag.
"""
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_platform_admin
from app.core.rate_limit import limiter  # noqa: F401  — pro budoucí dekorátory
from app.core.security import create_access_token
from app.models.employee import Employee
from app.models.tenant import Tenant
from app.models.training import TrainingAssignment
from app.models.user import User
from app.models.workplace import Workplace
from app.schemas.tenant import TenantResponse
from app.services.admin import (
    create_tenant_with_ozo,
    get_tenant_by_id,
    list_tenants,
    set_tenant_active,
)

router = APIRouter()


class CreateTenantRequest(BaseModel):
    tenant_name: str = Field(..., min_length=2, max_length=255)
    ozo_email: EmailStr
    ozo_full_name: str | None = Field(None, max_length=255)
    # Pokud True, klient (HR/admin firmy) se může do svého tenantu zaregistrovat
    # vlastním loginem. Pokud False, tenant je OZO-only (default).
    external_login_enabled: bool = False


class CreateTenantResponse(BaseModel):
    tenant: TenantResponse
    ozo_user_id: uuid.UUID
    onboarding_email_sent_to: str


class TenantPatchRequest(BaseModel):
    is_active: bool | None = None


@router.post(
    "/admin/tenants",
    response_model=CreateTenantResponse,
    status_code=status.HTTP_201_CREATED,
)
async def admin_create_tenant(
    data: CreateTenantRequest,
    _admin: User = Depends(require_platform_admin()),
    db: AsyncSession = Depends(get_db),
) -> CreateTenantResponse:
    """
    Platform admin vytvoří tenant + prvního OZO uživatele.
    Random heslo + password-reset email → OZO si nastaví heslo sám.
    """
    tenant, ozo = await create_tenant_with_ozo(
        db,
        tenant_name=data.tenant_name,
        ozo_email=data.ozo_email,
        ozo_full_name=data.ozo_full_name,
        external_login_enabled=data.external_login_enabled,
    )
    return CreateTenantResponse(
        tenant=TenantResponse.model_validate(tenant),
        ozo_user_id=ozo.id,
        onboarding_email_sent_to=ozo.email,
    )


@router.get("/admin/tenants", response_model=list[TenantResponse])
async def admin_list_tenants(
    _admin: User = Depends(require_platform_admin()),
    db: AsyncSession = Depends(get_db),
) -> list[TenantResponse]:
    tenants = await list_tenants(db)
    return [TenantResponse.model_validate(t) for t in tenants]


@router.get("/admin/tenants/{tenant_id}", response_model=TenantResponse)
async def admin_get_tenant(
    tenant_id: uuid.UUID,
    _admin: User = Depends(require_platform_admin()),
    db: AsyncSession = Depends(get_db),
) -> TenantResponse:
    tenant = await get_tenant_by_id(db, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant nenalezen")
    return TenantResponse.model_validate(tenant)


@router.patch("/admin/tenants/{tenant_id}", response_model=TenantResponse)
async def admin_update_tenant(
    tenant_id: uuid.UUID,
    data: TenantPatchRequest,
    _admin: User = Depends(require_platform_admin()),
    db: AsyncSession = Depends(get_db),
) -> TenantResponse:
    if data.is_active is not None:
        tenant = await set_tenant_active(db, tenant_id, data.is_active)
    else:
        tenant = await get_tenant_by_id(db, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant nenalezen")
    return TenantResponse.model_validate(tenant)


# ── Tenant overview pro billing a operativní rozhodnutí ─────────────────────


class TenantOverviewItem(BaseModel):
    id: uuid.UUID
    name: str
    is_active: bool
    created_at: datetime
    employee_count: int          # aktivní zaměstnanci (= "zákazníci" pro billing)
    user_count: int              # aktivní auth uživatelé
    workplace_count: int         # aktivní pracoviště
    training_assignment_count: int  # přiřazená školení (aktivita)


class TenantOverviewResponse(BaseModel):
    total_tenants: int
    total_employees: int
    tenants: list[TenantOverviewItem]


@router.get("/admin/tenant-overview", response_model=TenantOverviewResponse)
async def admin_tenant_overview(
    _admin: User = Depends(require_platform_admin()),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Přehled všech tenantů s počty aktivních zaměstnanců, uživatelů, pracovišť
    a přiřazených školení. Slouží jako základ pro pricing a operativní pohled.
    """
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))

    # Vynech systémový __PLATFORM__ tenant (kontejner pro admin účet,
    # není zákaznický a nemá být v billing přehledu)
    tenants = (await db.execute(
        select(Tenant)
        .where(Tenant.name != "__PLATFORM__")
        .order_by(Tenant.created_at.desc())
    )).scalars().all()

    employee_counts: dict[uuid.UUID, int] = {
        tid: int(cnt) for tid, cnt in (await db.execute(
            select(Employee.tenant_id, func.count())
            .where(Employee.status == "active")
            .group_by(Employee.tenant_id)
        )).all()
    }
    user_counts: dict[uuid.UUID, int] = {
        tid: int(cnt) for tid, cnt in (await db.execute(
            select(User.tenant_id, func.count())
            .where(User.is_active.is_(True))
            .group_by(User.tenant_id)
        )).all()
    }
    workplace_counts: dict[uuid.UUID, int] = {
        tid: int(cnt) for tid, cnt in (await db.execute(
            select(Workplace.tenant_id, func.count())
            .where(Workplace.status == "active")
            .group_by(Workplace.tenant_id)
        )).all()
    }
    assignment_counts: dict[uuid.UUID, int] = {
        tid: int(cnt) for tid, cnt in (await db.execute(
            select(TrainingAssignment.tenant_id, func.count())
            .group_by(TrainingAssignment.tenant_id)
        )).all()
    }

    items = [
        TenantOverviewItem(
            id=t.id,
            name=t.name,
            is_active=getattr(t, "is_active", True),
            created_at=t.created_at,
            employee_count=employee_counts.get(t.id, 0),
            user_count=user_counts.get(t.id, 0),
            workplace_count=workplace_counts.get(t.id, 0),
            training_assignment_count=assignment_counts.get(t.id, 0),
        )
        for t in tenants
    ]
    return TenantOverviewResponse(
        total_tenants=len(items),
        total_employees=sum(i.employee_count for i in items),
        tenants=items,
    )


# ── Impersonate / přepnutí do tenantu ────────────────────────────────────────


class ImpersonateRequest(BaseModel):
    tenant_id: uuid.UUID


class ImpersonateResponse(BaseModel):
    access_token: str
    tenant_id: uuid.UUID
    tenant_name: str


@router.post("/admin/impersonate-tenant", response_model=ImpersonateResponse)
async def admin_impersonate_tenant(
    payload: ImpersonateRequest,
    admin: User = Depends(require_platform_admin()),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Vydá access token, který platform admina pustí do daného tenantu.
    Frontend by ho použil v Bearer headeru pro běžné endpointy a viděl by
    tenant data tak, jak je vidí jeho OZO.
    """
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))
    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == payload.tenant_id)
    )).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant nenalezen",
        )
    access_token = create_access_token(admin.id, tenant.id, "admin")
    return ImpersonateResponse(
        access_token=access_token,
        tenant_id=tenant.id,
        tenant_name=tenant.name,
    )
