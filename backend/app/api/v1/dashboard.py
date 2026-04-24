from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_role
from app.models.user import User
from app.schemas.dashboard import DashboardResponse
from app.services.dashboard import get_dashboard

router = APIRouter()


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard_endpoint(
    current_user: User = Depends(require_role("ozo", "hr_manager")),
    db: AsyncSession = Depends(get_db),
) -> DashboardResponse:
    """
    Souhrnný přehled pro OZO / manažera.

    Vrátí:
    - pending_risk_reviews  – finalizované úrazy čekající na revizi rizik
    - expiring_trainings    – aktivní školení expirující do 30 dní nebo již prošlá
    - overdue_revisions     – aktivní revize s prošlým termínem
    - draft_accident_reports – záznamy o úrazech nezafinalizované
    - upcoming_calendar     – top 10 nejnaléhavějších termínů (30 dní + overdue)

    Přístup: ozo, manager.
    """
    return await get_dashboard(db, current_user.tenant_id)
