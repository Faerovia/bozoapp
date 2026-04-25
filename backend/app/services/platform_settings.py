"""
Service pro práci s globálním nastavením platformy.

Cache:
Hodnoty se cachují v paměti procesu po prvním načtení. PATCH cache invaliduje.
Vhodné protože většina setting čtení je v hot pathu (create_medical_exam,
generate_initial_exam_requests apod.) a změna setting je vzácná.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform_setting import PlatformSetting

# In-memory cache: key → value (Any). Invalidace: clear() při set_setting.
_cache: dict[str, Any] = {}
_cache_loaded: bool = False


async def _load_cache(db: AsyncSession) -> None:
    global _cache_loaded
    # Bypass RLS — settings tabulka nemá tenant_id, ale RLS by mohly
    # být nastavené na default deny pro běžné dotazy. Bezpečnostně bypass.
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))
    rows = (await db.execute(select(PlatformSetting))).scalars().all()
    _cache.clear()
    for row in rows:
        _cache[row.key] = row.value
    _cache_loaded = True


async def get_setting(
    db: AsyncSession, key: str, default: Any = None,
) -> Any:
    """Vrátí hodnotu setting (z cache nebo načte z DB poprvé)."""
    if not _cache_loaded:
        await _load_cache(db)
    return _cache.get(key, default)


async def list_settings(db: AsyncSession) -> list[PlatformSetting]:
    """Vrátí všechna nastavení s metadaty (klíč, hodnota, popis, updated_at)."""
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))
    rows = (await db.execute(
        select(PlatformSetting).order_by(PlatformSetting.key)
    )).scalars().all()
    return list(rows)


async def set_setting(
    db: AsyncSession,
    key: str,
    value: Any,
    *,
    updated_by: uuid.UUID | None = None,
) -> PlatformSetting:
    """Aktualizuje (nebo vytvoří) setting. Invaliduje cache."""
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))
    setting = (await db.execute(
        select(PlatformSetting).where(PlatformSetting.key == key)
    )).scalar_one_or_none()

    if setting is None:
        setting = PlatformSetting(
            key=key,
            value=value,
            updated_by=updated_by,
            updated_at=datetime.now(UTC),
        )
        db.add(setting)
    else:
        setting.value = value
        setting.updated_by = updated_by
        setting.updated_at = datetime.now(UTC)

    await db.flush()
    # Invalidace cache — full reload příště
    global _cache_loaded
    _cache_loaded = False
    return setting


def reset_cache_for_tests() -> None:
    """Pomocné API pro testy — vyčistí cache aby každý test měl čerstvý load."""
    global _cache_loaded
    _cache.clear()
    _cache_loaded = False
