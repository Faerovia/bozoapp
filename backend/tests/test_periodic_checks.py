"""Happy-path testy modulu Pravidelné kontroly."""
import pytest
from httpx import AsyncClient


async def _ozo_headers(client: AsyncClient, suffix: str) -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"ozo{suffix}@pc.cz",
            "password": "heslo1234",
            "tenant_name": f"PC Firma {suffix}",
        },
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.mark.asyncio
async def test_create_and_list_periodic_check(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "p1")
    plant = (await client.post(
        "/api/v1/plants",
        json={"name": "Provozovna Test"},
        headers=headers,
    )).json()

    resp = await client.post(
        "/api/v1/periodic-checks",
        json={
            "check_kind": "first_aid_kit",
            "title": "Lékárnička sklad A",
            "plant_id": plant["id"],
            "valid_months": 12,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["check_kind"] == "first_aid_kit"
    assert body["title"] == "Lékárnička sklad A"
    assert body["plant_id"] == plant["id"]
    assert body["status"] == "active"

    list_resp = await client.get(
        "/api/v1/periodic-checks?check_kind=first_aid_kit",
        headers=headers,
    )
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) == 1
    assert items[0]["plant_name"] == "Provozovna Test"


@pytest.mark.asyncio
async def test_create_record_updates_next_check_at(client: AsyncClient) -> None:
    """Po vytvoření záznamu se posune last_checked_at + recompute next."""
    headers = await _ozo_headers(client, "p2")
    plant = (await client.post(
        "/api/v1/plants",
        json={"name": "Provozovna Záznam"},
        headers=headers,
    )).json()
    check = (await client.post(
        "/api/v1/periodic-checks",
        json={
            "check_kind": "spill_tray",
            "title": "Vana 1",
            "plant_id": plant["id"],
            "valid_months": 6,
        },
        headers=headers,
    )).json()

    rec = await client.post(
        f"/api/v1/periodic-checks/{check['id']}/records",
        json={
            "performed_at": "2026-04-01",
            "performed_by_name": "Jan Novák",
            "result": "ok",
        },
        headers=headers,
    )
    assert rec.status_code == 201, rec.text

    detail = (await client.get(
        f"/api/v1/periodic-checks/{check['id']}",
        headers=headers,
    )).json()
    assert detail["last_checked_at"] == "2026-04-01"
    # 6 měsíců po duben → říjen
    assert detail["next_check_at"] == "2026-10-01"


@pytest.mark.asyncio
async def test_list_filter_by_kind(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "p3")
    plant = (await client.post(
        "/api/v1/plants", json={"name": "P"}, headers=headers,
    )).json()

    for kind, title in [
        ("sanitation_kit", "Sanační A"),
        ("spill_tray", "Vana B"),
        ("first_aid_kit", "Lékárnička C"),
    ]:
        await client.post(
            "/api/v1/periodic-checks",
            json={
                "check_kind": kind, "title": title,
                "plant_id": plant["id"], "valid_months": 12,
            },
            headers=headers,
        )

    only_first_aid = (await client.get(
        "/api/v1/periodic-checks?check_kind=first_aid_kit",
        headers=headers,
    )).json()
    assert len(only_first_aid) == 1
    assert only_first_aid[0]["title"] == "Lékárnička C"
