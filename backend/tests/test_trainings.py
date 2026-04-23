"""
Testy pro evidenci školení BOZP/PO.

Klíčové BOZP invarianty které testujeme:
- valid_until se automaticky vypočítá z trained_at + valid_months
- školení bez valid_months → validity_status = 'no_expiry'
- správné odvozování validity_status (valid / expiring_soon / expired)
- employee vidí pouze vlastní záznamy (ne záznamy ostatních)
- employee nesmí vytvářet záznamy
- archivace místo smazání

Po refaktoru (007_employees):
- employee_id odkazuje na employees.id (ne users.id)
- employee access se resolvuje přes employees.user_id
"""

from datetime import date, timedelta

import pytest
from httpx import AsyncClient


async def _ozo_headers(client: AsyncClient, suffix: str = "") -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"ozo{suffix}@skoleni.cz",
            "password": "heslo1234",
            "tenant_name": f"Firma {suffix}",
        },
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _create_employee(client: AsyncClient, ozo_headers: dict, suffix: str, user_id: str | None = None) -> str:
    """Vytvoří HR záznam zaměstnance a vrátí jeho employees.id."""
    resp = await client.post(
        "/api/v1/employees",
        json={
            "first_name": "Testovací",
            "last_name": f"Zaměstnanec {suffix}",
            "user_id": user_id,
            "employment_type": "hpp",
        },
        headers=ozo_headers,
    )
    assert resp.status_code == 201, f"create_employee failed: {resp.json()}"
    return resp.json()["id"]


async def _employee_in_tenant(client: AsyncClient, ozo_headers: dict, suffix: str) -> tuple[dict, str]:
    """
    Vytvoří employee User (auth) + Employee (HR) ve stejném tenantu.
    Vrátí (employee_headers, employee_record_id).
    """
    await client.post(
        "/api/v1/users",
        json={"email": f"emp{suffix}@skoleni.cz", "password": "heslo1234", "role": "employee"},
        headers=ozo_headers,
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": f"emp{suffix}@skoleni.cz", "password": "heslo1234"},
    )
    emp_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    user_id = (await client.get("/api/v1/users/me", headers=emp_headers)).json()["id"]

    # Vytvoříme HR záznam propojený s tímto userem
    emp_id = await _create_employee(client, ozo_headers, suffix, user_id=user_id)
    return emp_headers, emp_id


def _training_payload(employee_id: str, **overrides) -> dict:
    base = {
        "employee_id": employee_id,
        "title": "BOZP vstupní školení",
        "training_type": "bozp_initial",
        "trained_at": "2025-01-15",
        "valid_months": 24,
        "trainer_name": "Ing. Novák",
    }
    base.update(overrides)
    return base


# ── Vytváření záznamů ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_training_computes_valid_until(client: AsyncClient) -> None:
    """valid_until musí být trained_at + valid_months měsíců."""
    ozo_headers = await _ozo_headers(client, "t1")
    emp_id = await _create_employee(client, ozo_headers, "t1")

    resp = await client.post(
        "/api/v1/trainings",
        json=_training_payload(emp_id, trained_at="2025-01-15", valid_months=24),
        headers=ozo_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["valid_until"] == "2027-01-15"
    assert data["validity_status"] == "valid"


@pytest.mark.asyncio
async def test_create_training_no_expiry(client: AsyncClient) -> None:
    """Školení bez valid_months → valid_until None, validity_status = no_expiry."""
    ozo_headers = await _ozo_headers(client, "t2")
    emp_id = await _create_employee(client, ozo_headers, "t2")

    resp = await client.post(
        "/api/v1/trainings",
        json=_training_payload(emp_id, valid_months=None),
        headers=ozo_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["valid_until"] is None
    assert data["validity_status"] == "no_expiry"


@pytest.mark.asyncio
async def test_create_training_explicit_valid_until(client: AsyncClient) -> None:
    """Explicitně zadaný valid_until má přednost."""
    ozo_headers = await _ozo_headers(client, "t3")
    emp_id = await _create_employee(client, ozo_headers, "t3")

    resp = await client.post(
        "/api/v1/trainings",
        json=_training_payload(emp_id, valid_months=12, valid_until="2028-06-30"),
        headers=ozo_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["valid_until"] == "2028-06-30"


# ── Výpočet validity_status ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_validity_status_expired(client: AsyncClient) -> None:
    """Školení s valid_until v minulosti → expired."""
    ozo_headers = await _ozo_headers(client, "t4")
    emp_id = await _create_employee(client, ozo_headers, "t4")

    resp = await client.post(
        "/api/v1/trainings",
        json=_training_payload(emp_id, valid_months=None, valid_until="2020-01-01"),
        headers=ozo_headers,
    )
    assert resp.json()["validity_status"] == "expired"


@pytest.mark.asyncio
async def test_validity_status_expiring_soon(client: AsyncClient) -> None:
    """Školení expirující do 30 dní → expiring_soon."""
    ozo_headers = await _ozo_headers(client, "t5")
    emp_id = await _create_employee(client, ozo_headers, "t5")

    soon = (date.today() + timedelta(days=15)).isoformat()
    resp = await client.post(
        "/api/v1/trainings",
        json=_training_payload(emp_id, valid_months=None, valid_until=soon),
        headers=ozo_headers,
    )
    assert resp.json()["validity_status"] == "expiring_soon"


# ── Filtrování ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_filter_by_validity_status(client: AsyncClient) -> None:
    ozo_headers = await _ozo_headers(client, "t6")
    emp_id = await _create_employee(client, ozo_headers, "t6")

    await client.post(
        "/api/v1/trainings",
        json=_training_payload(emp_id, valid_months=None, valid_until="2099-01-01"),
        headers=ozo_headers,
    )
    await client.post(
        "/api/v1/trainings",
        json=_training_payload(emp_id, valid_months=None, valid_until="2020-01-01"),
        headers=ozo_headers,
    )

    valid_resp = await client.get("/api/v1/trainings?validity_status=valid", headers=ozo_headers)
    expired_resp = await client.get("/api/v1/trainings?validity_status=expired", headers=ozo_headers)

    assert all(t["validity_status"] == "valid" for t in valid_resp.json())
    assert all(t["validity_status"] == "expired" for t in expired_resp.json())


# ── Přístupová práva ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_employee_sees_only_own_trainings(client: AsyncClient) -> None:
    """
    Kritický invariant: employee nesmí vidět záznamy jiných zaměstnanců.
    OZO vidí záznamy obou.
    """
    ozo_headers = await _ozo_headers(client, "t7")
    emp_a_headers, emp_a_id = await _employee_in_tenant(client, ozo_headers, "7a")
    emp_b_headers, emp_b_id = await _employee_in_tenant(client, ozo_headers, "7b")

    await client.post(
        "/api/v1/trainings",
        json=_training_payload(emp_a_id, title="Školení A"),
        headers=ozo_headers,
    )
    await client.post(
        "/api/v1/trainings",
        json=_training_payload(emp_b_id, title="Školení B"),
        headers=ozo_headers,
    )

    # Employee A vidí jen své záznamy
    resp_a = await client.get("/api/v1/trainings", headers=emp_a_headers)
    titles_a = [t["title"] for t in resp_a.json()]
    assert "Školení A" in titles_a
    assert "Školení B" not in titles_a

    # OZO vidí oba
    resp_ozo = await client.get("/api/v1/trainings", headers=ozo_headers)
    titles_ozo = [t["title"] for t in resp_ozo.json()]
    assert "Školení A" in titles_ozo
    assert "Školení B" in titles_ozo


@pytest.mark.asyncio
async def test_employee_cannot_create_training(client: AsyncClient) -> None:
    ozo_headers = await _ozo_headers(client, "t8")
    emp_headers, emp_id = await _employee_in_tenant(client, ozo_headers, "8")

    resp = await client.post(
        "/api/v1/trainings",
        json=_training_payload(emp_id),
        headers=emp_headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_employee_cannot_read_other_employee_detail(client: AsyncClient) -> None:
    """Employee nesmí fetchnout detail školení jiného zaměstnance přes /trainings/{id}."""
    ozo_headers = await _ozo_headers(client, "t9")
    emp_a_headers, emp_a_id = await _employee_in_tenant(client, ozo_headers, "9a")
    emp_b_headers, _ = await _employee_in_tenant(client, ozo_headers, "9b")

    create_resp = await client.post(
        "/api/v1/trainings",
        json=_training_payload(emp_a_id),
        headers=ozo_headers,
    )
    training_id = create_resp.json()["id"]

    # Employee B se pokusí číst školení Employee A
    resp = await client.get(f"/api/v1/trainings/{training_id}", headers=emp_b_headers)
    assert resp.status_code == 403


# ── Archivace ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_archive_training_keeps_record(client: AsyncClient) -> None:
    """Kritický BOZP invariant: záznamy o školeních se nesmí fyzicky mazat."""
    ozo_headers = await _ozo_headers(client, "t10")
    emp_id = await _create_employee(client, ozo_headers, "t10")

    create_resp = await client.post(
        "/api/v1/trainings",
        json=_training_payload(emp_id),
        headers=ozo_headers,
    )
    training_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/api/v1/trainings/{training_id}", headers=ozo_headers)
    assert del_resp.status_code == 204

    get_resp = await client.get(f"/api/v1/trainings/{training_id}", headers=ozo_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "archived"
