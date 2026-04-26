"""
ARES (Administrativní Registr Ekonomických Subjektů) integrace.

Veřejné REST API Ministerstva financí ČR. Bez auth, bez rate limitu pro
běžné použití.

Endpoint: https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/{ico}

Vrací JSON s:
- obchodniJmeno (název firmy)
- sidlo: {nazevUlice, cisloDomovni, nazevObce, psc}
- dic (DIČ, pokud plátce DPH)
- pravniForma
- datumVzniku
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

ARES_BASE_URL = "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty"
TIMEOUT_SECONDS = 5


@dataclass
class AresCompanyInfo:
    """Strukturovaná odpověď z ARES — minimální podmnožina pro náš use case."""
    ico: str
    name: str
    dic: str | None
    address_street: str | None
    address_city: str | None
    address_zip: str | None
    legal_form: str | None = None


class AresError(Exception):
    """ARES API selhalo nebo IČO neexistuje."""


def _normalize_ico(ico: str) -> str:
    """Strip whitespace, ověř že je to 8 číslic."""
    cleaned = ico.strip().replace(" ", "")
    if not cleaned.isdigit() or len(cleaned) != 8:
        raise AresError("IČO musí být 8 číslic")
    return cleaned


def _parse_address(sidlo: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    """Vrátí (street, city, zip)."""
    street_parts: list[str] = []
    if "nazevUlice" in sidlo:
        street_parts.append(str(sidlo["nazevUlice"]))
    # ARES vrací cislo domovni a/nebo cislo orientacni
    cd = sidlo.get("cisloDomovni")
    co = sidlo.get("cisloOrientacni")
    if cd and co:
        street_parts.append(f"{cd}/{co}")
    elif cd:
        street_parts.append(str(cd))
    elif co:
        street_parts.append(str(co))
    street = " ".join(street_parts) if street_parts else None

    city = sidlo.get("nazevObce")
    zip_raw = sidlo.get("psc")
    zip_str: str | None = None
    if zip_raw is not None:
        # ARES vrací PSČ jako int (např. 11000) — formátujeme s mezerou
        zip_int = int(zip_raw)
        zip_str = f"{zip_int // 1000:03d} {zip_int % 1000:02d}"

    return street, str(city) if city else None, zip_str


def fetch_company_info(ico: str) -> AresCompanyInfo:
    """
    Synchronně zavolá ARES a vrátí strukturovaná data.
    Raises AresError pokud API selže nebo subjekt neexistuje.
    """
    cleaned = _normalize_ico(ico)
    url = f"{ARES_BASE_URL}/{cleaned}"

    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "BOZOapp/1.0 (+https://bozoapp.cz)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise AresError(f"Subjekt s IČO {cleaned} v ARES nenalezen") from e
        log.warning("ARES HTTP error for %s: %s", cleaned, e)
        raise AresError(f"ARES vrátil chybu {e.code}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        log.warning("ARES request failed for %s: %s", cleaned, e)
        raise AresError("ARES je momentálně nedostupný") from e
    except json.JSONDecodeError as e:
        raise AresError("ARES vrátil neplatný JSON") from e

    sidlo = data.get("sidlo", {}) or {}
    street, city, zip_str = _parse_address(sidlo)

    return AresCompanyInfo(
        ico=cleaned,
        name=str(data.get("obchodniJmeno", "")),
        dic=data.get("dic"),
        address_street=street,
        address_city=city,
        address_zip=zip_str,
        legal_form=data.get("pravniForma"),
    )


async def fetch_company_info_async(ico: str) -> AresCompanyInfo:
    """Async wrapper — spustí blocking call v threadpoolu."""
    import asyncio
    return await asyncio.to_thread(fetch_company_info, ico)
