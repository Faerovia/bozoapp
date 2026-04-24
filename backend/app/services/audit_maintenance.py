"""
Údržba partitionů audit_log tabulky.

Funkce:
- `ensure_monthly_partitions(months_ahead=2)` — vytvoří partitions pro
  budoucí měsíce, pokud ještě neexistují. Idempotentní.
- `drop_partitions_older_than(years=5)` — smaže partitions starší než
  retention window (BOZP zákon = 5 let).

Obě jsou navržené pro volání z cronu (daily) nebo manuálně přes admin script.
Nepoužívají RLS (jsou DDL) → volat jen jako DB owner (`bozoapp`).
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _add_month(d: date) -> date:
    year = d.year + (1 if d.month == 12 else 0)
    month = 1 if d.month == 12 else d.month + 1
    return date(year, month, 1)


async def ensure_monthly_partitions(
    db: AsyncSession, months_ahead: int = 2
) -> list[str]:
    """
    Zajistí existenci partitions pro current + next N měsíců. Vrací seznam
    nově vytvořených partition jmen (pro log).
    """
    created: list[str] = []
    today = datetime.now(UTC).date()
    cursor = _month_start(today)

    for _ in range(months_ahead + 1):
        start = cursor
        end = _add_month(cursor)
        name = f"audit_log_{start.strftime('%Y_%m')}"

        # CREATE IF NOT EXISTS pro partitions není standardní → použijeme DO block
        result = await db.execute(text(f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE c.relname = '{name}' AND n.nspname = 'public'
                ) THEN
                    EXECUTE format(
                        'CREATE TABLE %I PARTITION OF audit_log FOR VALUES FROM (%L) TO (%L)',
                        '{name}', '{start.isoformat()}'::DATE, '{end.isoformat()}'::DATE
                    );
                END IF;
            END $$;
        """))
        _ = result  # DO block nevrací řádky; efekt je vidět v subsequent dotazech
        log.info("Ensured audit partition: %s", name)
        created.append(name)
        cursor = end

    return created


async def drop_partitions_older_than(
    db: AsyncSession, years: int = 5
) -> list[str]:
    """
    Drop partitions jejichž range je celý před dnes-N let.

    BOZP: úrazy 5 let, ostatní dokumenty obvykle 5-10 let → default 5.
    """
    threshold = datetime.now(UTC).date() - timedelta(days=365 * years)
    threshold_month = _month_start(threshold)

    # Najdi všechny audit_log_* partitions a vyfiltruj podle názvu (YYYY_MM)
    result = await db.execute(text("""
        SELECT c.relname
        FROM pg_inherits i
        JOIN pg_class c ON c.oid = i.inhrelid
        JOIN pg_class p ON p.oid = i.inhparent
        WHERE p.relname = 'audit_log'
          AND c.relname LIKE 'audit_log_%'
          AND c.relname NOT IN ('audit_log_default')
        ORDER BY c.relname
    """))
    partitions = [row[0] for row in result.all()]

    dropped: list[str] = []
    for name in partitions:
        # name format: audit_log_YYYY_MM
        try:
            ymd = name.removeprefix("audit_log_")
            year = int(ymd[:4])
            month = int(ymd[5:7])
            p_start = date(year, month, 1)
        except (ValueError, IndexError):
            log.warning("Could not parse partition name: %s", name)
            continue

        if p_start < threshold_month:
            log.info("Dropping expired audit partition: %s (start=%s)", name, p_start)
            await db.execute(text(f'DROP TABLE IF EXISTS "{name}"'))
            dropped.append(name)

    return dropped
