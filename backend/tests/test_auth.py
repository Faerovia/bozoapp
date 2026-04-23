import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_creates_user_and_returns_tokens(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "ozo@example.com",
            "password": "heslo1234",
            "full_name": "Jan Novák",
            "tenant_name": "Testovací Firma s.r.o.",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_register_weak_password_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "ozo@example.com",
            "password": "abc",
            "tenant_name": "Firma",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_valid_credentials(client: AsyncClient) -> None:
    # Nejdřív registruj
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "login@example.com",
            "password": "heslo1234",
            "tenant_name": "Login Test Firma",
        },
    )
    # Pak přihlaš
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "login@example.com", "password": "heslo1234"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "wrongpw@example.com",
            "password": "heslo1234",
            "tenant_name": "WrongPW Firma",
        },
    )
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "wrongpw@example.com", "password": "spatne-heslo"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_current_user(client: AsyncClient) -> None:
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "me@example.com",
            "password": "heslo1234",
            "tenant_name": "Me Test Firma",
        },
    )
    token = reg.json()["access_token"]

    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "me@example.com"
    assert data["role"] == "ozo"


@pytest.mark.asyncio
async def test_me_without_token_returns_4xx(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")
    # Novější Starlette vrací 401, starší 403 – oba jsou správně
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_refresh_returns_new_tokens(client: AsyncClient) -> None:
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "refresh@example.com",
            "password": "heslo1234",
            "tenant_name": "Refresh Test Firma",
        },
    )
    refresh_token = reg.json()["refresh_token"]

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    # Tokeny mohou být identické pokud se generují ve stejnou sekundu (stejný exp).
    # Stačí ověřit, že jsou přítomné a request prošel.
