"""Service vrstva pro Risk Assessment."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.validation import assert_in_tenant
from app.models.accident_report import AccidentReport
from app.models.employee import Employee
from app.models.job_position import JobPosition
from app.models.oopp import EmployeeOoppIssue, PositionOoppItem
from app.models.revision import Revision
from app.models.risk_assessment import (
    RiskAssessment,
    RiskAssessmentRevision,
    RiskMeasure,
    score_to_level,
)
from app.models.training import Training
from app.models.workplace import Plant, Workplace
from app.schemas.risk_assessments import (
    RiskAssessmentCreateRequest,
    RiskAssessmentUpdateRequest,
    RiskMeasureCreateRequest,
    RiskMeasureUpdateRequest,
)

log = logging.getLogger("risk_assessments")


# ── Helpers ─────────────────────────────────────────────────────────────────


def _compute_score(p: int | None, s: int | None) -> int | None:
    if p is None or s is None:
        return None
    return p * s


async def _enrich_assessment(
    db: AsyncSession, ra: RiskAssessment,
) -> dict[str, Any]:
    """Doplnění read-only polí (workplace_name, measures_count atd.) pro response."""
    out = ra.__dict__.copy()
    out.pop("_sa_instance_state", None)

    if ra.workplace_id:
        wp = (await db.execute(
            select(Workplace).where(Workplace.id == ra.workplace_id),
        )).scalar_one_or_none()
        out["workplace_name"] = wp.name if wp else None
    else:
        out["workplace_name"] = None

    if ra.job_position_id:
        jp = (await db.execute(
            select(JobPosition).where(JobPosition.id == ra.job_position_id),
        )).scalar_one_or_none()
        out["job_position_name"] = jp.name if jp else None
    else:
        out["job_position_name"] = None

    if ra.plant_id:
        p = (await db.execute(
            select(Plant).where(Plant.id == ra.plant_id),
        )).scalar_one_or_none()
        out["plant_name"] = p.name if p else None
    else:
        out["plant_name"] = None

    # Measures counts
    counts_row = (await db.execute(
        select(
            func.count(RiskMeasure.id),
            func.count(RiskMeasure.id).filter(
                RiskMeasure.status.in_(["planned", "in_progress"]),
            ),
        ).where(RiskMeasure.risk_assessment_id == ra.id),
    )).first()
    if counts_row:
        out["measures_count"] = int(counts_row[0])
        out["measures_open_count"] = int(counts_row[1])
    else:
        out["measures_count"] = 0
        out["measures_open_count"] = 0

    return out


async def _enrich_measure(
    db: AsyncSession, m: RiskMeasure,
) -> dict[str, Any]:
    out = m.__dict__.copy()
    out.pop("_sa_instance_state", None)
    if m.position_oopp_item_id:
        item = (await db.execute(
            select(PositionOoppItem).where(
                PositionOoppItem.id == m.position_oopp_item_id,
            ),
        )).scalar_one_or_none()
        out["position_oopp_item_name"] = item.name if item else None
    else:
        out["position_oopp_item_name"] = None
    if m.training_template_id:
        t = (await db.execute(
            select(Training).where(Training.id == m.training_template_id),
        )).scalar_one_or_none()
        out["training_template_title"] = t.title if t else None
    else:
        out["training_template_title"] = None
    if m.responsible_employee_id:
        e = (await db.execute(
            select(Employee).where(Employee.id == m.responsible_employee_id),
        )).scalar_one_or_none()
        out["responsible_employee_name"] = e.full_name if e else None
    else:
        out["responsible_employee_name"] = None
    return out


def _serialize_for_snapshot(ra: RiskAssessment) -> dict[str, Any]:
    """Snapshot RiskAssessment pro audit trail revisions."""
    raw = ra.__dict__.copy()
    raw.pop("_sa_instance_state", None)
    # JSON-serializovatelné: UUID → str, datetime → isoformat
    out: dict[str, Any] = {}
    for k, v in raw.items():
        if isinstance(v, uuid.UUID):
            out[k] = str(v)
        elif isinstance(v, datetime):
            out[k] = v.isoformat()
        elif hasattr(v, "isoformat"):  # date
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


async def _create_revision_snapshot(
    db: AsyncSession,
    ra: RiskAssessment,
    *,
    revised_by_user_id: uuid.UUID,
    change_reason: str | None,
) -> None:
    """Uloží JSONB snapshot do risk_assessment_revisions."""
    last = (await db.execute(
        select(func.max(RiskAssessmentRevision.revision_number)).where(
            RiskAssessmentRevision.risk_assessment_id == ra.id,
        ),
    )).scalar_one_or_none() or 0
    snapshot = _serialize_for_snapshot(ra)
    rev = RiskAssessmentRevision(
        id=uuid.uuid4(),
        tenant_id=ra.tenant_id,
        risk_assessment_id=ra.id,
        revision_number=last + 1,
        snapshot=snapshot,
        change_reason=change_reason,
        revised_by_user_id=revised_by_user_id,
        revised_at=datetime.now(UTC),
    )
    db.add(rev)
    await db.flush()


# ── CRUD: RiskAssessment ────────────────────────────────────────────────────


async def get_risk_assessments(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    scope_type: str | None = None,
    workplace_id: uuid.UUID | None = None,
    job_position_id: uuid.UUID | None = None,
    plant_id: uuid.UUID | None = None,
    status: str | None = None,
    level: str | None = None,
    hazard_category: str | None = None,
) -> list[dict[str, Any]]:
    query = select(RiskAssessment).where(RiskAssessment.tenant_id == tenant_id)
    if scope_type:
        query = query.where(RiskAssessment.scope_type == scope_type)
    if workplace_id:
        query = query.where(RiskAssessment.workplace_id == workplace_id)
    if job_position_id:
        query = query.where(RiskAssessment.job_position_id == job_position_id)
    if plant_id:
        query = query.where(RiskAssessment.plant_id == plant_id)
    if status:
        query = query.where(RiskAssessment.status == status)
    if hazard_category:
        query = query.where(RiskAssessment.hazard_category == hazard_category)
    query = query.order_by(RiskAssessment.created_at.desc())

    rows = (await db.execute(query)).scalars().all()
    enriched = [await _enrich_assessment(db, r) for r in rows]
    if level:
        enriched = [
            r for r in enriched
            if (r.get("residual_level") or r.get("initial_level")) == level
        ]
    return enriched


async def get_risk_assessment(
    db: AsyncSession, ra_id: uuid.UUID, tenant_id: uuid.UUID,
) -> RiskAssessment | None:
    res = await db.execute(
        select(RiskAssessment).where(
            RiskAssessment.id == ra_id,
            RiskAssessment.tenant_id == tenant_id,
        ),
    )
    return res.scalar_one_or_none()


async def create_risk_assessment(
    db: AsyncSession,
    data: RiskAssessmentCreateRequest,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
) -> RiskAssessment:
    # FK validace pro scope target
    if data.workplace_id:
        await assert_in_tenant(
            db, Workplace, data.workplace_id, tenant_id, field_name="workplace_id",
        )
    if data.job_position_id:
        await assert_in_tenant(
            db, JobPosition, data.job_position_id, tenant_id,
            field_name="job_position_id",
        )
    if data.plant_id:
        await assert_in_tenant(
            db, Plant, data.plant_id, tenant_id, field_name="plant_id",
        )
    if data.related_accident_report_id:
        await assert_in_tenant(
            db, AccidentReport, data.related_accident_report_id, tenant_id,
            field_name="related_accident_report_id",
        )
    if data.related_revision_id:
        await assert_in_tenant(
            db, Revision, data.related_revision_id, tenant_id,
            field_name="related_revision_id",
        )

    initial_score = _compute_score(data.initial_probability, data.initial_severity)
    initial_level = score_to_level(initial_score)
    residual_score = _compute_score(
        data.residual_probability or data.initial_probability,
        data.residual_severity or data.initial_severity,
    )
    residual_level = score_to_level(residual_score)

    ra = RiskAssessment(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        scope_type=data.scope_type,
        workplace_id=data.workplace_id,
        job_position_id=data.job_position_id,
        plant_id=data.plant_id,
        activity_description=data.activity_description,
        hazard_category=data.hazard_category,
        oopp_risk_column=data.oopp_risk_column,
        hazard_description=data.hazard_description,
        consequence_description=data.consequence_description,
        exposed_persons=data.exposed_persons,
        exposure_frequency=data.exposure_frequency,
        initial_probability=data.initial_probability,
        initial_severity=data.initial_severity,
        initial_level=initial_level,
        existing_controls=data.existing_controls,
        existing_oopp=data.existing_oopp,
        residual_probability=data.residual_probability,
        residual_severity=data.residual_severity,
        residual_level=residual_level,
        status=data.status,
        assessed_at=data.assessed_at,
        assessed_by_user_id=created_by if data.assessed_at else None,
        review_due_date=data.review_due_date,
        related_accident_report_id=data.related_accident_report_id,
        related_revision_id=data.related_revision_id,
        notes=data.notes,
        created_by=created_by,
    )
    db.add(ra)
    await db.flush()

    await _create_revision_snapshot(
        db, ra, revised_by_user_id=created_by,
        change_reason="Vytvořeno",
    )
    return ra


async def update_risk_assessment(
    db: AsyncSession,
    ra: RiskAssessment,
    data: RiskAssessmentUpdateRequest,
    *,
    revised_by_user_id: uuid.UUID,
) -> RiskAssessment:
    fields = data.model_dump(exclude_unset=True, exclude={"change_reason"})

    # FK validace
    if "workplace_id" in fields and fields["workplace_id"]:
        await assert_in_tenant(
            db, Workplace, fields["workplace_id"], ra.tenant_id,
            field_name="workplace_id",
        )
    if "job_position_id" in fields and fields["job_position_id"]:
        await assert_in_tenant(
            db, JobPosition, fields["job_position_id"], ra.tenant_id,
            field_name="job_position_id",
        )
    if "plant_id" in fields and fields["plant_id"]:
        await assert_in_tenant(
            db, Plant, fields["plant_id"], ra.tenant_id, field_name="plant_id",
        )

    # Detekce přechodu na finální stav — hook pro uzavření vázaných action items.
    # Finálním stavem rozumíme `accepted` (riziko posouzeno a uzavřeno).
    previous_status = ra.status
    new_status = fields.get("status", previous_status)
    became_closed = previous_status != "accepted" and new_status == "accepted"

    for k, v in fields.items():
        setattr(ra, k, v)

    # Přepočet level — initial_score/residual_score jsou GENERATED v DB,
    # ale level je str sloupec — počítáme v Pythonu.
    initial_score = _compute_score(ra.initial_probability, ra.initial_severity)
    ra.initial_level = score_to_level(initial_score)
    residual_score = _compute_score(
        ra.residual_probability or ra.initial_probability,
        ra.residual_severity or ra.initial_severity,
    )
    ra.residual_level = score_to_level(residual_score)

    if "last_reviewed_at" in fields and fields["last_reviewed_at"]:
        ra.last_reviewed_by_user_id = revised_by_user_id

    ra.updated_at = datetime.now(UTC)
    await db.flush()
    # Computed columns: SQLAlchemy je po UPDATE nedotáhne automaticky
    await db.refresh(ra, ["initial_score", "residual_score"])

    # Hook: uzavřít navázané action items v úrazech (status='accepted')
    if became_closed:
        await _close_linked_accident_action_items(
            db, ra=ra, closed_by=revised_by_user_id,
        )

    await _create_revision_snapshot(
        db, ra, revised_by_user_id=revised_by_user_id,
        change_reason=data.change_reason or "Aktualizace",
    )
    return ra


async def _close_linked_accident_action_items(
    db: AsyncSession,
    *,
    ra: RiskAssessment,
    closed_by: uuid.UUID,
) -> None:
    """Při uzavření RA (status='accepted') uzavři všechny AccidentActionItem,
    které jsou na tuto RA navázané přes related_risk_assessment_id."""
    from app.models.accident_action import AccidentActionItem

    res = await db.execute(
        select(AccidentActionItem).where(
            AccidentActionItem.tenant_id == ra.tenant_id,
            AccidentActionItem.related_risk_assessment_id == ra.id,
            AccidentActionItem.status.in_(("pending", "in_progress")),
        )
    )
    items = list(res.scalars().all())
    if not items:
        return

    now = datetime.now(UTC)
    for item in items:
        item.status = "done"
        item.completed_at = now
        # poznámka — kdo a proč zavřel
        note = f"Auto-uzavřeno: hodnocení rizik {ra.id} bylo uzavřeno."
        if item.description:
            item.description = f"{item.description}\n\n{note}"
        else:
            item.description = note
    await db.flush()


async def delete_risk_assessment(
    db: AsyncSession, ra: RiskAssessment,
) -> None:
    """Soft delete přes status='archived'."""
    ra.status = "archived"
    ra.updated_at = datetime.now(UTC)
    await db.flush()


# ── CRUD: RiskMeasure ───────────────────────────────────────────────────────


async def get_measures(
    db: AsyncSession, ra_id: uuid.UUID, tenant_id: uuid.UUID,
) -> list[dict[str, Any]]:
    rows = (await db.execute(
        select(RiskMeasure).where(
            RiskMeasure.risk_assessment_id == ra_id,
            RiskMeasure.tenant_id == tenant_id,
        ).order_by(RiskMeasure.order_index, RiskMeasure.created_at),
    )).scalars().all()
    return [await _enrich_measure(db, m) for m in rows]


async def create_measure(
    db: AsyncSession,
    data: RiskMeasureCreateRequest,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
) -> RiskMeasure:
    """Vytvoří opatření.

    Pro PPE measure (control_type='ppe' s position_oopp_item_id) automaticky:
    - Pokud OOPP item ještě není přidělen pozici, ke které se riziko vztahuje,
      přidělíme ho. (Jinak: skip — měl by se manuálně řešit přes OOPP modul.)

    Pro administrative measure s training_template_id zatím nic neděláme
    (re-školení se řeší samostatným endpointem `/risks/{id}/trigger-retraining`,
    user řekl: školení se dodefinuje později).
    """
    ra = (await db.execute(
        select(RiskAssessment).where(
            RiskAssessment.id == data.risk_assessment_id,
            RiskAssessment.tenant_id == tenant_id,
        ),
    )).scalar_one_or_none()
    if ra is None:
        raise ValueError("risk_assessment_id: hodnocení nenalezeno")

    # FK validace volitelných polí
    if data.position_oopp_item_id:
        await assert_in_tenant(
            db, PositionOoppItem, data.position_oopp_item_id, tenant_id,
            field_name="position_oopp_item_id",
        )
    if data.training_template_id:
        await assert_in_tenant(
            db, Training, data.training_template_id, tenant_id,
            field_name="training_template_id",
        )
    if data.responsible_employee_id:
        await assert_in_tenant(
            db, Employee, data.responsible_employee_id, tenant_id,
            field_name="responsible_employee_id",
        )

    measure = RiskMeasure(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        risk_assessment_id=data.risk_assessment_id,
        order_index=data.order_index,
        control_type=data.control_type,
        description=data.description,
        position_oopp_item_id=data.position_oopp_item_id,
        training_template_id=data.training_template_id,
        responsible_employee_id=data.responsible_employee_id,
        responsible_user_id=data.responsible_user_id,
        deadline=data.deadline,
        status=data.status,
        notes=data.notes,
    )
    db.add(measure)
    await db.flush()

    # OOPP integrace: pro PPE measure vytvořit pending oopp_issues pro
    # zaměstnance dotčené rizikem. Funguje jen pokud:
    # - control_type = 'ppe'
    # - position_oopp_item_id je zadán (= existující OOPP položka přiřazená pozici)
    # - risk má scope position nebo workplace (víme, koho ovlivňuje)
    if data.control_type == "ppe" and data.position_oopp_item_id:
        try:
            await _ensure_oopp_issued_for_affected(
                db,
                tenant_id=tenant_id,
                ra=ra,
                position_oopp_item_id=data.position_oopp_item_id,
                created_by=created_by,
            )
        except Exception as e:  # noqa: BLE001
            log.warning(
                "OOPP integration failed for risk measure %s: %s",
                measure.id, e,
            )

    # OOPP grid auto-toggle: pro PPE measure zaškrtnout buňku v gridu pozice.
    # Vstupní data:
    # - body_part_code z navázaného úrazu (ra.related_accident_report_id) nebo
    #   z RA scope=position → primární zaměstnanec → účaz
    # - risk_col z ra.oopp_risk_column
    # Pokud chybí jakýkoli vstup, integrace se přeskočí (loguje warning).
    if data.control_type == "ppe":
        try:
            await _auto_toggle_oopp_grid(
                db, tenant_id=tenant_id, ra=ra, created_by=created_by,
            )
        except Exception as e:  # noqa: BLE001
            log.warning(
                "OOPP grid auto-toggle failed for risk measure %s: %s",
                measure.id, e,
            )

    return measure


async def _auto_toggle_oopp_grid(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    ra: RiskAssessment,
    created_by: uuid.UUID,
) -> None:
    """Auto-zaškrtne políčko v OOPP gridu pozice na základě RA + úraz.

    Resolve target position:
    1) ra.scope_type == 'position' → ra.job_position_id
    2) ra.related_accident_report_id → účaz.employee.job_position_id

    Resolve body_part_code:
    1) ra.related_accident_report_id → účaz.injured_body_part_code

    Resolve risk_col:
    1) ra.oopp_risk_column

    Pokud chybí jakýkoli vstup, no-op.
    """
    # Risk column
    if ra.oopp_risk_column is None:
        log.debug("RA %s has no oopp_risk_column — skip grid toggle", ra.id)
        return

    # Target position + body_part
    position_id: uuid.UUID | None = None
    body_part: str | None = None

    if ra.related_accident_report_id is not None:
        accident = (await db.execute(
            select(AccidentReport).where(
                AccidentReport.id == ra.related_accident_report_id,
                AccidentReport.tenant_id == tenant_id,
            ),
        )).scalar_one_or_none()
        if accident is not None:
            body_part = accident.injured_body_part_code
            if accident.employee_id is not None:
                emp = (await db.execute(
                    select(Employee).where(
                        Employee.id == accident.employee_id,
                        Employee.tenant_id == tenant_id,
                    ),
                )).scalar_one_or_none()
                if emp is not None and emp.job_position_id is not None:
                    position_id = emp.job_position_id

    if position_id is None and ra.scope_type == "position":
        position_id = ra.job_position_id

    if position_id is None or body_part is None:
        log.info(
            "RA %s: nelze vyhodnotit cílovou pozici/body_part "
            "(position=%s, body_part=%s) — skip grid toggle",
            ra.id, position_id, body_part,
        )
        return

    # Lokální import — kruhová závislost s services/oopp.py (oopp už importuje schemas)
    from app.services.oopp import mark_grid_cell

    grid, was_added = await mark_grid_cell(
        db,
        position_id=position_id,
        tenant_id=tenant_id,
        body_part=body_part,
        risk_col=ra.oopp_risk_column,
        created_by=created_by,
    )
    if was_added:
        log.info(
            "OOPP grid auto-toggle: position=%s, body_part=%s, risk_col=%s (RA=%s)",
            position_id, body_part, ra.oopp_risk_column, ra.id,
        )


async def _ensure_oopp_issued_for_affected(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    ra: RiskAssessment,
    position_oopp_item_id: uuid.UUID,
    created_by: uuid.UUID,
) -> int:
    """Najde zaměstnance dotčené rizikem a vytvoří pending OOPP issues.

    Dotčení = active employees na konkrétní pozici (scope='position') nebo
    všichni na pracovišti (scope='workplace').
    """
    from datetime import date

    item = (await db.execute(
        select(PositionOoppItem).where(
            PositionOoppItem.id == position_oopp_item_id,
            PositionOoppItem.tenant_id == tenant_id,
        ),
    )).scalar_one_or_none()
    if item is None:
        return 0

    # Najdi dotčené zaměstnance
    emp_query = select(Employee).where(
        Employee.tenant_id == tenant_id,
        Employee.status == "active",
    )
    if ra.scope_type == "position" and ra.job_position_id:
        emp_query = emp_query.where(Employee.job_position_id == ra.job_position_id)
    elif ra.scope_type == "workplace" and ra.workplace_id:
        emp_query = emp_query.where(Employee.workplace_id == ra.workplace_id)
    elif ra.scope_type == "plant" and ra.plant_id:
        emp_query = emp_query.where(Employee.plant_id == ra.plant_id)
    else:
        # 'activity' nebo nedefinováno → nevíme koho zasáhne, skip
        return 0

    employees = (await db.execute(emp_query)).scalars().all()

    today = date.today()
    created = 0
    for emp in employees:
        # Pokud už existuje aktivní issue pro tuto kombinaci (emp + item),
        # neduplikujeme.
        existing = (await db.execute(
            select(EmployeeOoppIssue).where(
                EmployeeOoppIssue.tenant_id == tenant_id,
                EmployeeOoppIssue.employee_id == emp.id,
                EmployeeOoppIssue.position_oopp_item_id == position_oopp_item_id,
                EmployeeOoppIssue.status == "active",
            ).limit(1),
        )).scalar_one_or_none()
        if existing is not None:
            continue
        issue = EmployeeOoppIssue(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            employee_id=emp.id,
            position_oopp_item_id=position_oopp_item_id,
            issued_at=today,
            quantity=1,
            status="active",
            notes=f"Auto-vytvořeno z hodnocení rizika #{ra.id}",
            created_by=created_by,
        )
        db.add(issue)
        created += 1
    await db.flush()
    log.info(
        "Created %d OOPP issues from risk measure (RA=%s, OOPP=%s)",
        created, ra.id, position_oopp_item_id,
    )
    return created


async def get_measure(
    db: AsyncSession, measure_id: uuid.UUID, tenant_id: uuid.UUID,
) -> RiskMeasure | None:
    return (await db.execute(
        select(RiskMeasure).where(
            RiskMeasure.id == measure_id,
            RiskMeasure.tenant_id == tenant_id,
        ),
    )).scalar_one_or_none()


async def update_measure(
    db: AsyncSession,
    measure: RiskMeasure,
    data: RiskMeasureUpdateRequest,
    *,
    user_id: uuid.UUID,
) -> RiskMeasure:
    fields = data.model_dump(exclude_unset=True)
    for k, v in fields.items():
        setattr(measure, k, v)
    if fields.get("status") == "done" and not measure.completed_at:
        from datetime import date
        measure.completed_at = date.today()
        measure.completed_by_user_id = user_id
    measure.updated_at = datetime.now(UTC)
    await db.flush()
    return measure


async def delete_measure(db: AsyncSession, measure: RiskMeasure) -> None:
    await db.delete(measure)
    await db.flush()


# ── Revisions ───────────────────────────────────────────────────────────────


async def get_revisions(
    db: AsyncSession, ra_id: uuid.UUID, tenant_id: uuid.UUID,
) -> list[RiskAssessmentRevision]:
    return list((await db.execute(
        select(RiskAssessmentRevision).where(
            RiskAssessmentRevision.risk_assessment_id == ra_id,
            RiskAssessmentRevision.tenant_id == tenant_id,
        ).order_by(RiskAssessmentRevision.revision_number.desc()),
    )).scalars().all())


# ── Helper pro accident integration ─────────────────────────────────────────


async def create_for_accident(
    db: AsyncSession,
    *,
    accident: AccidentReport,
    created_by: uuid.UUID,
) -> RiskAssessment:
    """Vždy vytvoří **nový** placeholder RA pro daný úraz.

    Každý úraz má svůj vlastní kontext (specifická situace, body_part, příčina),
    proto se nesdružují — i když existuje aktuální RA pro stejné pracoviště,
    nový úraz založí nové hodnocení rizik. Hodnocení rizik je neomezené dle
    pozic/pracovišť/provozů.

    Scope priorita (preferujeme position kvůli auto-toggle OOPP gridu):
    1) position — pokud má úraz zaměstnance s přiřazenou pozicí
    2) position — pokud má úraz workplace_id a je tam přesně 1 aktivní pozice
    3) workplace — pokud má úraz workplace_id (víc nebo žádná pozice na něm)
    4) activity — fallback (free text)

    Volá se z accident_action.ensure_default_item, které pak default action item
    napojí přes related_risk_assessment_id.
    """
    tenant_id = accident.tenant_id

    scope_type: str = "activity"
    workplace_id: uuid.UUID | None = None
    job_position_id: uuid.UUID | None = None

    # 1) Zaměstnanec s pozicí
    if accident.employee_id is not None:
        emp = (await db.execute(
            select(Employee).where(
                Employee.id == accident.employee_id,
                Employee.tenant_id == tenant_id,
            ),
        )).scalar_one_or_none()
        if emp is not None and emp.job_position_id is not None:
            scope_type = "position"
            job_position_id = emp.job_position_id
            workplace_id = accident.workplace_id

    # 2) Pracoviště s právě 1 aktivní pozicí
    if scope_type == "activity" and accident.workplace_id is not None:
        positions = (await db.execute(
            select(JobPosition).where(
                JobPosition.tenant_id == tenant_id,
                JobPosition.workplace_id == accident.workplace_id,
                JobPosition.status == "active",
            ),
        )).scalars().all()
        if len(positions) == 1:
            scope_type = "position"
            job_position_id = positions[0].id
            workplace_id = accident.workplace_id

    # 3) Fallback workplace (víc/žádná pozice)
    if scope_type == "activity" and accident.workplace_id is not None:
        scope_type = "workplace"
        workplace_id = accident.workplace_id

    workplace_label = accident.workplace or "neuvedené pracoviště"
    placeholder = RiskAssessment(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        scope_type=scope_type,
        workplace_id=workplace_id,
        job_position_id=job_position_id,
        activity_description=(
            f"Pracovní úraz: {workplace_label}" if scope_type == "activity" else None
        ),
        hazard_category="other",
        hazard_description=(
            f"Po úrazu (zdroj: {accident.injury_source}) vyžaduje OZO doplnit identifikaci."
        ),
        consequence_description=(
            f"Důsledek úrazu: {accident.injury_type} — {accident.injured_body_part}"
        ),
        initial_probability=3,  # placeholder, OZO upraví
        initial_severity=3,
        initial_level=score_to_level(9),
        status="draft",
        related_accident_report_id=accident.id,
        review_due_date=accident.accident_date,
        notes=(
            f"Auto-vytvořeno po úrazu {accident.id} ({accident.accident_date}). "
            "OZO musí doplnit detaily."
        ),
        created_by=created_by,
    )
    db.add(placeholder)
    await db.flush()
    await _create_revision_snapshot(
        db, placeholder, revised_by_user_id=created_by,
        change_reason=f"Auto-vytvořeno po úrazu {accident.id}",
    )
    return placeholder


# Backward-compat alias — staré jméno se může vyskytovat v importech
get_or_create_for_accident = create_for_accident


# Backward-compat: pomocná fce pro frontend co serializuje JSON
def revision_snapshot_to_dict(rev: RiskAssessmentRevision) -> dict[str, Any]:
    snap = rev.snapshot
    if isinstance(snap, str):
        try:
            return json.loads(snap)
        except json.JSONDecodeError:
            return {"raw": snap}
    return snap or {}
