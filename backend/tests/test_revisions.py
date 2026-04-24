"""
Testy pro modul Revize (zařízení + timeline + zodpovědnosti + QR).

BOZP invarianty:
- next_revision_at se automaticky vypočítá z last_revised_at + valid_months
- správné odvozování due_status (overdue / due_soon / ok / no_schedule)
- archivace místo smazání
- každá zařízení povinně plant_id + striktní device_type enum
- timeline = revision_records, vždy alespoň jeden záznam pokud last_revised_at je zadán
- QR token je unikátní a endpoint /qr.png vrací PNG
- employee_plant_responsibilities (M:N) řídí kdo smí přes /records zaznamenat
"""
from datetime import date, timedelta

import pytest
from httpx import AsyncClient



# ── Helpers ──────────────────────────────────────────────────────────────────

async def _register_ozo(client: AsyncClient, suffix: str) -> str:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"ozo{suffix}@revize.cz",
            "password": "heslo1234",
            "tenant_name": f"Firma {suffix}",
        },
    )
    return resp.json()["access_token"]


async def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_plant(client: AsyncClient, headers: dict, name: str = "Provozovna Praha") -> str:
    resp = await client.post(
        "/api/v1/plants",
        json={"name": name, "city": "Praha"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _device_payload(plant_id: str, **overrides) -> dict:
    base = {
        "title": "Elektrorevize rozvodny",
        "plant_id": plant_id,
        "device_type": "elektro",
        "device_code": "ROZVAD-01",
        "location": "Hala A",
        "last_revised_at": "2024-01-15",
        "valid_months": 12,
        "technician_name": "Ing. Novák",
        "technician_email": "novak@revize.cz",
        "technician_phone": "+420777111222",
    }
    base.update(overrides)
    return base


# ── Základní CRUD ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_device_computes_next_revision(client: AsyncClient) -> None:
    token = await _register_ozo(client, "rv1")
    headers = await _auth(token)
    plant_id = await _create_plant(client, headers)

    resp = await client.post(
        "/api/v1/revisions",
        json=_device_payload(plant_id, last_revised_at="2024-03-15", valid_months=12),
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["next_revision_at"] == "2025-03-15"
    assert data["plant_id"] == plant_id
    assert data["plant_name"] == "Provozovna Praha"
    assert data["device_type"] == "elektro"
    assert data["qr_token"]   # vygenerován automaticky
    assert len(data["qr_token"]) >= 8


@pytest.mark.asyncio
async def test_create_device_without_plant_is_accepted(client: AsyncClient) -> None:
    """plant_id je doporučené, ale na API úrovni optional (zpětná kompat).
    Frontend vynucuje plant_id v novém modelu."""
    token = await _register_ozo(client, "rv2")
    headers = await _auth(token)

    resp = await client.post(
        "/api/v1/revisions",
        json={"title": "Legacy zařízení", "device_type": "elektro", "valid_months": 12},
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["plant_id"] is None


@pytest.mark.asyncio
async def test_device_type_must_be_valid_enum(client: AsyncClient) -> None:
    token = await _register_ozo(client, "rv3")
    headers = await _auth(token)
    plant_id = await _create_plant(client, headers)

    resp = await client.post(
        "/api/v1/revisions",
        json=_device_payload(plant_id, device_type="solar_panels"),
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_explicit_next_revision_takes_precedence(client: AsyncClient) -> None:
    token = await _register_ozo(client, "rv4")
    headers = await _auth(token)
    plant_id = await _create_plant(client, headers)

    resp = await client.post(
        "/api/v1/revisions",
        json=_device_payload(
            plant_id,
            last_revised_at="2024-01-01",
            valid_months=12,
            next_revision_at="2028-06-30",
        ),
        headers=headers,
    )
    assert resp.json()["next_revision_at"] == "2028-06-30"


# ── due_status ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_due_status_overdue(client: AsyncClient) -> None:
    token = await _register_ozo(client, "rv5")
    headers = await _auth(token)
    plant_id = await _create_plant(client, headers)

    resp = await client.post(
        "/api/v1/revisions",
        json=_device_payload(
            plant_id,
            last_revised_at=None,
            next_revision_at="2020-01-01",
        ),
        headers=headers,
    )
    assert resp.json()["due_status"] == "overdue"


@pytest.mark.asyncio
async def test_due_status_due_soon(client: AsyncClient) -> None:
    token = await _register_ozo(client, "rv6")
    headers = await _auth(token)
    plant_id = await _create_plant(client, headers)

    soon = (date.today() + timedelta(days=15)).isoformat()
    resp = await client.post(
        "/api/v1/revisions",
        json=_device_payload(
            plant_id,
            last_revised_at=None,
            next_revision_at=soon,
        ),
        headers=headers,
    )
    assert resp.json()["due_status"] == "due_soon"


@pytest.mark.asyncio
async def test_due_status_ok(client: AsyncClient) -> None:
    token = await _register_ozo(client, "rv7")
    headers = await _auth(token)
    plant_id = await _create_plant(client, headers)

    future = (date.today() + timedelta(days=60)).isoformat()
    resp = await client.post(
        "/api/v1/revisions",
        json=_device_payload(
            plant_id,
            last_revised_at=None,
            next_revision_at=future,
        ),
        headers=headers,
    )
    assert resp.json()["due_status"] == "ok"


# ── Filtry ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_filter_by_plant_and_device_type(client: AsyncClient) -> None:
    token = await _register_ozo(client, "rv8")
    headers = await _auth(token)
    plant_a = await _create_plant(client, headers, "Praha")
    plant_b = await _create_plant(client, headers, "Brno")

    await client.post(
        "/api/v1/revisions",
        json=_device_payload(plant_a, device_type="elektro", title="A1"),
        headers=headers,
    )
    await client.post(
        "/api/v1/revisions",
        json=_device_payload(plant_b, device_type="plyn", title="B1"),
        headers=headers,
    )

    by_plant = await client.get(
        f"/api/v1/revisions?plant_id={plant_a}", headers=headers
    )
    by_type = await client.get(
        "/api/v1/revisions?device_type=plyn", headers=headers
    )

    assert [r["title"] for r in by_plant.json()] == ["A1"]
    assert [r["title"] for r in by_type.json()] == ["B1"]


# ── Archivace ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_archive_device(client: AsyncClient) -> None:
    token = await _register_ozo(client, "rv9")
    headers = await _auth(token)
    plant_id = await _create_plant(client, headers)

    create = await client.post(
        "/api/v1/revisions", json=_device_payload(plant_id), headers=headers
    )
    rid = create.json()["id"]

    dele = await client.delete(f"/api/v1/revisions/{rid}", headers=headers)
    assert dele.status_code == 204

    after = await client.get(f"/api/v1/revisions/{rid}", headers=headers)
    assert after.json()["status"] == "archived"


# ── Timeline (records) ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_device_with_last_revised_creates_first_record(
    client: AsyncClient,
) -> None:
    token = await _register_ozo(client, "rv10")
    headers = await _auth(token)
    plant_id = await _create_plant(client, headers)

    create = await client.post(
        "/api/v1/revisions",
        json=_device_payload(plant_id, last_revised_at="2024-01-15"),
        headers=headers,
    )
    rid = create.json()["id"]

    records = await client.get(f"/api/v1/revisions/{rid}/records", headers=headers)
    assert records.status_code == 200
    lst = records.json()
    assert len(lst) == 1
    assert lst[0]["performed_at"] == "2024-01-15"


@pytest.mark.asyncio
async def test_upload_revision_record_updates_last_revised(client: AsyncClient) -> None:
    token = await _register_ozo(client, "rv11")
    headers = await _auth(token)
    plant_id = await _create_plant(client, headers)

    create = await client.post(
        "/api/v1/revisions",
        json=_device_payload(plant_id, last_revised_at="2023-01-15", valid_months=12),
        headers=headers,
    )
    rid = create.json()["id"]

    # Nahraj novější záznam
    today = date.today().isoformat()
    pdf_content = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n%%EOF"
    resp = await client.post(
        f"/api/v1/revisions/{rid}/records",
        data={
            "performed_at": today,
            "technician_name": "Ing. Dvořák",
            "notes": "OK, bez závad",
        },
        files={"file": ("protokol.pdf", pdf_content, "application/pdf")},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text

    # Revize by měla mít aktualizované last_revised_at
    get_resp = await client.get(f"/api/v1/revisions/{rid}", headers=headers)
    assert get_resp.json()["last_revised_at"] == today

    # Timeline by měla mít 2 položky, nejnovější nahoře
    records = await client.get(f"/api/v1/revisions/{rid}/records", headers=headers)
    lst = records.json()
    assert len(lst) == 2
    assert lst[0]["performed_at"] == today


@pytest.mark.asyncio
async def test_upload_record_rejects_invalid_pdf(client: AsyncClient) -> None:
    token = await _register_ozo(client, "rv12")
    headers = await _auth(token)
    plant_id = await _create_plant(client, headers)

    create = await client.post(
        "/api/v1/revisions", json=_device_payload(plant_id), headers=headers
    )
    rid = create.json()["id"]

    resp = await client.post(
        f"/api/v1/revisions/{rid}/records",
        data={"performed_at": date.today().isoformat()},
        files={"file": ("fake.pdf", b"not a real pdf", "application/pdf")},
        headers=headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_upload_image_record_is_accepted(client: AsyncClient) -> None:
    token = await _register_ozo(client, "rv13")
    headers = await _auth(token)
    plant_id = await _create_plant(client, headers)

    create = await client.post(
        "/api/v1/revisions", json=_device_payload(plant_id), headers=headers
    )
    rid = create.json()["id"]

    # minimální PNG
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000d49444154785e63f80f0400010100015a5c1e9c0000000049454e44ae426082"
    )
    resp = await client.post(
        f"/api/v1/revisions/{rid}/records",
        data={"performed_at": date.today().isoformat()},
        files={"file": ("scan.png", png, "image/png")},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["image_path"]
    assert resp.json()["pdf_path"] is None


# ── QR ───────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_qr_endpoint_returns_png(client: AsyncClient) -> None:
    token = await _register_ozo(client, "rv14")
    headers = await _auth(token)
    plant_id = await _create_plant(client, headers)

    create = await client.post(
        "/api/v1/revisions", json=_device_payload(plant_id), headers=headers
    )
    rid = create.json()["id"]

    resp = await client.get(f"/api/v1/revisions/{rid}/qr.png", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"   # PNG magic


@pytest.mark.asyncio
async def test_qr_token_lookup(client: AsyncClient) -> None:
    token = await _register_ozo(client, "rv15")
    headers = await _auth(token)
    plant_id = await _create_plant(client, headers)

    create = await client.post(
        "/api/v1/revisions", json=_device_payload(plant_id), headers=headers
    )
    qr_token = create.json()["qr_token"]

    resp = await client.get(f"/api/v1/revisions/qr/{qr_token}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == create.json()["id"]


# ── Employee responsibilities ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_set_and_get_responsibilities(client: AsyncClient) -> None:
    token = await _register_ozo(client, "rv16")
    headers = await _auth(token)
    plant_a = await _create_plant(client, headers, "Praha")
    plant_b = await _create_plant(client, headers, "Brno")

    emp_resp = await client.post(
        "/api/v1/employees",
        json={
            "first_name": "Jan",
            "last_name": "Technik",
            "employment_type": "hpp",
            "email": "technik@firma.cz",
            "create_user_account": True,
            "is_equipment_responsible": True,
            "responsible_plant_ids": [plant_a],
        },
        headers=headers,
    )
    assert emp_resp.status_code == 201, emp_resp.text
    emp_id = emp_resp.json()["id"]

    get_resp = await client.get(
        f"/api/v1/employees/{emp_id}/responsibilities", headers=headers
    )
    assert set(get_resp.json()["plant_ids"]) == {plant_a}

    # PUT nahradí seznam
    put_resp = await client.put(
        f"/api/v1/employees/{emp_id}/responsibilities",
        json={"plant_ids": [plant_a, plant_b]},
        headers=headers,
    )
    assert put_resp.status_code == 200
    assert set(put_resp.json()["plant_ids"]) == {plant_a, plant_b}

    # Odebrání: prázdný seznam
    empty_resp = await client.put(
        f"/api/v1/employees/{emp_id}/responsibilities",
        json={"plant_ids": []},
        headers=headers,
    )
    assert empty_resp.json()["plant_ids"] == []


@pytest.mark.asyncio
async def test_responsibility_rejects_cross_tenant_plant(client: AsyncClient) -> None:
    """Plant z jiného tenantu → 422."""
    token_a = await _register_ozo(client, "rv17a")
    token_b = await _register_ozo(client, "rv17b")
    headers_a = await _auth(token_a)
    headers_b = await _auth(token_b)

    plant_b = await _create_plant(client, headers_b, "Brno B")

    emp_resp = await client.post(
        "/api/v1/employees",
        json={
            "first_name": "Eva",
            "last_name": "Nováková",
            "employment_type": "hpp",
            "email": "eva@a.cz",
            "create_user_account": True,
        },
        headers=headers_a,
    )
    emp_id = emp_resp.json()["id"]

    resp = await client.put(
        f"/api/v1/employees/{emp_id}/responsibilities",
        json={"plant_ids": [plant_b]},
        headers=headers_a,
    )
    assert resp.status_code == 422
