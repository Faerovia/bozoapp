"""
CSV import zaměstnanců.

Formát:
- UTF-8 s BOM (Excel kompatibilita)
- Delimiter čárka NEBO středník (auto-detect přes csv.Sniffer)
- Hlavička v prvním řádku — viz CSV_COLUMNS níže
- Jména pro FK entity (plant_name, workplace_name, job_position_name) —
  OZO nemusí znát interní UUID

Flow:
1. `generate_template_csv()` → string (pro download endpoint)
2. `import_from_csv(db, content, tenant_id, created_by)` →
   - Parsuje, validuje row-by-row
   - Každý řádek insert v SAVEPOINT (per-row rollback pokud INSERT padne)
   - Vrací ImportResult se seznamem úspěchů + chyb + případných vygenerovaných hesel

Partial import: úspěšné řádky se commitnou, chybné se přeskočí s error
hláškou. OZO dostane rich report — např. "řádek 47: duplicitní osobní číslo".
"""
from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.job_position import JobPosition
from app.models.workplace import Plant, Workplace
from app.schemas.employees import EmployeeCreateRequest
from app.services.employees import create_employee

# Název sloupce → popis pro help/template. Pořadí určuje sloupce ve vzoru.
CSV_COLUMNS: list[tuple[str, str]] = [
    ("first_name",               "Jméno (povinné)"),
    ("last_name",                "Příjmení (povinné)"),
    ("employment_type",          "Typ úvazku: hpp | dpp | dpc | externista | brigádník"),
    ("email",                    "Email (nepovinné, povinné pokud create_user_account=true)"),
    ("phone",                    "Telefon"),
    ("personal_id",              "Rodné číslo (např. 900101/1234)"),
    ("personal_number",          "Osobní číslo u zaměstnavatele (unikátní)"),
    ("birth_date",               "Datum narození YYYY-MM-DD"),
    ("hired_at",                 "Datum nástupu YYYY-MM-DD"),
    ("address_street",           "Ulice a č.p."),
    ("address_city",             "Město"),
    ("address_zip",              "PSČ"),
    ("plant_name",               "Název provozovny (musí existovat)"),
    ("workplace_name",           "Název pracoviště (musí existovat v provozovně)"),
    ("job_position_name",        "Název pracovní pozice (musí existovat)"),
    ("is_equipment_responsible", "true/false — přístup do Revizí"),
    ("create_user_account",      "true/false — vytvořit přihlašovací účet"),
    ("notes",                    "Poznámky"),
]


@dataclass
class ImportRowError:
    row: int  # 1-based, odpovídá řádku v Excelu (2 = první datový řádek)
    error: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ImportRowSuccess:
    row: int
    employee_id: uuid.UUID
    full_name: str
    email: str | None = None
    generated_password: str | None = None


@dataclass
class ImportResult:
    created: list[ImportRowSuccess] = field(default_factory=list)
    errors: list[ImportRowError] = field(default_factory=list)
    total_rows: int = 0


def generate_template_csv() -> str:
    """CSV šablona — hlavička + 1 řádek vzoru + komentář vysvětlující sloupce."""
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=",", quoting=csv.QUOTE_MINIMAL)

    header = [name for name, _ in CSV_COLUMNS]
    writer.writerow(header)

    # Vzor — typický zaměstnanec
    example = [
        "Jan",
        "Novák",
        "hpp",
        "jan.novak@firma.cz",
        "+420123456789",
        "900101/1234",
        "2024-001",
        "1990-01-01",
        "2024-03-15",
        "Dlouhá 12",
        "Praha",
        "110 00",
        "Sklad Praha",
        "Hlavní hala",
        "Skladník",
        "false",
        "true",
        "První den na ranní",
    ]
    writer.writerow(example)

    # UTF-8 BOM pro Excel (lepší české znaky)
    return "\ufeff" + buf.getvalue()


def _parse_bool(value: str) -> bool:
    v = (value or "").strip().lower()
    return v in ("true", "1", "yes", "ano", "y", "t")


def _parse_date(value: str, field_name: str) -> date | None:
    v = (value or "").strip()
    if not v:
        return None
    try:
        return date.fromisoformat(v)
    except ValueError as e:
        raise ValueError(f"{field_name}: neplatné datum '{v}' (očekávám YYYY-MM-DD)") from e


async def _resolve_plant_id(
    db: AsyncSession, name: str | None, tenant_id: uuid.UUID
) -> uuid.UUID | None:
    if not name or not name.strip():
        return None
    row = (await db.execute(
        select(Plant).where(Plant.tenant_id == tenant_id, Plant.name == name.strip())
    )).scalar_one_or_none()
    if row is None:
        raise ValueError(f"plant_name: provozovna '{name}' neexistuje")
    return row.id


async def _resolve_workplace_id(
    db: AsyncSession,
    name: str | None,
    plant_id: uuid.UUID | None,
    tenant_id: uuid.UUID,
) -> uuid.UUID | None:
    if not name or not name.strip():
        return None
    query = select(Workplace).where(
        Workplace.tenant_id == tenant_id, Workplace.name == name.strip()
    )
    if plant_id is not None:
        query = query.where(Workplace.plant_id == plant_id)
    row = (await db.execute(query)).scalar_one_or_none()
    if row is None:
        where = f" v provozovně" if plant_id else ""
        raise ValueError(f"workplace_name: pracoviště '{name}'{where} neexistuje")
    return row.id


async def _resolve_job_position_id(
    db: AsyncSession, name: str | None, tenant_id: uuid.UUID
) -> uuid.UUID | None:
    if not name or not name.strip():
        return None
    row = (await db.execute(
        select(JobPosition).where(
            JobPosition.tenant_id == tenant_id, JobPosition.name == name.strip()
        )
    )).scalar_one_or_none()
    if row is None:
        raise ValueError(f"job_position_name: pracovní pozice '{name}' neexistuje")
    return row.id


async def _row_to_create_request(
    db: AsyncSession, row: dict[str, str], tenant_id: uuid.UUID
) -> EmployeeCreateRequest:
    """Převede parsovaný CSV řádek na validovaný CreateRequest."""
    plant_id = await _resolve_plant_id(db, row.get("plant_name"), tenant_id)
    workplace_id = await _resolve_workplace_id(
        db, row.get("workplace_name"), plant_id, tenant_id
    )
    job_position_id = await _resolve_job_position_id(
        db, row.get("job_position_name"), tenant_id
    )

    return EmployeeCreateRequest(
        first_name=(row.get("first_name") or "").strip(),
        last_name=(row.get("last_name") or "").strip(),
        employment_type=(row.get("employment_type") or "hpp").strip() or "hpp",  # type: ignore[arg-type]
        email=(row.get("email") or "").strip() or None,
        phone=(row.get("phone") or "").strip() or None,
        personal_id=(row.get("personal_id") or "").strip() or None,
        personal_number=(row.get("personal_number") or "").strip() or None,
        birth_date=_parse_date(row.get("birth_date", ""), "birth_date"),
        hired_at=_parse_date(row.get("hired_at", ""), "hired_at"),
        address_street=(row.get("address_street") or "").strip() or None,
        address_city=(row.get("address_city") or "").strip() or None,
        address_zip=(row.get("address_zip") or "").strip() or None,
        plant_id=plant_id,
        workplace_id=workplace_id,
        job_position_id=job_position_id,
        is_equipment_responsible=_parse_bool(row.get("is_equipment_responsible", "")),
        create_user_account=_parse_bool(row.get("create_user_account", "")),
        notes=(row.get("notes") or "").strip() or None,
    )


def _strip_bom(content: str) -> str:
    return content.lstrip("\ufeff")


def _sniff_dialect(content_sample: str) -> csv.Dialect:
    """Detekce delimiteru (, nebo ;)."""
    try:
        return csv.Sniffer().sniff(content_sample, delimiters=",;")
    except csv.Error:
        # Fallback na comma
        class _Default(csv.excel):
            pass
        return _Default()


async def import_from_csv(
    db: AsyncSession,
    content: str,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
) -> ImportResult:
    """
    Hlavní import funkce. Vrací ImportResult se seznamem úspěchů a chyb.

    Validace a insert probíhají v per-row savepointu — úspěšné řádky se
    commitnou i když jiné selžou (partial import).
    """
    result = ImportResult()

    content = _strip_bom(content)
    if not content.strip():
        return result

    dialect = _sniff_dialect(content[:1024])
    reader = csv.DictReader(io.StringIO(content), dialect=dialect)

    for excel_row_num, raw_row in enumerate(reader, start=2):
        result.total_rows += 1
        # Přeskoč úplně prázdné řádky (Excel občas přidává)
        if not any((v or "").strip() for v in raw_row.values()):
            result.total_rows -= 1
            continue

        try:
            create_req = await _row_to_create_request(db, raw_row, tenant_id)
        except (ValueError, ValidationError) as e:
            result.errors.append(ImportRowError(
                row=excel_row_num,
                error=str(e),
                raw={k: (v or "")[:100] for k, v in raw_row.items()},
            ))
            continue

        # Per-row savepoint — když INSERT padne (unique constraint, FK cizí
        # tenant...), rollback na savepoint a pokračujeme s dalším řádkem.
        try:
            async with db.begin_nested():
                employee, generated_password = await create_employee(
                    db, create_req, tenant_id, created_by
                )
                result.created.append(ImportRowSuccess(
                    row=excel_row_num,
                    employee_id=employee.id,
                    full_name=f"{employee.first_name} {employee.last_name}".strip(),
                    email=employee.email,
                    generated_password=generated_password,
                ))
        except Exception as e:  # noqa: BLE001
            # FastAPI HTTPException má .detail, ostatní použijeme str()
            err_msg = getattr(e, "detail", None) or str(e) or e.__class__.__name__
            result.errors.append(ImportRowError(
                row=excel_row_num,
                error=str(err_msg),
                raw={k: (v or "")[:100] for k, v in raw_row.items()},
            ))

    return result
