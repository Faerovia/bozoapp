"""
Testy pro user management a tenant endpointy.

Setup pattern: každý test si zaregistruje OZO uživatele a pracuje
s tokeny z registrace.
"""

import pytest
from httpx import AsyncClient


async def _register_ozo(client: AsyncClient, suffix: str = "") -> dict:
    """Helper: zaregistruje OZO uživatele a vrátí response dict."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"ozo{suffix}@firma.cz",
            "password": "heslo1234",
            "full_name": f"Jan OZO {suffix}",
            "tenant_name": f"Testovací Firma {suffix}",
        },
    )
    assert resp.status_code == 201
    return resp.json()


async def _auth_headers(client: AsyncClient, suffix: str = "") -> dict:
    tokens = await _register_ozo(client, suffix)
    return {"Authorization": f"Bearer {tokens['access_token']}"}


# ── /tenant ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_tenant_returns_tenant_info(client: AsyncClient) -> None:
    headers = await _auth_headers(client, "t1")
    resp = await client.get("/api/v1/tenant", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "Testovací Firma t1" in data["name"]
    assert "id" in data


@pytest.mark.asyncio
async def test_update_tenant_name(client: AsyncClient) -> None:
    headers = await _auth_headers(client, "t2")
    resp = await client.patch(
        "/api/v1/tenant",
        json={"name": "Nový Název s.r.o."},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Nový Název s.r.o."


# ── /users ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ozo_can_list_users(client: AsyncClient) -> None:
    headers = await _auth_headers(client, "u1")
    resp = await client.get("/api/v1/users", headers=headers)
    assert resp.status_code == 200
    users = resp.json()
    # Měl by vidět aspoň sebe
    assert len(users) >= 1
    assert any(u["email"] == "ozou1@firma.cz" for u in users)


@pytest.mark.asyncio
async def test_ozo_can_create_employee(client: AsyncClient) -> None:
    headers = await _auth_headers(client, "u2")
    resp = await client.post(
        "/api/v1/users",
        json={
            "email": "zamestnanec@firma.cz",
            "password": "heslo1234",
            "full_name": "Petr Zaměstnanec",
            "role": "employee",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "zamestnanec@firma.cz"
    assert data["role"] == "employee"


@pytest.mark.asyncio
async def test_ozo_can_deactivate_user(client: AsyncClient) -> None:
    headers = await _auth_headers(client, "u3")

    # Vytvoř zaměstnance
    create_resp = await client.post(
        "/api/v1/users",
        json={"email": "worker@firma.cz", "password": "heslo1234", "role": "employee"},
        headers=headers,
    )
    user_id = create_resp.json()["id"]

    # Deaktivuj ho
    resp = await client.delete(f"/api/v1/users/{user_id}", headers=headers)
    assert resp.status_code == 204

    # Ověř že je neaktivní (OZO vidí is_active=False)
    detail_resp = await client.get(f"/api/v1/users/{user_id}", headers=headers)
    assert detail_resp.json()["is_active"] is False


@pytest.mark.asyncio
async def test_ozo_cannot_deactivate_self(client: AsyncClient) -> None:
    reg = await _register_ozo(client, "u4")
    ozo_token = reg["access_token"]
    headers = {"Authorization": f"Bearer {ozo_token}"}

    # Zjisti své ID přes /me
    me_resp = await client.get("/api/v1/auth/me", headers=headers)
    ozo_id = me_resp.json()["id"]

    resp = await client.delete(f"/api/v1/users/{ozo_id}", headers=headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_ozo_can_change_user_role(client: AsyncClient) -> None:
    headers = await _auth_headers(client, "u5")

    create_resp = await client.post(
        "/api/v1/users",
        json={"email": "budouci@firma.cz", "password": "heslo1234", "role": "employee"},
        headers=headers,
    )
    user_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/api/v1/users/{user_id}",
        json={"role": "manager"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "manager"


@pytest.mark.asyncio
async def test_employee_cannot_list_users(client: AsyncClient) -> None:
    ozo_headers = await _auth_headers(client, "u6")

    # OZO vytvoří zaměstnance
    create_resp = await client.post(
        "/api/v1/users",
        json={"email": "emp@firma.cz", "password": "heslo5678", "role": "employee"},
        headers=ozo_headers,
    )
    assert create_resp.status_code == 201

    # Zaměstnanec se přihlásí
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "emp@firma.cz", "password": "heslo5678"},
    )
    emp_token = login_resp.json()["access_token"]
    emp_headers = {"Authorization": f"Bearer {emp_token}"}

    # Zaměstnanec nemá přístup na seznam uživatelů
    resp = await client.get("/api/v1/users", headers=emp_headers)
    assert resp.status_code == 403
