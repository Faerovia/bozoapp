"""
Cron: denní RFC 3161 TSA kotva signature chainu.

Fetchne poslední chain_hash z `signatures` tabulky a pošle ho TSA
(default freetsa.org). Vrácený TimeStampToken uloží do `signature_anchors`.
Tím se externě prokáže, že chain k danému okamžiku obsahoval daný řádek
(seq + chain_hash) a žádný pozdější tampering DB toto nezvrátí.

Idempotency: pokud poslední anchor pokrývá aktuální max(seq), task
nedělá nic. Tj. kdyby byl spuštěn 2× za den, druhý běh je no-op.

Spouštění:
    python -m app.tasks.anchor_signatures

Doporučená frekvence: 1× denně. Vyžaduje pouze síťovou konektivitu na
TSA endpoint (freetsa.org / postsignum / ica). Pokud TSA není dostupné,
fallback na MockTsaProvider — chain integrita zůstává zachovaná i bez
externí kotvy.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models.signature import Signature, SignatureAnchor
from app.services.tsa import get_tsa_provider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("anchor_signatures")


async def _process(db: AsyncSession) -> dict[str, object]:
    """Vrátí dict popisující výsledek kotvy.

    Klíče:
    - status: 'noop_empty' | 'noop_already_anchored' | 'anchored' | 'failed'
    - last_seq, last_chain_hash, anchor_id, tsa_provider
    """
    # Najdi poslední řádek v chain
    last_sig_row = (
        await db.execute(
            select(Signature).order_by(Signature.seq.desc()).limit(1),
        )
    ).scalar_one_or_none()

    if last_sig_row is None:
        log.info("Chain je prázdný — kotvit není co.")
        return {"status": "noop_empty"}

    last_seq = int(last_sig_row.seq)
    last_chain_hash = last_sig_row.chain_hash

    # Idempotency: pokud existuje anchor s last_seq >= aktuálním, nic neděláme
    max_anchored_seq = (
        await db.execute(select(func.max(SignatureAnchor.last_seq)))
    ).scalar()
    if max_anchored_seq is not None and int(max_anchored_seq) >= last_seq:
        log.info(
            "Chain je již zakotven (last_anchored_seq=%d >= chain_max_seq=%d)",
            int(max_anchored_seq), last_seq,
        )
        return {
            "status": "noop_already_anchored",
            "last_seq": last_seq,
            "last_chain_hash": last_chain_hash,
        }

    # Pošli hash TSA
    provider = get_tsa_provider()
    try:
        result = await provider.anchor(last_chain_hash)
    except Exception as e:  # noqa: BLE001
        log.exception("TSA anchor selhalo: %s", e)
        return {"status": "failed", "error": str(e)}

    # Ulož kotvu. anchored_at musíme nastavit explicitně — DDL default
    # NOW() není v migraci 057.
    anchor = SignatureAnchor(
        id=uuid.uuid4(),
        anchored_at=datetime.now(UTC),
        last_seq=last_seq,
        last_chain_hash=last_chain_hash,
        tsa_provider=result.provider_name,
        tsa_token=result.token,
        tsa_serial=result.serial,
    )
    db.add(anchor)
    await db.flush()

    log.info(
        "Anchored chain seq=%d hash=%s via %s (token=%d bytes)",
        last_seq, last_chain_hash[:16], result.provider_name, len(result.token),
    )
    return {
        "status": "anchored",
        "last_seq": last_seq,
        "last_chain_hash": last_chain_hash,
        "anchor_id": str(anchor.id),
        "tsa_provider": result.provider_name,
    }


async def main() -> int:
    settings = get_settings()
    db_url = settings.migration_database_url or settings.database_url
    engine = create_async_engine(db_url, echo=False)
    async_session = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession,
    )
    async with async_session() as db, db.begin():
        # Platform admin context — abychom obešli RLS na signatures
        # (chain je cross-tenant; každý tenant podepisuje, ale anchor
        # se počítá globálně).
        await db.execute(
            text("SELECT set_config('app.is_platform_admin', 'true', true)"),
        )
        result = await _process(db)
    await engine.dispose()
    log.info("Done. Result=%s", result)
    return 0 if result["status"] != "failed" else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
