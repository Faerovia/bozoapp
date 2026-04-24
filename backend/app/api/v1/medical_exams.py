import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.permissions import require_role
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.medical_exams import (
    MedicalExamCreateRequest,
    MedicalExamResponse,
    MedicalExamUpdateRequest,
)
from app.services.employees import get_employee_by_user_id
from app.services.export_pdf import generate_medical_exams_pdf
from app.services.medical_exams import (
    create_medical_exam,
    get_medical_exam_by_id,
    get_medical_exams,
    update_medical_exam,
)

router = APIRouter()


@router.get("/medical-exams", response_model=list[MedicalExamResponse])
async def list_medical_exams(
    employee_id: uuid.UUID | None = Query(None),
    exam_type: str | None = Query(
        None, pattern="^(vstupni|periodicka|vystupni|mimoradna)$"
    ),
    me_status: str | None = Query(None, pattern="^(active|archived)$"),
    validity_status: str | None = Query(
        None, pattern="^(no_expiry|valid|expiring_soon|expired)$"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Any]:
    """
    Vrátí evidenci lékařských prohlídek.
    Employee vidí pouze vlastní záznamy.
    Filtry: ?employee_id=, ?exam_type=, ?me_status=, ?validity_status=
    """
    if current_user.role == "employee":
        emp = await get_employee_by_user_id(db, current_user.id, current_user.tenant_id)
        if emp is None:
            return []
        employee_id = emp.id

    return await get_medical_exams(
        db,
        current_user.tenant_id,
        employee_id=employee_id,
        exam_type=exam_type,
        status=me_status,
        validity_status=validity_status,
    )


# DŮLEŽITÉ: /medical-exams/export/pdf musí být před /medical-exams/{exam_id}
@router.get("/medical-exams/export/pdf")
async def export_medical_exams_pdf(
    employee_id: uuid.UUID | None = Query(None),
    exam_type: str | None = Query(
        None, pattern="^(vstupni|periodicka|vystupni|mimoradna)$"
    ),
    validity_status: str | None = Query(
        None, pattern="^(no_expiry|valid|expiring_soon|expired)$"
    ),
    download: bool = Query(False),
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Exportuje přehled lékařských prohlídek jako PDF."""
    tenant = (
        await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    ).scalar_one_or_none()
    tenant_name = tenant.name if tenant else str(current_user.tenant_id)

    exams = await get_medical_exams(
        db, current_user.tenant_id,
        employee_id=employee_id,
        exam_type=exam_type,
        validity_status=validity_status,
    )
    pdf_bytes = generate_medical_exams_pdf(exams, tenant_name)

    disposition = "attachment" if download else "inline"
    filename = f"prehled_lekarskych_prohlidek_{date.today()}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


@router.post(
    "/medical-exams",
    response_model=MedicalExamResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_medical_exam_endpoint(
    data: MedicalExamCreateRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> object:
    """Zaznamená lékařskou prohlídku. Přístup: ozo, manager."""
    return await create_medical_exam(db, data, current_user.tenant_id, current_user.id)


@router.get("/medical-exams/{exam_id}", response_model=MedicalExamResponse)
async def get_medical_exam(
    exam_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> object:
    """
    Vrátí detail záznamu prohlídky.
    Employee vidí pouze vlastní záznamy.
    """
    exam = await get_medical_exam_by_id(db, exam_id, current_user.tenant_id)
    if exam is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prohlídka nenalezena")

    if current_user.role == "employee":
        emp = await get_employee_by_user_id(db, current_user.id, current_user.tenant_id)
        if emp is None or exam.employee_id != emp.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Přístup odepřen"
            )
    return exam


@router.patch("/medical-exams/{exam_id}", response_model=MedicalExamResponse)
async def update_medical_exam_endpoint(
    exam_id: uuid.UUID,
    data: MedicalExamUpdateRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> object:
    exam = await get_medical_exam_by_id(db, exam_id, current_user.tenant_id)
    if exam is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prohlídka nenalezena")
    return await update_medical_exam(db, exam, data)


@router.delete("/medical-exams/{exam_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_medical_exam(
    exam_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Archivuje záznam prohlídky. Fyzické smazání zakázáno – BOZP dokumentace."""
    exam = await get_medical_exam_by_id(db, exam_id, current_user.tenant_id)
    if exam is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prohlídka nenalezena")
    exam.status = "archived"
    await db.flush()
