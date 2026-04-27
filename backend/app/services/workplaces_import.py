"""CSV import provozovny + pracoviště + pozice.

3 nezávislé import funkce:
- import_plants_csv          — POST /plants/import
- import_workplaces_csv      — POST /workplaces/import (FK plant_name)
- import_job_positions_csv   — POST /job-positions/import (FK workplace_name + plant_name)

Pro onboarding nového klienta: nahraj nejdřív Plants, pak Workplaces, pak Positions.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.csv_import import (
    ImportResult,
    generate_template_csv,
    import_from_csv,
    parse_int_field,
)
from app.models.job_position import JobPosition
from app.models.workplace import Plant, Workplace

# ── Plants ──────────────────────────────────────────────────────────────────

PLANT_COLUMNS = [
    ("name",          "Název provozovny (povinné, unikátní)"),
    ("ico",           "IČO firmy"),
    ("address",       "Ulice a č.p."),
    ("city",          "Město"),
    ("zip_code",      "PSČ"),
    ("plant_number",  "Číslo provozovny / interní ID"),
    ("notes",         "Poznámky"),
]
PLANT_EXAMPLE = [
    "Provozovna Praha", "12345678", "Vinohradská 1234/56",
    "Praha", "120 00", "P-001", "",
]


def generate_plants_template() -> str:
    return generate_template_csv(PLANT_COLUMNS, PLANT_EXAMPLE)


async def _process_plant_row(
    db: AsyncSession,
    row: dict[str, str],
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
) -> tuple[uuid.UUID, str]:
    name = (row.get("name") or "").strip()
    if not name:
        raise ValueError("name: název provozovny je povinný")
    # Duplicitní check
    existing = (await db.execute(
        select(Plant).where(Plant.tenant_id == tenant_id, Plant.name == name),
    )).scalar_one_or_none()
    if existing is not None:
        raise ValueError(f"name: provozovna '{name}' již existuje")
    plant = Plant(
        tenant_id=tenant_id,
        name=name,
        ico=(row.get("ico") or "").strip() or None,
        address=(row.get("address") or "").strip() or None,
        city=(row.get("city") or "").strip() or None,
        zip_code=(row.get("zip_code") or "").strip() or None,
        plant_number=(row.get("plant_number") or "").strip() or None,
        notes=(row.get("notes") or "").strip() or None,
        created_by=created_by,
    )
    db.add(plant)
    await db.flush()
    return plant.id, plant.name


async def import_plants_csv(
    db: AsyncSession, content: str, tenant_id: uuid.UUID, created_by: uuid.UUID,
) -> ImportResult:
    return await import_from_csv(
        db, content, tenant_id, created_by, processor=_process_plant_row,
    )


# ── Workplaces ──────────────────────────────────────────────────────────────

WORKPLACE_COLUMNS = [
    ("plant_name",  "Název provozovny (musí existovat) — povinné"),
    ("name",        "Název pracoviště (např. Hala A) — povinné"),
    ("notes",       "Poznámky"),
]
WORKPLACE_EXAMPLE = ["Provozovna Praha", "Hala A — provoz lis", ""]


def generate_workplaces_template() -> str:
    return generate_template_csv(WORKPLACE_COLUMNS, WORKPLACE_EXAMPLE)


async def _resolve_plant_by_name(
    db: AsyncSession, name: str, tenant_id: uuid.UUID,
) -> Plant:
    if not name.strip():
        raise ValueError("plant_name: název provozovny je povinný")
    plant = (await db.execute(
        select(Plant).where(
            Plant.tenant_id == tenant_id, Plant.name == name.strip(),
        ),
    )).scalar_one_or_none()
    if plant is None:
        raise ValueError(f"plant_name: provozovna '{name}' neexistuje")
    return plant


async def _process_workplace_row(
    db: AsyncSession,
    row: dict[str, str],
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
) -> tuple[uuid.UUID, str]:
    name = (row.get("name") or "").strip()
    if not name:
        raise ValueError("name: název pracoviště je povinný")
    plant = await _resolve_plant_by_name(db, row.get("plant_name", ""), tenant_id)
    existing = (await db.execute(
        select(Workplace).where(
            Workplace.tenant_id == tenant_id,
            Workplace.plant_id == plant.id,
            Workplace.name == name,
        ),
    )).scalar_one_or_none()
    if existing is not None:
        raise ValueError(
            f"name: pracoviště '{name}' v provozovně '{plant.name}' už existuje",
        )
    wp = Workplace(
        tenant_id=tenant_id,
        plant_id=plant.id,
        name=name,
        notes=(row.get("notes") or "").strip() or None,
        created_by=created_by,
    )
    db.add(wp)
    await db.flush()
    return wp.id, f"{plant.name} — {wp.name}"


async def import_workplaces_csv(
    db: AsyncSession, content: str, tenant_id: uuid.UUID, created_by: uuid.UUID,
) -> ImportResult:
    return await import_from_csv(
        db, content, tenant_id, created_by, processor=_process_workplace_row,
    )


# ── Job Positions ───────────────────────────────────────────────────────────

JOB_POSITION_COLUMNS = [
    ("plant_name",                  "Název provozovny (povinné)"),
    ("workplace_name",              "Název pracoviště v provozovně (povinné)"),
    ("name",                        "Název pozice (např. Soustružník) — povinné"),
    ("description",                 "Popis pozice"),
    ("work_category",               "Kategorie práce: 1 | 2 | 2R | 3 | 4 (volitelné)"),
    ("medical_exam_period_months",  "Lhůta lékařské prohlídky v měsících (volitelné)"),
    ("skip_vstupni_exam",           "true/false — opt-out vstupní prohlídky (jen cat 1)"),
    ("notes",                       "Poznámky"),
]
JOB_POSITION_EXAMPLE = [
    "Provozovna Praha", "Hala A — provoz lis", "Soustružník",
    "Obsluha CNC soustruhu Mazak", "3", "24", "false", "",
]


def generate_job_positions_template() -> str:
    return generate_template_csv(JOB_POSITION_COLUMNS, JOB_POSITION_EXAMPLE)


async def _resolve_workplace_by_name(
    db: AsyncSession, plant: Plant, name: str, tenant_id: uuid.UUID,
) -> Workplace:
    if not name.strip():
        raise ValueError("workplace_name: název pracoviště je povinný")
    wp = (await db.execute(
        select(Workplace).where(
            Workplace.tenant_id == tenant_id,
            Workplace.plant_id == plant.id,
            Workplace.name == name.strip(),
        ),
    )).scalar_one_or_none()
    if wp is None:
        raise ValueError(
            f"workplace_name: pracoviště '{name}' v provozovně '{plant.name}' neexistuje",
        )
    return wp


async def _process_job_position_row(
    db: AsyncSession,
    row: dict[str, str],
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
) -> tuple[uuid.UUID, str]:
    name = (row.get("name") or "").strip()
    if not name:
        raise ValueError("name: název pozice je povinný")
    plant = await _resolve_plant_by_name(db, row.get("plant_name", ""), tenant_id)
    workplace = await _resolve_workplace_by_name(
        db, plant, row.get("workplace_name", ""), tenant_id,
    )

    work_category = (row.get("work_category") or "").strip() or None
    if work_category and work_category not in ("1", "2", "2R", "3", "4"):
        raise ValueError(
            f"work_category: neplatná hodnota '{work_category}' (1/2/2R/3/4)",
        )

    period_months = parse_int_field(
        row.get("medical_exam_period_months"),
        "medical_exam_period_months",
    )
    if period_months is not None and (period_months < 1 or period_months > 120):
        raise ValueError(
            "medical_exam_period_months: hodnota musí být 1–120 měsíců",
        )

    skip_vstupni = (row.get("skip_vstupni_exam") or "").strip().lower() in (
        "true", "1", "yes", "ano",
    )

    pos = JobPosition(
        tenant_id=tenant_id,
        workplace_id=workplace.id,
        name=name,
        description=(row.get("description") or "").strip() or None,
        work_category=work_category,
        medical_exam_period_months=period_months,
        skip_vstupni_exam=skip_vstupni,
        notes=(row.get("notes") or "").strip() or None,
        created_by=created_by,
    )
    db.add(pos)
    await db.flush()
    return pos.id, f"{plant.name} — {workplace.name} — {pos.name}"


async def import_job_positions_csv(
    db: AsyncSession, content: str, tenant_id: uuid.UUID, created_by: uuid.UUID,
) -> ImportResult:
    return await import_from_csv(
        db, content, tenant_id, created_by, processor=_process_job_position_row,
    )
