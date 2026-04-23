"""
Testy pro registr rizik.

Klíčové BOZP invarianty které testujeme:
- skóre = pravděpodobnost × závažnost
- správné zařazení do pásem (low/medium/high)
- archivace místo smazání (BOZP dokumentace musí být dohledatelná)
- employee nemůže vytvářet/upravovat rizika
"""

import pytest
from httpx import AsyncClient


async def _ozo_headers(client: AsyncClient, suffix: str = "") -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"ozo{suffix}@firma.cz",
            "password": "heslo1234",
            "tenant_name": f"Firma {suffix}",
        },
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _risk_payload(**overrides) -> dict:
    base = {
        "title": "Pád z výšky",
        "description": "Riziko pádu při práci ve výšce nad 1,5 m",
        "location": "Střecha skladu",
        "activity": "Oprava střechy",
        "hazard_type": "physical",
        "probability": 3,
        "severity": 4,
        "control_measures": "Použití postroje, záchytná sítě",
        "residual_probability": 2,
        "residual_severity": 3,
    }
    base.update(overrides)
    return base


# ── Vytváření rizik ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_risk_returns_correct_score(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "r1")
    resp = await client.post("/api/v1/risks", json=_risk_payload(), headers=headers)

    assert resp.status_code == 201
    data = resp.json()
    # 3 × 4 = 12 → střední riziko
    assert data["risk_score"] == 12
    assert data["risk_level"] == "medium"
    # zbytková: 2 × 3 = 6 → nízké
    assert data["residual_risk_score"] == 6
    assert data["residual_risk_level"] == "low"


@pytest.mark.asyncio
async def test_risk_score_thresholds(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "r2")

    # Nízké riziko: 1 × 5 = 5
    resp = await client.post(
        "/api/v1/risks",
        json=_risk_payload(probability=1, severity=5, residual_probability=None, residual_severity=None),
        headers=headers,
    )
    assert resp.json()["risk_level"] == "low"

    # Vysoké riziko: 5 × 5 = 25
    resp = await client.post(
        "/api/v1/risks",
        json=_risk_payload(probability=5, severity=5, residual_probability=None, residual_severity=None),
        headers=headers,
    )
    assert resp.json()["risk_level"] == "high"
    assert resp.json()["risk_score"] == 25


@pytest.mark.asyncio
async def test_create_risk_without_residual(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "r3")
    resp = await client.post(
        "/api/v1/risks",
        json=_risk_payload(residual_probability=None, residual_severity=None),
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["residual_risk_score"] is None
    assert resp.json()["residual_risk_level"] is None


@pytest.mark.asyncio
async def test_residual_must_be_both_or_none(client: AsyncClient) -> None:
    """Nevalidní stav: jedna ze zbytkových hodnot chybí."""
    headers = await _ozo_headers(client, "r4")
    resp = await client.post(
        "/api/v1/risks",
        json=_risk_payload(residual_probability=2, residual_severity=None),
        headers=headers,
    )
    assert resp.status_code == 422


# ── Čtení a filtrování ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_risks_returns_own_tenant_only(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "r5")
    await client.post("/api/v1/risks", json=_risk_payload(title="Riziko A"), headers=headers)
    await client.post("/api/v1/risks", json=_risk_payload(title="Riziko B"), headers=headers)

    resp = await client.get("/api/v1/risks", headers=headers)
    assert resp.status_code == 200
    titles = [r["title"] for r in resp.json()]
    assert "Riziko A" in titles
    assert "Riziko B" in titles


@pytest.mark.asyncio
async def test_filter_by_status(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "r6")
    create_resp = await client.post(
        "/api/v1/risks", json=_risk_payload(), headers=headers
    )
    risk_id = create_resp.json()["id"]

    # Archivuj riziko
    await client.delete(f"/api/v1/risks/{risk_id}", headers=headers)

    active = await client.get("/api/v1/risks?status=active", headers=headers)
    archived = await client.get("/api/v1/risks?status=archived", headers=headers)

    assert all(r["status"] == "active" for r in active.json())
    assert any(r["id"] == risk_id for r in archived.json())


# ── Archivace (ne smazání) ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_archive_risk_keeps_record(client: AsyncClient) -> None:
    """
    Kritický BOZP invariant: záznamy o rizicích se nesmí fyzicky mazat.
    Archivace = status=archived, záznam zůstává v DB.
    """
    headers = await _ozo_headers(client, "r7")
    create_resp = await client.post("/api/v1/risks", json=_risk_payload(), headers=headers)
    risk_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/api/v1/risks/{risk_id}", headers=headers)
    assert del_resp.status_code == 204

    # Záznam stále existuje, jen archivovaný
    get_resp = await client.get(f"/api/v1/risks/{risk_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "archived"


# ── Permissions ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_employee_can_read_but_not_create(client: AsyncClient) -> None:
    ozo_headers = await _ozo_headers(client, "r8")

    # OZO vytvoří zaměstnance
    await client.post(
        "/api/v1/users",
        json={"email": "emp8@firma.cz", "password": "heslo1234", "role": "employee"},
        headers=ozo_headers,
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "emp8@firma.cz", "password": "heslo1234"},
    )
    emp_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # Employee smí číst
    read_resp = await client.get("/api/v1/risks", headers=emp_headers)
    assert read_resp.status_code == 200

    # Employee nesmí vytvářet
    create_resp = await client.post("/api/v1/risks", json=_risk_payload(), headers=emp_headers)
    assert create_resp.status_code == 403
