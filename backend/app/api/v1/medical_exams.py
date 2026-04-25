import uuid
from datetime import date
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.permissions import require_role
from app.core.storage import (
    delete_file,
    file_exists,
    read_file,
    save_medical_exam_report,
)
from app.models.employee import Employee
from app.models.job_position import JobPosition
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.medical_exams import (
    GenerateInitialExamsRequest,
    GenerateInitialExamsResponse,
    MedicalExamCreateRequest,
    MedicalExamResponse,
    MedicalExamUpdateRequest,
)
from app.services.employees import get_employee_by_user_id
from app.services.export_pdf import generate_medical_exams_pdf
from app.services.medical_exam_referral import generate_referral_pdf
from app.services.medical_exams import (
    attach_employee_info,
    create_medical_exam,
    generate_initial_exam_requests,
    get_medical_exam_by_id,
    get_medical_exams,
    update_medical_exam,
)
from app.services.medical_specialty_catalog import (
    SPECIALTY_CATALOG,
    SPECIALTY_PERIODICITY,
)

router = APIRouter()


@router.get("/medical-exams", response_model=list[MedicalExamResponse])
async def list_medical_exams(
    employee_id: uuid.UUID | None = Query(None),
    exam_type: str | None = Query(
        None, pattern="^(vstupni|periodicka|vystupni|mimoradna|odborna)$"
    ),
    exam_category: str | None = Query(None, pattern="^(preventivni|odborna)$"),
    me_status: str | None = Query(None, pattern="^(active|archived)$"),
    validity_status: str | None = Query(
        None, pattern="^(no_expiry|valid|expiring_soon|expired)$"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Any]:
    """
    Vrátí evidenci lékařských prohlídek (s naplněným employee_name a dalšími info).
    Employee vidí pouze vlastní záznamy.
    Filtry: ?employee_id=, ?exam_type=, ?exam_category=, ?me_status=, ?validity_status=
    """
    if current_user.role == "employee":
        emp = await get_employee_by_user_id(db, current_user.id, current_user.tenant_id)
        if emp is None:
            return []
        employee_id = emp.id

    exams = await get_medical_exams(
        db,
        current_user.tenant_id,
        employee_id=employee_id,
        exam_type=exam_type,
        status=me_status,
        validity_status=validity_status,
    )
    if exam_category is not None:
        exams = [e for e in exams if e.exam_category == exam_category]

    include_personal_id = current_user.role in ("ozo", "hr_manager")
    return await attach_employee_info(
        db, exams, include_personal_id=include_personal_id,
    )


@router.get("/medical-exams/specialty-catalog")
async def get_specialty_catalog(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Číselník odborných lékařských vyšetření a jejich periodicity."""
    _ = current_user  # auth ack
    return {
        "specialties":  SPECIALTY_CATALOG,
        "periodicity":  SPECIALTY_PERIODICITY,
    }


# DŮLEŽITÉ: /medical-exams/export/pdf musí být před /medical-exams/{exam_id}
@router.get("/medical-exams/export/pdf")
async def export_medical_exams_pdf(
    employee_id: uuid.UUID | None = Query(None),
    exam_type: str | None = Query(
        None, pattern="^(vstupni|periodicka|vystupni|mimoradna|odborna)$"
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
    enriched = await attach_employee_info(db, exams, include_personal_id=True)
    pdf_bytes = generate_medical_exams_pdf(enriched, tenant_name)

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
) -> Any:
    """Zaznamená lékařskou prohlídku. Přístup: ozo, manager."""
    exam = await create_medical_exam(db, data, current_user.tenant_id, current_user.id)
    enriched = await attach_employee_info(db, [exam], include_personal_id=True)
    return enriched[0]


@router.post(
    "/medical-exams/generate-initial",
    response_model=GenerateInitialExamsResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_initial_exams_endpoint(
    payload: GenerateInitialExamsRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Auto-vygeneruje vstupní + odborné prohlídky podle kategorie pozice zaměstnance.
    Skipuje typy/specialty, které už existují jako aktivní záznam.
    """
    return await generate_initial_exam_requests(
        db, payload.employee_id, current_user.tenant_id, current_user.id,
    )


@router.get("/medical-exams/{exam_id}", response_model=MedicalExamResponse)
async def get_medical_exam(
    exam_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
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
                status_code=status.HTTP_403_FORBIDDEN, detail="Přístup odepřen",
            )
    include_personal_id = current_user.role in ("ozo", "hr_manager")
    enriched = await attach_employee_info(db, [exam], include_personal_id=include_personal_id)
    return enriched[0]


@router.patch("/medical-exams/{exam_id}", response_model=MedicalExamResponse)
async def update_medical_exam_endpoint(
    exam_id: uuid.UUID,
    data: MedicalExamUpdateRequest,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    exam = await get_medical_exam_by_id(db, exam_id, current_user.tenant_id)
    if exam is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prohlídka nenalezena")
    updated = await update_medical_exam(db, exam, data)
    enriched = await attach_employee_info(db, [updated], include_personal_id=True)
    return enriched[0]


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


# ── Upload zprávy z prohlídky ────────────────────────────────────────────────


@router.post(
    "/medical-exams/{exam_id}/report",
    response_model=MedicalExamResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_exam_report_endpoint(
    exam_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Nahrát zprávu z prohlídky (PDF/sken). Přepíše předchozí."""
    exam = await get_medical_exam_by_id(db, exam_id, current_user.tenant_id)
    if exam is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prohlídka nenalezena")

    content = await file.read()
    try:
        path = save_medical_exam_report(
            current_user.tenant_id, exam.id, content, file.filename or "report.pdf",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e),
        ) from e

    if exam.report_path and exam.report_path != path:
        delete_file(exam.report_path)
    exam.report_path = path
    await db.flush()
    enriched = await attach_employee_info(db, [exam], include_personal_id=True)
    return enriched[0]


@router.get("/medical-exams/{exam_id}/report/file")
async def download_exam_report_endpoint(
    exam_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    exam = await get_medical_exam_by_id(db, exam_id, current_user.tenant_id)
    if exam is None or not exam.report_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Soubor nenalezen")

    if current_user.role == "employee":
        emp = await get_employee_by_user_id(db, current_user.id, current_user.tenant_id)
        if emp is None or exam.employee_id != emp.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Přístup odepřen",
            )

    if not file_exists(exam.report_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Soubor nenalezen")
    content = read_file(exam.report_path)
    ext = exam.report_path.rsplit(".", 1)[-1].lower()
    mime = {
        "pdf": "application/pdf",
        "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "webp": "image/webp", "heic": "image/heic",
    }.get(ext, "application/octet-stream")
    return Response(
        content=content, media_type=mime,
        headers={"Content-Disposition": "inline"},
    )


@router.delete(
    "/medical-exams/{exam_id}/report", status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_exam_report_endpoint(
    exam_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> None:
    exam = await get_medical_exam_by_id(db, exam_id, current_user.tenant_id)
    if exam is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prohlídka nenalezena")
    if not exam.report_path:
        return
    delete_file(exam.report_path)
    exam.report_path = None
    await db.flush()


# ── Žádanka pro PLS ──────────────────────────────────────────────────────────


@router.get("/medical-exams/{exam_id}/referral.pdf")
async def get_referral_pdf(
    exam_id: uuid.UUID,
    download: bool = Query(False),
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Vygeneruje PDF žádanku pro lékařskou prohlídku adresovanou PLS."""
    exam = await get_medical_exam_by_id(db, exam_id, current_user.tenant_id)
    if exam is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prohlídka nenalezena")

    employee = (await db.execute(
        select(Employee).where(Employee.id == exam.employee_id)
    )).scalar_one()

    position: JobPosition | None = None
    if exam.job_position_id:
        position = (await db.execute(
            select(JobPosition).where(JobPosition.id == exam.job_position_id)
        )).scalar_one_or_none()

    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == current_user.tenant_id)
    )).scalar_one()
    tenant_address = getattr(tenant, "address", None) or None

    specialty_label = None
    if exam.specialty:
        for entry in SPECIALTY_CATALOG:
            if entry["key"] == exam.specialty:
                specialty_label = entry["label"]
                break

    pdf_bytes = generate_referral_pdf(
        exam, employee, position, tenant.name,
        tenant_address=tenant_address,
        contact_person=current_user.email,
        specialty_label=specialty_label,
    )

    disposition = "attachment" if download else "inline"
    filename = f"zadanka_{employee.last_name}_{exam.exam_date}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )
