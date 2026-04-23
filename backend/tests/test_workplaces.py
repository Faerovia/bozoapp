"""
Testy pro modul Pracoviště:
  - Plants (závody)
  - Workplaces (pracoviště)
  - RiskFactorAssessments (hodnocení rizikových faktorů)
  - PDF export

Ověřujeme:
- CRUD operace včetně archivace (soft delete)
- Hierarchie: plant → workplace → rfa
- Validace rating hodnot (1|2|2R|3|4)
- category_proposed computed property (MAX logika, 2R jako 2.5)
- Tenant izolace
- PDF export endpoint
"""

import pytest
from httpx import AsyncClient


async def _ozo_headers(client: AsyncClient, suffix: str) -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"ozo{suffix}@wp.cz",
            "password": "heslo1234",
            "tenant_name": f"WP Firma {suffix}",
        },
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _create_plant(client: AsyncClient, headers: dict, name: str = "Závod 1") -> dict:
    resp = await client.post(
        "/api/v1/plants",
        json={"name": name, "address": "Průmyslová 1", "city": "Praha", "zip_code": "10000"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_workplace(
    client: AsyncClient, headers: dict, plant_id: str, name: str = "Výroba"
) -> dict:
    resp = await client.post(
        "/api/v1/workplaces",
        json={"plant_id": plant_id, "name": name},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_rfa(
    client: AsyncClient,
    headers: dict,
    workplace_id: str,
    profese: str = "Dělník",
    **rf_overrides,
) -> dict:
    payload = {
        "workplace_id": workplace_id,
        "profese": profese,
        "worker_count": 5,
        "women_count": 2,
    }
    payload.update(rf_overrides)
    resp = await client.post("/api/v1/risk-factors", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── Plants CRUD ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_plant(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "p1")
    plant = await _create_plant(client, headers)
    assert plant["name"] == "Závod 1"
    assert plant["city"] == "Praha"
    assert plant["status"] == "active"


@pytest.mark.asyncio
async def test_list_plants(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "p2")
    await _create_plant(client, headers, "Závod A")
    await _create_plant(client, headers, "Závod B")

    resp = await client.get("/api/v1/plants", headers=headers)
    assert resp.status_code == 200
    names = [p["name"] for p in resp.json()]
    assert "Závod A" in names
    assert "Závod B" in names


@pytest.mark.asyncio
async def test_get_plant_by_id(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "p3")
    plant = await _create_plant(client, headers)

    resp = await client.get(f"/api/v1/plants/{plant['id']}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == plant["id"]


@pytest.mark.asyncio
async def test_update_plant(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "p4")
    plant = await _create_plant(client, headers)

    resp = await client.patch(
        f"/api/v1/plants/{plant['id']}",
        json={"name": "Závod přejmenovaný", "city": "Brno"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Závod přejmenovaný"
    assert data["city"] == "Brno"


@pytest.mark.asyncio
async def test_archive_plant(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "p5")
    plant = await _create_plant(client, headers)

    del_resp = await client.delete(f"/api/v1/plants/{plant['id']}", headers=headers)
    assert del_resp.status_code == 204

    # Stále existuje, ale archivovaný
    get_resp = await client.get(f"/api/v1/plants/{plant['id']}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "archived"


@pytest.mark.asyncio
async def test_filter_plants_by_status(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "p6")
    plant = await _create_plant(client, headers, "Archivovaný závod")
    await client.delete(f"/api/v1/plants/{plant['id']}", headers=headers)
    await _create_plant(client, headers, "Aktivní závod")

    active = await client.get("/api/v1/plants?plant_status=active", headers=headers)
    archived = await client.get("/api/v1/plants?plant_status=archived", headers=headers)

    assert all(p["status"] == "active" for p in active.json())
    assert all(p["status"] == "archived" for p in archived.json())


# ── Workplaces CRUD ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_workplace(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "w1")
    plant = await _create_plant(client, headers)
    wp = await _create_workplace(client, headers, plant["id"])
    assert wp["name"] == "Výroba"
    assert wp["plant_id"] == plant["id"]
    assert wp["status"] == "active"


@pytest.mark.asyncio
async def test_create_workplace_invalid_plant(client: AsyncClient) -> None:
    """workplace_id z jiného tenantu → 422."""
    import uuid
    headers = await _ozo_headers(client, "w2")
    resp = await client.post(
        "/api/v1/workplaces",
        json={"plant_id": str(uuid.uuid4()), "name": "Výroba"},
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_workplaces_filter_by_plant(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "w3")
    plant_a = await _create_plant(client, headers, "Závod A")
    plant_b = await _create_plant(client, headers, "Závod B")
    await _create_workplace(client, headers, plant_a["id"], "Výroba A")
    await _create_workplace(client, headers, plant_b["id"], "Výroba B")

    resp = await client.get(f"/api/v1/workplaces?plant_id={plant_a['id']}", headers=headers)
    assert resp.status_code == 200
    names = [w["name"] for w in resp.json()]
    assert "Výroba A" in names
    assert "Výroba B" not in names


@pytest.mark.asyncio
async def test_archive_workplace(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "w4")
    plant = await _create_plant(client, headers)
    wp = await _create_workplace(client, headers, plant["id"])

    await client.delete(f"/api/v1/workplaces/{wp['id']}", headers=headers)
    get_resp = await client.get(f"/api/v1/workplaces/{wp['id']}", headers=headers)
    assert get_resp.json()["status"] == "archived"


# ── RiskFactorAssessment CRUD ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_rfa_minimal(client: AsyncClient) -> None:
    """Vytvoří hodnocení bez žádného rizikového faktoru – kategorie musí být '1'."""
    headers = await _ozo_headers(client, "r1")
    plant = await _create_plant(client, headers)
    wp = await _create_workplace(client, headers, plant["id"])

    rfa = await _create_rfa(client, headers, wp["id"])
    assert rfa["category_proposed"] == "1"
    assert rfa["status"] == "active"


@pytest.mark.asyncio
async def test_create_rfa_with_ratings(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "r2")
    plant = await _create_plant(client, headers)
    wp = await _create_workplace(client, headers, plant["id"])

    rfa = await _create_rfa(
        client, headers, wp["id"],
        rf_hluk="3",
        rf_prach="2",
        rf_teplo="1",
    )
    # MAX(3, 2, 1) = 3
    assert rfa["category_proposed"] == "3"
    assert rfa["rf_hluk"] == "3"
    assert rfa["rf_prach"] == "2"


@pytest.mark.asyncio
async def test_category_proposed_2r(client: AsyncClient) -> None:
    """2R je numericky 2.5 – vyhraje nad '2', prohraje nad '3'."""
    headers = await _ozo_headers(client, "r3")
    plant = await _create_plant(client, headers)
    wp = await _create_workplace(client, headers, plant["id"])

    rfa_2r = await _create_rfa(client, headers, wp["id"], rf_chem="2R", rf_prach="2")
    assert rfa_2r["category_proposed"] == "2R"

    rfa_3wins = await _create_rfa(client, headers, wp["id"], rf_chem="2R", rf_hluk="3")
    assert rfa_3wins["category_proposed"] == "3"


@pytest.mark.asyncio
async def test_category_override(client: AsyncClient) -> None:
    """category_override přebíjí automatický výpočet."""
    headers = await _ozo_headers(client, "r4")
    plant = await _create_plant(client, headers)
    wp = await _create_workplace(client, headers, plant["id"])

    rfa = await _create_rfa(
        client, headers, wp["id"],
        rf_hluk="1",
        category_override="3",
    )
    # Override 3 přebíjí MAX(1) = 1
    assert rfa["category_proposed"] == "3"


@pytest.mark.asyncio
async def test_invalid_rating_value(client: AsyncClient) -> None:
    """Hodnota '5' není validní rating – musí vrátit 422."""
    headers = await _ozo_headers(client, "r5")
    plant = await _create_plant(client, headers)
    wp = await _create_workplace(client, headers, plant["id"])

    resp = await client.post(
        "/api/v1/risk-factors",
        json={"workplace_id": wp["id"], "profese": "Dělník", "rf_hluk": "5"},
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_rfas_filter_by_workplace(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "r6")
    plant = await _create_plant(client, headers)
    wp_a = await _create_workplace(client, headers, plant["id"], "Výroba A")
    wp_b = await _create_workplace(client, headers, plant["id"], "Výroba B")

    await _create_rfa(client, headers, wp_a["id"], "Soustružník")
    await _create_rfa(client, headers, wp_b["id"], "Svářeč")

    resp = await client.get(f"/api/v1/risk-factors?workplace_id={wp_a['id']}", headers=headers)
    assert resp.status_code == 200
    profese_list = [r["profese"] for r in resp.json()]
    assert "Soustružník" in profese_list
    assert "Svářeč" not in profese_list


@pytest.mark.asyncio
async def test_update_rfa(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "r7")
    plant = await _create_plant(client, headers)
    wp = await _create_workplace(client, headers, plant["id"])
    rfa = await _create_rfa(client, headers, wp["id"], rf_hluk="2")

    resp = await client.patch(
        f"/api/v1/risk-factors/{rfa['id']}",
        json={"rf_hluk": "3", "worker_count": 10},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["rf_hluk"] == "3"
    assert resp.json()["worker_count"] == 10
    assert resp.json()["category_proposed"] == "3"


@pytest.mark.asyncio
async def test_archive_rfa(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "r8")
    plant = await _create_plant(client, headers)
    wp = await _create_workplace(client, headers, plant["id"])
    rfa = await _create_rfa(client, headers, wp["id"])

    del_resp = await client.delete(f"/api/v1/risk-factors/{rfa['id']}", headers=headers)
    assert del_resp.status_code == 204

    get_resp = await client.get(f"/api/v1/risk-factors/{rfa['id']}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "archived"


@pytest.mark.asyncio
async def test_rfa_invalid_workplace(client: AsyncClient) -> None:
    """Pracoviště z jiného tenantu → 422."""
    import uuid
    headers = await _ozo_headers(client, "r9")
    resp = await client.post(
        "/api/v1/risk-factors",
        json={"workplace_id": str(uuid.uuid4()), "profese": "Dělník"},
        headers=headers,
    )
    assert resp.status_code == 422


# ── PDF Export ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_export_risk_factors_pdf_empty(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "pdf1")
    resp = await client.get("/api/v1/risk-factors/export/pdf", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"


@pytest.mark.asyncio
async def test_export_risk_factors_pdf_with_data(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "pdf2")
    plant = await _create_plant(client, headers, "Testovací závod")
    wp = await _create_workplace(client, headers, plant["id"], "Hlavní výroba")
    await _create_rfa(client, headers, wp["id"], "Soustružník", rf_hluk="3", rf_vibrace="2R")
    await _create_rfa(client, headers, wp["id"], "Skladník", rf_fyz_zatez="2")

    resp = await client.get("/api/v1/risk-factors/export/pdf", headers=headers)
    assert resp.status_code == 200
    assert len(resp.content) > 1000  # Netriviální PDF


@pytest.mark.asyncio
async def test_export_pdf_filter_by_plant(client: AsyncClient) -> None:
    """Export filtrovaný na konkrétní závod vrátí PDF."""
    headers = await _ozo_headers(client, "pdf3")
    plant = await _create_plant(client, headers)
    wp = await _create_workplace(client, headers, plant["id"])
    await _create_rfa(client, headers, wp["id"])

    resp = await client.get(
        f"/api/v1/risk-factors/export/pdf?plant_id={plant['id']}",
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"


# ── Tenant izolace ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_plant_tenant_isolation(client: AsyncClient) -> None:
    headers_a = await _ozo_headers(client, "ti1a")
    headers_b = await _ozo_headers(client, "ti1b")

    await _create_plant(client, headers_a, "Závod tenanta A")

    resp_b = await client.get("/api/v1/plants", headers=headers_b)
    assert resp_b.json() == []


@pytest.mark.asyncio
async def test_workplace_tenant_isolation(client: AsyncClient) -> None:
    headers_a = await _ozo_headers(client, "ti2a")
    headers_b = await _ozo_headers(client, "ti2b")

    plant_a = await _create_plant(client, headers_a)
    await _create_workplace(client, headers_a, plant_a["id"], "Pracoviště A")

    resp_b = await client.get("/api/v1/workplaces", headers=headers_b)
    assert resp_b.json() == []


@pytest.mark.asyncio
async def test_rfa_tenant_isolation(client: AsyncClient) -> None:
    headers_a = await _ozo_headers(client, "ti3a")
    headers_b = await _ozo_headers(client, "ti3b")

    plant = await _create_plant(client, headers_a)
    wp = await _create_workplace(client, headers_a, plant["id"])
    await _create_rfa(client, headers_a, wp["id"])

    resp_b = await client.get("/api/v1/risk-factors", headers=headers_b)
    assert resp_b.json() == []
