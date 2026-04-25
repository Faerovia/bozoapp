"""
Testy pro modul Documents (generátor BOZP/PO dokumentů).

Pokrývá data-only generátory (bez Anthropic API):
- revision_schedule
- risk_categorization

AI generátory (bozp_directive, training_outline) testujeme jen 503
když ANTHROPIC_API_KEY není nastaven (test env).
"""
import pytest
from httpx import AsyncClient


async def _ozo_headers(client: AsyncClient, suffix: str) -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"ozo{suffix}@docs.cz",
            "password": "heslo1234",
            "tenant_name": f"Docs Firma {suffix}",
        },
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ── Data-only generators ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_revision_schedule_empty(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "d1")
    resp = await client.post(
        "/api/v1/documents/generate",
        json={"document_type": "revision_schedule"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["document_type"] == "revision_schedule"
    assert "Harmonogram revizí" in body["title"]
    assert "Žádná aktivní zařízení" in body["content_md"]


@pytest.mark.asyncio
async def test_generate_risk_categorization_empty(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "d2")
    resp = await client.post(
        "/api/v1/documents/generate",
        json={"document_type": "risk_categorization"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["document_type"] == "risk_categorization"
    assert "Kategorizace prací" in body["title"]


@pytest.mark.asyncio
async def test_generate_revision_schedule_with_data(client: AsyncClient) -> None:
    """Generátor harmonogramu obsahuje název zařízení v Markdown."""
    headers = await _ozo_headers(client, "d3")
    plant = (await client.post(
        "/api/v1/plants",
        json={"name": "Provozovna T", "ico": "12345678"},
        headers=headers,
    )).json()
    await client.post(
        "/api/v1/revisions",
        json={
            "title": "Rozvaděč R1",
            "plant_id": plant["id"],
            "device_type": "elektro",
            "device_code": "RZV-001",
            "valid_months": 60,
            "last_revised_at": "2024-01-15",
        },
        headers=headers,
    )
    resp = await client.post(
        "/api/v1/documents/generate",
        json={"document_type": "revision_schedule"},
        headers=headers,
    )
    md = resp.json()["content_md"]
    assert "Rozvaděč R1" in md
    assert "Provozovna T" in md
    assert "RZV-001" in md


# ── CRUD ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_and_update_document(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "d4")
    create = await client.post(
        "/api/v1/documents/generate",
        json={"document_type": "revision_schedule"},
        headers=headers,
    )
    doc_id = create.json()["id"]

    listing = await client.get("/api/v1/documents", headers=headers)
    assert listing.status_code == 200
    assert any(d["id"] == doc_id for d in listing.json())

    # Edit content
    new_md = "# Upravená verze\n\n*Lorem ipsum*"
    update = await client.patch(
        f"/api/v1/documents/{doc_id}",
        json={"content_md": new_md},
        headers=headers,
    )
    assert update.status_code == 200
    assert update.json()["content_md"] == new_md


@pytest.mark.asyncio
async def test_delete_document(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "d5")
    create = await client.post(
        "/api/v1/documents/generate",
        json={"document_type": "risk_categorization"},
        headers=headers,
    )
    doc_id = create.json()["id"]

    delete = await client.delete(f"/api/v1/documents/{doc_id}", headers=headers)
    assert delete.status_code == 204

    after = await client.get(f"/api/v1/documents/{doc_id}", headers=headers)
    assert after.status_code == 404


# ── AI generators bez API key → 503 ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_ai_generator_returns_503_without_key(client: AsyncClient) -> None:
    """Bez ANTHROPIC_API_KEY musí AI generování vrátit 503."""
    headers = await _ozo_headers(client, "d6")
    resp = await client.post(
        "/api/v1/documents/generate",
        json={"document_type": "bozp_directive"},
        headers=headers,
    )
    # V test prostředí klíč není → 503
    assert resp.status_code == 503
    assert "ANTHROPIC_API_KEY" in resp.json()["detail"]


# ── PDF export ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pdf_export_returns_pdf(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "d7")
    create = await client.post(
        "/api/v1/documents/generate",
        json={"document_type": "revision_schedule"},
        headers=headers,
    )
    doc_id = create.json()["id"]

    resp = await client.get(f"/api/v1/documents/{doc_id}/pdf", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


# ── Tenant izolace ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tenant_isolation(client: AsyncClient) -> None:
    h_a = await _ozo_headers(client, "ta")
    h_b = await _ozo_headers(client, "tb")

    create = await client.post(
        "/api/v1/documents/generate",
        json={"document_type": "revision_schedule"},
        headers=h_a,
    )
    doc_id = create.json()["id"]

    # Tenant B nesmí vidět dokument A
    resp = await client.get(f"/api/v1/documents/{doc_id}", headers=h_b)
    assert resp.status_code == 404

    listing = await client.get("/api/v1/documents", headers=h_b)
    assert listing.json() == []
