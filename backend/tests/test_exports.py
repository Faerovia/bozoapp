"""
Smoke testy pro PDF exporty.

Ověřujeme: HTTP 200, content-type application/pdf, neprázdný obsah,
správné Content-Disposition pro inline i download.
Testy jsou záměrně lehké – detailní obsah PDF se testuje manuálně.
"""

from datetime import date, timedelta

import pytest
from httpx import AsyncClient


async def _setup(client: AsyncClient, suffix: str) -> tuple[dict, str]:
    """Zaregistruje OZO a vytvoří employee záznam. Vrátí (headers, employee_id)."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"ozo{suffix}@export.cz",
            "password": "heslo1234",
            "tenant_name": f"Export Firma {suffix}",
        },
    )
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    emp = await client.post(
        "/api/v1/employees",
        json={"first_name": "Export", "last_name": suffix, "employment_type": "hpp"},
        headers=headers,
    )
    return headers, emp.json()["id"]


def _assert_pdf(resp: object, inline: bool = True) -> None:
    import httpx
    assert isinstance(resp, httpx.Response)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    disposition = resp.headers["content-disposition"]
    assert disposition.startswith("inline" if inline else "attachment")
    assert len(resp.content) > 500  # není prázdný PDF


# ── Registr rizik ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_export_risks_pdf_empty(client: AsyncClient) -> None:
    """Export funguje i s prázdným registrem."""
    headers, _ = await _setup(client, "ex1")
    resp = await client.get("/api/v1/risks/export/pdf", headers=headers)
    _assert_pdf(resp)


@pytest.mark.asyncio
async def test_export_risks_pdf_with_data(client: AsyncClient) -> None:
    headers, _ = await _setup(client, "ex2")
    await client.post(
        "/api/v1/risks",
        json={"title": "Testové riziko", "probability": 3, "severity": 4, "hazard_type": "physical"},
        headers=headers,
    )
    resp = await client.get("/api/v1/risks/export/pdf", headers=headers)
    _assert_pdf(resp)


@pytest.mark.asyncio
async def test_export_risks_pdf_download(client: AsyncClient) -> None:
    headers, _ = await _setup(client, "ex3")
    resp = await client.get("/api/v1/risks/export/pdf?download=true", headers=headers)
    _assert_pdf(resp, inline=False)


# ── Přehled školení ───────────────────────────────────────────────────────────
# POZNÁMKA: /trainings/export/pdf byl v commit 11a odstraněn — starý endpoint
# předpokládal schéma s employee_id a trained_at. Po refaktoru na šablony +
# přiřazení bude export řešen nad TrainingAssignment v samostatném commitu.


# ── Harmonogram revizí ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_export_revisions_pdf(client: AsyncClient) -> None:
    headers, _ = await _setup(client, "ex5")
    soon = (date.today() + timedelta(days=20)).isoformat()
    await client.post(
        "/api/v1/revisions",
        json={"title": "Elektrorevize", "revision_type": "electrical", "next_revision_at": soon},
        headers=headers,
    )
    resp = await client.get("/api/v1/revisions/export/pdf", headers=headers)
    _assert_pdf(resp)


@pytest.mark.asyncio
async def test_export_revisions_pdf_filter_overdue(client: AsyncClient) -> None:
    headers, _ = await _setup(client, "ex6")
    await client.post(
        "/api/v1/revisions",
        json={"title": "Prošlá", "revision_type": "other", "next_revision_at": "2020-01-01"},
        headers=headers,
    )
    resp = await client.get("/api/v1/revisions/export/pdf?due_status=overdue", headers=headers)
    _assert_pdf(resp)


# ── Kniha úrazů ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_export_accident_log_pdf(client: AsyncClient) -> None:
    headers, _ = await _setup(client, "ex7")
    await client.post(
        "/api/v1/accident-reports",
        json={
            "employee_name": "Jan Novák",
            "workplace": "Sklad",
            "accident_date": "2026-03-01",
            "accident_time": "09:00:00",
            "injury_type": "Řezná rána",
            "injured_body_part": "Ruka",
            "injured_body_part_code": "G",
            "injury_source": "Nůž",
            "injury_cause": "Skluz při řezání",
            "description": "Zaměstnanec se řízl.",
            "alcohol_test_performed": False,
            "drug_test_performed": False,
        },
        headers=headers,
    )
    resp = await client.get("/api/v1/accident-reports/export/pdf", headers=headers)
    _assert_pdf(resp)


@pytest.mark.asyncio
async def test_export_accident_log_pdf_download(client: AsyncClient) -> None:
    headers, _ = await _setup(client, "ex8")
    resp = await client.get("/api/v1/accident-reports/export/pdf?download=true", headers=headers)
    _assert_pdf(resp, inline=False)
