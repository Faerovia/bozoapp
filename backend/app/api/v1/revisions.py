import uuid
from datetime import date
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.permissions import require_role
from app.core.storage import (
    MAX_REVISION_FILE_BYTES,
    delete_file,
    read_file,
    save_revision_record_file,
)
from app.models.employee import Employee
from app.models.revision import Revision
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.revisions import (
    CalendarItem,
    EmployeeResponsibilitiesResponse,
    EmployeeResponsibilitiesUpdate,
    RevisionCreateRequest,
    RevisionRecordResponse,
    RevisionResponse,
    RevisionUpdateRequest,
)
from app.services.export_pdf import generate_revisions_pdf
from app.services.revisions import (
    add_revision_record,
    create_revision,
    generate_qr_png,
    get_calendar_items,
    get_employee_responsibilities,
    get_revision_by_id,
    get_revision_by_qr_token,
    get_revision_record_by_id,
    get_revision_records,
    get_revisions,
    revision_to_response_dict,
    set_employee_responsibilities,
    update_revision,
)

router = APIRouter()


# ── Kalendář (agregovaný pohled) ──────────────────────────────────────────────

@router.get("/calendar", response_model=list[CalendarItem])
async def get_calendar(
    days_ahead: int = Query(90, ge=1, le=365),
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> list[CalendarItem]:
    return await get_calendar_items(db, current_user.tenant_id, days_ahead=days_ahead)


# ── Revize CRUD ───────────────────────────────────────────────────────────────

@router.get("/revisions", response_model=list[RevisionResponse])
async def list_revisions(
    revision_type: str | None = Query(None),
    device_type: str | None = Query(None),
    plant_id: uuid.UUID | None = Query(None),
    status_filter: str | None = Query(None, alias="status", pattern="^(active|archived)$"),
    due_status: str | None = Query(None, pattern="^(no_schedule|ok|due_soon|overdue)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Vrátí zařízení. Přístup: všechny role. Filtry: typ, provozovna, status, due_status."""
    revisions = await get_revisions(
        db, current_user.tenant_id,
        revision_type=revision_type,
        status=status_filter,
        due_status=due_status,
        plant_id=plant_id,
        device_type=device_type,
    )
    return [await revision_to_response_dict(db, r) for r in revisions]


@router.post("/revisions", response_model=RevisionResponse, status_code=status.HTTP_201_CREATED)
async def create_revision_endpoint(
    data: RevisionCreateRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    revision = await create_revision(db, data, current_user.tenant_id, current_user.id)
    return await revision_to_response_dict(db, revision)


@router.get("/revisions/export/pdf")
async def export_revisions_pdf(
    revision_type: str | None = Query(None),
    due_status: str | None = Query(None, pattern="^(no_schedule|ok|due_soon|overdue)$"),
    download: bool = Query(False),
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    tenant = (
        await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    ).scalar_one_or_none()
    tenant_name = tenant.name if tenant else str(current_user.tenant_id)

    records = await get_revisions(
        db, current_user.tenant_id, revision_type=revision_type, due_status=due_status
    )
    pdf_bytes = generate_revisions_pdf(records, tenant_name)

    disposition = "attachment" if download else "inline"
    filename = f"harmonogram_revizi_{date.today()}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


# ── QR scan landing (po naskenu QR) ─────────────────────────────────────────

@router.get("/revisions/qr/{qr_token}", response_model=RevisionResponse)
async def revision_by_qr(
    qr_token: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Vrátí zařízení podle QR tokenu. Dostupné pro všechny přihlášené uživatele
    daného tenantu — ověření pravomoci zaznamenat revizi se děje v POST /records."""
    revision = await get_revision_by_qr_token(db, qr_token, current_user.tenant_id)
    if revision is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Zařízení nenalezeno"
        )
    return await revision_to_response_dict(db, revision)


@router.get("/revisions/{revision_id}", response_model=RevisionResponse)
async def get_revision(
    revision_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    revision = await get_revision_by_id(db, revision_id, current_user.tenant_id)
    if revision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Revize nenalezena")
    return await revision_to_response_dict(db, revision)


@router.patch("/revisions/{revision_id}", response_model=RevisionResponse)
async def update_revision_endpoint(
    revision_id: uuid.UUID,
    data: RevisionUpdateRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    revision = await get_revision_by_id(db, revision_id, current_user.tenant_id)
    if revision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Revize nenalezena")
    updated = await update_revision(db, revision, data)
    return await revision_to_response_dict(db, updated)


@router.delete("/revisions/{revision_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_revision(
    revision_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> None:
    revision = await get_revision_by_id(db, revision_id, current_user.tenant_id)
    if revision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Revize nenalezena")
    revision.status = "archived"
    await db.flush()


# ── QR kód (PNG) ─────────────────────────────────────────────────────────────

@router.get("/revisions/{revision_id}/qr.png")
async def get_revision_qr(
    revision_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Vrátí PNG s QR kódem odkazujícím na /devices/{qr_token}/record.
    URL je relativní — app frontend si doplní origin sám při tisku."""
    revision = await get_revision_by_id(db, revision_id, current_user.tenant_id)
    if revision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Revize nenalezena")

    settings = get_settings()
    base = settings.app_public_url.rstrip("/")
    target_url = f"{base}/devices/{revision.qr_token}/record"
    png_bytes = generate_qr_png(target_url)

    filename = f"qr_{revision.device_code or revision.id.hex[:8]}.png"
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


# ── Revision records (timeline) ──────────────────────────────────────────────

@router.get(
    "/revisions/{revision_id}/records",
    response_model=list[RevisionRecordResponse],
)
async def list_revision_records(
    revision_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Any]:
    revision = await get_revision_by_id(db, revision_id, current_user.tenant_id)
    if revision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Revize nenalezena")
    return await get_revision_records(db, revision_id, current_user.tenant_id)


async def _check_can_record(
    db: AsyncSession,
    current_user: User,
    revision: Revision,
) -> None:
    """
    Povolen record pro:
    - OZO / HR / admin (globálně)
    - zaměstnanec s aktivním EmployeePlantResponsibility pro provozovnu zařízení
    """
    if current_user.role in ("admin", "ozo", "hr_manager"):
        return

    if revision.plant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nelze zaznamenat revizi — zařízení nemá přiřazenou provozovnu",
        )

    # Najdi Employee svázaný s tímto userem
    emp_result = await db.execute(
        select(Employee).where(Employee.user_id == current_user.id)
    )
    employee = emp_result.scalar_one_or_none()
    if employee is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Zaměstnanec nenalezen")

    resp_plant_ids = await get_employee_responsibilities(
        db, employee.id, current_user.tenant_id
    )
    if revision.plant_id not in resp_plant_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nemáte oprávnění zaznamenat revizi pro tuto provozovnu",
        )


@router.post(
    "/revisions/{revision_id}/records",
    response_model=RevisionRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_revision_record(
    revision_id: uuid.UUID,
    performed_at: date = Form(...),
    technician_name: str | None = Form(None),
    notes: str | None = Form(None),
    file: UploadFile | None = File(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Zaznamená provedenou revizi. Lze volat:
    - OZO/HR z admin UI (manuálně zadat datum + upload PDF/obr)
    - zaměstnancem se zodpovědností za danou provozovnu (po QR scanu nebo přes UI)
    """
    revision = await get_revision_by_id(db, revision_id, current_user.tenant_id)
    if revision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Revize nenalezena")

    await _check_can_record(db, current_user, revision)

    pdf_path: str | None = None
    image_path: str | None = None

    if file is not None and file.filename:
        content = await file.read()
        if len(content) > MAX_REVISION_FILE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Soubor je větší než {MAX_REVISION_FILE_BYTES // 1024 // 1024} MB",
            )
        # Rezervujeme UUID pro cestu souboru předem — ať nekolíznou při pádu
        record_uid = uuid.uuid4()
        try:
            pdf_path, image_path = save_revision_record_file(
                current_user.tenant_id,
                revision.id,
                record_uid,
                content,
                file.filename,
            )
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
            ) from e

    record = await add_revision_record(
        db,
        revision=revision,
        performed_at=performed_at,
        technician_name=technician_name,
        notes=notes,
        created_by=current_user.id,
        pdf_path=pdf_path,
        image_path=image_path,
    )
    return record


@router.get("/revisions/records/{record_id}/file")
async def download_revision_record_file(
    record_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    record = await get_revision_record_by_id(db, record_id, current_user.tenant_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Záznam nenalezen")

    path = record.pdf_path or record.image_path
    if path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Žádná příloha")

    try:
        content = read_file(path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Soubor nenalezen") from e

    # Detekce MIME podle přípony
    if path.endswith(".pdf"):
        mime = "application/pdf"
    elif path.endswith(".png"):
        mime = "image/png"
    elif path.endswith(".webp"):
        mime = "image/webp"
    elif path.endswith(".heic"):
        mime = "image/heic"
    else:
        mime = "image/jpeg"

    return Response(
        content=content,
        media_type=mime,
        headers={"Content-Disposition": "inline"},
    )


@router.delete(
    "/revisions/records/{record_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_revision_record(
    record_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> None:
    record = await get_revision_record_by_id(db, record_id, current_user.tenant_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Záznam nenalezen")

    delete_file(record.pdf_path)
    delete_file(record.image_path)
    await db.delete(record)
    await db.flush()


# ── Employee responsibilities ────────────────────────────────────────────────

@router.get(
    "/employees/{employee_id}/responsibilities",
    response_model=EmployeeResponsibilitiesResponse,
)
async def get_responsibilities(
    employee_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> EmployeeResponsibilitiesResponse:
    plant_ids = await get_employee_responsibilities(
        db, employee_id, current_user.tenant_id
    )
    return EmployeeResponsibilitiesResponse(
        employee_id=employee_id,
        plant_ids=plant_ids,
    )


@router.put(
    "/employees/{employee_id}/responsibilities",
    response_model=EmployeeResponsibilitiesResponse,
)
async def set_responsibilities(
    employee_id: uuid.UUID,
    data: EmployeeResponsibilitiesUpdate,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> EmployeeResponsibilitiesResponse:
    plant_ids = await set_employee_responsibilities(
        db, employee_id, data.plant_ids, current_user.tenant_id
    )
    return EmployeeResponsibilitiesResponse(
        employee_id=employee_id,
        plant_ids=plant_ids,
    )
