"""Sdílené utility pro CSV import napříč moduly.

Pattern (per modul):
1. Definovat CSV_COLUMNS: list[(name, description)]
2. generate_template_csv(columns, example_row) → string
3. _row_to_create_request(row) → Pydantic model (per modul)
4. import_from_csv(db, content, tenant_id, created_by, processor) →
   ImportResult — generic loop, processor je callable per řádek

UTF-8 BOM se strippuje (Excel default), delimiter detekce přes csv.Sniffer.
Per-row savepoint: úspěšné se commitnou, chybné se přeskočí s error msg.
"""
from __future__ import annotations

import csv
import io
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ImportRowError:
    row: int
    error: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ImportRowSuccess:
    row: int
    entity_id: uuid.UUID
    label: str  # human readable identification — name/title/etc


@dataclass
class ImportResult:
    created: list[ImportRowSuccess] = field(default_factory=list)
    errors: list[ImportRowError] = field(default_factory=list)
    total_rows: int = 0


def generate_template_csv(
    columns: list[tuple[str, str]],
    example_row: list[str],
) -> str:
    """Vygeneruje CSV šablonu s hlavičkou + 1 příkladovým řádkem.

    columns: list of (column_name, description). Description se nepíše
    do CSV (nebyla by parseable jako data), ale slouží jako dokumentace
    pro generátor v UI.
    """
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=",", quoting=csv.QUOTE_MINIMAL)

    header = [name for name, _ in columns]
    writer.writerow(header)
    writer.writerow(example_row)

    return "\ufeff" + buf.getvalue()


def parse_bool(value: str | None) -> bool:
    v = (value or "").strip().lower()
    return v in ("true", "1", "yes", "ano", "y", "t")


def parse_date_field(value: str | None, field_name: str) -> date | None:
    v = (value or "").strip()
    if not v:
        return None
    try:
        return date.fromisoformat(v)
    except ValueError as e:
        raise ValueError(
            f"{field_name}: neplatné datum '{v}' (očekávám YYYY-MM-DD)",
        ) from e


def parse_int_field(value: str | None, field_name: str) -> int | None:
    v = (value or "").strip()
    if not v:
        return None
    try:
        return int(v)
    except ValueError as e:
        raise ValueError(f"{field_name}: neplatné číslo '{v}'") from e


def strip_bom(content: str) -> str:
    return content.lstrip("\ufeff")


def sniff_dialect(content_sample: str) -> type[csv.Dialect]:
    """Detekce delimiteru (, nebo ;). Excel CZ defaultně používá ;."""
    try:
        return csv.Sniffer().sniff(content_sample, delimiters=",;")
    except csv.Error:
        return csv.excel


# Processor signature: (db, row_dict, tenant_id, created_by) → (entity_id, label)
RowProcessor = Callable[
    [AsyncSession, dict[str, str], uuid.UUID, uuid.UUID],
    Awaitable[tuple[uuid.UUID, str]],
]


async def import_from_csv(
    db: AsyncSession,
    content: str,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
    *,
    processor: RowProcessor,
) -> ImportResult:
    """Generic CSV import loop s per-row savepointem.

    processor: async fce, která pro daný řádek vytvoří entitu a vrátí
    (entity_id, label). Při ValueError nebo ValidationError se řádek
    označí jako chybný, ostatní pokračují (partial import).
    """
    result = ImportResult()

    content = strip_bom(content)
    if not content.strip():
        return result

    dialect = sniff_dialect(content[:1024])
    reader = csv.DictReader(io.StringIO(content), dialect=dialect)

    for excel_row_num, raw_row in enumerate(reader, start=2):
        result.total_rows += 1
        # Přeskoč úplně prázdné řádky (Excel občas přidává)
        if not any((v or "").strip() for v in raw_row.values()):
            result.total_rows -= 1
            continue

        try:
            async with db.begin_nested():
                entity_id, label = await processor(
                    db, raw_row, tenant_id, created_by,
                )
                result.created.append(ImportRowSuccess(
                    row=excel_row_num,
                    entity_id=entity_id,
                    label=label,
                ))
        except (ValueError, ValidationError) as e:
            result.errors.append(ImportRowError(
                row=excel_row_num,
                error=str(e),
                raw={k: (v or "")[:100] for k, v in raw_row.items()},
            ))
        except Exception as e:  # noqa: BLE001
            err_msg = getattr(e, "detail", None) or str(e) or e.__class__.__name__
            result.errors.append(ImportRowError(
                row=excel_row_num,
                error=str(err_msg),
                raw={k: (v or "")[:100] for k, v in raw_row.items()},
            ))

    return result
