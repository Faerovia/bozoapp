"""
Akční plán a fotky pracovních úrazů.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accident_action import AccidentActionItem, AccidentPhoto
from app.models.accident_report import AccidentReport

DEFAULT_ITEM_TITLE = "Revize a případná změna rizik"
DEFAULT_ITEM_DESCRIPTION = (
    "Po pracovním úrazu prověřit aktuálnost vyhodnocení rizik příslušné pozice / "
    "pracoviště (RFA dle NV 361/2007 Sb.) a přijmout opravná opatření, "
    "pokud úraz odhalil nezohledněné riziko."
)
MAX_PHOTOS_PER_ACCIDENT = 2


# ── Action items ────────────────────────────────────────────────────────────


async def list_action_items(
    db: AsyncSession, accident_id: uuid.UUID, tenant_id: uuid.UUID,
) -> list[AccidentActionItem]:
    res = await db.execute(
        select(AccidentActionItem)
        .where(
            AccidentActionItem.tenant_id == tenant_id,
            AccidentActionItem.accident_report_id == accident_id,
        )
        .order_by(AccidentActionItem.sort_order, AccidentActionItem.created_at)
    )
    return list(res.scalars().all())


async def get_action_item(
    db: AsyncSession, item_id: uuid.UUID, tenant_id: uuid.UUID,
) -> AccidentActionItem | None:
    res = await db.execute(
        select(AccidentActionItem).where(
            AccidentActionItem.id == item_id,
            AccidentActionItem.tenant_id == tenant_id,
        )
    )
    return res.scalar_one_or_none()


async def ensure_default_item(
    db: AsyncSession,
    accident: AccidentReport,
    created_by: uuid.UUID,
) -> AccidentActionItem:
    """Idempotentně vytvoří výchozí položku „Revize a případná změna rizik"
    a napojí ji na konkrétní RiskAssessment (vytvoří/najde placeholder)."""
    res = await db.execute(
        select(AccidentActionItem).where(
            AccidentActionItem.tenant_id == accident.tenant_id,
            AccidentActionItem.accident_report_id == accident.id,
            AccidentActionItem.is_default.is_(True),
        )
    )
    existing = res.scalar_one_or_none()
    if existing is not None:
        # Pokud položka existuje ale ještě nemá napojení na RA (legacy data
        # před migrací 066), doplníme ho.
        if existing.related_risk_assessment_id is None:
            from app.services.risk_assessments import get_or_create_for_accident
            ra = await get_or_create_for_accident(
                db, accident=accident, created_by=created_by,
            )
            existing.related_risk_assessment_id = ra.id
            await db.flush()
        return existing

    # Vytvoř (nebo najdi) RiskAssessment placeholder pro toto pracoviště
    from app.services.risk_assessments import get_or_create_for_accident
    ra = await get_or_create_for_accident(
        db, accident=accident, created_by=created_by,
    )
    related_ra_id: uuid.UUID = ra.id

    item = AccidentActionItem(
        tenant_id=accident.tenant_id,
        accident_report_id=accident.id,
        title=DEFAULT_ITEM_TITLE,
        description=DEFAULT_ITEM_DESCRIPTION,
        status="pending",
        is_default=True,
        sort_order=0,
        related_risk_assessment_id=related_ra_id,
        created_by=created_by,
    )
    db.add(item)
    await db.flush()
    return item


async def create_action_item(
    db: AsyncSession,
    accident: AccidentReport,
    *,
    title: str,
    description: str | None,
    due_date: Any = None,
    assigned_to: uuid.UUID | None = None,
    created_by: uuid.UUID,
) -> AccidentActionItem:
    # Spočítej max sort_order pro řazení nového řádku na konec
    max_res = await db.execute(
        select(func.coalesce(func.max(AccidentActionItem.sort_order), 0)).where(
            AccidentActionItem.accident_report_id == accident.id,
        )
    )
    max_sort = int(max_res.scalar_one() or 0)

    item = AccidentActionItem(
        tenant_id=accident.tenant_id,
        accident_report_id=accident.id,
        title=title,
        description=description,
        status="pending",
        due_date=due_date,
        assigned_to=assigned_to,
        is_default=False,
        sort_order=max_sort + 1,
        created_by=created_by,
    )
    db.add(item)
    await db.flush()
    return item


async def update_action_item(
    db: AsyncSession,
    item: AccidentActionItem,
    *,
    title: str | None = None,
    description: str | None = None,
    status: str | None = None,
    due_date: Any = None,
    assigned_to: uuid.UUID | None = None,
) -> AccidentActionItem:
    if title is not None:
        item.title = title
    if description is not None:
        item.description = description
    if status is not None:
        if status not in ("pending", "in_progress", "done", "cancelled"):
            raise ValueError(f"Neplatný status: {status}")
        # Při přechodu na done zaznamenej čas
        if status == "done" and item.status != "done":
            item.completed_at = datetime.now(UTC)
        elif status != "done":
            item.completed_at = None
        item.status = status
    if due_date is not None:
        item.due_date = due_date
    if assigned_to is not None:
        item.assigned_to = assigned_to
    await db.flush()
    return item


async def delete_action_item(
    db: AsyncSession, item: AccidentActionItem,
) -> None:
    """Default položku nelze smazat (jen archivovat přes cancelled)."""
    if item.is_default:
        raise ValueError("Výchozí položku nelze smazat — můžete ji jen označit jako cancelled.")
    await db.delete(item)
    await db.flush()


# ── Photos ──────────────────────────────────────────────────────────────────


async def list_photos(
    db: AsyncSession, accident_id: uuid.UUID, tenant_id: uuid.UUID,
) -> list[AccidentPhoto]:
    res = await db.execute(
        select(AccidentPhoto)
        .where(
            AccidentPhoto.tenant_id == tenant_id,
            AccidentPhoto.accident_report_id == accident_id,
        )
        .order_by(AccidentPhoto.created_at)
    )
    return list(res.scalars().all())


async def get_photo(
    db: AsyncSession, photo_id: uuid.UUID, tenant_id: uuid.UUID,
) -> AccidentPhoto | None:
    res = await db.execute(
        select(AccidentPhoto).where(
            AccidentPhoto.id == photo_id,
            AccidentPhoto.tenant_id == tenant_id,
        )
    )
    return res.scalar_one_or_none()


async def count_photos(
    db: AsyncSession, accident_id: uuid.UUID, tenant_id: uuid.UUID,
) -> int:
    res = await db.execute(
        select(func.count(AccidentPhoto.id)).where(
            AccidentPhoto.tenant_id == tenant_id,
            AccidentPhoto.accident_report_id == accident_id,
        )
    )
    return int(res.scalar_one() or 0)


async def add_photo(
    db: AsyncSession,
    accident: AccidentReport,
    photo_path: str,
    caption: str | None,
    created_by: uuid.UUID,
) -> AccidentPhoto:
    photo = AccidentPhoto(
        tenant_id=accident.tenant_id,
        accident_report_id=accident.id,
        photo_path=photo_path,
        caption=caption,
        created_by=created_by,
    )
    db.add(photo)
    await db.flush()
    return photo


async def delete_photo(db: AsyncSession, photo: AccidentPhoto) -> None:
    await db.delete(photo)
    await db.flush()
