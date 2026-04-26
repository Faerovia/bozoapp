"""
API pro onboarding nového tenanta.

- GET  /onboarding/progress     — checklist + step1 flag + completed flag
- POST /onboarding/complete-step1 — označí krok 1 wizardu jako hotový
                                     (volá frontend po POST /tenant + plant)
- POST /onboarding/finish       — označí onboarding za hotový (manual finish)
- POST /onboarding/dismiss      — skryje checklist navždy
- GET  /onboarding/ares?ico=... — ARES lookup (pomocná pro frontend wizard)

Autorizace: pouze přihlášený OZO/HR aktuálního tenantu.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.permissions import require_role
from app.models.tenant import Tenant
from app.models.user import User
from app.services.ares import AresError, fetch_company_info_async
from app.services.onboarding import compute_progress

router = APIRouter()


class OnboardingItemResponse(BaseModel):
    key: str
    label: str
    done: bool
    href: str | None = None


class OnboardingProgressResponse(BaseModel):
    items: list[OnboardingItemResponse]
    done_count: int
    total_count: int
    percent: int
    step1_completed: bool
    can_finish: bool
    completed: bool
    dismissed: bool


class AresResponse(BaseModel):
    ico: str
    name: str
    dic: str | None = None
    address_street: str | None = None
    address_city: str | None = None
    address_zip: str | None = None
    legal_form: str | None = None


@router.get("/onboarding/progress", response_model=OnboardingProgressResponse)
async def get_progress(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))
    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == user.tenant_id)
    )).scalar_one()
    progress = await compute_progress(db, tenant)
    return OnboardingProgressResponse(
        items=[
            OnboardingItemResponse(
                key=it.key, label=it.label, done=it.done, href=it.href,
            )
            for it in progress.items
        ],
        done_count=progress.done_count,
        total_count=progress.total_count,
        percent=progress.percent,
        step1_completed=progress.step1_completed,
        can_finish=progress.can_finish,
        completed=progress.completed,
        dismissed=progress.dismissed,
    )


@router.post(
    "/onboarding/complete-step1",
    dependencies=[Depends(require_role("ozo", "hr_manager"))],
)
async def complete_step1(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))
    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == user.tenant_id)
    )).scalar_one()
    if tenant.onboarding_step1_completed_at is None:
        tenant.onboarding_step1_completed_at = datetime.now(UTC)
        await db.flush()
    return {"status": "ok"}


@router.post(
    "/onboarding/finish",
    dependencies=[Depends(require_role("ozo", "hr_manager"))],
)
async def finish_onboarding(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))
    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == user.tenant_id)
    )).scalar_one()
    if tenant.onboarding_completed_at is None:
        tenant.onboarding_completed_at = datetime.now(UTC)
        await db.flush()
    return {"status": "completed"}


@router.post(
    "/onboarding/dismiss",
    dependencies=[Depends(require_role("ozo", "hr_manager"))],
)
async def dismiss_onboarding(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))
    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == user.tenant_id)
    )).scalar_one()
    tenant.onboarding_dismissed = True
    if tenant.onboarding_completed_at is None:
        tenant.onboarding_completed_at = datetime.now(UTC)
    await db.flush()
    return {"status": "dismissed"}


@router.get("/onboarding/ares", response_model=AresResponse)
async def ares_lookup(
    ico: str = Query(..., min_length=1, max_length=20),
    _user: User = Depends(get_current_user),
) -> Any:
    """Ověří IČO v ARES a vrátí strukturovaná data pro frontend wizard."""
    try:
        info = await fetch_company_info_async(ico)
    except AresError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return AresResponse(
        ico=info.ico,
        name=info.name,
        dic=info.dic,
        address_street=info.address_street,
        address_city=info.address_city,
        address_zip=info.address_zip,
        legal_form=info.legal_form,
    )
