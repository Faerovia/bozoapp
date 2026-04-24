"""
Rate limiting a progressive delay pro auth endpointy.

Dvě vrstvy ochrany:

1. **slowapi rate limiter** (dekorátor na endpointu) — brání brute-force:
   každé IP má limit N requestů za časové okno. Překročení → 429.

2. **Progressive delay** (volá se uvnitř login service) — po každém neúspěšném
   loginu přičítá čítač Redisu. S rostoucím počtem chyb se `asyncio.sleep`
   prodlužuje. Bránění credential stuffing i když IP roluje.

Oba mechanismy sdílí Redis z `settings.redis_url`. Když Redis není dostupný,
degradujeme tiše — rate limit selže open (slowapi default) a progressive
delay jen přeskočí. Security-wise je to trade-off za dostupnost; alternativa
(fail-closed) by zablokovala legitimní login při výpadku Redis.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import redis.asyncio as redis_async
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)
settings = get_settings()

# V test environment vypínáme všechny rate-limit mechanismy — testy
# jinak prorazí limit (hodně registrací / loginů v řadě) a rozbijí
# se, aniž by testovaly skutečné chování aplikace.
_RATE_LIMIT_ENABLED = settings.environment != "test"


# ── slowapi limiter ──────────────────────────────────────────────────────────
# Klíčujeme podle IP adresy. `storage_uri` přes Redis znamená, že více
# backend instancí sdílí počítadla (nutné pro horizontální škálování).
# Pokud Redis není dostupný (dev bez docker-compose, test env bez Redis),
# spadneme na in-memory backend aby se aplikace vůbec nastartovala.
_storage_uri = settings.redis_url if _RATE_LIMIT_ENABLED else "memory://"

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_storage_uri,
    enabled=_RATE_LIMIT_ENABLED,
    default_limits=[],
)


# ── Progressive delay (async) ─────────────────────────────────────────────────
# Key format: "login_fail:<email_lower>"
# Počítadlo roste s každým neúspěšným pokusem, TTL obnovován.

_FAIL_KEY_PREFIX = "login_fail:"
_FAIL_TTL_SECONDS = 15 * 60  # 15 min — rolling window
# Tabulka delayů podle počtu fail attempts. None = block zcela až do TTL expire.
_DELAY_LADDER: list[float] = [0.0, 0.0, 0.5, 1.0, 2.0, 4.0, 8.0, 15.0, 30.0]
_MAX_DELAY_BEFORE_BLOCK = 60.0  # secondů; nad tím vracíme "blocked"


_redis_client: redis_async.Redis | None = None


def _get_redis() -> redis_async.Redis | None:
    """Lazy singleton. None pokud Redis není nakonfigurován / nedostupný."""
    global _redis_client
    if not _RATE_LIMIT_ENABLED:
        return None
    if _redis_client is None:
        try:
            _redis_client = redis_async.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=1.0,
            )
        except Exception as e:  # noqa: BLE001
            log.warning("Redis init failed, rate limiting disabled: %s", e)
            _redis_client = None
    return _redis_client


async def _fail_count(email: str) -> int:
    r = _get_redis()
    if r is None:
        return 0
    try:
        val = await r.get(f"{_FAIL_KEY_PREFIX}{email.lower()}")
    except Exception as e:  # noqa: BLE001
        log.warning("Redis get failed (fail_open): %s", e)
        return 0
    return int(val or 0)


async def _increment_fail(email: str) -> int:
    r = _get_redis()
    if r is None:
        return 0
    try:
        pipe = r.pipeline()
        key = f"{_FAIL_KEY_PREFIX}{email.lower()}"
        await pipe.incr(key)
        await pipe.expire(key, _FAIL_TTL_SECONDS)
        results = await pipe.execute()
        return int(results[0])
    except Exception as e:  # noqa: BLE001
        log.warning("Redis incr failed (fail_open): %s", e)
        return 0


async def _clear_fails(email: str) -> None:
    r = _get_redis()
    if r is None:
        return
    try:
        await r.delete(f"{_FAIL_KEY_PREFIX}{email.lower()}")
    except Exception as e:  # noqa: BLE001
        log.warning("Redis delete failed: %s", e)


def _delay_for_count(count: int) -> float:
    """Vrátí delay v sekundách podle počtu předchozích fail pokusů."""
    if count <= 0:
        return 0.0
    idx = min(count - 1, len(_DELAY_LADDER) - 1)
    return _DELAY_LADDER[idx]


async def apply_login_delay(email: str) -> bool:
    """
    Před pokusem o login: uspi proces na delay podle fail countu.
    Vrací True pokud lze pokračovat, False pokud máme útočníka blokovat rovnou (429).

    Volat před `verify_password`. `email` je vstupní (nemusí existovat) — aby
    nebyl enumeration timing leak, volej VŽDY i pro neexistující uživatele.
    """
    count = await _fail_count(email)
    delay = _delay_for_count(count)
    if delay >= _MAX_DELAY_BEFORE_BLOCK:
        return False
    if delay > 0:
        await asyncio.sleep(delay)
    return True


async def record_login_failure(email: str) -> None:
    await _increment_fail(email)


async def record_login_success(email: str) -> None:
    await _clear_fails(email)
