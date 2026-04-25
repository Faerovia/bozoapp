"""
CSV import zařízení (Revize) — analogicky s employee_import.

Sloupce CSV:
    title              povinný (název zařízení)
    plant_name         povinný (case-sensitive match na Plant.name)
    device_type        povinný (elektro/hromosvody/plyn/kotle/tlakove_nadoby/vytahy/spalinove_cesty)
    device_code        volitelný (interní ID)
    location           volitelný (upřesnění umístění)
    valid_months       povinný (perioda v měsících, > 0)
    last_revised_at    volitelný (YYYY-MM-DD; pokud zadáno, vytvoří se i 1. record)
    technician_name    volitelný
    technician_email   volitelný
    technician_phone   volitelný
    notes              volitelný
"""
from __future__ import annotations

import csv
import io
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.revision import Revision, RevisionRecord
from app.models.workplace import Plant

CSV_COLUMNS: list[tuple[str, str]] = [
    ("title", "Název zařízení (povinné)"),
    ("plant_name", "Název provozovny (povinné, musí existovat)"),
    (
        "device_type",
        "Typ: elektro / hromosvody / plyn / kotle / tlakove_nadoby / vytahy / spalinove_cesty",
    ),
    ("device_code", "Interní ID zařízení"),
    ("location", "Upřesnění umístění (např. 'Hala A — místnost 105')"),
    ("valid_months", "Periodicita revizí v měsících (povinné)"),
    ("last_revised_at", "Datum poslední revize (YYYY-MM-DD, volitelné)"),
    ("technician_name", "Jméno revizního technika"),
    ("technician_email", "E-mail revizního technika"),
    ("technician_phone", "Telefon revizního technika"),
    ("notes", "Poznámky"),
]

VALID_DEVICE_TYPES = frozenset({
    "elektro", "hromosvody", "plyn", "kotle",
    "tlakove_nadoby", "vytahy", "spalinove_cesty",
})


@dataclass
class ImportRowResult:
    row_index: int
    success: bool
    revision_id: uuid.UUID | None = None
    title: str | None = None
    error: str | None = None


@dataclass
class ImportSummary:
    total_rows: int
    created_count: int
    failed_count: int
    rows: list[ImportRowResult]


def generate_template_csv() -> str:
    """CSV šablona s hlavičkou + 2 vzorovými řádky."""
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=",", quoting=csv.QUOTE_MINIMAL)

    header = [name for name, _ in CSV_COLUMNS]
    writer.writerow(header)

    # Vzor 1 — elektrorozvaděč
    writer.writerow([
        "Hlavní rozvaděč R1",
        "Provozovna Praha",
        "elektro",
        "RZV-001",
        "Hala A, 1. patro",
        "60",
        "2024-01-15",
        "Ing. Novák",
        "novak@revize.cz",
        "+420603123456",
        "Pravidelná revize dle vyhl. 50/1978",
    ])
    # Vzor 2 — výtah
    writer.writerow([
        "Mostový jeřáb 5t",
        "Provozovna Praha",
        "vytahy",
        "MJ-5T",
        "Hala B",
        "12",
        "",
        "Servis Eltech",
        "info@eltech.cz",
        "+420604111222",
        "",
    ])

    return "\ufeff" + buf.getvalue()


def _parse_date(value: str, field_name: str) -> date | None:
    v = (value or "").strip()
    if not v:
        return None
    try:
        return datetime.strptime(v, "%Y-%m-%d").date()
    except ValueError as e:
        raise ValueError(
            f"{field_name}: neplatný formát data '{v}' (očekáván YYYY-MM-DD)"
        ) from e


def _strip_bom(content: str) -> str:
    return content.lstrip("\ufeff")


def _sniff_dialect(content_sample: str) -> type[csv.Dialect]:
    try:
        return csv.Sniffer().sniff(content_sample, delimiters=",;\t")
    except csv.Error:
        return csv.excel


async def _resolve_plant(
    db: AsyncSession, name: str, tenant_id: uuid.UUID,
) -> Plant:
    res = await db.execute(
        select(Plant).where(
            Plant.tenant_id == tenant_id,
            Plant.name == name,
            Plant.status == "active",
        )
    )
    plant = res.scalar_one_or_none()
    if plant is None:
        raise ValueError(f"plant_name: provozovna '{name}' v evidenci neexistuje")
    return plant


async def _add_months(d: date, months: int) -> date:
    import calendar
    month = d.month + months
    year = d.year + (month - 1) // 12
    month = ((month - 1) % 12) + 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(d.day, last_day)
    return date(year, month, day)


async def _create_revision_from_row(
    db: AsyncSession,
    row: dict[str, Any],
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
) -> Revision:
    """Validuje a vytvoří 1 řádek revize. Raise ValueError při validační chybě."""
    title = (row.get("title") or "").strip()
    if not title:
        raise ValueError("title: povinné pole")
    plant_name = (row.get("plant_name") or "").strip()
    if not plant_name:
        raise ValueError("plant_name: povinné pole")
    device_type = (row.get("device_type") or "").strip().lower()
    if device_type not in VALID_DEVICE_TYPES:
        raise ValueError(
            f"device_type: '{device_type}' není validní "
            f"(povolené: {', '.join(sorted(VALID_DEVICE_TYPES))})"
        )

    valid_months_str = (row.get("valid_months") or "").strip()
    if not valid_months_str:
        raise ValueError("valid_months: povinné pole")
    try:
        valid_months = int(valid_months_str)
        if valid_months <= 0 or valid_months > 600:
            raise ValueError
    except ValueError as e:
        raise ValueError(
            f"valid_months: '{valid_months_str}' není platné kladné celé číslo"
        ) from e

    last_revised_at = _parse_date(row.get("last_revised_at", ""), "last_revised_at")

    plant = await _resolve_plant(db, plant_name, tenant_id)

    next_revision_at: date | None = None
    if last_revised_at is not None:
        next_revision_at = await _add_months(last_revised_at, valid_months)

    revision = Revision(
        tenant_id=tenant_id,
        created_by=created_by,
        title=title,
        plant_id=plant.id,
        device_code=(row.get("device_code") or "").strip() or None,
        device_type=device_type,
        location=(row.get("location") or "").strip() or None,
        last_revised_at=last_revised_at,
        valid_months=valid_months,
        next_revision_at=next_revision_at,
        technician_name=(row.get("technician_name") or "").strip() or None,
        technician_email=(row.get("technician_email") or "").strip() or None,
        technician_phone=(row.get("technician_phone") or "").strip() or None,
        notes=(row.get("notes") or "").strip() or None,
        qr_token=secrets.token_urlsafe(24).replace("-", "").replace("_", "")[:32],
    )
    db.add(revision)
    await db.flush()

    # Pokud je last_revised_at, vytvořme i 1 record (timeline)
    if last_revised_at is not None:
        record = RevisionRecord(
            tenant_id=tenant_id,
            revision_id=revision.id,
            performed_at=last_revised_at,
            technician_name=revision.technician_name,
            created_by=created_by,
        )
        db.add(record)
        await db.flush()

    return revision


async def import_from_csv(
    db: AsyncSession,
    csv_content: str,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
) -> ImportSummary:
    """
    Naparsuj CSV a importuj revize. Per-row SAVEPOINT — chyba na 1 řádku
    nezablokuje import dalších.
    """
    content = _strip_bom(csv_content)
    sample = content[:4096]
    dialect = _sniff_dialect(sample)

    reader = csv.DictReader(io.StringIO(content), dialect=dialect)
    results: list[ImportRowResult] = []
    created = 0
    failed = 0

    for idx, raw_row in enumerate(reader, start=2):  # start=2: row 1 = header
        # Normalize keys (lowercase, strip)
        row = {(k or "").strip().lower(): (v or "") for k, v in raw_row.items()}

        try:
            async with db.begin_nested():
                rev = await _create_revision_from_row(db, row, tenant_id, created_by)
            results.append(ImportRowResult(
                row_index=idx, success=True, revision_id=rev.id, title=rev.title,
            ))
            created += 1
        except Exception as e:  # noqa: BLE001
            results.append(ImportRowResult(
                row_index=idx, success=False, error=str(e),
                title=row.get("title"),
            ))
            failed += 1

    _ = datetime.now(UTC)  # noqa: F841
    return ImportSummary(
        total_rows=len(results),
        created_count=created,
        failed_count=failed,
        rows=results,
    )
