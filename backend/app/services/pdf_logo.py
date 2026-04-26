"""Sdílený helper pro embed loga firmy do PDF."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.storage import file_exists

log = logging.getLogger(__name__)


def embed_tenant_logo(
    pdf: Any,
    tenant: Any,
    *,
    x: float = 10,
    y: float | None = None,
    h: float = 15,
) -> bool:
    """Pokud tenant má `logo_path` a soubor existuje, vloží PNG/JPG.

    Vrací True pokud logo bylo vloženo. Nikdy neraisuje — selhání jen logujeme.
    Použití:
        from app.services.pdf_logo import embed_tenant_logo
        embed_tenant_logo(pdf, tenant)
    """
    if not getattr(tenant, "logo_path", None):
        return False
    if not file_exists(tenant.logo_path):
        return False
    settings = get_settings()
    logo_y = y if y is not None else pdf.get_y()
    try:
        logo_full = Path(settings.upload_dir) / tenant.logo_path
        pdf.image(str(logo_full), x=x, y=logo_y, h=h)
        return True
    except Exception:  # noqa: BLE001
        log.warning("Failed to embed tenant logo: %s", tenant.logo_path)
        return False
