"""API pro modul Provozní deníky."""
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.http_utils import content_disposition
from app.core.permissions import require_role
from app.models.user import User
from app.models.workplace import Plant
from app.schemas.operating_logs import (
    DeviceCreateRequest,
    DeviceResponse,
    DeviceUpdateRequest,
    EntryCreateRequest,
    EntryResponse,
)
from app.services import operating_logs as svc
from app.services.revisions import generate_qr_png

router = APIRouter()


def _to_device_response(d: Any, plant_name: str | None = None) -> DeviceResponse:
    resp = DeviceResponse.model_validate(d)
    resp.plant_name = plant_name
    return resp


@router.get("/operating-logs/devices", response_model=list[DeviceResponse])
async def list_devices_endpoint(
    category: str | None = Query(None),
    device_status: str | None = Query(None, pattern="^(active|archived)$"),
    plant_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(require_role("ozo", "hr_manager", "employee")),
    db: AsyncSession = Depends(get_db),
) -> list[Any]:
    rows = await svc.list_devices(
        db, current_user.tenant_id,
        category=category, status=device_status, plant_id=plant_id,
    )
    plant_ids = {r.plant_id for r in rows if r.plant_id is not None}
    plant_names: dict[uuid.UUID, str] = {}
    if plant_ids:
        prows = (await db.execute(
            select(Plant).where(Plant.id.in_(plant_ids))
        )).scalars().all()
        plant_names = {p.id: p.name for p in prows}
    return [
        _to_device_response(r, plant_names.get(r.plant_id) if r.plant_id else None)
        for r in rows
    ]


@router.post(
    "/operating-logs/devices",
    response_model=DeviceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_device_endpoint(
    data: DeviceCreateRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    device = await svc.create_device(db, data, current_user.tenant_id, current_user.id)
    return _to_device_response(device)


@router.get(
    "/operating-logs/devices/{device_id}",
    response_model=DeviceResponse,
)
async def get_device_endpoint(
    device_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager", "employee")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    device = await svc.get_device(db, device_id, current_user.tenant_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Zařízení nenalezeno")
    return _to_device_response(device)


@router.patch(
    "/operating-logs/devices/{device_id}",
    response_model=DeviceResponse,
)
async def update_device_endpoint(
    device_id: uuid.UUID,
    data: DeviceUpdateRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    device = await svc.get_device(db, device_id, current_user.tenant_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Zařízení nenalezeno")
    return _to_device_response(await svc.update_device(db, device, data))


@router.delete(
    "/operating-logs/devices/{device_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def archive_device_endpoint(
    device_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> None:
    device = await svc.get_device(db, device_id, current_user.tenant_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Zařízení nenalezeno")
    device.status = "archived"
    await db.flush()


# ── Entries ───────────────────────────────────────────────────────────────


@router.get(
    "/operating-logs/devices/{device_id}/entries",
    response_model=list[EntryResponse],
)
async def list_entries_endpoint(
    device_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager", "employee")),
    db: AsyncSession = Depends(get_db),
) -> list[Any]:
    return await svc.list_entries(db, current_user.tenant_id, device_id)


@router.post(
    "/operating-logs/devices/{device_id}/entries",
    response_model=EntryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_entry_endpoint(
    device_id: uuid.UUID,
    data: EntryCreateRequest,
    current_user: User = Depends(require_role(
        "ozo", "hr_manager", "employee", "equipment_responsible",
    )),
    db: AsyncSession = Depends(get_db),
) -> Any:
    device = await svc.get_device(db, device_id, current_user.tenant_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Zařízení nenalezeno")
    try:
        return await svc.create_entry(
            db, data, device=device,
            tenant_id=current_user.tenant_id, created_by=current_user.id,
            current_user=current_user,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e),
        ) from e


# ── QR kód + scan endpoint ──────────────────────────────────────────────────


@router.get("/operating-logs/devices/{device_id}/qr.png")
async def get_device_qr_png(
    device_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """PNG s QR kódem odkazujícím na /devices/{qr_token}/operating-log."""
    device = await svc.get_device(db, device_id, current_user.tenant_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Zařízení nenalezeno")
    settings = get_settings()
    base = getattr(settings, "app_public_url", "").rstrip("/") or ""
    target_url = f"{base}/devices/{device.qr_token}/operating-log"
    png_bytes = generate_qr_png(target_url)
    filename = f"qr_oplog_{device.device_code or str(device.id)[:8]}.png"
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Content-Disposition": content_disposition(filename, inline=True)},
    )


@router.get(
    "/operating-logs/qr/{qr_token}",
    response_model=DeviceResponse,
)
async def get_device_by_qr(
    qr_token: str,
    current_user: User = Depends(require_role(
        "ozo", "hr_manager", "employee", "equipment_responsible",
    )),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Vrátí zařízení podle qr_token — pro scan flow z mobilu."""
    device = await svc.get_device_by_qr_token(
        db, qr_token, current_user.tenant_id,
    )
    if device is None:
        raise HTTPException(status_code=404, detail="Zařízení nenalezeno")
    return _to_device_response(device)
