"""API pro modul Pravidelné kontroly."""
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_role
from app.models.user import User
from app.models.workplace import Plant
from app.schemas.periodic_checks import (
    PeriodicCheckCreateRequest,
    PeriodicCheckRecordCreateRequest,
    PeriodicCheckRecordResponse,
    PeriodicCheckResponse,
    PeriodicCheckUpdateRequest,
)
from app.services import periodic_checks as svc

router = APIRouter()


def _to_response(check: Any, plant_name: str | None = None) -> PeriodicCheckResponse:
    resp = PeriodicCheckResponse.model_validate(check)
    resp.due_status = check.due_status
    resp.plant_name = plant_name
    return resp


@router.get("/periodic-checks", response_model=list[PeriodicCheckResponse])
async def list_checks_endpoint(
    check_kind: str | None = Query(
        None, pattern="^(sanitation_kit|spill_tray|first_aid_kit)$",
    ),
    check_status: str | None = Query(None, pattern="^(active|archived)$"),
    plant_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(require_role("ozo", "hr_manager", "employee")),
    db: AsyncSession = Depends(get_db),
) -> list[Any]:
    rows = await svc.list_checks(
        db, current_user.tenant_id,
        check_kind=check_kind, status=check_status, plant_id=plant_id,
    )

    plant_ids = {r.plant_id for r in rows if r.plant_id is not None}
    plant_names: dict[uuid.UUID, str] = {}
    if plant_ids:
        plant_rows = (await db.execute(
            select(Plant).where(Plant.id.in_(plant_ids))
        )).scalars().all()
        plant_names = {p.id: p.name for p in plant_rows}

    return [_to_response(r, plant_names.get(r.plant_id) if r.plant_id else None) for r in rows]


@router.post(
    "/periodic-checks",
    response_model=PeriodicCheckResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_check_endpoint(
    data: PeriodicCheckCreateRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    check = await svc.create_check(db, data, current_user.tenant_id, current_user.id)
    return _to_response(check)


@router.get("/periodic-checks/{check_id}", response_model=PeriodicCheckResponse)
async def get_check_endpoint(
    check_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager", "employee")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    check = await svc.get_check(db, check_id, current_user.tenant_id)
    if check is None:
        raise HTTPException(status_code=404, detail="Kontrola nenalezena")
    return _to_response(check)


@router.patch("/periodic-checks/{check_id}", response_model=PeriodicCheckResponse)
async def update_check_endpoint(
    check_id: uuid.UUID,
    data: PeriodicCheckUpdateRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    check = await svc.get_check(db, check_id, current_user.tenant_id)
    if check is None:
        raise HTTPException(status_code=404, detail="Kontrola nenalezena")
    updated = await svc.update_check(db, check, data)
    return _to_response(updated)


@router.delete("/periodic-checks/{check_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_check_endpoint(
    check_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> None:
    check = await svc.get_check(db, check_id, current_user.tenant_id)
    if check is None:
        raise HTTPException(status_code=404, detail="Kontrola nenalezena")
    check.status = "archived"
    await db.flush()


# ── Records ────────────────────────────────────────────────────────────────


@router.get(
    "/periodic-checks/{check_id}/records",
    response_model=list[PeriodicCheckRecordResponse],
)
async def list_records_endpoint(
    check_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager", "employee")),
    db: AsyncSession = Depends(get_db),
) -> list[Any]:
    return await svc.list_records(db, current_user.tenant_id, check_id)


@router.post(
    "/periodic-checks/{check_id}/records",
    response_model=PeriodicCheckRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_record_endpoint(
    check_id: uuid.UUID,
    data: PeriodicCheckRecordCreateRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager", "employee")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    check = await svc.get_check(db, check_id, current_user.tenant_id)
    if check is None:
        raise HTTPException(status_code=404, detail="Kontrola nenalezena")
    return await svc.create_record(
        db, data, check=check, tenant_id=current_user.tenant_id,
        created_by=current_user.id,
    )
