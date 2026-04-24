import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accident_report import AccidentReport
from app.models.medical_exam import EXPIRING_SOON_DAYS as ME_EXPIRING_SOON_DAYS
from app.models.medical_exam import MedicalExam
from app.models.revision import Revision
from app.models.training import EXPIRING_SOON_DAYS, TrainingAssignment
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

    # 6. Nadcházející kalendář – top 10 (30 dní + overdue)
    all_items = await get_calendar_items(db, tenant_id, days_ahead=30)
    upcoming_calendar = all_items[:10]

    return DashboardResponse(
        pending_risk_reviews=pending_risk_reviews,
        expiring_trainings=expiring_trainings,
        overdue_revisions=overdue_revisions,
        draft_accident_reports=draft_accident_reports,
        expiring_medical_exams=expiring_medical_exams,
        upcoming_calendar=upcoming_calendar,
    )
