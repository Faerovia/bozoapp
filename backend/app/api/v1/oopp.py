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
from app.schemas.oopp import OOPPCreateRequest, OOPPResponse, OOPPUpdateRequest
from app.services.employees import get_employee_by_user_id
from app.services.export_pdf import generate_oopp_pdf
from app.services.oopp import (
    create_oopp_assignment,
    get_oopp_assignments,
    get_oopp_by_id,
    update_oopp_assignment,
)

router = APIRouter()


@router.get("/oopp", response_model=list[OOPPResponse])
async def list_oopp(
    employee_id: uuid.UUID | None = Query(None),
    oopp_type: str | None = Query(None),
    status: str | None = Query(None, pattern="^(active|archived)$"),
    validity_status: str | None = Query(
        None, pattern="^(no_expiry|valid|expiring_soon|expired)$"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list:
    """
    Vrátí evidenci OOPP.
    Employee vidí pouze vlastní záznamy.
    Filtry: ?employee_id=, ?oopp_type=, ?status=, ?validity_status=
    """
    if current_user.role == "employee":
        emp = await get_employee_by_user_id(db, current_user.id, current_user.tenant_id)
        if emp is None:
            return []
        employee_id = emp.id

    return await get_oopp_assignments(
        db,
        current_user.tenant_id,
        employee_id=employee_id,
        oopp_type=oopp_type,
        status=status,
        validity_status=validity_status,
    )


@router.post("/oopp", response_model=OOPPResponse, status_code=status.HTTP_201_CREATED)
async def create_oopp_endpoint(
    data: OOPPCreateRequest,
    current_user: User = Depends(require_role("ozo", "manager")),
    db: AsyncSession = Depends(get_db),
) -> object:
    """Zaznamená výdej OOPP zaměstnanci. Přístup: ozo, manager."""
    return await create_oopp_assignment(db, data, current_user.tenant_id, current_user.id)


# DŮLEŽITÉ: /oopp/export/pdf musí být před /oopp/{assignment_id}
@router.get("/oopp/export/pdf")
async def export_oopp_pdf(
    oopp_type: str | None = Query(None),
    oopp_status: str | None = Query(None, pattern="^(active|archived)$"),
    validity_status: str | None = Query(
        None, pattern="^(no_expiry|valid|expiring_soon|expired)$"
    ),
    download: bool = Query(False),
    current_user: User = Depends(require_role("ozo", "manager")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Exportuje evidenci OOPP jako PDF.
    Filtry: ?oopp_type=, ?oopp_status=, ?validity_status=
    """
    tenant = (
        await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    ).scalar_one_or_none()
    tenant_name = tenant.name if tenant else str(current_user.tenant_id)

    records = await get_oopp_assignments(
        db, current_user.tenant_id,
        oopp_type=oopp_type,
        status=oopp_status,
        validity_status=validity_status,
    )
    pdf_bytes = generate_oopp_pdf(records, tenant_name)

    disposition = "attachment" if download else "inline"
    filename = f"evidence_oopp_{date.today()}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


@router.get("/oopp/{assignment_id}", response_model=OOPPResponse)
async def get_oopp(
    assignment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> object:
    """
    Vrátí detail záznamu OOPP.
    Employee vidí pouze vlastní záznamy.
    """
    assignment = await get_oopp_by_id(db, assignment_id, current_user.tenant_id)
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Záznam nenalezen")
    if current_user.role == "employee":
        emp = await get_employee_by_user_id(db, current_user.id, current_user.tenant_id)
        if emp is None or assignment.employee_id != emp.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Přístup odepřen")
    return assignment


@router.patch("/oopp/{assignment_id}", response_model=OOPPResponse)
async def update_oopp_endpoint(
    assignment_id: uuid.UUID,
    data: OOPPUpdateRequest,
    current_user: User = Depends(require_role("ozo", "manager")),
    db: AsyncSession = Depends(get_db),
) -> object:
    """Aktualizuje záznam OOPP. Přístup: ozo, manager."""
    assignment = await get_oopp_by_id(db, assignment_id, current_user.tenant_id)
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Záznam nenalezen")
    return await update_oopp_assignment(db, assignment, data)


@router.delete("/oopp/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_oopp(
    assignment_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "manager")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Archivuje záznam OOPP (status=archived). Fyzické smazání není povoleno –
    evidence výdeje OOPP je součástí BOZP dokumentace.
    """
    assignment = await get_oopp_by_id(db, assignment_id, current_user.tenant_id)
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Záznam nenalezen")
    assignment.status = "archived"
    await db.flush()
