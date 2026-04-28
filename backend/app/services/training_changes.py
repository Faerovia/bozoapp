"""
Auto-školení zaměstnanců po změně hodnocení rizik (RA).

Trigger: změna RA, která je významná pro absolventy:
  - přidání nového RiskMeasure (= nové opatření, nutno seznámit)
  - změna RA.status na 'mitigated' (= residuální riziko je popsáno)
  - změna RA.status na 'accepted' (= riziko posouzeno a uzavřeno)

Flow:
  1. Najít dotčené zaměstnance dle scope RA (position/workplace/plant)
  2. Vygenerovat NOVÝ GeneratedDocument 'Hodnocení rizik — <scope>'
     (každý trigger = nová verze pro audit)
  3. Najít / vytvořit singleton Training šablonu 'Změna rizik' (per tenant)
  4. Pro každého dotčeného zaměstnance:
       - existuje OPEN assignment (status=pending) → update content_document_id
         na nejnovější verzi (zaměstnanec se školí vždy na aktuální rizika)
       - existuje completed assignment → vytvořit NOVÝ assignment (eviduje
         se historie absolvování)
       - žádný assignment → vytvořit nový

Podpis: šablona má requires_qes=True, valid_months=None (jednorázová absolvence
per change event — neexpiruje, ale další změna RA generuje další assignment).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.job_position import JobPosition
from app.models.risk_assessment import RiskAssessment
from app.models.training import Training, TrainingAssignment

log = logging.getLogger(__name__)

CHANGE_TRAINING_TITLE = "Změna rizik"
CHANGE_TRAINING_DEADLINE_DAYS = 14


async def _get_or_create_change_training(
    db: AsyncSession, tenant_id: uuid.UUID, created_by: uuid.UUID,
) -> Training:
    """Singleton šablona 'Změna rizik' per tenant."""
    existing = (await db.execute(
        select(Training).where(
            Training.tenant_id == tenant_id,
            Training.title == CHANGE_TRAINING_TITLE,
        ).limit(1),
    )).scalar_one_or_none()
    if existing is not None:
        return existing

    template = Training(
        tenant_id=tenant_id,
        title=CHANGE_TRAINING_TITLE,
        training_type="bozp",
        trainer_kind="ozo_bozp",
        # Šablona má NOT NULL valid_months — nastavíme symbolicky 12 měsíců.
        # Reálný refresh school workflow: další významná změna RA vytvoří
        # nový assignment, takže expirace nemá praktický dopad.
        valid_months=12,
        requires_qes=True,
        status="active",
        notes=(
            "Auto-generované školení po změně hodnocení rizik na pozici / "
            "pracovišti zaměstnance. Obsahem je aktuální dokument 'Hodnocení "
            "rizik' pro daný scope. Po seznámení je vyžadován digitální podpis."
        ),
        created_by=created_by,
    )
    db.add(template)
    await db.flush()
    return template


async def _affected_employees(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    ra: RiskAssessment,
) -> list[Employee]:
    """Vrátí aktivní zaměstnance dotčené danou RA dle scope."""
    q = select(Employee).where(
        Employee.tenant_id == tenant_id,
        Employee.status == "active",
    )
    if ra.scope_type == "position" and ra.job_position_id:
        q = q.where(Employee.job_position_id == ra.job_position_id)
    elif ra.scope_type == "workplace" and ra.workplace_id:
        q = q.where(Employee.workplace_id == ra.workplace_id)
    elif ra.scope_type == "plant" and ra.plant_id:
        q = q.where(Employee.plant_id == ra.plant_id)
    else:
        # 'activity' scope — nelze určit dotčené zaměstnance, vracíme prázdno
        return []
    res = await db.execute(q)
    return list(res.scalars().all())


async def trigger_change_training_for_ra(
    db: AsyncSession,
    *,
    ra: RiskAssessment,
    triggered_by: uuid.UUID,
) -> int:
    """Spustí auto-školení 'Změna rizik' pro zaměstnance dotčené danou RA.

    Vrací počet vytvořených/aktualizovaných assignmentů.

    Volá se z risk_assessments service:
      - po vytvoření RiskMeasure
      - po změně RA.status na 'mitigated' nebo 'accepted'

    Idempotentní per scope: pokud ten samý zaměstnanec má open assignment,
    aktualizuje se jen content_document_id (nejnovější dokument).
    """
    # Lokální import (cyklická závislost: documents.py importuje risk_assessments
    # nepřímo přes _gen_risk_assessment_for_scope)
    from app.models.generated_document import GeneratedDocument
    from app.models.workplace import Workplace
    from app.services.document_folders import find_or_create_folder
    from app.services.documents import _gen_risk_assessment_for_scope

    tenant_id = ra.tenant_id

    # 1. Resolve scope_id pro generátor (preferujeme position > workplace > plant)
    scope_type = ra.scope_type
    scope_id: uuid.UUID | None = None
    if scope_type == "position":
        scope_id = ra.job_position_id
    elif scope_type == "workplace":
        scope_id = ra.workplace_id
    elif scope_type == "plant":
        scope_id = ra.plant_id

    if scope_id is None:
        log.info(
            "RA %s má scope=%s bez scope_id — change training se nespouští",
            ra.id, scope_type,
        )
        return 0

    # 2. Najít dotčené zaměstnance
    employees = await _affected_employees(db, tenant_id, ra)
    if not employees:
        log.info("RA %s: žádní dotčení zaměstnanci → no-op", ra.id)
        return 0

    # 3. Vygenerovat NOVÝ dokument (každý trigger = nová verze, audit)
    #    Volíme stejný scope_type/scope_id, do správné podsložky 'Rizika/<workplace>'.
    result = await _gen_risk_assessment_for_scope(
        db, tenant_id, scope_type=scope_type, scope_id=scope_id,
    )
    if result is None:
        log.warning("RA %s: generátor dokumentu vrátil None — no-op", ra.id)
        return 0
    title, content = result

    # Zařadit do auto-složky 'Rizika' / pracoviště
    rizika_root = await find_or_create_folder(
        db, tenant_id, triggered_by,
        name="Rizika", domain="bozp", parent_id=None,
    )
    target_folder_id = rizika_root.id
    workplace_id_for_folder: uuid.UUID | None = None
    if scope_type == "position":
        pos = (await db.execute(
            select(JobPosition).where(JobPosition.id == scope_id),
        )).scalar_one_or_none()
        if pos is not None:
            workplace_id_for_folder = pos.workplace_id
    elif scope_type == "workplace":
        workplace_id_for_folder = scope_id
    if workplace_id_for_folder is not None:
        wp = (await db.execute(
            select(Workplace).where(Workplace.id == workplace_id_for_folder),
        )).scalar_one_or_none()
        if wp is not None:
            subfolder = await find_or_create_folder(
                db, tenant_id, triggered_by,
                name=wp.name, domain="bozp", parent_id=rizika_root.id,
            )
            target_folder_id = subfolder.id

    new_doc = GeneratedDocument(
        tenant_id=tenant_id,
        document_type="risk_assessment",
        folder_id=target_folder_id,
        title=title,
        content_md=content,
        params={
            "scope_type": scope_type,
            "scope_id": str(scope_id),
            "generated_at": datetime.now(UTC).isoformat(),
            "triggered_by_ra": str(ra.id),
            "purpose": "change_training",
        },
        ai_input_tokens=None,
        ai_output_tokens=None,
        created_by=triggered_by,
    )
    db.add(new_doc)
    await db.flush()

    # 4. Singleton šablona "Změna rizik"
    template = await _get_or_create_change_training(db, tenant_id, triggered_by)

    # 5. Pro každého zaměstnance: update existing open OR create new
    deadline_dt = datetime.now(UTC) + timedelta(days=CHANGE_TRAINING_DEADLINE_DAYS)
    touched = 0
    for emp in employees:
        existing_open = (await db.execute(
            select(TrainingAssignment).where(
                TrainingAssignment.tenant_id == tenant_id,
                TrainingAssignment.training_id == template.id,
                TrainingAssignment.employee_id == emp.id,
                TrainingAssignment.status == "pending",
            ).limit(1),
        )).scalar_one_or_none()

        if existing_open is not None:
            # Open assignment → update na nejnovější dokument
            existing_open.content_document_id = new_doc.id
            existing_open.deadline = deadline_dt  # prodloužit (nový obsah)
            existing_open.updated_at = datetime.now(UTC)
            touched += 1
        else:
            # Žádný open → vytvoř nový (i když existuje completed historie)
            assignment = TrainingAssignment(
                tenant_id=tenant_id,
                training_id=template.id,
                employee_id=emp.id,
                deadline=deadline_dt,
                status="pending",
                assigned_by=triggered_by,
                content_document_id=new_doc.id,
            )
            db.add(assignment)
            touched += 1

    await db.flush()
    log.info(
        "Change training: RA %s → %d assignment(ů) aktualizováno/vytvořeno "
        "(doc=%s, scope=%s)",
        ra.id, touched, new_doc.id, scope_type,
    )
    return touched
