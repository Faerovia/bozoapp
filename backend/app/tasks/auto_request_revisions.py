"""
Denní cron: automatické poptávky revize.

Pro každé zařízení (Revision), kde:
- status='active'
- auto_request_enabled=true
- technician_email je vyplněný
- next_revision_at <= today + 30 days
- (auto_request_sent_at IS NULL OR auto_request_sent_at < next_revision_at - 30 days)
  → poslední poptávka odeslaná před více jak 30 dny vůči aktuálnímu termínu
    (idempotence per cyklus revize — po nové revizi se to zase pošle).

Email:
- TO: technician_email
- CC: zaměstnanci s EmployeePlantResponsibility na Revision.plant_id
- Subject: 'Poptávka revize zařízení — {title} ({plant_name})'
- Body: text s žádostí + termín + kontakty

Spouštění (cron / systemd timer):
    python -m app.tasks.auto_request_revisions

V Docker Compose lze připojit jako samostatnou run-once službu.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.email import EmailMessage, get_email_sender
from app.models.employee import Employee
from app.models.revision import EmployeePlantResponsibility, Revision
from app.models.workplace import Plant

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("auto_request_revisions")


REQUEST_HORIZON_DAYS = 30


def _build_email_body(
    revision: Revision,
    plant: Plant | None,
) -> tuple[str, str]:
    plant_name = plant.name if plant else "—"
    plant_address = ""
    if plant:
        parts = [plant.address, plant.zip_code, plant.city]
        plant_address = ", ".join(p for p in parts if p)

    subject = f"Poptávka revize: {revision.title} — {plant_name}"

    next_date = (
        revision.next_revision_at.strftime("%d. %m. %Y")
        if revision.next_revision_at else "—"
    )
    device_code = f" (kód {revision.device_code})" if revision.device_code else ""

    lines = [
        "Dobrý den,",
        "",
        "obracíme se na Vás s automatizovanou poptávkou na provedení revize",
        "níže uvedeného zařízení, jehož platná revize končí v blízké době.",
        "",
        f"Zařízení: {revision.title}{device_code}",
        f"Provozovna: {plant_name}",
    ]
    if plant_address:
        lines.append(f"Adresa:    {plant_address}")
    lines.extend([
        f"Termín další revize: {next_date}",
        "",
        "Prosíme o potvrzení termínu provedení a zaslání cenové nabídky.",
        "V kopii tohoto e-mailu jsou odpovědné osoby za zařízení v rámci",
        "naší firmy — komunikujte primárně se mnou nebo s nimi.",
        "",
        "Děkujeme.",
        "",
        "—",
        "Tato zpráva byla odeslána automaticky systémem DigitalOZO.",
    ])
    return subject, "\n".join(lines)


async def _process_due_revisions(db: AsyncSession) -> int:
    today = datetime.now(UTC).date()
    horizon = today + timedelta(days=REQUEST_HORIZON_DAYS)

    # Najdi revize splňující podmínky
    cutoff_for_resend = today - timedelta(days=REQUEST_HORIZON_DAYS)
    result = await db.execute(
        select(Revision).where(
            Revision.status == "active",
            Revision.auto_request_enabled.is_(True),
            Revision.technician_email.is_not(None),
            Revision.next_revision_at.is_not(None),
            Revision.next_revision_at <= horizon,
            Revision.next_revision_at >= today,  # neposílat pro overdue (>30 dní zpět)
            or_(
                Revision.auto_request_sent_at.is_(None),
                # Pokud poslední odeslání bylo před více než 30 dní vůči
                # aktuálnímu termínu, jde o nový cyklus revize.
                and_(
                    Revision.auto_request_sent_at.is_not(None),
                    Revision.auto_request_sent_at <= cutoff_for_resend,
                ),
            ),
        )
    )
    revisions: list[Revision] = list(result.scalars().all())
    log.info("Found %d revisions due for auto-request", len(revisions))
    if not revisions:
        return 0

    sender = get_email_sender()
    sent_count = 0

    for rev in revisions:
        plant = None
        if rev.plant_id is not None:
            plant = (await db.execute(
                select(Plant).where(Plant.id == rev.plant_id)
            )).scalar_one_or_none()

        # CC: emaily zodpovědných osob na plantu
        cc: list[str] = []
        if rev.plant_id is not None:
            resp_result = await db.execute(
                select(Employee).join(
                    EmployeePlantResponsibility,
                    EmployeePlantResponsibility.employee_id == Employee.id,
                ).where(
                    EmployeePlantResponsibility.tenant_id == rev.tenant_id,
                    EmployeePlantResponsibility.plant_id == rev.plant_id,
                    Employee.status == "active",
                )
            )
            for emp in resp_result.scalars():
                if emp.email and emp.email not in cc:
                    cc.append(emp.email)

        subject, body = _build_email_body(rev, plant)

        try:
            assert rev.technician_email is not None
            await sender.send(EmailMessage(
                to=rev.technician_email,
                subject=subject,
                body_text=body,
                cc=cc or None,
            ))
            rev.auto_request_sent_at = today
            await db.flush()
            sent_count += 1
            log.info(
                "Sent auto-request for revision %s to %s (CC %d)",
                rev.id, rev.technician_email, len(cc),
            )
        except Exception:  # noqa: BLE001
            log.exception(
                "Failed to send auto-request for revision %s", rev.id,
            )

    return sent_count


async def main() -> int:
    settings = get_settings()
    db_url = settings.migration_database_url or settings.database_url
    engine = create_async_engine(db_url, echo=False)
    async_session = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession,
    )
    async with async_session() as db, db.begin():
        await db.execute(
            text("SELECT set_config('app.is_platform_admin', 'true', true)")
        )
        sent = await _process_due_revisions(db)
    await engine.dispose()
    log.info("Done. %d auto-requests sent.", sent)
    return sent


if __name__ == "__main__":
    sent = asyncio.run(main())
    sys.exit(0 if sent >= 0 else 1)
