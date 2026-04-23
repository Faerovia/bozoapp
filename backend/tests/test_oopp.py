"""
Testy pro OOPP evidenci (Evidence osobních ochranných pracovních prostředků).

Ověřujeme:
- CRUD operace
- Správný výpočet valid_until z issued_at + valid_months
- validity_status computed property
- Filtrování (employee, typ, validity_status)
- Archivace (ne fyzické smazání)
- Tenant izolace (OZO A nevidí záznamy OZO B)
- PDF export
"""

from datetime import date, timedelta

import pytest
from httpx import AsyncClient


async def _ozo_headers(client: AsyncClient, suffix: str) -> tuple[dict, str]:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"ozo{suffix}@oopp.cz",
            "password": "heslo1234",
            "tenant_name": f"OOPP Firma {suffix}",
        },
    )
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    me = await client.get("/api/v1/users/me", headers=headers)
    return headers, me.json()["id"]


def _oopp_payload(employee_name: str = "Jan Novák", **overrides: object) -> dict:
    base = {
        "employee_name": employee_name,
        "item_name": "Bezpečnostní přilba",
        "oopp_type": "head_protection",
        "issued_at": "2025-01-01",
        "quantity": 1,
    }
    base.update(overrides)
    return base


# ── Základní CRUD ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_oopp(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "o1")
    resp = await client.post("/api/v1/oopp", json=_oopp_payload(), headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["item_name"] == "Bezpečnostní přilba"
    assert data["oopp_type"] == "head_protection"
    assert data["status"] == "active"
    assert data["validity_status"] == "no_expiry"  # valid_months=None → no_expiry


@pytest.mark.asyncio
async def test_valid_until_computed_from_valid_months(client: AsyncClient) -> None:
    """valid_until = issued_at + valid_months (automatický výpočet)."""
    headers, _ = await _ozo_headers(client, "o2")
    resp = await client.post(
        "/api/v1/oopp",
        json=_oopp_payload(issued_at="2025-01-15", valid_months=12),
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["valid_until"] == "2026-01-15"


@pytest.mark.asyncio
async def test_explicit_valid_until_overrides_months(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "o3")
    resp = await client.post(
        "/api/v1/oopp",
        json=_oopp_payload(issued_at="2025-01-01", valid_months=12, valid_until="2026-06-30"),
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["valid_until"] == "2026-06-30"


@pytest.mark.asyncio
async def test_get_oopp_by_id(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "o4")
    create = await client.post("/api/v1/oopp", json=_oopp_payload(), headers=headers)
    aid = create.json()["id"]
    resp = await client.get(f"/api/v1/oopp/{aid}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == aid


@pytest.mark.asyncio
async def test_update_oopp(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "o5")
    create = await client.post("/api/v1/oopp", json=_oopp_payload(), headers=headers)
    aid = create.json()["id"]
    resp = await client.patch(
        f"/api/v1/oopp/{aid}",
        json={"item_name": "Přilba XL", "quantity": 2},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["item_name"] == "Přilba XL"
    assert resp.json()["quantity"] == 2


@pytest.mark.asyncio
async def test_archive_oopp(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "o6")
    create = await client.post("/api/v1/oopp", json=_oopp_payload(), headers=headers)
    aid = create.json()["id"]

    del_resp = await client.delete(f"/api/v1/oopp/{aid}", headers=headers)
    assert del_resp.status_code == 204

    # Záznam stále existuje, status=archived
    get_resp = await client.get(f"/api/v1/oopp/{aid}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "archived"


# ── validity_status ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_validity_status_expired(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "o7")
    resp = await client.post(
        "/api/v1/oopp",
        json=_oopp_payload(issued_at="2020-01-01", valid_until="2021-01-01"),
        headers=headers,
    )
    assert resp.json()["validity_status"] == "expired"


@pytest.mark.asyncio
async def test_validity_status_expiring_soon(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "o8")
    soon = (date.today() + timedelta(days=10)).isoformat()
    resp = await client.post(
        "/api/v1/oopp",
        json=_oopp_payload(issued_at="2020-01-01", valid_until=soon),
        headers=headers,
    )
    assert resp.json()["validity_status"] == "expiring_soon"


@pytest.mark.asyncio
async def test_validity_status_valid(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "o9")
    far = (date.today() + timedelta(days=90)).isoformat()
    resp = await client.post(
        "/api/v1/oopp",
        json=_oopp_payload(issued_at="2024-01-01", valid_until=far),
        headers=headers,
    )
    assert resp.json()["validity_status"] == "valid"


# ── Filtrování ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_filter_by_validity_status(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "o10")

    # Prošlý záznam
    await client.post(
        "/api/v1/oopp",
        json=_oopp_payload(valid_until="2020-01-01"),
        headers=headers,
    )
    # Platný záznam
    far = (date.today() + timedelta(days=90)).isoformat()
    await client.post(
        "/api/v1/oopp",
        json=_oopp_payload(employee_name="Pavel Novák", item_name="Rukavice", valid_until=far),
        headers=headers,
    )

    expired = await client.get("/api/v1/oopp?validity_status=expired", headers=headers)
    assert len(expired.json()) == 1

    valid = await client.get("/api/v1/oopp?validity_status=valid", headers=headers)
    assert len(valid.json()) == 1


@pytest.mark.asyncio
async def test_filter_by_oopp_type(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "o11")
    await client.post("/api/v1/oopp", json=_oopp_payload(oopp_type="hand_protection"), headers=headers)
    await client.post("/api/v1/oopp", json=_oopp_payload(oopp_type="foot_protection"), headers=headers)

    resp = await client.get("/api/v1/oopp?oopp_type=hand_protection", headers=headers)
    assert len(resp.json()) == 1
    assert resp.json()[0]["oopp_type"] == "hand_protection"


# ── Tenant izolace ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tenant_isolation(client: AsyncClient) -> None:
    headers_a, _ = await _ozo_headers(client, "o12a")
    headers_b, _ = await _ozo_headers(client, "o12b")

    await client.post("/api/v1/oopp", json=_oopp_payload(), headers=headers_a)

    resp_b = await client.get("/api/v1/oopp", headers=headers_b)
    assert resp_b.json() == []


# ── PDF export ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_export_oopp_pdf_empty(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "o13")
    resp = await client.get("/api/v1/oopp/export/pdf", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert len(resp.content) > 500


@pytest.mark.asyncio
async def test_export_oopp_pdf_with_data(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "o14")
    await client.post(
        "/api/v1/oopp",
        json=_oopp_payload(item_name="Reflexní vesta", oopp_type="visibility", valid_months=24),
        headers=headers,
    )
    resp = await client.get("/api/v1/oopp/export/pdf", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    disposition = resp.headers["content-disposition"]
    assert disposition.startswith("inline")
    assert len(resp.content) > 500


@pytest.mark.asyncio
async def test_export_oopp_pdf_download(client: AsyncClient) -> None:
    headers, _ = await _ozo_headers(client, "o15")
    resp = await client.get("/api/v1/oopp/export/pdf?download=true", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-disposition"].startswith("attachment")
