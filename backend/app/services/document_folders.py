"""
CRUD a auto-číslování pro adresářovou strukturu dokumentace.

Číslování je automatické: nová root složka v doméně dostane code "000" / "001",
podsložka v parent="000" dostane "000.001", "000.002", atd. Každý segment
je 3-cifeřné nulou-doplněné číslo.

Pokud user smaže prostřední složku (např. "000.005") a pak přidá novou,
nová dostane next-after-max ("000.011" pokud nejvyšší existující byl "000.010").
Žádná recyklace mezer — chronologicky inkrementační.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.validation import assert_in_tenant
from app.models.document_folder import DocumentFolder

CODE_SEGMENT_WIDTH = 3  # "000" 3-cifeřné


def _format_segment(num: int) -> str:
    return str(num).zfill(CODE_SEGMENT_WIDTH)


def _next_segment(existing_codes: list[str], parent_code: str | None) -> str:
    """
    Najde příští volný segment pro daný parent.
    existing_codes = full codes všech bezprostředních potomků.
    parent_code = "000" / "000.001" / None pro root.
    """
    if parent_code is None:
        # Root level — segments jsou jen samotné code "000", "001"
        nums = []
        for c in existing_codes:
            try:
                nums.append(int(c))
            except (ValueError, TypeError):
                continue
    else:
        # Vnořená — extrahuj poslední segment za prefixem
        prefix = parent_code + "."
        nums = []
        for c in existing_codes:
            if not c.startswith(prefix):
                continue
            tail = c[len(prefix):]
            if "." in tail:
                continue   # příliš hluboko (vnuk), ignoruj
            try:
                nums.append(int(tail))
            except (ValueError, TypeError):
                continue
    next_num = (max(nums) + 1) if nums else 0
    return _format_segment(next_num)


async def list_folders(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    domain: str | None = None,
) -> list[DocumentFolder]:
    query = select(DocumentFolder).where(DocumentFolder.tenant_id == tenant_id)
    if domain is not None:
        query = query.where(DocumentFolder.domain == domain)
    query = query.order_by(DocumentFolder.code)
    res = await db.execute(query)
    return list(res.scalars().all())


async def get_folder_by_id(
    db: AsyncSession, folder_id: uuid.UUID, tenant_id: uuid.UUID,
) -> DocumentFolder | None:
    res = await db.execute(
        select(DocumentFolder).where(
            DocumentFolder.id == folder_id,
            DocumentFolder.tenant_id == tenant_id,
        )
    )
    return res.scalar_one_or_none()


async def create_folder(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
    *,
    name: str,
    domain: str,
    parent_id: uuid.UUID | None = None,
) -> DocumentFolder:
    """Vytvoří novou složku, automaticky přidělí code."""
    if domain not in ("bozp", "po"):
        raise ValueError(f"Neplatná doména: {domain}")

    parent_code: str | None = None
    if parent_id is not None:
        await assert_in_tenant(
            db, DocumentFolder, parent_id, tenant_id, field_name="parent_id",
        )
        parent = (await db.execute(
            select(DocumentFolder).where(DocumentFolder.id == parent_id)
        )).scalar_one()
        if parent.domain != domain:
            raise ValueError(
                "Doména podsložky musí odpovídat doméně rodiče",
            )
        parent_code = parent.code

    # Najdi všechny existující sourozence (stejný parent, stejný tenant+domain)
    siblings = (await db.execute(
        select(DocumentFolder).where(
            DocumentFolder.tenant_id == tenant_id,
            DocumentFolder.parent_id == parent_id,
            DocumentFolder.domain == domain,
        )
    )).scalars().all()
    existing_codes = [f.code for f in siblings]

    next_seg = _next_segment(existing_codes, parent_code)
    new_code = next_seg if parent_code is None else f"{parent_code}.{next_seg}"

    folder = DocumentFolder(
        tenant_id=tenant_id,
        parent_id=parent_id,
        code=new_code,
        name=name,
        domain=domain,
        sort_order=len(siblings),
        created_by=created_by,
    )
    db.add(folder)
    await db.flush()
    return folder


async def update_folder(
    db: AsyncSession,
    folder: DocumentFolder,
    *,
    name: str | None = None,
    sort_order: int | None = None,
) -> DocumentFolder:
    """Přejmenování / sort_order. Code se NEMĚNÍ — strukturní stabilita."""
    if name is not None:
        folder.name = name
    if sort_order is not None:
        folder.sort_order = sort_order
    await db.flush()
    return folder


async def delete_folder(
    db: AsyncSession, folder: DocumentFolder,
) -> None:
    """
    Smaže složku. ON DELETE RESTRICT na parent_id — pokud má potomky, vyhodí
    integrity error. Volající musí potomky nejdřív smazat / přesunout.
    Generated documents s folder_id=tato → folder_id se nastaví na NULL
    (ON DELETE SET NULL).
    """
    await db.delete(folder)
    await db.flush()


async def has_children(
    db: AsyncSession, folder_id: uuid.UUID, tenant_id: uuid.UUID,
) -> bool:
    res = await db.execute(
        select(DocumentFolder.id).where(
            DocumentFolder.parent_id == folder_id,
            DocumentFolder.tenant_id == tenant_id,
        )
    )
    return res.first() is not None
