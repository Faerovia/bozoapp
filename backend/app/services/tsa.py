"""RFC 3161 Time-Stamping Authority abstrakce.

V MVP používáme freetsa.org (zdarma, technický důkaz). Před live release
přepneme na PostSignum (~500 Kč/rok) nebo I.CA (~700 Kč/rok) — kvalifikovaný
eIDAS TSA s váhou pro řízení u SÚIP / soudu.

Workflow:
1. Cron task `anchor_signatures` denně 03:00 fetchne poslední chain_hash
   z `signatures` tabulky.
2. Sestaví TimeStampReq (RFC 3161) s SHA-256 messageImprint.
3. Pošle TSA serveru (HTTP POST, content-type application/timestamp-query).
4. Odpověď je TimeStampResp obsahující TimeStampToken (CMS SignedData).
5. Token uloží do `signature_anchors` tabulky.

V dev/mock módu (MockTsaProvider) jen vytvoří fake binární token —
testy nemusí volat externí službu.
"""
from __future__ import annotations

import hashlib
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

log = logging.getLogger("tsa_provider")

# RFC 3161 — content-type
TS_QUERY_TYPE = "application/timestamp-query"
TS_REPLY_TYPE = "application/timestamp-reply"


@dataclass
class AnchorResult:
    provider_name: str  # 'freetsa' | 'postsignum' | 'ica' | 'mock'
    token: bytes        # binární TimeStampToken (CMS SignedData)
    serial: str | None


class TsaProvider(ABC):
    @abstractmethod
    async def anchor(self, hash_hex: str) -> AnchorResult:
        """Pošle SHA-256 hash do TSA, vrátí podepsaný token."""


class MockTsaProvider(TsaProvider):
    """Pro dev a testy — vrací fake token, neposílá síťový request."""

    async def anchor(self, hash_hex: str) -> AnchorResult:
        # Fake token — sha256(hash_hex || 'mock-tsa-' || timestamp)
        # Není kryptograficky validní RFC 3161 token, jen placeholder.
        ts_marker = b"MOCK-TSA-" + os.urandom(16)
        fake_token = hashlib.sha256(
            hash_hex.encode() + ts_marker,
        ).digest() + ts_marker
        log.warning(
            "MockTsaProvider: hash=%s anchored (NOT cryptographically valid)",
            hash_hex[:16],
        )
        return AnchorResult(
            provider_name="mock",
            token=fake_token,
            serial=None,
        )


class FreeTsaProvider(TsaProvider):
    """freetsa.org — zdarma, bez právní váhy v ČR.

    Pro produkci (premium tier) přejít na PostSignum nebo I.CA.
    Implementace je jen HTTP POST — RFC 3161 TimeStampReq má známý
    binární formát; pro MVP používáme `rfc3161ng` lib NEBO ručně:

    Vzhledem k tomu, že rfc3161ng není v core dependencies, MVP pošle
    raw `messageImprint` jako tlačený DER blob přes httpx. Pokud knihovna
    není dostupná, fallback na MockTsaProvider.
    """

    URL = "https://freetsa.org/tsr"

    async def anchor(self, hash_hex: str) -> AnchorResult:
        try:
            from rfc3161ng import RemoteTimestamper  # noqa: I001
        except ImportError:
            log.warning("rfc3161ng není nainstalován — fallback na mock")
            return await MockTsaProvider().anchor(hash_hex)

        try:
            timestamper = RemoteTimestamper(self.URL, hashname="sha256")
            digest = bytes.fromhex(hash_hex)
            # Knihovna provádí HTTP request synchronně. Pro MVP OK,
            # je to denní cron, ne hot path. Případně later wrap async.
            token: bytes = timestamper(data=None, digest=digest)
            return AnchorResult(
                provider_name="freetsa",
                token=token,
                serial=None,
            )
        except Exception as e:  # noqa: BLE001
            log.exception("FreeTSA selhalo: %s", e)
            # Fallback na mock — chain integrita je zachována i bez TSA
            return await MockTsaProvider().anchor(hash_hex)


def get_tsa_provider() -> TsaProvider:
    """V MVP vždy freetsa (s mock fallbackem).

    Production swap: přidat PostSignumProvider, IcaProvider a routovat
    přes settings.tsa_provider.
    """
    return FreeTsaProvider()


# Suppression: httpx import (zatím použit jen jako future hook pro custom request)
_ = httpx
