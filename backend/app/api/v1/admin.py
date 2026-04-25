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

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_platform_admin
from app.core.rate_limit import limiter  # noqa: F401  — pro budoucí dekorátory
from app.models.user import User
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
