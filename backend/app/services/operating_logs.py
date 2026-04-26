"""Service pro Provozní deníky."""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.email import EmailMessage, get_email_sender
from app.core.validation import assert_in_tenant
from app.models.employee import Employee
from app.models.operating_log import OperatingLogDevice, OperatingLogEntry
from app.models.revision import EmployeePlantResponsibility
from app.models.user import User
from app.models.workplace import Plant, Workplace
from app.schemas.operating_logs import (
    DeviceCreateRequest,
    DeviceUpdateRequest,
    EntryCreateRequest,
)

log = logging.getLogger(__name__)


async def list_devices(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    category: str | None = None,
    status: str | None = None,
    plant_id: uuid.UUID | None = None,
) -> list[OperatingLogDevice]:
    q = (
        select(OperatingLogDevice)
        .where(OperatingLogDevice.tenant_id == tenant_id)
        .order_by(OperatingLogDevice.title)
    )
    if category:
        q = q.where(OperatingLogDevice.category == category)
    if status:
        q = q.where(OperatingLogDevice.status == status)
    if plant_id is not None:
        q = q.where(OperatingLogDevice.plant_id == plant_id)
    res = await db.execute(q)
    return list(res.scalars().all())


async def get_device(
    db: AsyncSession, device_id: uuid.UUID, tenant_id: uuid.UUID,
) -> OperatingLogDevice | None:
    res = await db.execute(
        select(OperatingLogDevice).where(
            OperatingLogDevice.id == device_id,
            OperatingLogDevice.tenant_id == tenant_id,
        )
    )
    return res.scalar_one_or_none()


async def create_device(
    db: AsyncSession,
    data: DeviceCreateRequest,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
) -> OperatingLogDevice:
    if data.plant_id is not None:
        await assert_in_tenant(db, Plant, data.plant_id, tenant_id, field_name="plant_id")
    if data.workplace_id is not None:
        await assert_in_tenant(
            db, Workplace, data.workplace_id, tenant_id, field_name="workplace_id",
        )
    device = OperatingLogDevice(
        tenant_id=tenant_id,
        created_by=created_by,
        **data.model_dump(),
    )
    db.add(device)
    await db.flush()
    return device


async def update_device(
    db: AsyncSession,
    device: OperatingLogDevice,
    data: DeviceUpdateRequest,
) -> OperatingLogDevice:
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(device, k, v)
    await db.flush()
    return device


async def get_device_by_qr_token(
    db: AsyncSession, qr_token: str, tenant_id: uuid.UUID,
) -> OperatingLogDevice | None:
    res = await db.execute(
        select(OperatingLogDevice).where(
            OperatingLogDevice.qr_token == qr_token,
            OperatingLogDevice.tenant_id == tenant_id,
        )
    )
    return res.scalar_one_or_none()


async def list_entries(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    device_id: uuid.UUID,
    *,
    limit: int = 100,
) -> list[OperatingLogEntry]:
    res = await db.execute(
        select(OperatingLogEntry)
        .where(
            OperatingLogEntry.tenant_id == tenant_id,
            OperatingLogEntry.device_id == device_id,
        )
        .order_by(OperatingLogEntry.performed_at.desc())
        .limit(limit)
    )
    return list(res.scalars().all())


async def create_entry(
    db: AsyncSession,
    data: EntryCreateRequest,
    *,
    device: OperatingLogDevice,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
    current_user: User | None = None,
) -> OperatingLogEntry:
    """Vytvoří zápis do provozního deníku.

    Pokud `current_user` není None, performed_by_name se auto-doplní ze
    jména přihlášeného uživatele (full_name OR email), pokud nebyl explicitně
    předán v `data`.

    Pokud entry.overall_capable=False → odešleme alert email zodpovědným
    osobám za vyhrazená zařízení (přes EmployeePlantResponsibility na
    device.plant_id).
    """
    # Validace: capable_items délka musí odpovídat device.check_items
    if len(data.capable_items) != len(device.check_items):
        raise ValueError(
            f"capable_items má délku {len(data.capable_items)}, "
            f"očekáváno {len(device.check_items)} (dle definovaných kontrolních úkonů)"
        )

    payload = data.model_dump()
    # Auto-fill performed_by_name z current_user, pokud nebyl explicitně zadán
    if current_user is not None and not (payload.get("performed_by_name") or "").strip():
        payload["performed_by_name"] = (
            current_user.full_name or current_user.email or "—"
        )

    entry = OperatingLogEntry(
        tenant_id=tenant_id,
        device_id=device.id,
        created_by=created_by,
        **payload,
    )
    db.add(entry)
    await db.flush()

    # Alert email pokud zařízení NENÍ plně způsobilé (NO i CONDITIONAL)
    # — best-effort, neblokuje uložení.
    if data.overall_status != "yes":
        try:
            await _send_unfit_alert(
                db, device, entry, tenant_id=tenant_id,
            )
        except Exception:  # noqa: BLE001
            log.exception(
                "Failed to send unfit alert for device %s entry %s",
                device.id, entry.id,
            )

    return entry


async def _send_unfit_alert(
    db: AsyncSession,
    device: OperatingLogDevice,
    entry: OperatingLogEntry,
    *,
    tenant_id: uuid.UUID,
) -> None:
    """Odešle alert email zodpovědným osobám za vyhrazená zařízení daného plantu.

    Příjemci (TO) = všechny aktivní zaměstnance s EmployeePlantResponsibility
    na device.plant_id. Pokud device nemá plant nebo žádné zodpovědné osoby
    nemají email, pouze logujeme a vracíme.
    """
    if device.plant_id is None:
        log.info(
            "Device %s (%s) marked unfit, ale nemá plant — alert se nepošle",
            device.id, device.title,
        )
        return

    # Vyhledej zodpovědné osoby (M:N přes EmployeePlantResponsibility)
    res = await db.execute(
        select(Employee).join(
            EmployeePlantResponsibility,
            EmployeePlantResponsibility.employee_id == Employee.id,
        ).where(
            EmployeePlantResponsibility.tenant_id == tenant_id,
            EmployeePlantResponsibility.plant_id == device.plant_id,
            Employee.status == "active",
        )
    )
    employees = list(res.scalars().all())
    recipients = [e.email for e in employees if e.email]

    if not recipients:
        log.info(
            "Device %s unfit, ale žádná zodpovědná osoba s emailem na plantu %s",
            device.id, device.plant_id,
        )
        return

    # Plant info pro tělo emailu
    plant = (await db.execute(
        select(Plant).where(Plant.id == device.plant_id)
    )).scalar_one_or_none()
    plant_name = plant.name if plant else "—"

    # Souhrn položek které nejsou ANO (zahrnuje NE i Podmíněný)
    def _label(s: str) -> str:
        return {
            "no": "NE",
            "conditional": "Podmíněný",
            "yes": "ANO",
        }.get(s, s)

    flagged_items = [
        f"  • {item} — **{_label(status)}**"
        for item, status in zip(
            device.check_items, entry.capable_items, strict=False,
        )
        if status != "yes"
    ]
    flagged_block = (
        "\n".join(flagged_items) if flagged_items
        else "  (souhrnný stav nesplněn — dílčí položky byly potvrzeny ANO)"
    )

    is_conditional = entry.overall_status == "conditional"
    if is_conditional:
        subject = (
            f"⚠ Podmíněně způsobilé zařízení: {device.title} — {plant_name}"
        )
        action_text = (
            "Zařízení LZE PODMÍNĚNĚ PROVOZOVAT — byla zjištěna závada, která "
            "neznemožňuje provoz, ale vyžaduje urychlenou nápravu. Zajistěte "
            "opravu v co nejkratším termínu a do té doby provozujte se zvýšenou "
            "opatrností v souladu s konkrétními omezeními uvedenými v poznámce."
        )
        status_label = "PODMÍNĚNĚ ZPŮSOBILÉ"
    else:
        subject = (
            f"⚠ Nezpůsobilé zařízení: {device.title} — {plant_name}"
        )
        action_text = (
            "Prosíme zajistit okamžitou nápravu nebo vyřaďte zařízení z provozu, "
            "dokud nebude obnovena plná způsobilost."
        )
        status_label = "NEZPŮSOBILÉ k provozu"

    code = f" (kód {device.device_code})" if device.device_code else ""
    perf_at = entry.performed_at.strftime("%d. %m. %Y") if entry.performed_at else "—"

    body = (
        "Dobrý den,\n\n"
        f"při kontrole zařízení **{device.title}**{code} v provozovně "
        f"„{plant_name}“ bylo zařízení označeno jako **{status_label}**.\n\n"
        f"Datum kontroly: {perf_at}\n"
        f"Kontroloval: {entry.performed_by_name}\n\n"
        f"Položky vyžadující pozornost:\n{flagged_block}\n\n"
        f"Poznámky kontrolora: {entry.notes or '—'}\n\n"
        f"{action_text}\n\n"
        "Detail najdete v aplikaci DigitalOZO → Provozní deníky.\n\n"
        "—\n"
        "Tato zpráva byla odeslána automaticky systémem DigitalOZO.\n"
    )

    sender = get_email_sender()
    # Pošli každému zvlášť (zachovává soukromí adres) — small N, lze sériově.
    for to in recipients:
        try:
            await sender.send(EmailMessage(
                to=to, subject=subject, body_text=body,
            ))
            log.info(
                "Sent unfit-device alert to %s (device=%s, entry=%s)",
                to, device.id, entry.id,
            )
        except Exception:  # noqa: BLE001
            log.exception("Failed to send unfit alert to %s", to)


# Pozn.: QR PNG generator žije v app.services.revisions.generate_qr_png
# (sdílená logika); API endpointy si ho importují přímo, není třeba re-export.
