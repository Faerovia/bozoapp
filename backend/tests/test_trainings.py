"""
Testy pro evidenci školení BOZP/PO.

Klíčové BOZP invarianty které testujeme:
- valid_until se automaticky vypočítá z trained_at + valid_months
- školení bez valid_months → validity_status = 'no_expiry'
- správné odvozování validity_status (valid / expiring_soon / expired)
- employee vidí pouze vlastní záznamy (ne záznamy ostatních)
- employee nesmí vytvářet záznamy
- archivace místo smazání
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


async def _employee_in_tenant(client: AsyncClient, ozo_headers: dict, suffix: str) -> dict:
    """Vytvoří zaměstnance a vrátí jeho auth hlavičky."""
    await client.post(
        "/api/v1/users",
        json={"email": f"emp{suffix}@skoleni.cz", "password": "heslo1234", "role": "employee"},
        headers=ozo_headers,
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": f"emp{suffix}@skoleni.cz", "password": "heslo1234"},
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _my_user_id(client: AsyncClient, headers: dict) -> str:
    resp = await client.get("/api/v1/users/me", headers=headers)
    return resp.json()["id"]


def _training_payload(**overrides) -> dict:
    base = {
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
    emp_id = await _my_user_id(client, ozo_headers)

    resp = await client.post(
        "/api/v1/trainings",
        json=_training_payload(employee_id=emp_id, trained_at="2025-01-15", valid_months=24),
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
    emp_id = await _my_user_id(client, ozo_headers)

    resp = await client.post(
        "/api/v1/trainings",
        json=_training_payload(employee_id=emp_id, valid_months=None),
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
    emp_id = await _my_user_id(client, ozo_headers)

    resp = await client.post(
        "/api/v1/trainings",
        json=_training_payload(
            employee_id=emp_id,
            valid_months=12,
            valid_until="2028-06-30",  # přebíjí výpočet z valid_months
        ),
        headers=ozo_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["valid_until"] == "2028-06-30"


# ── Výpočet validity_status ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_validity_status_expired(client: AsyncClient) -> None:
    """Školení s valid_until v minulosti → expired."""
    ozo_headers = await _ozo_headers(client, "t4")
    emp_id = await _my_user_id(client, ozo_headers)

    resp = await client.post(
        "/api/v1/trainings",
        json=_training_payload(
            employee_id=emp_id,
            valid_months=None,
            valid_until="2020-01-01",  # minulost
        ),
        headers=ozo_headers,
    )
    assert resp.json()["validity_status"] == "expired"


@pytest.mark.asyncio
async def test_validity_status_expiring_soon(client: AsyncClient) -> None:
    """Školení expirující do 30 dní → expiring_soon."""
    ozo_headers = await _ozo_headers(client, "t5")
    emp_id = await _my_user_id(client, ozo_headers)

    soon = (date.today() + timedelta(days=15)).isoformat()
    resp = await client.post(
        "/api/v1/trainings",
        json=_training_payload(
            employee_id=emp_id,
            valid_months=None,
            valid_until=soon,
        ),
        headers=ozo_headers,
    )
    assert resp.json()["validity_status"] == "expiring_soon"


# ── Filtrování ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_filter_by_validity_status(client: AsyncClient) -> None:
    ozo_headers = await _ozo_headers(client, "t6")
    emp_id = await _my_user_id(client, ozo_headers)

    # Jedno platné, jedno prošlé
    await client.post(
        "/api/v1/trainings",
        json=_training_payload(employee_id=emp_id, valid_months=None, valid_until="2099-01-01"),
        headers=ozo_headers,
    )
    await client.post(
        "/api/v1/trainings",
        json=_training_payload(employee_id=emp_id, valid_months=None, valid_until="2020-01-01"),
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
    emp_a_headers = await _employee_in_tenant(client, ozo_headers, "7a")
    emp_b_headers = await _employee_in_tenant(client, ozo_headers, "7b")

    emp_a_id = await _my_user_id(client, emp_a_headers)
    emp_b_id = await _my_user_id(client, emp_b_headers)

    # OZO zaznamená školení pro oba
    await client.post(
        "/api/v1/trainings",
        json=_training_payload(employee_id=emp_a_id, title="Školení A"),
        headers=ozo_headers,
    )
    await client.post(
        "/api/v1/trainings",
        json=_training_payload(employee_id=emp_b_id, title="Školení B"),
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
    emp_headers = await _employee_in_tenant(client, ozo_headers, "8")
    emp_id = await _my_user_id(client, emp_headers)

    resp = await client.post(
        "/api/v1/trainings",
        json=_training_payload(employee_id=emp_id),
        headers=emp_headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_employee_cannot_read_other_employee_detail(client: AsyncClient) -> None:
    """Employee nesmí fetechnout detail školení jiného zaměstnance přes /trainings/{id}."""
    ozo_headers = await _ozo_headers(client, "t9")
    emp_a_headers = await _employee_in_tenant(client, ozo_headers, "9a")
    emp_b_headers = await _employee_in_tenant(client, ozo_headers, "9b")

    emp_a_id = await _my_user_id(client, emp_a_headers)

    create_resp = await client.post(
        "/api/v1/trainings",
        json=_training_payload(employee_id=emp_a_id),
        headers=ozo_headers,
    )
    training_id = create_resp.json()["id"]

    # Employee B se pokusí číst školení Employee A
    resp = await client.get(f"/api/v1/trainings/{training_id}", headers=emp_b_headers)
    assert resp.status_code == 403


# ── Archivace ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_archive_training_keeps_record(client: AsyncClient) -> None:
    """
    Kritický BOZP invariant: záznamy o školeních se nesmí fyzicky mazat.
    """
    ozo_headers = await _ozo_headers(client, "t10")
    emp_id = await _my_user_id(client, ozo_headers)

    create_resp = await client.post(
        "/api/v1/trainings",
        json=_training_payload(employee_id=emp_id),
        headers=ozo_headers,
    )
    training_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/api/v1/trainings/{training_id}", headers=ozo_headers)
    assert del_resp.status_code == 204

    # Záznam stále existuje, jen archivovaný
    get_resp = await client.get(f"/api/v1/trainings/{training_id}", headers=ozo_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "archived"
