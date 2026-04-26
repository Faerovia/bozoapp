"""Happy-path testy modulu Provozní deníky (operating_logs)."""
import pytest
from httpx import AsyncClient


async def _ozo_headers(client: AsyncClient, suffix: str) -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"ozo{suffix}@oplog.cz",
            "password": "heslo1234",
            "tenant_name": f"OpLog Firma {suffix}",
        },
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.mark.asyncio
async def test_create_device_with_check_items(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "o1")
    plant = (await client.post(
        "/api/v1/plants", json={"name": "Test plant"}, headers=headers,
    )).json()

    resp = await client.post(
        "/api/v1/operating-logs/devices",
        json={
            "category": "vzv",
            "title": "VZV Linde H25",
            "device_code": "VZV-001",
            "plant_id": plant["id"],
            "check_items": [
                "Brzdy", "Hydraulika", "Pneumatiky", "Osvětlení",
            ],
            "period": "daily",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["category"] == "vzv"
    assert body["check_items"] == ["Brzdy", "Hydraulika", "Pneumatiky", "Osvětlení"]
    assert body["period"] == "daily"
    assert len(body["qr_token"]) > 30


@pytest.mark.asyncio
async def test_create_entry_3way_capability(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "o2")
    plant = (await client.post(
        "/api/v1/plants", json={"name": "P"}, headers=headers,
    )).json()
    device = (await client.post(
        "/api/v1/operating-logs/devices",
        json={
            "category": "kotelna", "title": "Kotel V",
            "plant_id": plant["id"],
            "check_items": ["Tlak", "Teplota", "Ventily"],
            "period": "daily",
        },
        headers=headers,
    )).json()

    resp = await client.post(
        f"/api/v1/operating-logs/devices/{device['id']}/entries",
        json={
            "performed_at": "2026-04-15",
            "performed_by_name": "Jan Topič",
            "capable_items": ["yes", "conditional", "yes"],
            "overall_status": "conditional",
            "notes": "Ventil pojistný — zajistit servis 17.4.",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["overall_status"] == "conditional"
    assert body["capable_items"] == ["yes", "conditional", "yes"]


@pytest.mark.asyncio
async def test_entry_capable_items_length_must_match(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "o3")
    plant = (await client.post(
        "/api/v1/plants", json={"name": "P"}, headers=headers,
    )).json()
    device = (await client.post(
        "/api/v1/operating-logs/devices",
        json={
            "category": "vzv", "title": "VZV X", "plant_id": plant["id"],
            "check_items": ["A", "B", "C"],
            "period": "daily",
        },
        headers=headers,
    )).json()

    resp = await client.post(
        f"/api/v1/operating-logs/devices/{device['id']}/entries",
        json={
            "performed_at": "2026-04-15",
            "performed_by_name": "Test",
            "capable_items": ["yes", "yes"],  # 2 místo 3
            "overall_status": "yes",
        },
        headers=headers,
    )
    assert resp.status_code == 422
    assert "capable_items" in resp.json()["detail"].lower() or "délk" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_qr_token_lookup(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "o4")
    plant = (await client.post(
        "/api/v1/plants", json={"name": "P"}, headers=headers,
    )).json()
    device = (await client.post(
        "/api/v1/operating-logs/devices",
        json={
            "category": "jerab", "title": "Jeřáb 5t",
            "plant_id": plant["id"],
            "check_items": ["Lana", "Háky"],
            "period": "shift",
        },
        headers=headers,
    )).json()

    qr = device["qr_token"]
    resp = await client.get(
        f"/api/v1/operating-logs/qr/{qr}",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == device["id"]


@pytest.mark.asyncio
async def test_entry_autofills_performed_by_from_user(client: AsyncClient) -> None:
    """Pokud klient pošle prázdné jméno, backend doplní z auth usera."""
    headers = await _ozo_headers(client, "o5")
    plant = (await client.post(
        "/api/v1/plants", json={"name": "P"}, headers=headers,
    )).json()
    device = (await client.post(
        "/api/v1/operating-logs/devices",
        json={
            "category": "vzv", "title": "Auto-fill device",
            "plant_id": plant["id"],
            "check_items": ["A"],
            "period": "daily",
        },
        headers=headers,
    )).json()

    resp = await client.post(
        f"/api/v1/operating-logs/devices/{device['id']}/entries",
        json={
            "performed_at": "2026-04-15",
            "performed_by_name": "",  # prázdné — backend doplní
            "capable_items": ["yes"],
            "overall_status": "yes",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    # full_name nebo email se vyplní (z register fixture je email)
    assert resp.json()["performed_by_name"]
