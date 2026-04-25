"""
Testy pro cross-tenant FK injection ochranu.

Scénář: útočník v tenantu A se pokusí vytvořit entitu odkazující na
foreign key z tenantu B. Service vrstva má `assert_in_tenant()` helper,
který takový pokus odmítne s 422.

Pokrývá: trainings, medical_exams, oopp, accident_reports, risks, revisions,
employees.
"""
from datetime import date

import pytest
from httpx import AsyncClient


async def _register_tenant(client: AsyncClient, suffix: str) -> tuple[dict, str, str]:
    """Vrátí (headers, user_id, tenant_id přes registraci)."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"owner{suffix}@me.cz",
            "password": "heslo1234",
            "tenant_name": f"Firma {suffix}",
        },
    )
    data = resp.json()
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    me = await client.get("/api/v1/users/me", headers=headers)
    me_data = me.json()
    return headers, me_data["id"], me_data["tenant_id"]


async def _create_employee(client: AsyncClient, headers: dict, name: str) -> str:
    resp = await client.post(
        "/api/v1/employees",
        json={"first_name": "Emp", "last_name": name, "employment_type": "hpp"},
        headers=headers,
    )
    return resp.json()["id"]


async def _create_risk(client: AsyncClient, headers: dict, title: str) -> str:
    resp = await client.post(
        "/api/v1/risks",
        json={
            "title": title,
            "probability": 3,
            "severity": 3,
        },
        headers=headers,
    )
    return resp.json()["id"]


# ── FK: employee_id across tenants ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_training_rejects_cross_tenant_employee(client: AsyncClient) -> None:
    h_a, _, _ = await _register_tenant(client, "fk1a")
    h_b, _, _ = await _register_tenant(client, "fk1b")

    emp_b = await _create_employee(client, h_b, "B")

    # Tenant A se pokusí vytvořit training pro employee z tenantu B
    resp = await client.post(
        "/api/v1/trainings",
        json={
            "employee_id": emp_b,
            "title": "Cross-tenant injection attempt",
            "training_type": "bozp_initial",
            "trained_at": str(date.today()),
        },
        headers=h_a,
    )
    assert resp.status_code == 422
    assert "employee_id" in resp.text


@pytest.mark.asyncio
async def test_medical_exam_rejects_cross_tenant_employee(client: AsyncClient) -> None:
    h_a, _, _ = await _register_tenant(client, "fk2a")
    h_b, _, _ = await _register_tenant(client, "fk2b")

    emp_b = await _create_employee(client, h_b, "B")

    resp = await client.post(
        "/api/v1/medical-exams",
        json={
            "employee_id": emp_b,
            "exam_type": "periodicka",
            "exam_date": str(date.today()),
        },
        headers=h_a,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_oopp_rejects_cross_tenant_employee(client: AsyncClient) -> None:
    """V novém OOPP modelu (NV 390/2021) se výdej váže na employee_id +
    position_oopp_item_id. Cross-tenant employee musí být rejectnutý."""
    h_a, _, _ = await _register_tenant(client, "fk3a")
    h_b, _, _ = await _register_tenant(client, "fk3b")

    emp_b = await _create_employee(client, h_b, "B")

    # Vytvoř pozici + OOPP item pod tenantem A
    plant_a = (await client.post(
        "/api/v1/plants", json={"name": "P-A"}, headers=h_a
    )).json()
    wp_a = (await client.post(
        "/api/v1/workplaces",
        json={"plant_id": plant_a["id"], "name": "W-A"},
        headers=h_a,
    )).json()
    pos_a = (await client.post(
        "/api/v1/job-positions",
        json={"name": "Pozice A", "workplace_id": wp_a["id"]},
        headers=h_a,
    )).json()
    item_a = (await client.post(
        "/api/v1/oopp/items",
        json={"job_position_id": pos_a["id"], "body_part": "G", "name": "Rukavice"},
        headers=h_a,
    )).json()

    # Pokus pod h_a vytvořit issue s emp_b z tenantu B → 422
    resp = await client.post(
        "/api/v1/oopp/issues",
        json={
            "employee_id": emp_b,
            "position_oopp_item_id": item_a["id"],
            "issued_at": str(date.today()),
        },
        headers=h_a,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_accident_report_rejects_cross_tenant_employee(client: AsyncClient) -> None:
    h_a, _, _ = await _register_tenant(client, "fk4a")
    h_b, _, _ = await _register_tenant(client, "fk4b")

    emp_b = await _create_employee(client, h_b, "B")

    resp = await client.post(
        "/api/v1/accident-reports",
        json={
            "employee_id": emp_b,
            "employee_name": "Fake",
            "workplace": "sklad",
            "accident_date": str(date.today()),
            "accident_time": "10:00:00",
            "injury_type": "řezná rána",
            "injured_body_part": "ruka",
            "injury_source": "nůž",
            "injury_cause": "neopatrnost",
            "description": "test",
        },
        headers=h_a,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_accident_report_rejects_cross_tenant_risk(client: AsyncClient) -> None:
    h_a, _, _ = await _register_tenant(client, "fk5a")
    h_b, _, _ = await _register_tenant(client, "fk5b")

    risk_b = await _create_risk(client, h_b, "Riziko v tenantu B")

    resp = await client.post(
        "/api/v1/accident-reports",
        json={
            "employee_name": "Someone",
            "workplace": "sklad",
            "accident_date": str(date.today()),
            "accident_time": "10:00:00",
            "injury_type": "řezná rána",
            "injured_body_part": "ruka",
            "injury_source": "nůž",
            "injury_cause": "neopatrnost",
            "description": "test",
            "risk_id": risk_b,
        },
        headers=h_a,
    )
    assert resp.status_code == 422


# ── FK: responsible_user_id across tenants ────────────────────────────────────

@pytest.mark.asyncio
async def test_risk_rejects_cross_tenant_responsible_user(client: AsyncClient) -> None:
    h_a, _, _ = await _register_tenant(client, "fk6a")
    _, user_b_id, _ = await _register_tenant(client, "fk6b")

    resp = await client.post(
        "/api/v1/risks",
        json={
            "title": "Test riziko",
            "probability": 3,
            "severity": 3,
            "responsible_user_id": user_b_id,
        },
        headers=h_a,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_revision_rejects_cross_tenant_responsible_user(client: AsyncClient) -> None:
    h_a, _, _ = await _register_tenant(client, "fk7a")
    _, user_b_id, _ = await _register_tenant(client, "fk7b")

    resp = await client.post(
        "/api/v1/revisions",
        json={
            "title": "Revize elektra",
            "revision_type": "electrical",
            "last_revised_at": str(date.today()),
            "valid_months": 12,
            "responsible_user_id": user_b_id,
        },
        headers=h_a,
    )
    assert resp.status_code == 422


# ── FK: user_id pro employees ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_employee_rejects_cross_tenant_user_id(client: AsyncClient) -> None:
    h_a, _, _ = await _register_tenant(client, "fk8a")
    _, user_b_id, _ = await _register_tenant(client, "fk8b")

    resp = await client.post(
        "/api/v1/employees",
        json={
            "first_name": "Emp",
            "last_name": "Cross",
            "employment_type": "hpp",
            "user_id": user_b_id,
        },
        headers=h_a,
    )
    assert resp.status_code == 422


# ── Happy path: FK ze stejného tenantu projde ────────────────────────────────
# Po refaktoru Training v commitu 11a má FK validaci employee_id už jen
# flow `POST /trainings/assignments` (šablona nemá employee_id přímo).

@pytest.mark.asyncio
async def test_training_accepts_own_tenant_employee(client: AsyncClient) -> None:
    h_a, _, _ = await _register_tenant(client, "fk9")
    emp_a = await _create_employee(client, h_a, "OwnTenant")

    # Vytvoř šablonu (bez employee_id — ten přiřazení flow)
    t_resp = await client.post(
        "/api/v1/trainings",
        json={
            "title": "BOZP školení",
            "training_type": "bozp",
            "trainer_kind": "employer",
            "valid_months": 12,
        },
        headers=h_a,
    )
    assert t_resp.status_code == 201
    training_id = t_resp.json()["id"]

    # Přiřaď employee ze STEJNÉHO tenantu — FK check propustí
    assign_resp = await client.post(
        "/api/v1/trainings/assignments",
        json={"training_id": training_id, "employee_ids": [emp_a]},
        headers=h_a,
    )
    assert assign_resp.status_code == 201
    assert assign_resp.json()["created_count"] == 1
