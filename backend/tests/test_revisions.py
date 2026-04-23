"""
Testy pro záznamy o revizích zařízení.

BOZP invarianty:
- next_revision_at se automaticky vypočítá z last_revised_at + valid_months
- správné odvozování due_status (overdue / due_soon / ok / no_schedule)
- archivace místo smazání
"""

from datetime import date, timedelta

import pytest
from httpx import AsyncClient


async def _ozo_headers(client: AsyncClient, suffix: str = "") -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"ozo{suffix}@revize.cz",
            "password": "heslo1234",
            "tenant_name": f"Firma {suffix}",
        },
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _revision_payload(**overrides) -> dict:
    base = {
        "title": "Elektrorevize rozvodny",
        "revision_type": "electrical",
        "location": "Hala A",
        "last_revised_at": "2024-01-15",
        "valid_months": 12,
        "contractor": "Revize s.r.o.",
    }
    base.update(overrides)
    return base


# ── Vytváření záznamů ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_revision_computes_next_revision_at(client: AsyncClient) -> None:
    """next_revision_at = last_revised_at + valid_months."""
    ozo_headers = await _ozo_headers(client, "rv1")
    resp = await client.post(
        "/api/v1/revisions",
        json=_revision_payload(last_revised_at="2024-03-15", valid_months=12),
        headers=ozo_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["next_revision_at"] == "2025-03-15"


@pytest.mark.asyncio
async def test_create_revision_no_schedule(client: AsyncClient) -> None:
    """Bez last_revised_at/valid_months → next_revision_at None, due_status no_schedule."""
    ozo_headers = await _ozo_headers(client, "rv2")
    resp = await client.post(
        "/api/v1/revisions",
        json={"title": "Žebřík sklad", "revision_type": "ladder"},
        headers=ozo_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["next_revision_at"] is None
    assert data["due_status"] == "no_schedule"


@pytest.mark.asyncio
async def test_create_revision_explicit_next_revision_at(client: AsyncClient) -> None:
    """Explicitní next_revision_at má přednost před výpočtem."""
    ozo_headers = await _ozo_headers(client, "rv3")
    resp = await client.post(
        "/api/v1/revisions",
        json=_revision_payload(
            last_revised_at="2024-01-01",
            valid_months=12,
            next_revision_at="2028-06-30",
        ),
        headers=ozo_headers,
    )
    assert resp.json()["next_revision_at"] == "2028-06-30"


# ── due_status výpočet ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_due_status_overdue(client: AsyncClient) -> None:
    ozo_headers = await _ozo_headers(client, "rv4")
    resp = await client.post(
        "/api/v1/revisions",
        json={"title": "Stará revize", "revision_type": "other", "next_revision_at": "2020-01-01"},
        headers=ozo_headers,
    )
    assert resp.json()["due_status"] == "overdue"


@pytest.mark.asyncio
async def test_due_status_due_soon(client: AsyncClient) -> None:
    ozo_headers = await _ozo_headers(client, "rv5")
    soon = (date.today() + timedelta(days=15)).isoformat()
    resp = await client.post(
        "/api/v1/revisions",
        json={"title": "Blížící se revize", "revision_type": "other", "next_revision_at": soon},
        headers=ozo_headers,
    )
    assert resp.json()["due_status"] == "due_soon"


@pytest.mark.asyncio
async def test_due_status_ok(client: AsyncClient) -> None:
    ozo_headers = await _ozo_headers(client, "rv6")
    future = (date.today() + timedelta(days=60)).isoformat()
    resp = await client.post(
        "/api/v1/revisions",
        json={"title": "Vzdálená revize", "revision_type": "other", "next_revision_at": future},
        headers=ozo_headers,
    )
    assert resp.json()["due_status"] == "ok"


# ── Filtrování ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_filter_by_due_status(client: AsyncClient) -> None:
    ozo_headers = await _ozo_headers(client, "rv7")

    await client.post(
        "/api/v1/revisions",
        json={"title": "Prošlá", "revision_type": "other", "next_revision_at": "2020-01-01"},
        headers=ozo_headers,
    )
    future = (date.today() + timedelta(days=60)).isoformat()
    await client.post(
        "/api/v1/revisions",
        json={"title": "Budoucí", "revision_type": "other", "next_revision_at": future},
        headers=ozo_headers,
    )

    overdue_resp = await client.get("/api/v1/revisions?due_status=overdue", headers=ozo_headers)
    ok_resp = await client.get("/api/v1/revisions?due_status=ok", headers=ozo_headers)

    assert all(r["due_status"] == "overdue" for r in overdue_resp.json())
    assert all(r["due_status"] == "ok" for r in ok_resp.json())


# ── Archivace ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_archive_revision_keeps_record(client: AsyncClient) -> None:
    ozo_headers = await _ozo_headers(client, "rv8")
    create_resp = await client.post(
        "/api/v1/revisions", json=_revision_payload(), headers=ozo_headers
    )
    revision_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/api/v1/revisions/{revision_id}", headers=ozo_headers)
    assert del_resp.status_code == 204

    get_resp = await client.get(f"/api/v1/revisions/{revision_id}", headers=ozo_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "archived"
