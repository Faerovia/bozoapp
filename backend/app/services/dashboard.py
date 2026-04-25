import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accident_report import AccidentReport
from app.models.job_position import JobPosition
from app.models.medical_exam import EXPIRING_SOON_DAYS as ME_EXPIRING_SOON_DAYS
from app.models.medical_exam import MedicalExam
from app.models.revision import Revision
from app.models.risk_factor_assessment import RiskFactorAssessment
from app.models.training import EXPIRING_SOON_DAYS, TrainingAssignment
from app.models.workplace import Workplace
from app.schemas.dashboard import DashboardResponse
from app.services.revisions import get_calendar_items


async def get_dashboard(db: AsyncSession, tenant_id: uuid.UUID) -> DashboardResponse:
    today = datetime.now(UTC).date()

    # 1. Úrazy čekající na revizi rizik
    #    status='final' AND risk_review_required=True AND risk_review_completed_at IS NULL
    pending_risk_reviews: int = (
        await db.execute(
            select(func.count()).where(
                AccidentReport.tenant_id == tenant_id,
                AccidentReport.status == "final",
                AccidentReport.risk_review_required.is_(True),
                AccidentReport.risk_review_completed_at.is_(None),
            )
        )
    ).scalar_one()

    # 2. Expirující nebo expirovaná aktivní přiřazení školení
    #    (počítáme přiřazení zaměstnancům, ne šablony — jedna šablona může mít N assignment)
    expiring_horizon = today + timedelta(days=EXPIRING_SOON_DAYS)
    expiring_trainings: int = (
        await db.execute(
            select(func.count()).where(
                TrainingAssignment.tenant_id == tenant_id,
                TrainingAssignment.status.in_(["pending", "completed"]),
                TrainingAssignment.valid_until.is_not(None),
                TrainingAssignment.valid_until <= expiring_horizon,
            )
        )
    ).scalar_one()

    # 3. Aktivní revize s prošlým termínem
    overdue_revisions: int = (
        await db.execute(
            select(func.count()).where(
                Revision.tenant_id == tenant_id,
                Revision.status == "active",
                Revision.next_revision_at.is_not(None),
                Revision.next_revision_at < today,
            )
        )
    ).scalar_one()

    # 4. Záznamy o úrazech ve stavu draft
    draft_accident_reports: int = (
        await db.execute(
            select(func.count()).where(
                AccidentReport.tenant_id == tenant_id,
                AccidentReport.status == "draft",
            )
        )
    ).scalar_one()

    # 5. Expirující nebo prošlé aktivní lékařské prohlídky
    #    valid_until IS NOT NULL AND valid_until <= today + ME_EXPIRING_SOON_DAYS
    me_horizon = today + timedelta(days=ME_EXPIRING_SOON_DAYS)
    expiring_medical_exams: int = (
        await db.execute(
            select(func.count()).where(
                MedicalExam.tenant_id == tenant_id,
                MedicalExam.status == "active",
                MedicalExam.valid_until.is_not(None),
                MedicalExam.valid_until <= me_horizon,
            )
        )
    ).scalar_one()

    # 6. Pracoviště bez určené kategorie rizik
    #    Pracoviště je „bez kategorie" pokud žádná z jeho aktivních pozic
    #    nemá určenou kategorii (work_category override) ani RFA s ohodnoceným
    #    faktorem (category_proposed je computed property — počítáme v Pythonu).
    workplace_rows = (await db.execute(
        select(Workplace.id).where(
            Workplace.tenant_id == tenant_id,
            Workplace.status == "active",
        )
    )).scalars().all()
    workplaces_without_category: int = 0
    for wp_id in workplace_rows:
        # Najdi aktivní pozice na pracovišti
        positions = (await db.execute(
            select(JobPosition).where(
                JobPosition.workplace_id == wp_id,
                JobPosition.status == "active",
            )
        )).scalars().all()
        if not positions:
            workplaces_without_category += 1
            continue
        # Má alespoň jedna pozice work_category (manuální override)?
        has_category = any(p.work_category for p in positions)
        if has_category:
            continue
        # Má alespoň jedna pozice RFA s ohodnoceným faktorem?
        position_ids = [p.id for p in positions]
        rfa_rows = (await db.execute(
            select(RiskFactorAssessment).where(
                RiskFactorAssessment.job_position_id.in_(position_ids),
            )
        )).scalars().all()
        has_rfa_category = any(r.category_proposed for r in rfa_rows)
        if not has_rfa_category:
            workplaces_without_category += 1

    # 7. Nadcházející kalendář – top 10 (30 dní + overdue)
    all_items = await get_calendar_items(db, tenant_id, days_ahead=30)
    upcoming_calendar = all_items[:10]

    return DashboardResponse(
        pending_risk_reviews=pending_risk_reviews,
        expiring_trainings=expiring_trainings,
        overdue_revisions=overdue_revisions,
        draft_accident_reports=draft_accident_reports,
        expiring_medical_exams=expiring_medical_exams,
        workplaces_without_category=workplaces_without_category,
        upcoming_calendar=upcoming_calendar,
    )
