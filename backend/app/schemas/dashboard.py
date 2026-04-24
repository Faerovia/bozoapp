from pydantic import BaseModel

from app.schemas.revisions import CalendarItem


class DashboardResponse(BaseModel):
    # ── Souhrnné počty ────────────────────────────────────────────────────────
    pending_risk_reviews: int
    """Finalizované úrazy čekající na revizi rizik (OZO akce)."""

    expiring_trainings: int
    """Aktivní školení, která expirovala nebo expirují do 30 dní."""

    overdue_revisions: int
    """Aktivní revize s prošlým termínem."""

    draft_accident_reports: int
    """Záznamy o úrazech ve stavu draft (nezafinalizované)."""

    expiring_medical_exams: int
    """Aktivní lékařské prohlídky, které expirují do 60 dní nebo jsou prošlé."""

    # ── Nadcházející termíny ──────────────────────────────────────────────────
    upcoming_calendar: list[CalendarItem]
    """Top 10 nejnaléhavějších položek (overdue první, pak nejbližší)."""
