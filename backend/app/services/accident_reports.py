import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.validation import assert_in_tenant
from app.models.accident_report import AccidentReport
from app.models.employee import Employee
from app.models.risk import Risk
from app.models.signature import DOC_TYPE_ACCIDENT_REPORT, Signature
from app.schemas.accident_reports import (
    AccidentReportCreateRequest,
    AccidentReportUpdateRequest,
)


async def hydrate_signed_count(
    db: AsyncSession, reports: list[AccidentReport],
) -> dict[uuid.UUID, int]:
    """Pro každý report v listu spočítá počet existujících podpisů.

    Vrací mapping {report_id: signed_count}. Použito pro `is_fully_signed`
    a filter podepsané/nepodepsané v API.
    """
    if not reports:
        return {}
    report_ids = [r.id for r in reports]
    rows = (await db.execute(
        select(Signature.doc_id, func.count())
        .where(
            Signature.doc_type == DOC_TYPE_ACCIDENT_REPORT,
            Signature.doc_id.in_(report_ids),
        )
        .group_by(Signature.doc_id),
    )).all()
    return {row[0]: int(row[1]) for row in rows}


def to_response_dict(report: AccidentReport, signed_count: int) -> dict[str, Any]:
    """Sestaví dict s computed fields pro API response.

    AccidentReportResponse má extra fields (signed_count, is_fully_signed),
    které nejsou na modelu — populujeme je tady.
    """
    required_count = len(report.required_signer_employee_ids or [])
    return {
        "id": report.id,
        "tenant_id": report.tenant_id,
        "employee_id": report.employee_id,
        "employee_name": report.employee_name,
        "workplace": report.workplace,
        "accident_date": report.accident_date,
        "accident_time": report.accident_time,
        "shift_start_time": report.shift_start_time,
        "injury_type": report.injury_type,
        "injured_body_part": report.injured_body_part,
        "injury_source": report.injury_source,
        "injury_cause": report.injury_cause,
        "injured_count": report.injured_count,
        "is_fatal": report.is_fatal,
        "has_other_injuries": report.has_other_injuries,
        "description": report.description,
        "blood_pathogen_exposure": report.blood_pathogen_exposure,
        "blood_pathogen_persons": report.blood_pathogen_persons,
        "violated_regulations": report.violated_regulations,
        "alcohol_test_performed": report.alcohol_test_performed,
        "alcohol_test_result": report.alcohol_test_result,
        "alcohol_test_value": report.alcohol_test_value,
        "drug_test_performed": report.drug_test_performed,
        "drug_test_result": report.drug_test_result,
        "injured_signed_at": report.injured_signed_at,
        "injured_external": report.injured_external,
        "witnesses": report.witnesses,
        "supervisor_name": report.supervisor_name,
        "supervisor_employee_id": report.supervisor_employee_id,
        "supervisor_signed_at": report.supervisor_signed_at,
        "risk_id": report.risk_id,
        "risk_review_required": report.risk_review_required,
        "risk_review_completed_at": report.risk_review_completed_at,
        "status": report.status,
        "signed_document_path": report.signed_document_path,
        "created_by": report.created_by,
        "signature_required": report.signature_required,
        "required_signer_employee_ids": report.required_signer_employee_ids or [],
        "signed_count": signed_count,
        "is_fully_signed": (
            required_count > 0
            and signed_count >= required_count
            and report.signature_required
        ),
    }


async def _assert_fk_in_tenant(
    db: AsyncSession,
    *,
    employee_id: uuid.UUID | None,
    risk_id: uuid.UUID | None,
    tenant_id: uuid.UUID,
) -> None:
    """Ochrana proti cross-tenant FK injection přes employee_id a risk_id."""
    if employee_id is not None:
        await assert_in_tenant(db, Employee, employee_id, tenant_id, field_name="employee_id")
    if risk_id is not None:
        await assert_in_tenant(db, Risk, risk_id, tenant_id, field_name="risk_id")


async def get_accident_reports(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    report_status: str | None = None,
    risk_review_pending: bool | None = None,
    signed_filter: str | None = None,
) -> list[AccidentReport]:
    """signed_filter: 'signed' | 'unsigned' | None.
    - 'signed':   is_fully_signed AND signature_required
    - 'unsigned': NOT is_fully_signed AND signature_required (chybí podpisy)
    """
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
    reports = list(result.scalars().all())

    if signed_filter in ("signed", "unsigned"):
        # Filter v Pythonu po hydrataci — pro MVP OK, optimalizovat lze
        # JOINem na (SELECT doc_id, COUNT(*) FROM signatures GROUP BY doc_id).
        sig_counts = await hydrate_signed_count(db, reports)
        filtered: list[AccidentReport] = []
        for r in reports:
            required_count = len(r.required_signer_employee_ids or [])
            signed = sig_counts.get(r.id, 0)
            fully_signed = (
                r.signature_required
                and required_count > 0
                and signed >= required_count
            )
            if signed_filter == "signed" and fully_signed:
                filtered.append(r)
            elif signed_filter == "unsigned" and not fully_signed:
                filtered.append(r)
        reports = filtered

    return reports


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


async def _resolve_workplace_snapshot(
    db: AsyncSession,
    *,
    workplace_id: uuid.UUID | None,
    workplace_external_description: str | None,
    fallback: str | None,
    tenant_id: uuid.UUID,
) -> str:
    """Vrací textový snapshot názvu pracoviště pro AccidentReport.workplace.

    Priorita:
    1. workplace_id → načti Workplace.name z DB (per tenant) → vrať Plant + " — " + Workplace.name
    2. workplace_external_description → "Mimo provozovnu — {popis}"
    3. fallback (legacy free-text z update / starý klient)
    Pokud nic z toho, vyhodí ValueError.
    """
    if workplace_id is not None:
        from app.models.workplace import Plant, Workplace
        wp = (await db.execute(
            select(Workplace).where(
                Workplace.id == workplace_id,
                Workplace.tenant_id == tenant_id,
            ),
        )).scalar_one_or_none()
        if wp is None:
            raise ValueError(f"Pracoviště {workplace_id} nenalezeno v tenantu")
        plant = (await db.execute(
            select(Plant).where(Plant.id == wp.plant_id),
        )).scalar_one_or_none() if wp.plant_id else None
        plant_name = plant.name if plant is not None else None
        return f"{plant_name} — {wp.name}" if plant_name else wp.name
    if workplace_external_description and workplace_external_description.strip():
        return f"Mimo provozovnu — {workplace_external_description.strip()}"[:255]
    if fallback and fallback.strip():
        return fallback.strip()[:255]
    raise ValueError(
        "Pracoviště musí být specifikované — buď workplace_id z evidence, "
        "nebo workplace_external_description (mimo provozovnu).",
    )


async def create_accident_report(
    db: AsyncSession,
    data: AccidentReportCreateRequest,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
) -> AccidentReport:
    await _assert_fk_in_tenant(
        db,
        employee_id=data.employee_id,
        risk_id=data.risk_id,
        tenant_id=tenant_id,
    )
    workplace_text = await _resolve_workplace_snapshot(
        db,
        workplace_id=data.workplace_id,
        workplace_external_description=data.workplace_external_description,
        fallback=data.workplace,
        tenant_id=tenant_id,
    )
    # Svědky serializuj do JSONB-friendly formátu (employee_id = None
    # pro externí svědky)
    witnesses_data = [
        {
            "name": w.name,
            "employee_id": str(w.employee_id) if w.employee_id else None,
            "signed_at": w.signed_at.isoformat() if w.signed_at else None,
        }
        for w in data.witnesses
    ]

    # signature_required: True pokud všichni účastníci jsou interní.
    # required_signer_employee_ids: list employee IDs, kteří musí podepsat.
    sig_meta = _compute_signature_meta(
        injured_employee_id=data.employee_id,
        injured_external=data.injured_external,
        witnesses=witnesses_data,
        supervisor_employee_id=data.supervisor_employee_id,
        supervisor_name=data.supervisor_name,
    )

    report = AccidentReport(
        tenant_id=tenant_id,
        created_by=created_by,
        employee_id=data.employee_id,
        employee_name=data.employee_name,
        workplace=workplace_text,
        workplace_id=data.workplace_id,
        workplace_external_description=data.workplace_external_description,
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
        alcohol_test_value=data.alcohol_test_value,
        drug_test_performed=data.drug_test_performed,
        drug_test_result=data.drug_test_result,
        injured_signed_at=data.injured_signed_at,
        injured_external=data.injured_external,
        witnesses=witnesses_data,
        supervisor_name=data.supervisor_name,
        supervisor_employee_id=data.supervisor_employee_id,
        supervisor_signed_at=data.supervisor_signed_at,
        risk_id=data.risk_id,
        signature_required=sig_meta["signature_required"],
        required_signer_employee_ids=sig_meta["required_signer_employee_ids"],
    )
    db.add(report)
    await db.flush()

    # Akční plán — výchozí položka „Revize a případná změna rizik" se vytvoří
    # už při založení úrazu (i v draft fázi) a napojí se na placeholder
    # RiskAssessment. Když OZO uzavře RA, položka se automaticky uzavře.
    # Invariant: úraz nesmí existovat bez default action item — pokud to
    # selže, propagujeme exception a transakce se rollbackne.
    from app.services.accident_action import ensure_default_item
    await ensure_default_item(db, report, created_by)

    return report


def _compute_signature_meta(
    *,
    injured_employee_id: uuid.UUID | None,
    injured_external: bool,
    witnesses: list[dict[str, Any]],
    supervisor_employee_id: uuid.UUID | None,
    supervisor_name: str | None,
) -> dict[str, Any]:
    """Spočítá signature_required + required_signer_employee_ids pro úraz.

    Pravidla:
    - Postižený je interní iff (injured_employee_id NOT NULL) AND
      NOT injured_external.
    - Svědek je interní iff witness.employee_id NOT NULL.
    - Vedoucí je interní iff supervisor_employee_id NOT NULL.
    - signature_required = AND všech (postižený, všichni svědci, vedoucí)
      jsou interní. Externí účastník = fyzický tisk a podpis.
    - required_signer_employee_ids = pole UUID interních účastníků (deduplikace).
    """
    required: list[str] = []
    has_external = False

    # Postižený
    if injured_external or injured_employee_id is None:
        has_external = True
    else:
        required.append(str(injured_employee_id))

    # Svědci
    for w in witnesses:
        emp_id = w.get("employee_id")
        if not emp_id:
            has_external = True
        else:
            required.append(str(emp_id))

    # Vedoucí — pokud je vyplněný (supervisor_name) ale není interní → externí
    if supervisor_name and not supervisor_employee_id:
        has_external = True
    elif supervisor_employee_id is not None:
        required.append(str(supervisor_employee_id))

    # Deduplikace (jeden zaměstnanec může být současně postižený a vedoucí —
    # podepíše ale jen jednou)
    deduped = list(dict.fromkeys(required))

    return {
        "signature_required": not has_external,
        "required_signer_employee_ids": deduped,
    }


async def update_accident_report(
    db: AsyncSession, report: AccidentReport, data: AccidentReportUpdateRequest
) -> AccidentReport:
    if report.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Finalizovaný záznam nelze upravovat",
        )

    update_fields = data.model_dump(exclude_unset=True)

    # FK tenant validace
    new_employee_id = update_fields.get("employee_id")
    new_risk_id = update_fields.get("risk_id")
    if (
        ("employee_id" in update_fields and new_employee_id is not None)
        or ("risk_id" in update_fields and new_risk_id is not None)
    ):
        await _assert_fk_in_tenant(
            db,
            employee_id=new_employee_id if "employee_id" in update_fields else None,
            risk_id=new_risk_id if "risk_id" in update_fields else None,
            tenant_id=report.tenant_id,
        )

    # Svědky zpracuj zvlášť — zachovat employee_id pro digital signing
    if "witnesses" in update_fields and update_fields["witnesses"] is not None:
        update_fields["witnesses"] = [
            {
                "name": w["name"],
                "employee_id": (
                    str(w["employee_id"]) if w.get("employee_id") else None
                ),
                "signed_at": w.get("signed_at"),
            }
            for w in update_fields["witnesses"]
        ]

    # Pokud klient mění workplace (id nebo external description), přepočítej
    # textový snapshot. Klient nemusí workplace text posílat — service ho dopočítá.
    workplace_changed = (
        "workplace_id" in update_fields
        or "workplace_external_description" in update_fields
    )

    for field, value in update_fields.items():
        setattr(report, field, value)

    if workplace_changed:
        report.workplace = await _resolve_workplace_snapshot(
            db,
            workplace_id=report.workplace_id,
            workplace_external_description=report.workplace_external_description,
            fallback=report.workplace,
            tenant_id=report.tenant_id,
        )

    # Přepočítej signature meta po update (může se změnit kdokoliv ze
    # signers — postižený, svědci, vedoucí, injured_external).
    sig_meta = _compute_signature_meta(
        injured_employee_id=report.employee_id,
        injured_external=report.injured_external,
        witnesses=list(report.witnesses or []),
        supervisor_employee_id=report.supervisor_employee_id,
        supervisor_name=report.supervisor_name,
    )
    report.signature_required = sig_meta["signature_required"]
    report.required_signer_employee_ids = sig_meta["required_signer_employee_ids"]

    await db.flush()
    return report


async def finalize_accident_report(
    db: AsyncSession, report: AccidentReport, *, created_by: uuid.UUID | None = None,
) -> AccidentReport:
    """Draft → final. Nastaví risk_review_required = True a vytvoří
    výchozí položku akčního plánu „Revize a případná změna rizik"."""
    if report.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Nelze finalizovat záznam ve stavu '{report.status}'",
        )
    report.status = "final"
    report.risk_review_required = True
    await db.flush()

    # Vytvoř default action item — živý dokument pro OZO
    if created_by is not None:
        from app.services.accident_action import ensure_default_item
        await ensure_default_item(db, report, created_by)

    return report


async def complete_risk_review(
    db: AsyncSession, report: AccidentReport
) -> AccidentReport:
    """Potvrdí, že OZO zkontroloval/upravil rizika po úrazu."""
    if report.status == "archived":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Archivovaný záznam nelze upravovat",
        )
    if not report.risk_review_required:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Revize rizik nebyla vyžadována",
        )
    report.risk_review_completed_at = datetime.now(UTC)
    await db.flush()
    return report
