"""
Testy nového OOPP modulu (NV 390/2021 Sb. Příloha č. 2).

Pokrýváme:
- /oopp/catalog (statický seznam body parts + risk columns)
- Risk grid PUT/GET per pozice
- OOPP items CRUD per pozice (multi-item per body part)
- Issues create (valid_until dopočítané z item.valid_months)
- Tenant izolace
"""
from datetime import date, timedelta

import pytest
from httpx import AsyncClient


async def _ozo_headers(client: AsyncClient, suffix: str) -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"ozo{suffix}@oopp.cz",
            "password": "heslo1234",
            "tenant_name": f"OOPP Firma {suffix}",
        },
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _create_position(
    client: AsyncClient, headers: dict, name: str = "Soustružník"
) -> str:
    """Vytvoří plant + workplace + position a vrátí position id."""
    plant = await client.post(
        "/api/v1/plants", json={"name": "Provozovna T"}, headers=headers
    )
    plant_id = plant.json()["id"]
    wp = await client.post(
        "/api/v1/workplaces",
        json={"plant_id": plant_id, "name": "Pracoviště T"},
        headers=headers,
    )
    wp_id = wp.json()["id"]
    pos = await client.post(
        "/api/v1/job-positions",
        json={"name": name, "workplace_id": wp_id},
        headers=headers,
    )
    assert pos.status_code == 201, pos.text
    return pos.json()["id"]


async def _create_employee(
    client: AsyncClient, headers: dict, suffix: str = "1"
) -> str:
    resp = await client.post(
        "/api/v1/employees",
        json={
            "first_name": "Jan",
            "last_name": f"Novák{suffix}",
            "employment_type": "hpp",
            "email": f"emp{suffix}@oopp.cz",
            "create_user_account": True,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ── Catalog ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_catalog_returns_full_table(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "c1")
    resp = await client.get("/api/v1/oopp/catalog", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["body_parts"]) == 14
    assert len(data["risk_columns"]) == 26
    assert data["body_parts"][0]["key"] == "A"
    assert data["risk_columns"][0]["col"] == 1
    assert data["risk_columns"][0]["group"] == "fyzikální"


# ── Risk grid ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_set_and_get_grid(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "g1")
    pos_id = await _create_position(client, headers)

    put = await client.put(
        f"/api/v1/job-positions/{pos_id}/oopp-grid",
        json={"grid": {"G": [1, 6], "I": [3]}},
        headers=headers,
    )
    assert put.status_code == 200, put.text
    body = put.json()
    assert body["grid"] == {"G": [1, 6], "I": [3]}
    assert body["has_any_risk"] is True

    get = await client.get(
        f"/api/v1/job-positions/{pos_id}/oopp-grid", headers=headers
    )
    assert get.status_code == 200
    assert get.json()["grid"] == {"G": [1, 6], "I": [3]}


@pytest.mark.asyncio
async def test_grid_rejects_invalid_body_part(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "g2")
    pos_id = await _create_position(client, headers)
    resp = await client.put(
        f"/api/v1/job-positions/{pos_id}/oopp-grid",
        json={"grid": {"Z": [1]}},
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_grid_rejects_invalid_risk_col(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "g3")
    pos_id = await _create_position(client, headers)
    resp = await client.put(
        f"/api/v1/job-positions/{pos_id}/oopp-grid",
        json={"grid": {"A": [99]}},
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_empty_grid_persists_as_empty(client: AsyncClient) -> None:
    """Replace strategy: posláním {} se grid vyčistí."""
    headers = await _ozo_headers(client, "g4")
    pos_id = await _create_position(client, headers)
    await client.put(
        f"/api/v1/job-positions/{pos_id}/oopp-grid",
        json={"grid": {"G": [1]}},
        headers=headers,
    )
    await client.put(
        f"/api/v1/job-positions/{pos_id}/oopp-grid",
        json={"grid": {}},
        headers=headers,
    )
    g = await client.get(f"/api/v1/job-positions/{pos_id}/oopp-grid", headers=headers)
    assert g.json()["has_any_risk"] is False


# ── Positions with grid ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_positions_with_grid_lists_only_filled(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "p1")
    pos_a = await _create_position(client, headers, "Svářeč")
    pos_b = await _create_position(client, headers, "Skladník")
    await client.put(
        f"/api/v1/job-positions/{pos_a}/oopp-grid",
        json={"grid": {"G": [1]}},
        headers=headers,
    )

    resp = await client.get("/api/v1/oopp/positions", headers=headers)
    ids = [p["id"] for p in resp.json()]
    assert pos_a in ids
    assert pos_b not in ids


# ── OOPP items ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_oopp_item(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "i1")
    pos_id = await _create_position(client, headers)
    resp = await client.post(
        "/api/v1/oopp/items",
        json={
            "job_position_id": pos_id,
            "body_part": "G",
            "name": "Pracovní rukavice",
            "valid_months": 12,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["body_part"] == "G"
    assert body["valid_months"] == 12


@pytest.mark.asyncio
async def test_multiple_items_per_body_part(client: AsyncClient) -> None:
    """Ke stejné body part lze přidat libovolný počet OOPP."""
    headers = await _ozo_headers(client, "i2")
    pos_id = await _create_position(client, headers)
    for name in ["Rukavice", "Manžety", "Chrániče prstů"]:
        await client.post(
            "/api/v1/oopp/items",
            json={"job_position_id": pos_id, "body_part": "G", "name": name},
            headers=headers,
        )
    resp = await client.get(
        f"/api/v1/oopp/items?job_position_id={pos_id}", headers=headers
    )
    items = resp.json()
    assert len(items) == 3
    assert {i["name"] for i in items} == {"Rukavice", "Manžety", "Chrániče prstů"}


@pytest.mark.asyncio
async def test_item_invalid_body_part_rejected(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "i3")
    pos_id = await _create_position(client, headers)
    resp = await client.post(
        "/api/v1/oopp/items",
        json={"job_position_id": pos_id, "body_part": "Z", "name": "Test"},
        headers=headers,
    )
    assert resp.status_code == 422


# ── Issues ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_issue_valid_until_from_item_period(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "is1")
    pos_id = await _create_position(client, headers)
    emp_id = await _create_employee(client, headers, "1")

    item = await client.post(
        "/api/v1/oopp/items",
        json={
            "job_position_id": pos_id,
            "body_part": "G",
            "name": "Rukavice",
            "valid_months": 6,
        },
        headers=headers,
    )
    item_id = item.json()["id"]

    issue = await client.post(
        "/api/v1/oopp/issues",
        json={
            "employee_id": emp_id,
            "position_oopp_item_id": item_id,
            "issued_at": "2026-01-15",
        },
        headers=headers,
    )
    assert issue.status_code == 201, issue.text
    assert issue.json()["valid_until"] == "2026-07-15"
    assert issue.json()["item_name"] == "Rukavice"
    assert issue.json()["body_part"] == "G"


@pytest.mark.asyncio
async def test_issue_validity_status(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "is2")
    pos_id = await _create_position(client, headers)
    emp_id = await _create_employee(client, headers, "2")
    item = await client.post(
        "/api/v1/oopp/items",
        json={"job_position_id": pos_id, "body_part": "G", "name": "X"},
        headers=headers,
    )
    item_id = item.json()["id"]

    expired = await client.post(
        "/api/v1/oopp/issues",
        json={
            "employee_id": emp_id,
            "position_oopp_item_id": item_id,
            "issued_at": "2024-01-01",
            "valid_until": "2024-12-31",
        },
        headers=headers,
    )
    assert expired.json()["validity_status"] == "expired"

    soon = (date.today() + timedelta(days=15)).isoformat()
    expiring = await client.post(
        "/api/v1/oopp/issues",
        json={
            "employee_id": emp_id,
            "position_oopp_item_id": item_id,
            "issued_at": date.today().isoformat(),
            "valid_until": soon,
        },
        headers=headers,
    )
    assert expiring.json()["validity_status"] == "expiring_soon"


@pytest.mark.asyncio
async def test_list_issues_filters_by_employee(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "is3")
    pos_id = await _create_position(client, headers)
    emp1 = await _create_employee(client, headers, "1")
    emp2 = await _create_employee(client, headers, "2")
    item = await client.post(
        "/api/v1/oopp/items",
        json={"job_position_id": pos_id, "body_part": "G", "name": "X"},
        headers=headers,
    )
    item_id = item.json()["id"]

    for emp_id in (emp1, emp2):
        await client.post(
            "/api/v1/oopp/issues",
            json={
                "employee_id": emp_id,
                "position_oopp_item_id": item_id,
                "issued_at": "2026-01-15",
            },
            headers=headers,
        )

    resp = await client.get(
        f"/api/v1/oopp/issues?employee_id={emp1}", headers=headers
    )
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["employee_id"] == emp1


# ── Tenant izolace ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tenant_isolation(client: AsyncClient) -> None:
    headers_a = await _ozo_headers(client, "ta")
    headers_b = await _ozo_headers(client, "tb")
    pos_a = await _create_position(client, headers_a)

    await client.put(
        f"/api/v1/job-positions/{pos_a}/oopp-grid",
        json={"grid": {"G": [1]}},
        headers=headers_a,
    )

    resp = await client.get(
        f"/api/v1/job-positions/{pos_a}/oopp-grid", headers=headers_b
    )
    assert resp.status_code == 404
