import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.revision import DUE_SOON_DAYS, Revision
from app.models.risk import Risk
from app.models.training import Training
from app.schemas.revisions import CalendarItem, RevisionCreateRequest, RevisionUpdateRequest


async def get_revisions(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    revision_type: str | None = None,
    status: str | None = None,
    due_status: str | None = None,
) -> list[Revision]:
    query = select(Revision).where(Revision.tenant_id == tenant_id)
    if revision_type is not None:
        query = query.where(Revision.revision_type == revision_type)
    if status is not None:
        query = query.where(Revision.status == status)
    query = query.order_by(Revision.next_revision_at.asc().nulls_last())
    result = await db.execute(query)
    rows = list(result.scalars().all())

    if due_status is not None:
        rows = [r for r in rows if r.due_status == due_status]

    return rows


async def get_revision_by_id(
    db: AsyncSession, revision_id: uuid.UUID, tenant_id: uuid.UUID
) -> Revision | None:
    result = await db.execute(
        select(Revision).where(
            Revision.id == revision_id,
            Revision.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def create_revision(
    db: AsyncSession,
    data: RevisionCreateRequest,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
) -> Revision:
    revision = Revision(
        tenant_id=tenant_id,
        created_by=created_by,
        title=data.title,
        revision_type=data.revision_type,
        location=data.location,
        last_revised_at=data.last_revised_at,
        valid_months=data.valid_months,
        next_revision_at=data.next_revision_at,
        contractor=data.contractor,
        responsible_user_id=data.responsible_user_id,
        notes=data.notes,
    )
    db.add(revision)
    await db.flush()
    return revision


async def update_revision(
    db: AsyncSession, revision: Revision, data: RevisionUpdateRequest
) -> Revision:
    update_fields = data.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        setattr(revision, field, value)

    # Přepočítej next_revision_at pokud se změnil last_revised_at nebo valid_months
    # a next_revision_at nebyl explicitně nastaven v tomto requestu
    if "next_revision_at" not in update_fields:
        last = revision.last_revised_at
        months = revision.valid_months
        if last is not None and months is not None:
            import calendar
            month = last.month + months
            year = last.year + (month - 1) // 12
            month = ((month - 1) % 12) + 1
            last_day = calendar.monthrange(year, month)[1]
            day = min(last.day, last_day)
            revision.next_revision_at = date(year, month, day)

    await db.flush()
    return revision


# ── Agregovaný kalendář ───────────────────────────────────────────────────────

def _compute_due_status(due_date: date) -> str:
    today = datetime.now(UTC).date()
    delta = (due_date - today).days
    if delta < 0:
        return "overdue"
    if delta <= DUE_SOON_DAYS:
        return "due_soon"
    return "ok"


async def get_calendar_items(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    days_ahead: int = 90,
) -> list[CalendarItem]:
    """
    Agreguje nadcházející termíny ze tří zdrojů:
    - revisions.next_revision_at
    - risks.review_date
    - trainings.valid_until

    Vrátí pouze položky s due_date <= today + days_ahead, seřazené by due_date asc.
    Položky bez due_date (no_schedule) jsou vynechány.
    Archivované záznamy jsou vynechány.
    """
    today = datetime.now(UTC).date()
    from datetime import timedelta
    horizon = today + timedelta(days=days_ahead)

    items: list[CalendarItem] = []

    # 1. Revize
    rev_result = await db.execute(
        select(Revision).where(
            Revision.tenant_id == tenant_id,
            Revision.status == "active",
            Revision.next_revision_at.is_not(None),
        )
    )
    for rev in rev_result.scalars():
        if rev.next_revision_at <= horizon:  # type: ignore[operator]
            items.append(CalendarItem(
                source="revision",
                source_id=rev.id,
                title=rev.title,
                due_date=rev.next_revision_at,  # type: ignore[arg-type]
                due_status=_compute_due_status(rev.next_revision_at),  # type: ignore[arg-type]
                responsible_user_id=rev.responsible_user_id,
                detail_url=f"/api/v1/revisions/{rev.id}",
            ))

    # 2. Rizika s review_date
    risk_result = await db.execute(
        select(Risk).where(
            Risk.tenant_id == tenant_id,
            Risk.status == "active",
            Risk.review_date.is_not(None),
        )
    )
    for risk in risk_result.scalars():
        if risk.review_date <= horizon:  # type: ignore[operator]
            items.append(CalendarItem(
                source="risk",
                source_id=risk.id,
                title=risk.title,
                due_date=risk.review_date,  # type: ignore[arg-type]
                due_status=_compute_due_status(risk.review_date),  # type: ignore[arg-type]
                responsible_user_id=risk.responsible_user_id,
                detail_url=f"/api/v1/risks/{risk.id}",
            ))

    # 3. Školení s valid_until
    training_result = await db.execute(
        select(Training).where(
            Training.tenant_id == tenant_id,
            Training.status == "active",
            Training.valid_until.is_not(None),
        )
    )
    for training in training_result.scalars():
        if training.valid_until <= horizon:  # type: ignore[operator]
            items.append(CalendarItem(
                source="training",
                source_id=training.id,
                title=f"{training.title} – {training.employee_id}",
                due_date=training.valid_until,  # type: ignore[arg-type]
                due_status=_compute_due_status(training.valid_until),  # type: ignore[arg-type]
                responsible_user_id=None,
                detail_url=f"/api/v1/trainings/{training.id}",
            ))

    # Seřadit: nejdříve overdue, pak nejbližší termíny
    items.sort(key=lambda x: x.due_date)
    return items
