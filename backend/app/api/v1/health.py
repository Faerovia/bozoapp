import logging

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db

router = APIRouter()
log = logging.getLogger(__name__)
settings = get_settings()


@router.get("/health")
async def health_liveness() -> dict[str, str]:
    """
    Liveness probe — rychlá, bez externích závislostí.
    Kubernetes/LB volá každých pár sekund → nesmí zatěžovat DB.
    """
    return {"status": "ok"}


@router.get("/health/ready")
async def health_readiness(
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """
    Readiness probe — ověří externí závislosti (DB, Redis).
    Vrací 503 pokud některá není dostupná, aby LB instance nestavěl do rotace.
    """
    checks: dict[str, object] = {"database": "unknown", "redis": "unknown"}
    ok = True

    # PostgreSQL
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:  # noqa: BLE001
        log.warning("Readiness: DB check failed: %s", e)
        checks["database"] = f"error: {e.__class__.__name__}"
        ok = False

    # Redis (rate limiter + progressive delay)
    try:
        import redis.asyncio as redis_async
        client = redis_async.from_url(
            settings.redis_url, socket_connect_timeout=1.0, socket_timeout=1.0,
        )
        try:
            # redis-py typing překrývá sync/async variantu — `await` sedí
            # na runtime (async client), mypy strict nad tím vrtí hlavou.
            await client.ping()  # type: ignore[misc]
            checks["redis"] = "ok"
        finally:
            await client.aclose()
    except Exception as e:  # noqa: BLE001
        log.warning("Readiness: Redis check failed: %s", e)
        checks["redis"] = f"error: {e.__class__.__name__}"
        # Redis down je degraded, ne fatal — rate limiting padne open.
        # Chceme 200, ale flag v response.
        checks["redis_required"] = False

    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    checks["status"] = "ok" if ok else "degraded"
    return checks
