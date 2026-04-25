"""
Testy pro modul Lékařské prohlídky.

Ověřujeme:
- CRUD + archivace (soft delete)
- Automatický výpočet valid_until z exam_date + valid_months
- validity_status computed property (no_expiry | valid | expiring_soon | expired)
- days_until_expiry computed property
- Filtrování (employee_id, exam_type, validity_status)
- Přístupová práva (employee vidí jen vlastní záznamy)
- Tenant izolace
"""

from datetime import date, timedelta

import pytest
from httpx import AsyncClient


async def _ozo_headers(client: AsyncClient, suffix: str) -> tuple[dict, str]:
    """Vrátí (headers, tenant_id přes registraci OZO)."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"ozo{suffix}@me.cz",
            "password": "heslo1234",
            "tenant_name": f"ME Firma {suffix}",
        },
    )
    data = resp.json()
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    me = await client.get("/api/v1/users/me", headers=headers)
    return headers, me.json()["id"]


async def _create_employee(client: AsyncClient, headers: dict, suffix: str) -> str:
    resp = await client.post(
        "/api/v1/employees",
        json={"first_name": "Test", "last_name": suffix, "employment_type": "hpp"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _create_exam(
    client: AsyncClient,
    headers: dict,
    employee_id: str,
    exam_type: str = "periodicka",
    **kwargs,
) -> dict:
    payload = {
        "employee_id": employee_id,
        "exam_type": exam_type,
        "exam_date": str(date.today()),
        **kwargs,
    }
    resp = await client.post("/api/v1/medical-exams", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── Základní CRUD ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_exam_minimal(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "m1")
    eid = await _create_employee(client, headers, "m1")
    exam = await _create_exam(client, headers, eid, exam_type="vstupni")

    assert exam["exam_type"] == "vstupni"
    assert exam["result"] is None
    assert exam["valid_until"] is None
    assert exam["validity_status"] == "no_expiry"
    assert exam["status"] == "active"


@pytest.mark.asyncio
async def test_create_exam_with_valid_months(client: AsyncClient) -> None:
    """valid_until se automaticky vypočítá z exam_date + valid_months."""
    headers, _ = await _ozo_headers(client, "m2")
    eid = await _create_employee(client, headers, "m2")

    today = date.today()
    exam = await _create_exam(
        client, headers, eid,
        exam_date=str(today),
        valid_months=24,
        result="zpusobily",
    )
    assert exam["valid_until"] is not None
    # valid_until = today + 24 měsíce
    parsed = date.fromisoformat(exam["valid_until"])
    assert parsed > today
    assert exam["validity_status"] in ("valid", "expiring_soon")


@pytest.mark.asyncio
async def test_list_exams(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "m3")
    eid = await _create_employee(client, headers, "m3")
    # Při vytvoření zaměstnance se auto-vygeneruje vstupní prohlídka draft
    # (bez RFA žádná odborná). Test pak přidá manuálně další 2 → celkem 3.
    await _create_exam(client, headers, eid, exam_type="vstupni")
    await _create_exam(client, headers, eid, exam_type="periodicka")

    resp = await client.get("/api/v1/medical-exams", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 3


@pytest.mark.asyncio
async def test_get_exam_by_id(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "m4")
    eid = await _create_employee(client, headers, "m4")
    exam = await _create_exam(client, headers, eid)

    resp = await client.get(f"/api/v1/medical-exams/{exam['id']}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == exam["id"]


@pytest.mark.asyncio
async def test_update_exam(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "m5")
    eid = await _create_employee(client, headers, "m5")
    exam = await _create_exam(client, headers, eid)

    resp = await client.patch(
        f"/api/v1/medical-exams/{exam['id']}",
        json={"result": "zpusobily", "physician_name": "MUDr. Novák"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["result"] == "zpusobily"
    assert resp.json()["physician_name"] == "MUDr. Novák"


@pytest.mark.asyncio
async def test_archive_exam(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "m6")
    eid = await _create_employee(client, headers, "m6")
    exam = await _create_exam(client, headers, eid)

    del_resp = await client.delete(f"/api/v1/medical-exams/{exam['id']}", headers=headers)
    assert del_resp.status_code == 204

    get_resp = await client.get(f"/api/v1/medical-exams/{exam['id']}", headers=headers)
    assert get_resp.json()["status"] == "archived"


# ── validity_status + days_until_expiry ───────────────────────────────────────

@pytest.mark.asyncio
async def test_validity_status_expired(client: AsyncClient) -> None:
    """Prohlídka s valid_until v minulosti → expired."""
    headers, _ = await _ozo_headers(client, "m7")
    eid = await _create_employee(client, headers, "m7")

    past_date = str(date.today() - timedelta(days=1))
    exam = await _create_exam(
        client, headers, eid,
        exam_date=str(date.today() - timedelta(days=400)),
        valid_until=past_date,
    )
    assert exam["validity_status"] == "expired"
    assert exam["days_until_expiry"] is not None
    assert exam["days_until_expiry"] < 0


@pytest.mark.asyncio
async def test_validity_status_expiring_soon(client: AsyncClient) -> None:
    """Prohlídka, která vyprší za 30 dní → expiring_soon."""
    headers, _ = await _ozo_headers(client, "m8")
    eid = await _create_employee(client, headers, "m8")

    soon = str(date.today() + timedelta(days=30))
    exam = await _create_exam(client, headers, eid, valid_until=soon)
    assert exam["validity_status"] == "expiring_soon"
    assert 0 <= exam["days_until_expiry"] <= 60


@pytest.mark.asyncio
async def test_validity_status_valid(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "m9")
    eid = await _create_employee(client, headers, "m9")

    future = str(date.today() + timedelta(days=200))
    exam = await _create_exam(client, headers, eid, valid_until=future)
    assert exam["validity_status"] == "valid"


# ── Filtrování ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_filter_by_employee(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "m10")
    eid_a = await _create_employee(client, headers, "m10a")
    eid_b = await _create_employee(client, headers, "m10b")
    await _create_exam(client, headers, eid_a)
    await _create_exam(client, headers, eid_b)

    resp = await client.get(f"/api/v1/medical-exams?employee_id={eid_a}", headers=headers)
    assert resp.status_code == 200
    assert all(e["employee_id"] == eid_a for e in resp.json())


@pytest.mark.asyncio
async def test_filter_by_exam_type(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "m11")
    eid = await _create_employee(client, headers, "m11")
    await _create_exam(client, headers, eid, exam_type="vstupni")
    await _create_exam(client, headers, eid, exam_type="periodicka")

    resp = await client.get("/api/v1/medical-exams?exam_type=vstupni", headers=headers)
    assert all(e["exam_type"] == "vstupni" for e in resp.json())


@pytest.mark.asyncio
async def test_filter_by_validity_status(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "m12")
    eid = await _create_employee(client, headers, "m12")

    past = str(date.today() - timedelta(days=1))
    future = str(date.today() + timedelta(days=200))
    await _create_exam(client, headers, eid, valid_until=past)
    await _create_exam(client, headers, eid, valid_until=future)

    expired = await client.get("/api/v1/medical-exams?validity_status=expired", headers=headers)
    valid = await client.get("/api/v1/medical-exams?validity_status=valid", headers=headers)

    assert all(e["validity_status"] == "expired" for e in expired.json())
    assert all(e["validity_status"] == "valid" for e in valid.json())


# ── Přístupová práva ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_employee_sees_own_exam(client: AsyncClient) -> None:
    ozo_headers, _ = await _ozo_headers(client, "m13")

    await client.post(
        "/api/v1/users",
        json={"email": "empuser_m13@me.cz", "password": "heslo1234", "role": "employee"},
        headers=ozo_headers,
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "empuser_m13@me.cz", "password": "heslo1234"},
    )
    emp_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    emp_user_id = (await client.get("/api/v1/users/me", headers=emp_headers)).json()["id"]

    emp_rec = await client.post(
        "/api/v1/employees",
        json={"first_name": "Emp", "last_name": "M13", "employment_type": "hpp",
              "user_id": emp_user_id},
        headers=ozo_headers,
    )
    eid = emp_rec.json()["id"]
    exam = await _create_exam(client, ozo_headers, eid)

    resp = await client.get(f"/api/v1/medical-exams/{exam['id']}", headers=emp_headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_employee_cannot_see_other_exam(client: AsyncClient) -> None:
    ozo_headers, _ = await _ozo_headers(client, "m14")

    for suffix in ["14a", "14b"]:
        await client.post(
            "/api/v1/users",
            json={"email": f"empuser_{suffix}@me.cz", "password": "heslo1234", "role": "employee"},
            headers=ozo_headers,
        )

    login_a = await client.post("/api/v1/auth/login", json={"email": "empuser_14a@me.cz", "password": "heslo1234"})
    login_b = await client.post("/api/v1/auth/login", json={"email": "empuser_14b@me.cz", "password": "heslo1234"})
    emp_a_headers = {"Authorization": f"Bearer {login_a.json()['access_token']}"}
    emp_b_id = (await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {login_b.json()['access_token']}"})).json()["id"]

    emp_b_rec = await client.post(
        "/api/v1/employees",
        json={"first_name": "Emp", "last_name": "B14", "employment_type": "hpp",
              "user_id": emp_b_id},
        headers=ozo_headers,
    )
    eid_b = emp_b_rec.json()["id"]
    exam_b = await _create_exam(client, ozo_headers, eid_b)

    resp = await client.get(f"/api/v1/medical-exams/{exam_b['id']}", headers=emp_a_headers)
    assert resp.status_code == 403


# ── Tenant izolace ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tenant_isolation(client: AsyncClient) -> None:
    headers_a, _ = await _ozo_headers(client, "mt1a")
    headers_b, _ = await _ozo_headers(client, "mt1b")

    eid = await _create_employee(client, headers_a, "mt1")
    await _create_exam(client, headers_a, eid)

    resp_b = await client.get("/api/v1/medical-exams", headers=headers_b)
    assert resp_b.json() == []
