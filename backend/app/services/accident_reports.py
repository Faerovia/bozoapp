import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accident_report import AccidentReport
from app.schemas.accident_reports import (
    AccidentReportCreateRequest,
    AccidentReportUpdateRequest,
)


async def get_accident_reports(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    report_status: str | None = None,
    risk_review_pending: bool | None = None,
) -> list[AccidentReport]:
    query = select(AccidentReport).where(AccidentReport.tenant_id == tenant_id)
    if report_status is not None:
        query = query.where(AccidentReport.status == report_status)
    if risk_review_pending is True:
        query = query.where(
            AccidentReport.risk_review_required.is_(True),
            AccidentReport.risk_review_completed_at.is_(None),
        )
    query = query.order_by(AccidentReport.accident_date.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_accident_report_by_id(
    db: AsyncSession, report_id: uuid.UUID, tenant_id: uuid.UUID
) -> AccidentReport | None:
    result = await db.execute(
        select(AccidentReport).where(
            AccidentReport.id == report_id,
            AccidentReport.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def create_accident_report(
    db: AsyncSession,
    data: AccidentReportCreateRequest,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
) -> AccidentReport:
    # Svědky serializuj do JSONB-friendly formátu
    witnesses_data = [
        {"name": w.name, "signed_at": w.signed_at.isoformat() if w.signed_at else None}
        for w in data.witnesses
    ]

    report = AccidentReport(
        tenant_id=tenant_id,
        created_by=created_by,
        employee_id=data.employee_id,
        employee_name=data.employee_name,
        workplace=data.workplace,
        accident_date=data.accident_date,
        accident_time=data.accident_time,
        shift_start_time=data.shift_start_time,
        injury_type=data.injury_type,
        injured_body_part=data.injured_body_part,
        injury_source=data.injury_source,
        injury_cause=data.injury_cause,
        injured_count=data.injured_count,
        is_fatal=data.is_fatal,
        has_other_injuries=data.has_other_injuries,
        description=data.description,
        blood_pathogen_exposure=data.blood_pathogen_exposure,
        blood_pathogen_persons=data.blood_pathogen_persons,
        violated_regulations=data.violated_regulations,
        alcohol_test_performed=data.alcohol_test_performed,
        alcohol_test_result=data.alcohol_test_result,
        drug_test_performed=data.drug_test_performed,
        drug_test_result=data.drug_test_result,
        injured_signed_at=data.injured_signed_at,
        witnesses=witnesses_data,
        supervisor_name=data.supervisor_name,
        supervisor_signed_at=data.supervisor_signed_at,
        risk_id=data.risk_id,
    )
    db.add(report)
    await db.flush()
    return report


async def update_accident_report(
    db: AsyncSession, report: AccidentReport, data: AccidentReportUpdateRequest
) -> AccidentReport:
    if report.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Finalizovaný záznam nelze upravovat",
        )

    update_fields = data.model_dump(exclude_unset=True)

    # Svědky zpracuj zvlášť
    if "witnesses" in update_fields and update_fields["witnesses"] is not None:
        update_fields["witnesses"] = [
            {"name": w["name"], "signed_at": w.get("signed_at")}
            for w in update_fields["witnesses"]
        ]

    for field, value in update_fields.items():
        setattr(report, field, value)

    await db.flush()
    return report


async def finalize_accident_report(
    db: AsyncSession, report: AccidentReport
) -> AccidentReport:
    """Draft → final. Nastaví risk_review_required = True."""
    if report.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Nelze finalizovat záznam ve stavu '{report.status}'",
        )
    report.status = "final"
    report.risk_review_required = True
    await db.flush()
    return report


async def complete_risk_review(
    db: AsyncSession, report: AccidentReport
) -> AccidentReport:
    """Potvrdí, že OZO zkontroloval/upravil rizika po úrazu."""
    if report.status == "archived":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Archivovaný záznam nelze upravovat",
        )
    if not report.risk_review_required:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Revize rizik nebyla vyžadována",
        )
    report.risk_review_completed_at = datetime.now(UTC)
    await db.flush()
    return report
