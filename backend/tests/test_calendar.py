"""
Testy pro agregovaný kalendář termínů.

Testujeme:
- kalendář sbírá položky ze všech tří zdrojů (revisions, risks, trainings)
- položky mimo horizont days_ahead se neobjeví
- archivované záznamy se neobjeví
- položky jsou seřazeny podle due_date vzestupně
- záznamy bez due_date (no_schedule) v kalendáři nejsou
"""

from datetime import date, timedelta

import pytest
from httpx import AsyncClient


async def _setup_tenant(client: AsyncClient, suffix: str) -> tuple[dict, str]:
    """Zaregistruje OZO, vytvoří employee záznam a vrátí (headers, employee_id)."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"ozo{suffix}@calendar.cz",
            "password": "heslo1234",
            "tenant_name": f"Firma {suffix}",
        },
    )
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    emp_resp = await client.post(
        "/api/v1/employees",
        json={"first_name": "Kal", "last_name": suffix, "employment_type": "hpp"},
        headers=headers,
    )
    return headers, emp_resp.json()["id"]


@pytest.mark.asyncio
async def test_calendar_aggregates_all_sources(client: AsyncClient) -> None:
    """
    Kalendář musí obsahovat položky z revisions, risks i trainings
    pokud mají due_date v horizontu.
    """
    headers, user_id = await _setup_tenant(client, "cal1")
    soon = (date.today() + timedelta(days=10)).isoformat()

    # Revize
    await client.post(
        "/api/v1/revisions",
        json={"title": "Elektrorevize", "revision_type": "electrical", "next_revision_at": soon},
        headers=headers,
    )

    # Riziko s review_date
    await client.post(
        "/api/v1/risks",
        json={
            "title": "Pád z výšky",
            "probability": 3,
            "severity": 4,
            "hazard_type": "physical",
            "review_date": soon,
        },
        headers=headers,
    )

    # Školení s valid_until
    await client.post(
        "/api/v1/trainings",
        json={
            "employee_id": user_id,
            "title": "BOZP školení",
            "training_type": "bozp_periodic",
            "trained_at": "2020-01-01",
            "valid_until": soon,
        },
        headers=headers,
    )

    resp = await client.get("/api/v1/calendar", headers=headers)
    assert resp.status_code == 200
    sources = {item["source"] for item in resp.json()}
    assert "revision" in sources
    assert "risk" in sources
    assert "training" in sources


@pytest.mark.asyncio
async def test_calendar_respects_days_ahead(client: AsyncClient) -> None:
    """Položky dál než days_ahead se neobjeví v kalendáři."""
    headers, _ = await _setup_tenant(client, "cal2")

    near = (date.today() + timedelta(days=10)).isoformat()
    far = (date.today() + timedelta(days=200)).isoformat()

    await client.post(
        "/api/v1/revisions",
        json={"title": "Blízká revize", "revision_type": "other", "next_revision_at": near},
        headers=headers,
    )
    await client.post(
        "/api/v1/revisions",
        json={"title": "Vzdálená revize", "revision_type": "other", "next_revision_at": far},
        headers=headers,
    )

    resp = await client.get("/api/v1/calendar?days_ahead=30", headers=headers)
    titles = [item["title"] for item in resp.json()]
    assert "Blízká revize" in titles
    assert "Vzdálená revize" not in titles


@pytest.mark.asyncio
async def test_calendar_includes_overdue(client: AsyncClient) -> None:
    """Překročené termíny jsou v kalendáři vždy bez ohledu na days_ahead."""
    headers, _ = await _setup_tenant(client, "cal3")

    await client.post(
        "/api/v1/revisions",
        json={"title": "Prošlá revize", "revision_type": "other", "next_revision_at": "2020-01-01"},
        headers=headers,
    )

    resp = await client.get("/api/v1/calendar?days_ahead=30", headers=headers)
    titles = [item["title"] for item in resp.json()]
    assert "Prošlá revize" in titles


@pytest.mark.asyncio
async def test_calendar_excludes_archived(client: AsyncClient) -> None:
    """Archivované záznamy se v kalendáři neobjevují."""
    headers, _ = await _setup_tenant(client, "cal4")
    soon = (date.today() + timedelta(days=10)).isoformat()

    create_resp = await client.post(
        "/api/v1/revisions",
        json={"title": "Archivovaná revize", "revision_type": "other", "next_revision_at": soon},
        headers=headers,
    )
    revision_id = create_resp.json()["id"]
    await client.delete(f"/api/v1/revisions/{revision_id}", headers=headers)

    resp = await client.get("/api/v1/calendar", headers=headers)
    titles = [item["title"] for item in resp.json()]
    assert "Archivovaná revize" not in titles


@pytest.mark.asyncio
async def test_calendar_sorted_by_due_date(client: AsyncClient) -> None:
    """Položky musí být seřazeny vzestupně podle due_date."""
    headers, _ = await _setup_tenant(client, "cal5")

    dates = [
        (date.today() + timedelta(days=d)).isoformat()
        for d in [40, 5, 20]
    ]
    for i, d in enumerate(dates):
        await client.post(
            "/api/v1/revisions",
            json={"title": f"Revize {i}", "revision_type": "other", "next_revision_at": d},
            headers=headers,
        )

    resp = await client.get("/api/v1/calendar", headers=headers)
    due_dates = [item["due_date"] for item in resp.json()]
    assert due_dates == sorted(due_dates)


@pytest.mark.asyncio
async def test_calendar_no_schedule_excluded(client: AsyncClient) -> None:
    """Záznamy bez next_revision_at se v kalendáři neobjevují."""
    headers, _ = await _setup_tenant(client, "cal6")

    await client.post(
        "/api/v1/revisions",
        json={"title": "Bez termínu", "revision_type": "other"},
        headers=headers,
    )

    resp = await client.get("/api/v1/calendar", headers=headers)
    titles = [item["title"] for item in resp.json()]
    assert "Bez termínu" not in titles
