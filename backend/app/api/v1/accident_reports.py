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
from pydantic import BaseModel as _BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.http_utils import content_disposition
from app.core.permissions import require_role
from app.core.storage import (
    delete_file,
    file_exists,
    read_file,
    save_accident_photo,
    save_accident_signed_document,
)
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.accident_reports import (
    AccidentReportCreateRequest,
    AccidentReportResponse,
    AccidentReportUpdateRequest,
)
from app.services.accident_action import (
    MAX_PHOTOS_PER_ACCIDENT,
    add_photo,
    count_photos,
    ensure_default_item,
    list_action_items,
)
from app.services.accident_pdf import generate_accident_report_pdf
from app.services.accident_reports import (
    complete_risk_review,
    create_accident_report,
    finalize_accident_report,
    get_accident_report_by_id,
    get_accident_reports,
    update_accident_report,
)
from app.services.export_pdf import generate_accident_log_pdf

router = APIRouter()


# DŮLEŽITÉ: /accident-reports/export/pdf musí být před /accident-reports/{report_id}
@router.get("/accident-reports/export/pdf")
async def export_accident_log_pdf_endpoint(
    report_status: str | None = Query(None, pattern="^(draft|final|archived)$"),
    download: bool = Query(False),
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Exportuje knihu úrazů jako PDF (chronologický přehled).
    ?report_status=draft|final|archived  – filtr (výchozí: vše)
    """
    tenant = (
        await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    ).scalar_one_or_none()
    tenant_name = tenant.name if tenant else str(current_user.tenant_id)

    reports = await get_accident_reports(db, current_user.tenant_id, report_status=report_status)
    pdf_bytes = generate_accident_log_pdf(reports, tenant_name)

    filename = f"kniha_urazu_{date.today()}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": content_disposition(filename, inline=not download)},
    )


@router.get("/accident-reports", response_model=list[AccidentReportResponse])
async def list_accident_reports(
    report_status: str | None = Query(None, pattern="^(draft|final|archived)$"),
    risk_review_pending: bool | None = Query(None),
    signed: str | None = Query(None, pattern="^(signed|unsigned)$"),
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> list[Any]:
    """
    Vrátí záznamy o pracovních úrazech.
    Filtry:
    - ?report_status=draft|final|archived
    - ?risk_review_pending=true
    - ?signed=signed|unsigned  — filtr digitálního podpisu (#105)
    Přístup: ozo, manager.
    """
    from app.services.accident_reports import hydrate_signed_count, to_response_dict

    reports = await get_accident_reports(
        db,
        current_user.tenant_id,
        report_status=report_status,
        risk_review_pending=risk_review_pending,
        signed_filter=signed,
    )
    sig_counts = await hydrate_signed_count(db, reports)
    return [to_response_dict(r, sig_counts.get(r.id, 0)) for r in reports]


async def _one_report_response(
    db: AsyncSession, report: Any,
) -> dict[str, Any]:
    """Helper — hydratuje single report s signed_count a vrátí response dict."""
    from app.services.accident_reports import hydrate_signed_count, to_response_dict
    counts = await hydrate_signed_count(db, [report])
    return to_response_dict(report, counts.get(report.id, 0))


@router.post(
    "/accident-reports",
    response_model=AccidentReportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_accident_report_endpoint(
    data: AccidentReportCreateRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> object:
    """Vytvoří nový záznam o úrazu (status=draft). Přístup: ozo, manager."""
    report = await create_accident_report(
        db, data, current_user.tenant_id, current_user.id,
    )
    return await _one_report_response(db, report)


@router.get("/accident-reports/{report_id}", response_model=AccidentReportResponse)
async def get_accident_report(
    report_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> object:
    """Vrátí detail záznamu o úrazu. Přístup: všechny role."""
    report = await get_accident_report_by_id(db, report_id, current_user.tenant_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Záznam nenalezen")
    return await _one_report_response(db, report)


@router.patch("/accident-reports/{report_id}", response_model=AccidentReportResponse)
async def update_accident_report_endpoint(
    report_id: uuid.UUID,
    data: AccidentReportUpdateRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> object:
    """
    Aktualizuje záznam o úrazu.
    Povoleno pouze ve stavu draft – finalizovaný záznam vrátí 422.
    Přístup: ozo, manager.
    """
    report = await get_accident_report_by_id(db, report_id, current_user.tenant_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Záznam nenalezen")
    updated = await update_accident_report(db, report, data)
    return await _one_report_response(db, updated)


@router.post("/accident-reports/{report_id}/finalize", response_model=AccidentReportResponse)
async def finalize_accident_report_endpoint(
    report_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> object:
    """
    Finalizuje záznam (draft → final).
    Automaticky nastaví risk_review_required=True.
    Finální záznam je immutable.
    Přístup: ozo, manager.
    """
    report = await get_accident_report_by_id(db, report_id, current_user.tenant_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Záznam nenalezen")
    finalized = await finalize_accident_report(db, report, created_by=current_user.id)
    return await _one_report_response(db, finalized)


@router.post(
    "/accident-reports/{report_id}/complete-risk-review",
    response_model=AccidentReportResponse,
)
async def complete_risk_review_endpoint(
    report_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo")),
    db: AsyncSession = Depends(get_db),
) -> object:
    """
    Potvrdí, že OZO zkontroloval a případně upravil rizika po úrazu.
    Nastaví risk_review_completed_at na aktuální čas.
    Přístup: pouze ozo (ne manager – revize rizik je odborná činnost OZO).
    """
    report = await get_accident_report_by_id(db, report_id, current_user.tenant_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Záznam nenalezen")
    reviewed = await complete_risk_review(db, report)
    return await _one_report_response(db, reviewed)


@router.get("/accident-reports/{report_id}/pdf")
async def get_accident_report_pdf(
    report_id: uuid.UUID,
    download: bool = Query(
        False,
        description="True = attachment (stáhnout), False = inline (zobrazit v prohlížeči)",  # noqa: E501
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Vygeneruje PDF záznamu o pracovním úrazu.
    ?download=false (výchozí) → inline (zobrazení v prohlížeči/tisk)
    ?download=true            → attachment (stažení souboru)
    Přístup: všechny role.
    """
    report = await get_accident_report_by_id(db, report_id, current_user.tenant_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Záznam nenalezen")

    # Název tenanta pro hlavičku PDF
    # Načteme tenant přes relaci nebo přímý dotaz – zatím použijeme tenant_id jako fallback
    tenant_result = await db.execute(
        select(Tenant).where(Tenant.id == current_user.tenant_id)
    )
    tenant = tenant_result.scalar_one_or_none()
    tenant_name = tenant.name if tenant else str(current_user.tenant_id)

    pdf_bytes = generate_accident_report_pdf(report, tenant_name)

    filename = f"uraz_{report.accident_date}_{report_id}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": content_disposition(filename, inline=not download)},
    )


@router.delete("/accident-reports/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_accident_report(
    report_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Archivuje záznam o úrazu (status=archived).
    Fyzické smazání není povoleno – záznamy jsou součástí BOZP dokumentace.
    """
    report = await get_accident_report_by_id(db, report_id, current_user.tenant_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Záznam nenalezen")
    report.status = "archived"
    await db.flush()


# ── Action plan ──────────────────────────────────────────────────────────────


class ActionItemResponse(_BaseModel):
    id: uuid.UUID
    accident_report_id: uuid.UUID
    title: str
    description: str | None
    status: str
    due_date: date | None
    assigned_to: uuid.UUID | None
    completed_at: Any | None
    is_default: bool
    sort_order: int
    created_by: uuid.UUID

    model_config = {"from_attributes": True}


class ActionItemCreateRequest(_BaseModel):
    title: str
    description: str | None = None
    due_date: date | None = None
    assigned_to: uuid.UUID | None = None


class ActionItemUpdateRequest(_BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    due_date: date | None = None
    assigned_to: uuid.UUID | None = None


class PhotoResponse(_BaseModel):
    id: uuid.UUID
    accident_report_id: uuid.UUID
    photo_path: str
    caption: str | None
    created_by: uuid.UUID

    model_config = {"from_attributes": True}


@router.get(
    "/accident-reports/{report_id}/action-items",
    response_model=list[ActionItemResponse],
)
async def list_action_items_endpoint(
    report_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> list[Any]:
    report = await get_accident_report_by_id(db, report_id, current_user.tenant_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Záznam nenalezen")
    # Idempotentně zaručit default item (pokud byl úraz finalizován dřív, než
    # migrace 028 existovala — vytvoří se na fly při prvním fetchnutí)
    if report.status == "final":
        await ensure_default_item(db, report, current_user.id)
    return await list_action_items(db, report_id, current_user.tenant_id)


@router.post(
    "/accident-reports/{report_id}/action-items",
    response_model=ActionItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_action_item_endpoint(
    report_id: uuid.UUID,
    data: ActionItemCreateRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    from app.services.accident_action import create_action_item
    report = await get_accident_report_by_id(db, report_id, current_user.tenant_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Záznam nenalezen")
    return await create_action_item(
        db, report,
        title=data.title, description=data.description,
        due_date=data.due_date, assigned_to=data.assigned_to,
        created_by=current_user.id,
    )


@router.patch(
    "/accident-action-items/{item_id}", response_model=ActionItemResponse
)
async def update_action_item_endpoint(
    item_id: uuid.UUID,
    data: ActionItemUpdateRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    from app.services.accident_action import get_action_item, update_action_item
    item = await get_action_item(db, item_id, current_user.tenant_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Položka nenalezena")
    try:
        return await update_action_item(
            db, item,
            title=data.title, description=data.description,
            status=data.status, due_date=data.due_date,
            assigned_to=data.assigned_to,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e),
        ) from e


@router.delete(
    "/accident-action-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_action_item_endpoint(
    item_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> None:
    from app.services.accident_action import delete_action_item, get_action_item
    item = await get_action_item(db, item_id, current_user.tenant_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Položka nenalezena")
    try:
        await delete_action_item(db, item)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e),
        ) from e


# ── Photos ──────────────────────────────────────────────────────────────────


@router.get(
    "/accident-reports/{report_id}/photos",
    response_model=list[PhotoResponse],
)
async def list_photos_endpoint(
    report_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> list[Any]:
    from app.services.accident_action import list_photos
    report = await get_accident_report_by_id(db, report_id, current_user.tenant_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Záznam nenalezen")
    return await list_photos(db, report_id, current_user.tenant_id)


@router.post(
    "/accident-reports/{report_id}/photos",
    response_model=PhotoResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_photo_endpoint(
    report_id: uuid.UUID,
    file: UploadFile = File(...),
    caption: str | None = Form(None),
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    report = await get_accident_report_by_id(db, report_id, current_user.tenant_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Záznam nenalezen")

    current_count = await count_photos(db, report_id, current_user.tenant_id)
    if current_count >= MAX_PHOTOS_PER_ACCIDENT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"K úrazu lze nahrát max {MAX_PHOTOS_PER_ACCIDENT} fotek",
        )

    content = await file.read()
    photo_id = uuid.uuid4()
    try:
        path = save_accident_photo(
            current_user.tenant_id, report.id, photo_id, content, file.filename or "photo.jpg",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e),
        ) from e
    return await add_photo(db, report, path, caption, current_user.id)


@router.get("/accident-photos/{photo_id}/file")
async def download_photo(
    photo_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    from app.core.storage import read_file
    from app.services.accident_action import get_photo

    photo = await get_photo(db, photo_id, current_user.tenant_id)
    if photo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fotka nenalezena")
    try:
        content = read_file(photo.photo_path)
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Soubor nenalezen",
        ) from e
    ext = photo.photo_path.rsplit(".", 1)[-1].lower()
    mime = {
        "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "webp": "image/webp", "heic": "image/heic",
    }.get(ext, "image/jpeg")
    return Response(content=content, media_type=mime,
                    headers={"Content-Disposition": "inline"})


@router.delete(
    "/accident-photos/{photo_id}", status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_photo_endpoint(
    photo_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> None:
    from app.services.accident_action import delete_photo, get_photo
    photo = await get_photo(db, photo_id, current_user.tenant_id)
    if photo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fotka nenalezena")
    delete_file(photo.photo_path)
    await delete_photo(db, photo)


# ── Podepsaný papírový dokument (1 per úraz) ────────────────────────────────


@router.post(
    "/accident-reports/{report_id}/signed-document",
    response_model=AccidentReportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_signed_document_endpoint(
    report_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> object:
    """Nahrát podepsaný papírový záznam (PDF nebo sken). Přepíše předchozí."""
    report = await get_accident_report_by_id(db, report_id, current_user.tenant_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Záznam nenalezen")

    content = await file.read()
    try:
        path = save_accident_signed_document(
            current_user.tenant_id, report.id, content, file.filename or "document.pdf",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e),
        ) from e

    # Pokud existoval předchozí soubor s jinou extension (např. byl JPG, teď PDF), smaž
    if report.signed_document_path and report.signed_document_path != path:
        delete_file(report.signed_document_path)

    report.signed_document_path = path
    await db.flush()
    return await _one_report_response(db, report)


@router.get("/accident-reports/{report_id}/signed-document/file")
async def download_signed_document_endpoint(
    report_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    report = await get_accident_report_by_id(db, report_id, current_user.tenant_id)
    if report is None or not report.signed_document_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Soubor nenalezen")
    if not file_exists(report.signed_document_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Soubor nenalezen")

    content = read_file(report.signed_document_path)
    ext = report.signed_document_path.rsplit(".", 1)[-1].lower()
    mime = {
        "pdf": "application/pdf",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
        "heic": "image/heic",
    }.get(ext, "application/octet-stream")
    return Response(
        content=content,
        media_type=mime,
        headers={"Content-Disposition": "inline"},
    )


@router.delete(
    "/accident-reports/{report_id}/signed-document",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_signed_document_endpoint(
    report_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> None:
    report = await get_accident_report_by_id(db, report_id, current_user.tenant_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Záznam nenalezen")
    if not report.signed_document_path:
        return
    delete_file(report.signed_document_path)
    report.signed_document_path = None
    await db.flush()
