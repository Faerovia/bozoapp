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


async def _gen_risk_categorization(
    db: AsyncSession, tenant_id: uuid.UUID, params: dict[str, Any],
) -> tuple[str, str]:
    """Tabulka kategorie rizik per pozice — z RFA, bez AI."""
    tenant = await _get_tenant(db, tenant_id)
    tree = await _get_workplace_tree(db, tenant_id)

    today = datetime.now(UTC).date().isoformat()
    title = f"Kategorizace prací — {tenant.name}"

    md = [
        "# Kategorizace prací dle NV 361/2007 Sb.",
        f"**{tenant.name}**",
        "",
        f"Vystaveno: {today}",
        "",
        "---",
        "",
    ]

    if not tree:
        md.append("*Žádná provozovna není v evidenci.*")
        return title, "\n".join(md)

    for plant in tree:
        md.append(f"## {plant['name']}")
        addr_parts = [plant.get("address"), plant.get("city")]
        addr = ", ".join(p for p in addr_parts if p)
        if addr:
            md.append(f"_{addr}_")
        md.append("")
        if not plant["workplaces"]:
            md.append("*Žádná pracoviště.*")
            md.append("")
            continue

        for wp in plant["workplaces"]:
            md.append(f"### Pracoviště: {wp['name']}")
            md.append("")
            if not wp["positions"]:
                md.append("*Žádné pozice.*")
                md.append("")
                continue
            rows = []
            for pos in wp["positions"]:
                ratings_str = ", ".join(
                    f"{k}: {v}" for k, v in pos["rfa_ratings"].items()
                ) or "—"
                rows.append([
                    pos["name"],
                    pos["category"] or "neurčeno",
                    ratings_str,
                ])
            md.append(_md_table(
                ["Pozice", "Celková kategorie", "Hodnocení faktorů"],
                rows,
            ))
            md.append("")

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


# ── Public API ──────────────────────────────────────────────────────────────


async def generate_document(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    document_type: str,
    params: dict[str, Any],
    created_by: uuid.UUID,
) -> GeneratedDocument:
    """Vygeneruje a uloží dokument."""
    if document_type == "revision_schedule":
        title, content = await _gen_revision_schedule(db, tenant_id, params)
        in_tokens = out_tokens = None
    elif document_type == "risk_categorization":
        title, content = await _gen_risk_categorization(db, tenant_id, params)
        in_tokens = out_tokens = None
    elif document_type == "bozp_directive":
        title, content, in_tokens, out_tokens = await _gen_bozp_directive(
            db, tenant_id, params, created_by,
        )
    elif document_type == "training_outline":
        title, content, in_tokens, out_tokens = await _gen_training_outline(
            db, tenant_id, params, created_by,
        )
    else:
        raise ValueError(f"Neznámý typ dokumentu: {document_type}")

    doc = GeneratedDocument(
        tenant_id=tenant_id,
        document_type=document_type,
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
