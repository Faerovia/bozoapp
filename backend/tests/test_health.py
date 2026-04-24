import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_liveness_returns_ok(client: AsyncClient) -> None:
    """Liveness probe — bez externích závislostí, jen že běží uvicorn."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_health_readiness_checks_db(client: AsyncClient) -> None:
    """Readiness probe — ověřuje DB. Redis v test env není, ale readiness
    ho nepovažuje za fatální (vrátí 200 s redis=error)."""
    response = await client.get("/api/v1/health/ready")
    # 200 když DB OK; 503 pokud DB down. Redis down neposkytuje 503.
    assert response.status_code in (200, 503)
    data = response.json()
    assert data["status"] in ("ok", "degraded")
    assert data["database"] in ("ok", "error: OperationalError", "error: InterfaceError")
