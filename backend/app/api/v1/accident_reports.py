import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.permissions import require_role
from app.models.user import User
from app.schemas.accident_reports import (
    AccidentReportCreateRequest,
    AccidentReportResponse,
    AccidentReportUpdateRequest,
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

router = APIRouter()


@router.get("/accident-reports", response_model=list[AccidentReportResponse])
async def list_accident_reports(
    report_status: str | None = Query(None, pattern="^(draft|final|archived)$"),
    risk_review_pending: bool | None = Query(None),
    current_user: User = Depends(require_role("ozo", "manager")),
    db: AsyncSession = Depends(get_db),
) -> list:
    """
    Vrátí záznamy o pracovních úrazech.
    Filtry: ?report_status=draft|final|archived, ?risk_review_pending=true
    Přístup: ozo, manager.
    """
    return await get_accident_reports(
        db,
        current_user.tenant_id,
        report_status=report_status,
        risk_review_pending=risk_review_pending,
    )


@router.post(
    "/accident-reports",
    response_model=AccidentReportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_accident_report_endpoint(
    data: AccidentReportCreateRequest,
    current_user: User = Depends(require_role("ozo", "manager")),
    db: AsyncSession = Depends(get_db),
) -> object:
    """Vytvoří nový záznam o úrazu (status=draft). Přístup: ozo, manager."""
    return await create_accident_report(db, data, current_user.tenant_id, current_user.id)


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
    return report


@router.patch("/accident-reports/{report_id}", response_model=AccidentReportResponse)
async def update_accident_report_endpoint(
    report_id: uuid.UUID,
    data: AccidentReportUpdateRequest,
    current_user: User = Depends(require_role("ozo", "manager")),
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
    return await update_accident_report(db, report, data)


@router.post("/accident-reports/{report_id}/finalize", response_model=AccidentReportResponse)
async def finalize_accident_report_endpoint(
    report_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "manager")),
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
    return await finalize_accident_report(db, report)


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
    return await complete_risk_review(db, report)


@router.get("/accident-reports/{report_id}/pdf")
async def get_accident_report_pdf(
    report_id: uuid.UUID,
    download: bool = Query(False, description="True = attachment (stáhnout), False = inline (zobrazit v prohlížeči)"),
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
    from sqlalchemy import select
    from app.models.tenant import Tenant
    tenant_result = await db.execute(
        select(Tenant).where(Tenant.id == current_user.tenant_id)
    )
    tenant = tenant_result.scalar_one_or_none()
    tenant_name = tenant.name if tenant else str(current_user.tenant_id)

    pdf_bytes = generate_accident_report_pdf(report, tenant_name)

    disposition = "attachment" if download else "inline"
    filename = f"uraz_{report.accident_date}_{report_id}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


@router.delete("/accident-reports/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_accident_report(
    report_id: uuid.UUID,
    current_user: User = Depends(require_role("ozo", "manager")),
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
