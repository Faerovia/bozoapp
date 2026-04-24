"""
Testy pro modul Pracovní pozice (job positions).

Ověřujeme:
- CRUD + archivace
- effective_exam_period_months computed property (override > default z kategorie)
- Filtrování dle kategorie a statusu
- Přiřazení pozice zaměstnanci (employee.job_position_id)
- Tenant izolace
"""

import pytest
from httpx import AsyncClient


async def _ozo_headers(client: AsyncClient, suffix: str) -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"ozo{suffix}@jp.cz",
            "password": "heslo1234",
            "tenant_name": f"JP Firma {suffix}",
        },
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _create_plant_workplace(client: AsyncClient, headers: dict) -> str:
    """Vytvoří plant + workplace a vrátí workplace_id.

    V novém modelu má JobPosition povinný workplace_id — všechny testy potřebují
    nejprve vytvořit plant+workplace.
    """
    plant = await client.post(
        "/api/v1/plants", json={"name": "Provozovna Test"}, headers=headers
    )
    plant_id = plant.json()["id"]
    wp = await client.post(
        "/api/v1/workplaces",
        json={"plant_id": plant_id, "name": "Pracoviště Test"},
        headers=headers,
    )
    return wp.json()["id"]


async def _create_jp(
    client: AsyncClient, headers: dict, name: str = "Soustružník",
    workplace_id: str | None = None, **kwargs
) -> dict:
    if workplace_id is None:
        workplace_id = await _create_plant_workplace(client, headers)
    payload = {"name": name, "workplace_id": workplace_id, **kwargs}
    resp = await client.post("/api/v1/job-positions", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── CRUD ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_job_position(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "j1")
    jp = await _create_jp(client, headers, "Skladník", work_category="2")
    assert jp["name"] == "Skladník"
    assert jp["work_category"] == "2"
    assert jp["status"] == "active"
    assert jp["medical_exam_period_months"] is None


@pytest.mark.asyncio
async def test_list_job_positions(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "j2")
    await _create_jp(client, headers, "Svářeč", work_category="3")
    await _create_jp(client, headers, "Řidič", work_category="2")

    resp = await client.get("/api/v1/job-positions", headers=headers)
    assert resp.status_code == 200
    names = [jp["name"] for jp in resp.json()]
    assert "Svářeč" in names
    assert "Řidič" in names


@pytest.mark.asyncio
async def test_get_job_position_by_id(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "j3")
    jp = await _create_jp(client, headers)
    resp = await client.get(f"/api/v1/job-positions/{jp['id']}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == jp["id"]


@pytest.mark.asyncio
async def test_update_job_position(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "j4")
    jp = await _create_jp(client, headers, work_category="2")

    resp = await client.patch(
        f"/api/v1/job-positions/{jp['id']}",
        json={"name": "Operátor CNC", "work_category": "3"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Operátor CNC"
    assert resp.json()["work_category"] == "3"


@pytest.mark.asyncio
async def test_archive_job_position(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "j5")
    jp = await _create_jp(client, headers)

    del_resp = await client.delete(f"/api/v1/job-positions/{jp['id']}", headers=headers)
    assert del_resp.status_code == 204

    get_resp = await client.get(f"/api/v1/job-positions/{jp['id']}", headers=headers)
    assert get_resp.json()["status"] == "archived"


# ── effective_exam_period_months ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_effective_exam_period_default_from_category(client: AsyncClient) -> None:
    """Bez override se použije výchozí lhůta z kategorie."""
    headers = await _ozo_headers(client, "j6")

    cases = [
        ("1", 72),
        ("2", 48),
        ("2R", 24),
        ("3", 24),
        ("4", 12),
    ]
    for cat, expected in cases:
        jp = await _create_jp(client, headers, f"Pozice kat {cat}", work_category=cat)
        assert jp["effective_exam_period_months"] == expected, (
            f"Kategorie {cat}: expected {expected}, got {jp['effective_exam_period_months']}"
        )


@pytest.mark.asyncio
async def test_effective_exam_period_override(client: AsyncClient) -> None:
    """Ruční override přebíjí výchozí z kategorie."""
    headers = await _ozo_headers(client, "j7")
    jp = await _create_jp(
        client, headers, work_category="2", medical_exam_period_months=36
    )
    # Kategorie 2 → default 48, ale override je 36
    assert jp["medical_exam_period_months"] == 36
    assert jp["effective_exam_period_months"] == 36


@pytest.mark.asyncio
async def test_effective_exam_period_derives_from_rfa_default(client: AsyncClient) -> None:
    """
    Pozice bez work_category: v novém modelu se při create auto-vytvoří RFA stub,
    jehož category_proposed defaultuje na '1' (pokud žádný faktor není zadán).
    Takže effective kategorie = '1' → period 72 měsíců dle vyhl. 79/2013.
    """
    headers = await _ozo_headers(client, "j8")
    jp = await _create_jp(client, headers, "THP bez kategorie")
    assert jp["work_category"] is None
    assert jp["effective_category"] == "1"
    assert jp["effective_exam_period_months"] == 72


# ── Filtrování ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_filter_by_work_category(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "j9")
    await _create_jp(client, headers, "Kat3 pozice", work_category="3")
    await _create_jp(client, headers, "Kat1 pozice", work_category="1")

    resp = await client.get("/api/v1/job-positions?work_category=3", headers=headers)
    assert resp.status_code == 200
    assert all(jp["work_category"] == "3" for jp in resp.json())


@pytest.mark.asyncio
async def test_filter_by_status(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "j10")
    jp = await _create_jp(client, headers, "Archivovaná")
    await client.delete(f"/api/v1/job-positions/{jp['id']}", headers=headers)
    await _create_jp(client, headers, "Aktivní")

    active = await client.get("/api/v1/job-positions?jp_status=active", headers=headers)
    archived = await client.get("/api/v1/job-positions?jp_status=archived", headers=headers)

    assert all(jp["status"] == "active" for jp in active.json())
    assert all(jp["status"] == "archived" for jp in archived.json())


# ── Přiřazení zaměstnanci ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_assign_job_position_to_employee(client: AsyncClient) -> None:
    """Employee lze přiřadit job_position_id přes PATCH /employees/{id}."""
    headers = await _ozo_headers(client, "j11")

    jp = await _create_jp(client, headers, "Operátor výroby", work_category="2")

    emp_resp = await client.post(
        "/api/v1/employees",
        json={"first_name": "Petr", "last_name": "Novák", "employment_type": "hpp"},
        headers=headers,
    )
    eid = emp_resp.json()["id"]

    patch_resp = await client.patch(
        f"/api/v1/employees/{eid}",
        json={"job_position_id": jp["id"]},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["job_position_id"] == jp["id"]


@pytest.mark.asyncio
async def test_invalid_category(client: AsyncClient) -> None:
    """Kategorie '5' není validní – 422."""
    headers = await _ozo_headers(client, "j12")
    resp = await client.post(
        "/api/v1/job-positions",
        json={"name": "Nevalidní", "work_category": "5"},
        headers=headers,
    )
    assert resp.status_code == 422


# ── Tenant izolace ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tenant_isolation(client: AsyncClient) -> None:
    headers_a = await _ozo_headers(client, "jt1a")
    headers_b = await _ozo_headers(client, "jt1b")

    await _create_jp(client, headers_a, "Pozice tenantu A")

    resp_b = await client.get("/api/v1/job-positions", headers=headers_b)
    assert resp_b.json() == []
