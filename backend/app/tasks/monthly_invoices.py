"""
Měsíční vystavení faktur.

Spouští se 1. dne každého měsíce (cron / systemd timer). Pro každého aktivního
tenanta s billing_type IN (monthly, yearly, per_employee) vygeneruje fakturu
za předchozí kalendářní měsíc, vyrenderuje PDF, uloží do UPLOAD_DIR/invoices
a pošle email na recipient_snapshot.email.

Spouštění:
    python -m app.tasks.monthly_invoices

Idempotence: cron pojede jen jednou měsíčně. Případná duplicita by vytvořila
faktury s vyšším pořadím (číslo se inkrementuje atomicky), ale duplicitní
emaily by šly. Doporučení: NESPOUŠTĚT manuálně po cronu — místo toho použít
admin endpoint /admin/invoices (manuální vystavení per-tenant).
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.services.invoice_delivery import deliver_invoice
from app.services.invoicing import generate_monthly_invoices

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("monthly_invoices")


async def main(today: date | None = None) -> int:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session() as db:
        async with db.begin():
            await db.execute(
                text("SELECT set_config('app.is_superadmin', 'true', true)")
            )
            invoices = await generate_monthly_invoices(db, today=today)
            log.info("Vystaveno %d faktur.", len(invoices))

            for inv in invoices:
                try:
                    await deliver_invoice(db, inv)
                    log.info(
                        "Doručena faktura %s (tenant %s, %s %s)",
                        inv.invoice_number, inv.tenant_id,
                        inv.total, inv.currency,
                    )
                except Exception as exc:
                    log.exception(
                        "Chyba při doručení faktury %s: %s",
                        inv.invoice_number, exc,
                    )

    await engine.dispose()
    return len(invoices)


if __name__ == "__main__":
    count = asyncio.run(main())
    sys.exit(0 if count >= 0 else 1)
