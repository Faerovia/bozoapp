"""
Testy pro modul Zaměstnanci (employees).

Ověřujeme:
- CRUD operace
- Vazba employee ↔ user (user_id)
- Filtrování (status, employment_type)
- Přístupová práva (employee vidí jen sebe)
- Terminate místo fyzického smazání
- Tenant izolace
"""

import pytest
from httpx import AsyncClient


async def _ozo_headers(client: AsyncClient, suffix: str) -> tuple[dict, str]:
    """Vrátí (headers, user_id) pro OZO."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"ozo{suffix}@emp.cz",
            "password": "heslo1234",
            "tenant_name": f"Emp Firma {suffix}",
        },
    )
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    me = await client.get("/api/v1/users/me", headers=headers)
    return headers, me.json()["id"]


def _emp_payload(**overrides) -> dict:
    base = {
        "first_name": "Jan",
        "last_name": "Novák",
        "employment_type": "hpp",
    }
    base.update(overrides)
    return base


# ── Základní CRUD ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_employee(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "e1")
    resp = await client.post("/api/v1/employees", json=_emp_payload(), headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["first_name"] == "Jan"
    assert data["last_name"] == "Novák"
    assert data["full_name"] == "Jan Novák"
    assert data["status"] == "active"
    assert data["user_id"] is None


@pytest.mark.asyncio
async def test_create_employee_with_user_link(client: AsyncClient) -> None:
    """Zaměstnanec propojený s auth účtem přes user_id."""
    headers, user_id = await _ozo_headers(client, "e2")
    resp = await client.post(
        "/api/v1/employees",
        json=_emp_payload(user_id=user_id, first_name="Linked"),
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["user_id"] == user_id


@pytest.mark.asyncio
async def test_create_employee_invalid_user_id(client: AsyncClient) -> None:
    """user_id z jiného tenantu musí vrátit 422."""
    import uuid
    headers, _ = await _ozo_headers(client, "e3")
    resp = await client.post(
        "/api/v1/employees",
        json=_emp_payload(user_id=str(uuid.uuid4())),  # neexistující user
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_employees(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "e4")
    await client.post("/api/v1/employees", json=_emp_payload(first_name="Alice"), headers=headers)
    await client.post("/api/v1/employees", json=_emp_payload(first_name="Bob"), headers=headers)

    resp = await client.get("/api/v1/employees", headers=headers)
    assert resp.status_code == 200
    names = [e["first_name"] for e in resp.json()]
    assert "Alice" in names
    assert "Bob" in names


@pytest.mark.asyncio
async def test_get_employee_by_id(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "e5")
    create = await client.post("/api/v1/employees", json=_emp_payload(), headers=headers)
    eid = create.json()["id"]

    resp = await client.get(f"/api/v1/employees/{eid}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == eid


@pytest.mark.asyncio
async def test_update_employee(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "e6")
    create = await client.post("/api/v1/employees", json=_emp_payload(), headers=headers)
    eid = create.json()["id"]

    resp = await client.patch(
        f"/api/v1/employees/{eid}",
        json={"first_name": "Jana", "phone": "+420123456789"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["first_name"] == "Jana"
    assert resp.json()["phone"] == "+420123456789"


@pytest.mark.asyncio
async def test_terminate_employee(client: AsyncClient) -> None:
    """DELETE → status=terminated, fyzicky stále existuje."""
    headers, _ = await _ozo_headers(client, "e7")
    create = await client.post("/api/v1/employees", json=_emp_payload(), headers=headers)
    eid = create.json()["id"]

    del_resp = await client.delete(f"/api/v1/employees/{eid}", headers=headers)
    assert del_resp.status_code == 204

    get_resp = await client.get(f"/api/v1/employees/{eid}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "terminated"


# ── Filtrování ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_filter_by_status(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "e8")
    create = await client.post("/api/v1/employees", json=_emp_payload(first_name="Aktivní"), headers=headers)
    eid = create.json()["id"]

    # Terminate jednoho
    await client.delete(f"/api/v1/employees/{eid}", headers=headers)

    await client.post("/api/v1/employees", json=_emp_payload(first_name="Druhý aktivní"), headers=headers)

    active = await client.get("/api/v1/employees?emp_status=active", headers=headers)
    terminated = await client.get("/api/v1/employees?emp_status=terminated", headers=headers)

    assert all(e["status"] == "active" for e in active.json())
    assert all(e["status"] == "terminated" for e in terminated.json())


@pytest.mark.asyncio
async def test_filter_by_employment_type(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "e9")
    await client.post("/api/v1/employees", json=_emp_payload(employment_type="hpp"), headers=headers)
    await client.post("/api/v1/employees", json=_emp_payload(employment_type="dpp"), headers=headers)

    resp = await client.get("/api/v1/employees?employment_type=hpp", headers=headers)
    assert all(e["employment_type"] == "hpp" for e in resp.json())


# ── Přístupová práva ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_employee_can_see_own_record(client: AsyncClient) -> None:
    """Employee s propojeným user_id vidí svůj vlastní záznam."""
    ozo_headers, ozo_user_id = await _ozo_headers(client, "e10")

    # Vytvoříme employee user
    await client.post(
        "/api/v1/users",
        json={"email": "empuser_e10@emp.cz", "password": "heslo1234", "role": "employee"},
        headers=ozo_headers,
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "empuser_e10@emp.cz", "password": "heslo1234"},
    )
    emp_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    emp_user_id = (await client.get("/api/v1/users/me", headers=emp_headers)).json()["id"]

    # OZO vytvoří employee záznam propojený s tímto userem
    create = await client.post(
        "/api/v1/employees",
        json=_emp_payload(user_id=emp_user_id),
        headers=ozo_headers,
    )
    eid = create.json()["id"]

    # Employee může vidět svůj záznam
    resp = await client.get(f"/api/v1/employees/{eid}", headers=emp_headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_employee_cannot_see_other_record(client: AsyncClient) -> None:
    """Employee nesmí vidět záznamy jiných zaměstnanců."""
    ozo_headers, _ = await _ozo_headers(client, "e11")

    # Vytvoříme dva employee usery
    for suffix in ["11a", "11b"]:
        await client.post(
            "/api/v1/users",
            json={"email": f"empuser_{suffix}@emp.cz", "password": "heslo1234", "role": "employee"},
            headers=ozo_headers,
        )

    login_a = await client.post("/api/v1/auth/login", json={"email": "empuser_11a@emp.cz", "password": "heslo1234"})
    login_b = await client.post("/api/v1/auth/login", json={"email": "empuser_11b@emp.cz", "password": "heslo1234"})
    emp_a_headers = {"Authorization": f"Bearer {login_a.json()['access_token']}"}
    emp_b_headers = {"Authorization": f"Bearer {login_b.json()['access_token']}"}
    emp_b_user_id = (await client.get("/api/v1/users/me", headers=emp_b_headers)).json()["id"]

    # OZO vytvoří záznam pro emp B
    create = await client.post(
        "/api/v1/employees",
        json=_emp_payload(user_id=emp_b_user_id),
        headers=ozo_headers,
    )
    eid_b = create.json()["id"]

    # Employee A nesmí vidět záznam B
    resp = await client.get(f"/api/v1/employees/{eid_b}", headers=emp_a_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_employee_cannot_create(client: AsyncClient) -> None:
    """Employee nesmí vytvářet záznamy zaměstnanců."""
    ozo_headers, _ = await _ozo_headers(client, "e12")
    await client.post(
        "/api/v1/users",
        json={"email": "empuser_e12@emp.cz", "password": "heslo1234", "role": "employee"},
        headers=ozo_headers,
    )
    login = await client.post("/api/v1/auth/login", json={"email": "empuser_e12@emp.cz", "password": "heslo1234"})
    emp_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await client.post("/api/v1/employees", json=_emp_payload(), headers=emp_headers)
    assert resp.status_code == 403


# ── Tenant izolace ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tenant_isolation(client: AsyncClient) -> None:
    headers_a, _ = await _ozo_headers(client, "e13a")
    headers_b, _ = await _ozo_headers(client, "e13b")

    await client.post("/api/v1/employees", json=_emp_payload(), headers=headers_a)

    resp_b = await client.get("/api/v1/employees", headers=headers_b)
    assert resp_b.json() == []
