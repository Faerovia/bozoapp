"""
Generátor BOZP/PO dokumentů.

4 templates:
- bozp_directive       (AI: Směrnice BOZP firmy ~10 stran)
- training_outline     (AI: Osnova školení BOZP per pozice)
- revision_schedule    (data-only: harmonogram revizí jako MD tabulka)
- risk_categorization  (data-only: kategorie rizik z RFA)

AI vol\u00e1 \"\"sdílený platformový klíč\"\" (settings.anthropic_api_key).
Pokud klíč chybí, generátor vrací HTTPException 503.
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.validation import assert_in_tenant
from app.models.generated_document import GeneratedDocument
from app.models.job_position import JobPosition
from app.models.oopp import RISK_COLUMNS as OOPP_RISK_COLS
from app.models.revision import DEVICE_TYPES, Revision
from app.models.risk_factor_assessment import RF_FIELDS, RF_LABELS, RiskFactorAssessment
from app.models.tenant import Tenant
from app.models.workplace import Plant, Workplace

log = logging.getLogger(__name__)


# ── CRUD ────────────────────────────────────────────────────────────────────


async def list_documents(
    db: AsyncSession, tenant_id: uuid.UUID,
    *,
    document_type: str | None = None,
    folder_id: uuid.UUID | None = None,
    folder_id_set: bool = False,
) -> list[GeneratedDocument]:
    """
    List documents. Pokud folder_id_set=True, filtruje na konkrétní složku
    (None = root úroveň, žádná složka). Bez folder_id_set se vrací vše.
    """
    q = (
        select(GeneratedDocument)
        .where(GeneratedDocument.tenant_id == tenant_id)
        .order_by(GeneratedDocument.created_at.desc())
    )
    if document_type:
        q = q.where(GeneratedDocument.document_type == document_type)
    if folder_id_set:
        if folder_id is None:
            q = q.where(GeneratedDocument.folder_id.is_(None))
        else:
            q = q.where(GeneratedDocument.folder_id == folder_id)
    res = await db.execute(q)
    return list(res.scalars().all())


async def get_document_by_id(
    db: AsyncSession, doc_id: uuid.UUID, tenant_id: uuid.UUID,
) -> GeneratedDocument | None:
    res = await db.execute(
        select(GeneratedDocument).where(
            GeneratedDocument.id == doc_id,
            GeneratedDocument.tenant_id == tenant_id,
        )
    )
    return res.scalar_one_or_none()


async def update_document(
    db: AsyncSession, doc: GeneratedDocument,
    *,
    title: str | None = None,
    content_md: str | None = None,
    folder_id: uuid.UUID | None = None,
    folder_id_set: bool = False,
) -> GeneratedDocument:
    if title is not None:
        doc.title = title
    if content_md is not None:
        doc.content_md = content_md
    if folder_id_set:
        if folder_id is not None:
            from app.models.document_folder import DocumentFolder
            await assert_in_tenant(
                db, DocumentFolder, folder_id, doc.tenant_id, field_name="folder_id",
            )
        doc.folder_id = folder_id
    await db.flush()
    return doc


# ── Helpers: data fetchers ───────────────────────────────────────────────────


async def _get_tenant(db: AsyncSession, tenant_id: uuid.UUID) -> Tenant:
    res = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = res.scalar_one()
    return tenant


async def _get_workplace_tree(
    db: AsyncSession, tenant_id: uuid.UUID,
) -> list[dict[str, Any]]:
    """Vrátí list provozoven s nested workplaces a pozicemi (s RFA)."""
    plants_res = await db.execute(
        select(Plant).where(
            Plant.tenant_id == tenant_id, Plant.status == "active"
        ).order_by(Plant.name)
    )
    out: list[dict[str, Any]] = []
    for plant in plants_res.scalars():
        wps_res = await db.execute(
            select(Workplace).where(
                Workplace.plant_id == plant.id, Workplace.status == "active"
            ).order_by(Workplace.name)
        )
        wp_list: list[dict[str, Any]] = []
        for wp in wps_res.scalars():
            pos_res = await db.execute(
                select(JobPosition).where(
                    JobPosition.workplace_id == wp.id,
                    JobPosition.status == "active",
                ).order_by(JobPosition.name)
            )
            positions: list[dict[str, Any]] = []
            for pos in pos_res.scalars():
                rfa_res = await db.execute(
                    select(RiskFactorAssessment).where(
                        RiskFactorAssessment.job_position_id == pos.id,
                    )
                )
                rfa = rfa_res.scalar_one_or_none()
                positions.append({
                    "name": pos.name,
                    "description": pos.description,
                    "category": rfa.category_proposed if rfa else None,
                    "rfa_ratings": (
                        {RF_LABELS[f]: getattr(rfa, f) for f in RF_FIELDS if getattr(rfa, f)}
                        if rfa else {}
                    ),
                    # Plná data pro NV 361/2007 tabulku (Excel-like layout)
                    "operator_names": (rfa.operator_names if rfa else None),
                    "worker_count": (rfa.worker_count if rfa else 0),
                    "women_count": (rfa.women_count if rfa else 0),
                    "rf_values": (
                        {f: getattr(rfa, f) for f in RF_FIELDS}
                        if rfa else dict.fromkeys(RF_FIELDS)
                    ),
                })
            wp_list.append({"name": wp.name, "notes": wp.notes, "positions": positions})
        out.append({
            "name": plant.name,
            "address": plant.address,
            "city": plant.city,
            "ico": plant.ico,
            "workplaces": wp_list,
        })
    return out


async def _get_revisions_data(
    db: AsyncSession, tenant_id: uuid.UUID,
) -> list[dict[str, Any]]:
    res = await db.execute(
        select(Revision, Plant)
        .join(Plant, Revision.plant_id == Plant.id, isouter=True)
        .where(
            Revision.tenant_id == tenant_id,
            Revision.status == "active",
        )
        .order_by(Plant.name, Revision.title)
    )
    out: list[dict[str, Any]] = []
    for rev, plant in res.all():
        out.append({
            "title": rev.title,
            "device_code": rev.device_code,
            "device_type": rev.device_type,
            "plant": plant.name if plant else None,
            "location": rev.location,
            "last_revised_at": rev.last_revised_at.isoformat() if rev.last_revised_at else None,
            "next_revision_at": rev.next_revision_at.isoformat() if rev.next_revision_at else None,
            "valid_months": rev.valid_months,
            "due_status": rev.due_status,
            "technician": rev.technician_name or rev.contractor,
        })
    return out


# ── Generators: data-only (bez AI) ──────────────────────────────────────────


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    """Render simple Markdown table."""
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for r in rows:
        lines.append("| " + " | ".join(str(c) if c is not None else "—" for c in r) + " |")
    return "\n".join(lines)


def _device_type_label(dt: str | None) -> str:
    labels = {
        "elektro": "Elektrická zařízení",
        "hromosvody": "Hromosvody",
        "plyn": "Plynová zařízení",
        "kotle": "Kotle",
        "tlakove_nadoby": "Tlakové nádoby",
        "vytahy": "Zdvihací zařízení",
        "spalinove_cesty": "Spalinové cesty",
    }
    return labels.get(dt or "", dt or "—")


async def _gen_revision_schedule(
    db: AsyncSession, tenant_id: uuid.UUID, params: dict[str, Any],
) -> tuple[str, str]:
    """Harmonogram revizí — data-only export. Vrátí (title, content_md)."""
    tenant = await _get_tenant(db, tenant_id)
    revisions = await _get_revisions_data(db, tenant_id)

    today = datetime.now(UTC).date().isoformat()
    title = f"Harmonogram revizí — {tenant.name}"

    md = [
        "# Harmonogram revizí zařízení",
        f"**{tenant.name}**",
        "",
        f"Vystaveno: {today}",
        "",
        "---",
        "",
    ]

    if not revisions:
        md.append("*Žádná aktivní zařízení v evidenci.*")
        return title, "\n".join(md)

    # Group by plant
    by_plant: dict[str, list[dict[str, Any]]] = {}
    for r in revisions:
        plant = r["plant"] or "(bez provozovny)"
        by_plant.setdefault(plant, []).append(r)

    for plant_name in sorted(by_plant):
        md.append(f"## {plant_name}")
        md.append("")
        rows = []
        for r in by_plant[plant_name]:
            rows.append([
                r["title"] + (f" ({r['device_code']})" if r['device_code'] else ""),
                _device_type_label(r["device_type"]),
                r["last_revised_at"] or "—",
                r["next_revision_at"] or "—",
                {"overdue": "🚨 PO TERMÍNU", "due_soon": "⚠ blíží se",
                 "ok": "OK", "no_schedule": "—"}.get(r["due_status"], r["due_status"]),
                r["technician"] or "—",
            ])
        md.append(_md_table(
            ["Zařízení", "Typ", "Poslední revize", "Další revize", "Stav", "Technik"],
            rows,
        ))
        md.append("")

    overdue_count = sum(1 for r in revisions if r["due_status"] == "overdue")
    due_soon_count = sum(1 for r in revisions if r["due_status"] == "due_soon")
    md.append("---")
    md.append(
        f"**Celkem zařízení:** {len(revisions)}   |   "
        f"**Po termínu:** {overdue_count}   |   "
        f"**Blíží se termín:** {due_soon_count}"
    )

    return title, "\n".join(md)


# Kompaktní zkratky RF pro Excel-like tabulku (musí se vejít do landscape A4)
_RF_SHORT_LABELS = {
    "rf_prach":       "Prach",
    "rf_chem":        "Chem.",
    "rf_hluk":        "Hluk",
    "rf_vibrace":     "Vibr.",
    "rf_zareni":      "Záření",
    "rf_tlak":        "Tlak",
    "rf_fyz_zatez":   "Fyz.z.",
    "rf_prac_poloha": "Poloha",
    "rf_teplo":       "Teplo",
    "rf_chlad":       "Chlad",
    "rf_psych":       "Psych.",
    "rf_zrak":        "Zrak",
    "rf_bio":         "Bio",
}


async def _gen_operating_log_summary(
    db: AsyncSession, tenant_id: uuid.UUID, params: dict[str, Any],
) -> tuple[str, str]:
    """Souhrn provozních deníků zařízení tenantu (data-only).

    Pro každé aktivní zařízení (operating_log_devices) vypíše:
    - kategorii, název, kód, umístění, plant, periodicitu
    - definované kontrolní úkony (1-20 položek)
    - posledních 5 zápisů (datum, kontrolor, souhrnný stav, krátká poznámka)

    Cílem je tisknutelný přehled deníků pro audit (SÚIP, OIP, externí audit).
    """
    from app.models.operating_log import (
        OperatingLogDevice,
        OperatingLogEntry,
    )

    tenant = await _get_tenant(db, tenant_id)
    today = datetime.now(UTC).date().isoformat()
    title = f"Provozní deníky — souhrn — {tenant.name}"

    # Načti všechna aktivní zařízení + plant_name lookup
    devices_res = await db.execute(
        select(OperatingLogDevice).where(
            OperatingLogDevice.tenant_id == tenant_id,
            OperatingLogDevice.status == "active",
        ).order_by(OperatingLogDevice.category, OperatingLogDevice.title)
    )
    devices = list(devices_res.scalars().all())

    plant_ids = {d.plant_id for d in devices if d.plant_id is not None}
    plant_names: dict[uuid.UUID, str] = {}
    if plant_ids:
        plant_rows = (await db.execute(
            select(Plant).where(Plant.id.in_(plant_ids))
        )).scalars().all()
        plant_names = {p.id: p.name for p in plant_rows}

    # Mapování kategorie → human label
    cat_labels = {
        "vzv": "Vysokozdvižné vozíky (VZV)",
        "kotelna": "Kotelny",
        "tlakova_nadoba": "Tlakové nádoby (TNS)",
        "jerab": "Jeřáby a zdvihadla",
        "eps": "Elektrická požární signalizace (EPS)",
        "sprinklery": "Stabilní hasicí zařízení (sprinklery)",
        "cov": "Čističky odpadních vod / Odlučovače",
        "diesel": "Náhradní zdroje (Dieselagregáty)",
        "regaly_sklad": "Regálové systémy (sklady)",
        "vytah": "Výtahy (osobní/nákladní)",
        "stroje_riziko": "Stroje s vyšším rizikem (lisy, pily)",
        "other": "Jiné",
    }
    period_labels = {
        "daily": "Denně",
        "weekly": "Týdně",
        "monthly": "Měsíčně",
        "shift": "Před každou směnou",
        "other": "Jiné",
    }
    status_labels = {"yes": "ANO", "no": "NE", "conditional": "Podmíněný"}

    md: list[str] = [
        "# Provozní deníky technických zařízení — souhrn",
        "",
        "_dle NV 168/2002 Sb., NV 378/2001 Sb., vyhl. 91/1993 Sb. atd._",
        "",
        f"**Firma:** {tenant.billing_company_name or tenant.name}",
    ]
    if tenant.billing_ico:
        md.append(f"**IČO:** {tenant.billing_ico}")
    md.append("")
    md.append(f"_Vystaveno: {today}_  ·  Celkem zařízení: **{len(devices)}**")
    md.append("")
    md.append("---")
    md.append("")

    if not devices:
        md.append("*Žádné aktivní provozní deníky.*")
        return title, "\n".join(md)

    # Skupina podle kategorie
    by_cat: dict[str, list[OperatingLogDevice]] = {}
    for d in devices:
        by_cat.setdefault(d.category, []).append(d)

    for cat in sorted(by_cat.keys()):
        cat_devices = by_cat[cat]
        md.append(f"## {cat_labels.get(cat, cat)} ({len(cat_devices)})")
        md.append("")
        for d in cat_devices:
            plant_name = plant_names.get(d.plant_id) if d.plant_id else None
            md.append(f"### {d.title}")
            meta = []
            if d.device_code:
                meta.append(f"Kód: **{d.device_code}**")
            if plant_name:
                meta.append(f"Provozovna: **{plant_name}**")
            if d.location:
                meta.append(f"Umístění: {d.location}")
            meta.append(f"Periodicita: **{period_labels.get(d.period, d.period)}**")
            if d.period_note:
                meta.append(f"({d.period_note})")
            md.append(" · ".join(meta))
            md.append("")

            if d.check_items:
                md.append("**Kontrolní úkony:**")
                for i, item in enumerate(d.check_items, 1):
                    md.append(f"{i}. {item}")
                md.append("")

            # Posledních 5 zápisů
            entries_res = await db.execute(
                select(OperatingLogEntry)
                .where(
                    OperatingLogEntry.tenant_id == tenant_id,
                    OperatingLogEntry.device_id == d.id,
                )
                .order_by(OperatingLogEntry.performed_at.desc())
                .limit(5)
            )
            entries = list(entries_res.scalars().all())
            if entries:
                md.append("**Poslední zápisy:**")
                md.append("")
                rows = []
                for e in entries:
                    yes_n = sum(1 for s in e.capable_items if s == "yes")
                    cond_n = sum(1 for s in e.capable_items if s == "conditional")
                    no_n = sum(1 for s in e.capable_items if s == "no")
                    items_summary = (
                        f"ANO {yes_n}"
                        + (f" / Podm. {cond_n}" if cond_n else "")
                        + (f" / NE {no_n}" if no_n else "")
                    )
                    rows.append([
                        e.performed_at.isoformat(),
                        e.performed_by_name,
                        status_labels.get(e.overall_status, e.overall_status),
                        items_summary,
                        (e.notes or "").replace("\n", " ")[:60] or "—",
                    ])
                md.append(_md_table(
                    ["Datum", "Kontroloval", "Souhrn", "Položky", "Poznámka"],
                    rows,
                ))
                md.append("")
            else:
                md.append("_Žádné zápisy v deníku._")
                md.append("")

            md.append("---")
            md.append("")

    return title, "\n".join(md)


async def _gen_risk_categorization(
    db: AsyncSession, tenant_id: uuid.UUID, params: dict[str, Any],
    created_by: uuid.UUID | None = None,
) -> tuple[str, str]:
    """Seznam rizikových faktorů pracovního prostředí (NV 361/2007 Sb.).

    Layout napodobuje Excel "Seznam rizikových faktorů": jeden řádek =
    (profese × pracoviště) s počty pracovníků, 13 hodnocení faktorů a
    návrhem kategorie. Per-provozovna sekce.

    Na konec dokumentu se přidá podpisová sekce (Jednatel + OZO).
    """
    tenant = await _get_tenant(db, tenant_id)
    tree = await _get_workplace_tree(db, tenant_id)

    # Načti jméno OZO (autora dokumentu) — pokud nelze, použij placeholder
    ozo_name = "[DOPLŇTE: jméno OZO BOZP]"
    if created_by is not None:
        from app.models.user import User
        user_res = await db.execute(select(User).where(User.id == created_by))
        user = user_res.scalar_one_or_none()
        if user is not None:
            ozo_name = user.full_name or user.email or ozo_name

    # Jednatel — z params (může vyplnit OZO před generováním) nebo placeholder
    director_name = (
        params.get("director_name") or "[DOPLŇTE: jméno jednatele]"
    )

    today = datetime.now(UTC).date().isoformat()
    title = f"Seznam rizikových faktorů — {tenant.name}"

    # Hlavička — obchodní jméno, IČO, sídlo (z billing údajů Tenant)
    md: list[str] = [
        "# Seznam rizikových faktorů pracovního prostředí",
        "",
        "_dle § 37 odst. 2 zákona č. 258/2000 Sb. a NV č. 361/2007 Sb._",
        "",
        f"**Obchodní jméno:** {tenant.billing_company_name or tenant.name}",
    ]
    if tenant.billing_ico:
        md.append(f"**IČO:** {tenant.billing_ico}")
    sidlo_parts = [
        tenant.billing_address_street,
        tenant.billing_address_zip,
        tenant.billing_address_city,
    ]
    sidlo = ", ".join(p for p in sidlo_parts if p)
    if sidlo:
        md.append(f"**Sídlo:** {sidlo}")
    md.append("")
    md.append(f"_Vystaveno: {today}_")
    md.append("")
    md.append("---")
    md.append("")

    if not tree:
        md.append("*Žádná provozovna není v evidenci.*")
        return title, "\n".join(md)

    headers = (
        ["Profese", "Pracoviště", "Obsluha", "Počet (M/Ž)"]
        + [_RF_SHORT_LABELS[f] for f in RF_FIELDS]
        + ["Kat."]
    )

    total_rows = 0
    cat3_plus = 0

    for plant in tree:
        md.append(f"## Provozovna: {plant['name']}")
        addr_parts = [plant.get("address"), plant.get("city")]
        addr = ", ".join(p for p in addr_parts if p)
        if addr:
            md.append(f"_{addr}_")
        md.append("")

        if not plant["workplaces"]:
            md.append("*Žádná pracoviště.*")
            md.append("")
            continue

        rows: list[list[str]] = []
        # Pomocný state pro mergování stejné profese po sobě jdoucích řádků
        # (vizuální zjednodušení — Markdown tabulka mergování nepodporuje
        # nativně, ale vyprázdníme buňku jak v Excelu).
        last_profese: str | None = None
        for wp in plant["workplaces"]:
            for pos in wp["positions"]:
                rf_vals: dict[str, str | None] = pos.get("rf_values", {})
                worker = pos.get("worker_count") or 0
                women = pos.get("women_count") or 0
                pocet = f"{worker}/{women}" if (worker or women) else "—"

                profese_cell = pos["name"] if pos["name"] != last_profese else ""
                last_profese = pos["name"]

                cat = pos["category"] or "—"
                if cat in ("3", "4"):
                    cat3_plus += 1
                cat_cell = f"**{cat}**" if cat != "—" else "—"

                rows.append([
                    profese_cell,
                    wp["name"],
                    pos.get("operator_names") or "",
                    pocet,
                    *[(rf_vals.get(f) or "") for f in RF_FIELDS],
                    cat_cell,
                ])
                total_rows += 1

        if not rows:
            md.append("*Žádné pozice s hodnocením.*")
            md.append("")
            continue

        md.append(_md_table(headers, rows))
        md.append("")

    # Souhrn + legenda
    md.append("---")
    md.append("")
    md.append(
        f"**Celkem hodnocených profesí:** {total_rows}  ·  "
        f"**Kategorie 3 a vyšší:** {cat3_plus}"
    )
    md.append("")
    md.append(
        "**Vysvětlivky kategorií:** "
        "1 = nejnižší riziko · 2 = přijatelné · 2R = riziková (přesahy ojediněle) · "
        "3 = zvýšené riziko · 4 = vysoké riziko"
    )
    md.append("")
    md.append(
        "**Legenda zkratek faktorů:** "
        + " · ".join(
            f"{_RF_SHORT_LABELS[f]} = {RF_LABELS[f]}" for f in RF_FIELDS
        )
    )

    # ── Podpisová sekce ─────────────────────────────────────────────────────
    md.append("")
    md.append("---")
    md.append("")
    md.append("## Podpisy")
    md.append("")
    md.append("**Vyhodnocení rizikových faktorů provedl(a):**")
    md.append("")
    md.append(f"Odborně způsobilá osoba v BOZP: **{ozo_name}**")
    md.append("")
    md.append(
        "Datum: ____________________     "
        "Podpis: _______________________________________"
    )
    md.append("")
    md.append("")
    md.append("**Schvaluje:**")
    md.append("")
    md.append(f"Jednatel společnosti: **{director_name}**")
    md.append("")
    md.append(
        "Datum: ____________________     "
        "Podpis: _______________________________________"
    )

    return title, "\n".join(md)


# ── Generators: AI ──────────────────────────────────────────────────────────


def _get_anthropic_client() -> Any:
    """Lazy import — pokud `anthropic` není nainstalován / klíč chybí, raise."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY není nastaven. Generování AI dokumentů "
            "není dostupné. Nastavte v .env."
        )
    from anthropic import Anthropic
    return Anthropic(api_key=settings.anthropic_api_key)


_BOZP_SYSTEM_PROMPT = """Jsi expert na český BOZP (bezpečnost a ochrana zdraví při práci) a požární ochranu.
Tvým úkolem je generovat **profesionální, právně relevantní BOZP/PO dokumenty v češtině**
podle platné české legislativy:
- Zákon č. 262/2006 Sb. (Zákoník práce, část pátá: BOZP)
- Zákon č. 309/2006 Sb. (zajištění dalších podmínek BOZP)
- NV č. 361/2007 Sb. (kategorizace prací, ochrana zdraví)
- NV č. 390/2021 Sb. (poskytování OOPP)
- Vyhláška č. 50/1978 Sb., NV č. 194/2022 Sb. (elektro kvalifikace)
- Zákon č. 133/1985 Sb. + vyhl. 246/2001 Sb. (PO)

Pravidla:
1. Piš formálním, ale srozumitelným jazykem, používej **správnou českou právní terminologii**.
2. Cituj konkrétní paragrafy zákonů a vyhlášek tam, kde je to relevantní.
3. Strukturu dej do nadpisů `##` a `###`. Používej Markdown bullety a tabulky.
4. **Nevymýšlej si data, která nejsou v inputu** — pokud chybí, použij placeholder
   `[DOPLŇTE: …]`.
5. Dokument musí obstát při kontrole SÚIP nebo OIP."""


async def _gen_bozp_directive(
    db: AsyncSession, tenant_id: uuid.UUID, params: dict[str, Any],
    created_by: uuid.UUID,
) -> tuple[str, str, int, int]:
    """Směrnice BOZP firmy — AI generated. Vrátí (title, content_md, in_tokens, out_tokens)."""
    tenant = await _get_tenant(db, tenant_id)
    tree = await _get_workplace_tree(db, tenant_id)

    # OZO jméno (z params, jinak placeholder)
    ozo_name = params.get("ozo_name") or "[DOPLŇTE: jméno OZO]"

    today = datetime.now(UTC).date().isoformat()
    title = f"Směrnice BOZP — {tenant.name}"

    # Sestaveno data input pro AI
    plants_summary = []
    for plant in tree:
        wps = []
        for wp in plant["workplaces"]:
            poses = [
                f"{p['name']} (kat. {p['category'] or '?'})"
                for p in wp["positions"]
            ]
            wps.append(f"{wp['name']}: {', '.join(poses) if poses else 'žádné pozice'}")
        addr = ", ".join(p for p in [plant.get("address"), plant.get("city")] if p)
        plants_summary.append(
            f"- **{plant['name']}** ({addr or 'bez adresy'}) — pracoviště: {'; '.join(wps) if wps else 'žádná'}"
        )

    user_msg = f"""Vygeneruj kompletní **Směrnici BOZP** pro firmu:

**Název:** {tenant.name}
**IČO:** {(tree[0].get('ico') if tree else None) or '[DOPLŇTE]'}
**Provozovny a pracoviště:**
{chr(10).join(plants_summary) if plants_summary else 'Žádné provozovny nejsou v evidenci.'}
**Odborně způsobilá osoba (OZO):** {ozo_name}
**Datum vystavení:** {today}

Struktura dokumentu (cca 8-12 stran):

1. **Úvod a účel směrnice** (odkaz na §103 ZP, §349 ZP)
2. **Působnost a závaznost**
3. **Povinnosti zaměstnavatele** (vyhodnocení rizik, OOPP, školení, lékařské
   prohlídky, evidence úrazů — dle §101-§108 ZP)
4. **Povinnosti vedoucích zaměstnanců**
5. **Povinnosti zaměstnanců**
6. **Vyhodnocení rizik** — odkaz na výše uvedené pracoviště, kategorizace prací
   dle NV 361/2007
7. **Lékařské preventivní prohlídky** (vyhl. 79/2013 Sb., periody dle kategorie)
8. **Školení BOZP** (vstupní, periodické, mimořádné — §103 odst. 2 ZP)
9. **Osobní ochranné pracovní prostředky (OOPP)** — NV 390/2021 Sb., příloha 2
10. **Evidence pracovních úrazů a nemocí z povolání** (§105 ZP, NV 201/2010)
11. **Postupy v případě úrazu / havárie**
12. **Sankce a kontroly**
13. **Závěrečná ustanovení**

Použij konkrétní pracoviště a pozice z dat výše. **Vrať čistý Markdown bez
úvodního textu typu „Zde je směrnice…"**. Začni přímo nadpisem `# Směrnice…`."""

    client = _get_anthropic_client()
    settings = get_settings()
    response = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=settings.anthropic_max_tokens,
        system=_BOZP_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    # Anthropic SDK vrací response.content jako list[ContentBlock]
    content = ""
    for block in response.content:
        if hasattr(block, "text"):
            content += block.text

    in_tokens = response.usage.input_tokens
    out_tokens = response.usage.output_tokens

    log.info(
        "Generated BOZP directive for %s — tokens in=%d out=%d",
        tenant.name, in_tokens, out_tokens,
    )

    return title, content, in_tokens, out_tokens


async def _gen_training_outline(
    db: AsyncSession, tenant_id: uuid.UUID, params: dict[str, Any],
    created_by: uuid.UUID,
) -> tuple[str, str, int, int]:
    """Osnova školení BOZP per pozice — AI."""
    position_id_str = params.get("position_id")
    if not position_id_str:
        raise ValueError("training_outline vyžaduje params.position_id")
    position_id = uuid.UUID(position_id_str)

    await assert_in_tenant(db, JobPosition, position_id, tenant_id, field_name="position_id")

    pos_res = await db.execute(
        select(JobPosition).where(JobPosition.id == position_id)
    )
    pos = pos_res.scalar_one()

    # Workplace + plant
    wp_res = await db.execute(
        select(Workplace, Plant)
        .join(Plant, Workplace.plant_id == Plant.id)
        .where(Workplace.id == pos.workplace_id)
    )
    wp_row = wp_res.first()
    wp_name = wp_row[0].name if wp_row else "?"
    plant_name = wp_row[1].name if wp_row else "?"

    rfa_res = await db.execute(
        select(RiskFactorAssessment).where(
            RiskFactorAssessment.job_position_id == position_id
        )
    )
    rfa = rfa_res.scalar_one_or_none()

    risk_factors_str = "(žádná hodnocení)"
    if rfa:
        risks = [f"{RF_LABELS[f]}: kategorie {getattr(rfa, f)}" for f in RF_FIELDS if getattr(rfa, f)]
        risk_factors_str = "\n".join(f"- {r}" for r in risks) or "(bez identifikovaných faktorů)"

    tenant = await _get_tenant(db, tenant_id)
    title = f"Osnova školení BOZP — {pos.name}"

    user_msg = f"""Vygeneruj **osnovu vstupního školení BOZP** pro konkrétní pracovní pozici:

**Firma:** {tenant.name}
**Provozovna:** {plant_name}
**Pracoviště:** {wp_name}
**Pozice:** {pos.name}
**Kategorie práce:** {(rfa.category_proposed if rfa else 'neurčena')}

**Identifikovaná rizika (z hodnocení rizikových faktorů):**
{risk_factors_str}

Osnova má sloužit jako **podklad pro OZO při školení** a obsahovat:
1. Cíl školení
2. Právní rámec (relevantní zákony pro tuto pozici)
3. Specifická rizika pracoviště (vycházej z faktorů výše)
4. Bezpečné pracovní postupy
5. OOPP — co tato pozice musí používat
6. Postupy v případě nehody / úrazu
7. Kontakty (OZO, lékař, IZS)
8. Test ověření znalostí — 5-10 otázek s 4 možnostmi odpovědí, jen jedna správná
   (formát: `**Otázka:** ... A) ... B) ... C) ... D) ...  **Správně: B**`)

Vrať čistý Markdown, začni nadpisem `# Osnova školení BOZP — …`."""

    client = _get_anthropic_client()
    settings = get_settings()
    response = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=settings.anthropic_max_tokens,
        system=_BOZP_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    content = ""
    for block in response.content:
        if hasattr(block, "text"):
            content += block.text

    return title, content, response.usage.input_tokens, response.usage.output_tokens


# ── Generator: Hodnocení rizik (per scope, batch-friendly) ──────────────────


_RA_LEVEL_LABEL = {
    "low": "Nízká",
    "medium": "Střední",
    "high": "Vysoká",
    "critical": "Kritická",
}

_RA_STATUS_LABEL = {
    "draft": "Návrh",
    "open": "Otevřené",
    "in_progress": "Řešeno",
    "mitigated": "Zmírněno",
    "accepted": "Akceptováno",
    "archived": "Archivováno",
}

_CONTROL_TYPE_LABEL = {
    "elimination": "Eliminace",
    "substitution": "Substituce",
    "engineering": "Inženýrské opatření",
    "administrative": "Administrativní opatření",
    "ppe": "OOPP",
}

_MEASURE_STATUS_LABEL = {
    "planned": "Plánováno",
    "in_progress": "Probíhá",
    "done": "Hotovo",
    "cancelled": "Zrušeno",
}


async def _gen_risk_assessment_for_scope(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    scope_type: str,
    scope_id: uuid.UUID,
) -> tuple[str, str] | None:
    """Vygeneruje markdown dokument se souhrnem všech aktivních RA pro daný
    scope (position/workplace/plant). Vrátí (title, content_md) nebo None
    pokud pro scope neexistuje žádná RA.
    """
    from app.models.oopp import OOPP_RISK_COLUMN_LABELS as RA_OOPP_LABELS
    from app.models.risk_assessment import RiskAssessment, RiskMeasure

    if scope_type not in ("position", "workplace", "plant"):
        raise ValueError(f"Neplatný scope_type: {scope_type}")

    # Resolve název scope (pro title + heading)
    scope_label = "—"
    parent_label = ""
    if scope_type == "position":
        pos = (await db.execute(
            select(JobPosition).where(
                JobPosition.id == scope_id,
                JobPosition.tenant_id == tenant_id,
            ),
        )).scalar_one_or_none()
        if pos is None:
            return None
        scope_label = pos.name
        wp = (await db.execute(
            select(Workplace, Plant)
            .join(Plant, Workplace.plant_id == Plant.id)
            .where(Workplace.id == pos.workplace_id),
        )).first()
        if wp is not None:
            parent_label = f"{wp[1].name} → {wp[0].name}"
    elif scope_type == "workplace":
        wp_row = (await db.execute(
            select(Workplace, Plant)
            .join(Plant, Workplace.plant_id == Plant.id)
            .where(
                Workplace.id == scope_id,
                Workplace.tenant_id == tenant_id,
            ),
        )).first()
        if wp_row is None:
            return None
        scope_label = wp_row[0].name
        parent_label = wp_row[1].name
    else:  # plant
        plant = (await db.execute(
            select(Plant).where(
                Plant.id == scope_id,
                Plant.tenant_id == tenant_id,
            ),
        )).scalar_one_or_none()
        if plant is None:
            return None
        scope_label = plant.name

    # Načíst všechny aktivní RA pro daný scope
    ra_query = (
        select(RiskAssessment)
        .where(
            RiskAssessment.tenant_id == tenant_id,
            RiskAssessment.scope_type == scope_type,
            RiskAssessment.status != "archived",
        )
        .order_by(RiskAssessment.created_at)
    )
    if scope_type == "position":
        ra_query = ra_query.where(RiskAssessment.job_position_id == scope_id)
    elif scope_type == "workplace":
        ra_query = ra_query.where(RiskAssessment.workplace_id == scope_id)
    else:
        ra_query = ra_query.where(RiskAssessment.plant_id == scope_id)

    ras = list((await db.execute(ra_query)).scalars().all())
    if not ras:
        return None

    tenant = await _get_tenant(db, tenant_id)
    today = datetime.now(UTC).date().strftime("%d. %m. %Y")

    title = f"Hodnocení rizik — {scope_label}"

    md: list[str] = [
        f"# Hodnocení rizik — {scope_label}",
        "",
        f"**{tenant.name}**",
        "",
    ]
    if parent_label:
        md.append(f"Lokalita: *{parent_label}*")
        md.append("")
    md.extend([
        f"Datum vystavení: {today}",
        f"Počet hodnocených rizik: **{len(ras)}**",
        "",
        "---",
        "",
    ])

    # Souhrnná tabulka
    md.append("## Přehled rizik")
    md.append("")
    summary_rows: list[list[str]] = []
    for ra in ras:
        risk_label = ""
        if ra.oopp_risk_column is not None:
            risk_label = (
                f"{ra.oopp_risk_column}. "
                f"{RA_OOPP_LABELS.get(ra.oopp_risk_column, '')}"
            )
        else:
            risk_label = ra.hazard_category or "—"
        summary_rows.append([
            risk_label,
            ra.hazard_description[:60] + ("…" if len(ra.hazard_description) > 60 else ""),
            f"{ra.initial_probability}×{ra.initial_severity}={ra.initial_score or '—'}",
            _RA_LEVEL_LABEL.get(ra.initial_level or "", ra.initial_level or "—"),
            _RA_LEVEL_LABEL.get(ra.residual_level or "", ra.residual_level or "—"),
            _RA_STATUS_LABEL.get(ra.status, ra.status),
        ])
    md.append(_md_table(
        ["Riziko", "Popis", "P×S", "Vstupní úroveň", "Reziduální", "Stav"],
        summary_rows,
    ))
    md.append("")
    md.append("---")
    md.append("")

    # Detail každé RA + opatření
    md.append("## Detail jednotlivých rizik")
    md.append("")

    for idx, ra in enumerate(ras, start=1):
        risk_label = (
            f"{ra.oopp_risk_column}. {RA_OOPP_LABELS.get(ra.oopp_risk_column, '')}"
            if ra.oopp_risk_column is not None
            else ra.hazard_category or "—"
        )
        md.append(f"### {idx}. {risk_label}")
        md.append("")
        md.append(f"**Popis nebezpečí:** {ra.hazard_description}")
        md.append("")
        md.append(f"**Důsledky:** {ra.consequence_description}")
        md.append("")

        detail_rows: list[list[str]] = []
        detail_rows.append([
            "Pravděpodobnost / závažnost (vstupní)",
            f"{ra.initial_probability} × {ra.initial_severity} = "
            f"**{ra.initial_score or '—'}** ({_RA_LEVEL_LABEL.get(ra.initial_level or '', '—')})",
        ])
        if ra.residual_probability is not None and ra.residual_severity is not None:
            detail_rows.append([
                "Pravděpodobnost / závažnost (reziduální)",
                f"{ra.residual_probability} × {ra.residual_severity} = "
                f"**{ra.residual_score or '—'}** "
                f"({_RA_LEVEL_LABEL.get(ra.residual_level or '', '—')})",
            ])
        if ra.exposed_persons is not None:
            detail_rows.append(["Počet exponovaných osob", str(ra.exposed_persons)])
        if ra.exposure_frequency:
            detail_rows.append(["Frekvence expozice", ra.exposure_frequency])
        if ra.existing_controls:
            detail_rows.append(["Stávající opatření", ra.existing_controls])
        if ra.existing_oopp:
            detail_rows.append(["Stávající OOPP", ra.existing_oopp])
        detail_rows.append(["Stav hodnocení", _RA_STATUS_LABEL.get(ra.status, ra.status)])
        if ra.review_due_date:
            detail_rows.append([
                "Termín revize",
                ra.review_due_date.strftime("%d. %m. %Y"),
            ])

        md.append(_md_table(["Atribut", "Hodnota"], detail_rows))
        md.append("")

        # Opatření per RA
        measures = list((await db.execute(
            select(RiskMeasure).where(
                RiskMeasure.tenant_id == tenant_id,
                RiskMeasure.risk_assessment_id == ra.id,
            ).order_by(RiskMeasure.order_index, RiskMeasure.created_at),
        )).scalars().all())

        if measures:
            md.append("**Opatření:**")
            md.append("")
            measure_rows: list[list[str]] = []
            for m in measures:
                measure_rows.append([
                    _CONTROL_TYPE_LABEL.get(m.control_type, m.control_type),
                    m.description,
                    m.deadline.strftime("%d. %m. %Y") if m.deadline else "—",
                    _MEASURE_STATUS_LABEL.get(m.status, m.status),
                ])
            md.append(_md_table(
                ["Typ", "Popis", "Termín", "Stav"],
                measure_rows,
            ))
            md.append("")
        else:
            md.append("*Bez navrhovaných opatření.*")
            md.append("")

        md.append("")

    # Patička
    md.append("---")
    md.append("")
    md.append(
        "*Dokument vygenerován z evidence hodnocení rizik (ČSN ISO 45001, "
        "Zákoník práce §102). Závazná verze je v aplikaci, tento export "
        "slouží pro tisk a předání auditorovi.*",
    )

    return title, "\n".join(md)


async def generate_risk_assessment_batch(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    created_by: uuid.UUID,
    folder_id: uuid.UUID | None = None,  # noqa: ARG001 — auto-routing přebíjí
    scope_filter: str | None = None,
) -> list[GeneratedDocument]:
    """Vygeneruje sérii dokumentů 'Hodnocení rizik' — jeden per unique scope
    (pozice/pracoviště/provozovna) v tenant, kde existuje aspoň 1 aktivní RA.

    Auto-routing dokumentů do složek (doména `bozp`):
      - root složka 'Rizika' (kořenová úroveň) — auto-vytvořena pokud chybí
      - pod-složky s názvem konkrétního pracoviště — auto-vytvořeny per workplace
      - dokument scope=position  → složka pracoviště, ke kterému pozice patří
      - dokument scope=workplace → složka pracoviště
      - dokument scope=plant     → root složka 'Rizika' (bez pod-složky)

    scope_filter: omezí generování pouze na daný scope_type
    ('position'|'workplace'|'plant'). Pokud None, generují se všechny tři.

    Parameter `folder_id` je ignorován — auto-routing určuje umístění.
    """
    from app.models.risk_assessment import RiskAssessment
    from app.services.document_folders import find_or_create_folder

    valid_scopes = ("position", "workplace", "plant")
    scopes_to_process = [scope_filter] if scope_filter else list(valid_scopes)
    for s in scopes_to_process:
        if s not in valid_scopes:
            raise ValueError(f"Neplatný scope_filter: {s}")

    # Auto-vytvořit / najít root složku "Rizika" v doméně bozp
    rizika_root = await find_or_create_folder(
        db, tenant_id, created_by,
        name="Rizika", domain="bozp", parent_id=None,
    )

    # Cache pod-složek per workplace_id, ať nezakládáme duplicity
    workplace_folder_cache: dict[uuid.UUID, uuid.UUID] = {}

    async def _resolve_target_folder_id(
        scope_type: str, scope_id: uuid.UUID,
    ) -> uuid.UUID:
        """Pro daný RA scope vrátí ID cílové složky (auto-vytvořené)."""
        # Resolve workplace_id z scope
        workplace_id: uuid.UUID | None = None
        if scope_type == "position":
            pos = (await db.execute(
                select(JobPosition).where(
                    JobPosition.id == scope_id,
                    JobPosition.tenant_id == tenant_id,
                ),
            )).scalar_one_or_none()
            if pos is not None:
                workplace_id = pos.workplace_id
        elif scope_type == "workplace":
            workplace_id = scope_id

        # scope=plant nebo workplace nelze resolvit → root "Rizika"
        if workplace_id is None:
            return rizika_root.id

        # Cache hit?
        if workplace_id in workplace_folder_cache:
            return workplace_folder_cache[workplace_id]

        wp = (await db.execute(
            select(Workplace).where(
                Workplace.id == workplace_id,
                Workplace.tenant_id == tenant_id,
            ),
        )).scalar_one_or_none()
        wp_name = wp.name if wp else "Neznámé pracoviště"

        subfolder = await find_or_create_folder(
            db, tenant_id, created_by,
            name=wp_name, domain="bozp", parent_id=rizika_root.id,
        )
        workplace_folder_cache[workplace_id] = subfolder.id
        return subfolder.id

    # Najdi unique scope_id per scope_type kde existuje aspoň 1 aktivní RA
    docs: list[GeneratedDocument] = []
    for scope_type in scopes_to_process:
        fk_col = {
            "position": RiskAssessment.job_position_id,
            "workplace": RiskAssessment.workplace_id,
            "plant": RiskAssessment.plant_id,
        }[scope_type]

        ids_res = await db.execute(
            select(fk_col)
            .where(
                RiskAssessment.tenant_id == tenant_id,
                RiskAssessment.scope_type == scope_type,
                RiskAssessment.status != "archived",
                fk_col.is_not(None),
            )
            .distinct(),
        )
        scope_ids = [row[0] for row in ids_res.all() if row[0] is not None]

        for scope_id in scope_ids:
            result = await _gen_risk_assessment_for_scope(
                db, tenant_id, scope_type=scope_type, scope_id=scope_id,
            )
            if result is None:
                continue
            title, content = result

            target_folder_id = await _resolve_target_folder_id(scope_type, scope_id)

            doc = GeneratedDocument(
                tenant_id=tenant_id,
                document_type="risk_assessment",
                folder_id=target_folder_id,
                title=title,
                content_md=content,
                params={
                    "scope_type": scope_type,
                    "scope_id": str(scope_id),
                    "generated_at": datetime.now(UTC).isoformat(),
                },
                ai_input_tokens=None,
                ai_output_tokens=None,
                created_by=created_by,
            )
            db.add(doc)
            docs.append(doc)

    await db.flush()
    return docs


# ── Public API ──────────────────────────────────────────────────────────────


async def generate_document(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    document_type: str,
    params: dict[str, Any],
    created_by: uuid.UUID,
    folder_id: uuid.UUID | None = None,
) -> GeneratedDocument:
    """Vygeneruje a uloží dokument."""
    if folder_id is not None:
        from app.models.document_folder import DocumentFolder
        await assert_in_tenant(
            db, DocumentFolder, folder_id, tenant_id, field_name="folder_id",
        )

    if document_type == "revision_schedule":
        title, content = await _gen_revision_schedule(db, tenant_id, params)
        in_tokens = out_tokens = None
    elif document_type == "risk_categorization":
        title, content = await _gen_risk_categorization(
            db, tenant_id, params, created_by=created_by,
        )
        in_tokens = out_tokens = None
    elif document_type == "bozp_directive":
        title, content, in_tokens, out_tokens = await _gen_bozp_directive(
            db, tenant_id, params, created_by,
        )
    elif document_type == "training_outline":
        title, content, in_tokens, out_tokens = await _gen_training_outline(
            db, tenant_id, params, created_by,
        )
    elif document_type == "operating_log_summary":
        title, content = await _gen_operating_log_summary(db, tenant_id, params)
        in_tokens = out_tokens = None
    else:
        raise ValueError(f"Neznámý typ dokumentu: {document_type}")

    doc = GeneratedDocument(
        tenant_id=tenant_id,
        document_type=document_type,
        folder_id=folder_id,
        title=title,
        content_md=content,
        params=params,
        ai_input_tokens=in_tokens,
        ai_output_tokens=out_tokens,
        created_by=created_by,
    )
    db.add(doc)
    await db.flush()
    return doc


async def create_imported_document(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
    *,
    title: str,
    content_md: str,
    folder_id: uuid.UUID | None,
    source_filename: str | None = None,
) -> GeneratedDocument:
    """
    Uloží naimportovaný textový dokument jako GeneratedDocument typu 'imported'.
    """
    if folder_id is not None:
        from app.models.document_folder import DocumentFolder
        await assert_in_tenant(
            db, DocumentFolder, folder_id, tenant_id, field_name="folder_id",
        )
    doc = GeneratedDocument(
        tenant_id=tenant_id,
        created_by=created_by,
        folder_id=folder_id,
        document_type="imported",
        title=title,
        content_md=content_md,
        params={
            "source_filename": source_filename,
            "imported_at": datetime.now(UTC).isoformat(),
        },
    )
    db.add(doc)
    await db.flush()
    return doc


# Re-export pro testy
__all__ = [
    "DEVICE_TYPES",
    "OOPP_RISK_COLS",
    "create_imported_document",
    "generate_document",
    "get_document_by_id",
    "list_documents",
    "update_document",
]
