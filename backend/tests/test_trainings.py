"""
Testy nového Training modelu (commit 11a):
Training (šablona) + TrainingAssignment + TrainingAttempt.
"""
import io

import pytest
from httpx import AsyncClient


async def _ozo_headers(client: AsyncClient, suffix: str) -> tuple[dict, str]:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"ozo_tr_{suffix}@me.cz",
            "password": "heslo1234",
            "tenant_name": f"Firma TR {suffix}",
        },
    )
    data = resp.json()
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    return headers, data["access_token"]


async def _create_employee(
    client: AsyncClient, headers: dict, last: str, email: str | None = None
) -> str:
    payload: dict = {
        "first_name": "Emp",
        "last_name": last,
        "employment_type": "hpp",
    }
    if email:
        payload["email"] = email
    resp = await client.post("/api/v1/employees", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _create_training(
    client: AsyncClient, headers: dict, title: str, **extra
) -> dict:
    payload = {
        "title": title,
        "training_type": "bozp",
        "trainer_kind": "employer",
        "valid_months": 12,
        **extra,
    }
    resp = await client.post("/api/v1/trainings", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── Training template CRUD ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_training_template(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "t1")
    t = await _create_training(client, headers, "BOZP vstupní školení")
    assert t["title"] == "BOZP vstupní školení"
    assert t["training_type"] == "bozp"
    assert t["trainer_kind"] == "employer"
    assert t["valid_months"] == 12
    assert t["has_test"] is False
    assert t["question_count"] == 0


@pytest.mark.asyncio
async def test_duplicate_title_rejected(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "t2")
    await _create_training(client, headers, "Duplicitní")
    resp = await client.post(
        "/api/v1/trainings",
        json={"title": "Duplicitní", "training_type": "bozp", "valid_months": 12},
        headers=headers,
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_list_trainings(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "t3")
    await _create_training(client, headers, "A")
    await _create_training(client, headers, "B")
    resp = await client.get("/api/v1/trainings", headers=headers)
    assert resp.status_code == 200
    titles = [t["title"] for t in resp.json()]
    assert "A" in titles and "B" in titles


@pytest.mark.asyncio
async def test_update_training_valid_months(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "t4")
    t = await _create_training(client, headers, "ToUpdate", valid_months=6)
    upd = await client.patch(
        f"/api/v1/trainings/{t['id']}",
        json={"valid_months": 24},
        headers=headers,
    )
    assert upd.status_code == 200
    assert upd.json()["valid_months"] == 24


@pytest.mark.asyncio
async def test_delete_training(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "t5")
    t = await _create_training(client, headers, "ToDelete")
    resp = await client.delete(f"/api/v1/trainings/{t['id']}", headers=headers)
    assert resp.status_code == 204
    get_resp = await client.get(f"/api/v1/trainings/{t['id']}", headers=headers)
    assert get_resp.status_code == 404


# ── Assignments ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_assignments_bulk(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "a1")
    t = await _create_training(client, headers, "Vstupní")
    e1 = await _create_employee(client, headers, "E1")
    e2 = await _create_employee(client, headers, "E2")

    resp = await client.post(
        "/api/v1/trainings/assignments",
        json={"training_id": t["id"], "employee_ids": [e1, e2]},
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["created_count"] == 2
    assert body["skipped_existing_count"] == 0


@pytest.mark.asyncio
async def test_assignments_skip_duplicate(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "a2")
    t = await _create_training(client, headers, "Dup")
    e1 = await _create_employee(client, headers, "Dup")

    r1 = await client.post(
        "/api/v1/trainings/assignments",
        json={"training_id": t["id"], "employee_ids": [e1]},
        headers=headers,
    )
    assert r1.json()["created_count"] == 1

    r2 = await client.post(
        "/api/v1/trainings/assignments",
        json={"training_id": t["id"], "employee_ids": [e1]},
        headers=headers,
    )
    assert r2.json()["created_count"] == 0
    assert r2.json()["skipped_existing_count"] == 1


@pytest.mark.asyncio
async def test_assignment_deadline_7_days(client: AsyncClient) -> None:
    from datetime import date
    headers, _ = await _ozo_headers(client, "a3")
    t = await _create_training(client, headers, "Deadline")
    emp_id = await _create_employee(client, headers, "Dead")
    await client.post(
        "/api/v1/trainings/assignments",
        json={"training_id": t["id"], "employee_ids": [emp_id]},
        headers=headers,
    )
    list_resp = await client.get(
        f"/api/v1/trainings/{t['id']}/assignments", headers=headers
    )
    ta = list_resp.json()[0]
    assigned = date.fromisoformat(ta["assigned_at"][:10])
    deadline = date.fromisoformat(ta["deadline"][:10])
    assert (deadline - assigned).days == 7


# ── Test CSV parsing ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_test_csv_too_few_rejected(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "cs1")
    t = await _create_training(client, headers, "S testem")

    csv_short = b"otazka,spravna,a,b,c\n" + b"\n".join(
        f"q{i},correct{i},w1_{i},w2_{i},w3_{i}".encode() for i in range(4)
    )
    resp = await client.post(
        f"/api/v1/trainings/{t['id']}/test",
        data={"pass_percentage": "80"},
        files={"file": ("test.csv", io.BytesIO(csv_short), "text/csv")},
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_upload_test_csv_valid(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "cs2")
    t = await _create_training(client, headers, "S testem OK")

    lines = ["otazka,spravna,a,b,c"]
    for i in range(5):
        lines.append(f"Otazka {i}?,Spravna{i},Spatna1_{i},Spatna2_{i},Spatna3_{i}")
    csv_content = "\n".join(lines).encode("utf-8")

    resp = await client.post(
        f"/api/v1/trainings/{t['id']}/test",
        data={"pass_percentage": "80"},
        files={"file": ("test.csv", io.BytesIO(csv_content), "text/csv")},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["question_count"] == 5
    assert resp.json()["pass_percentage"] == 80


@pytest.mark.asyncio
async def test_test_template_downloadable(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "cs3")
    resp = await client.get("/api/v1/trainings/test-template", headers=headers)
    assert resp.status_code == 200


# ── Tenant isolation ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_training_tenant_isolation(client: AsyncClient) -> None:
    h_a, _ = await _ozo_headers(client, "iso_a")
    h_b, _ = await _ozo_headers(client, "iso_b")

    await _create_training(client, h_a, "A training")

    resp_b = await client.get("/api/v1/trainings", headers=h_b)
    assert all(t["title"] != "A training" for t in resp_b.json())
