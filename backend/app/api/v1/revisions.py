import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.permissions import require_role
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.revisions import (
    CalendarItem,
    RevisionCreateRequest,
    RevisionResponse,
    RevisionUpdateRequest,
)
from app.services.export_pdf import generate_revisions_pdf
from app.services.revisions import (
    create_revision,
    get_calendar_items,
    get_revision_by_id,
    get_revisions,
    update_revision,
)

router = APIRouter()


# ── Kalendář (agregovaný pohled) ──────────────────────────────────────────────

@router.get("/calendar", response_model=list[CalendarItem])
async def get_calendar(
    days_ahead: int = Query(90, ge=1, le=365),
    current_user: User = Depends(require_role("ozo", "manager")),
    db: AsyncSession = Depends(get_db),
) -> list:
    """
    Agregovaný přehled nadcházejících termínů (revize, přezkum rizik, expiry školení).
    Řazeno vzestupně podle termínu. Překročené termíny jsou zahrnuty vždy.
    Přístup: ozo, manager.
    """
    return await get_calendar_items(db, current_user.tenant_id, days_ahead=days_ahead)


# ── Revize CRUD ───────────────────────────────────────────────────────────────

@router.get("/revisions", response_model=list[RevisionResponse])
async def list_revisions(
    revision_type: str | None = Query(None),
    status: str | None = Query(None, pattern="^(active|archived)$"),
    due_status: str | None = Query(None, pattern="^(no_schedule|ok|due_soon|overdue)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list:
    """Vrátí záznamy o revizích. Přístup: všechny role."""
    return await get_revisions(
        db, current_user.tenant_id,
        revision_type=revision_type,
        status=status,
        due_status=due_status,
    )


@router.post("/revisions", response_model=RevisionResponse, status_code=status.HTTP_201_CREATED)
async def create_revision_endpoint(
    data: RevisionCreateRequest,
    current_user: User = Depends(require_role("ozo", "manager")),
    db: AsyncSession = Depends(get_db),
) -> object:
    """Vytvoří záznam o revizi. Přístup: ozo, manager."""
    return await create_revision(db, data, current_user.tenant_id, current_user.id)


# DŮLEŽITÉ: /revisions/export/pdf musí být před /revisions/{revision_id}
@router.get("/revisions/export/pdf")
async def export_revisions_pdf(
    revision_type: str | None = Query(None),
    due_status: str | None = Query(None, pattern="^(no_schedule|ok|due_soon|overdue)$"),
    download: bool = Query(False),
    current_user: User = Depends(require_role("ozo", "manager")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Exportuje harmonogram revizí jako PDF.
    Filtry: ?revision_type=, ?due_status=
    """
    tenant = (await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))).scalar_one_or_none()
    tenant_name = tenant.name if tenant else str(current_user.tenant_id)

    records = await get_revisions(db, current_user.tenant_id, revision_type=revision_type, due_status=due_status)
    pdf_bytes = generate_revisions_pdf(records, tenant_name)

    disposition = "attachment" if download else "inline"
    filename = f"harmonogram_revizi_{date.today()}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


@router.get("/revisions/{revision_id}", response_model=RevisionResponse)
async def get_revision(
    revision_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> object:
    """Vrátí detail záznamu o revizi. Přístup: všechny role."""
    revision = await get_revision_by_id(db, revision_id, current_user.tenant_id)
    if revision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Revize nenalezena")
    return revision


@router.patch("/revisions/{revision_id}", response_model=RevisionResponse)
async def update_revision_endpoint(
    revision_id: uuid.UUID,
    data: RevisionUpdateRequest,
    current_user: User = Depends(require_role("ozo", "manager")),
    db: AsyncSession = Depends(get_db),
) -> object:
    """Aktualizuje záznam o revizi. Přístup: ozo, manager."""
    revision = await get_revision_by_id(db, revision_id, current_user.tenant_id)
    if revision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Revize nenalezena")
    return await update_revision(db, revision, data)


@router.delete("/revisions/{revision_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_revision(
    revision_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "manager")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Archivuje záznam o revizi. Fyzické smazání není povoleno."""
    revision = await get_revision_by_id(db, revision_id, current_user.tenant_id)
    if revision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Revize nenalezena")
    revision.status = "archived"
    await db.flush()
