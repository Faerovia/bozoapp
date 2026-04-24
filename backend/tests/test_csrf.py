"""
Testy CSRF ochrany.

CSRFMiddleware checkuje X-CSRF-Token header vs csrf_token cookie pro
state-changing requesty s COOKIE auth. Bearer auth je výjimkou.

Pokrývá:
- Bearer auth: CSRF se nekontroluje (testy jinak by vůbec nefungovaly)
- Cookie auth bez tokenu: 403
- Cookie auth s nesouhlasícím tokenem: 403
- Cookie auth se správným tokenem: průchod
- GET requesty: nikdy nekontrolováno
- /auth/login, /auth/register, /auth/refresh, /auth/logout: exempt
"""
import pytest
from httpx import AsyncClient


async def _register_and_cookies(
    client: AsyncClient, suffix: str
) -> tuple[str, str]:
    """Registruje usera a vrátí (access_token, csrf_token) zachycené z Set-Cookie."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"csrf{suffix}@me.cz",
            "password": "heslo1234",
            "tenant_name": f"CSRF firma {suffix}",
        },
    )
    access_token = resp.json()["access_token"]
    # httpx AsyncClient automaticky uložil cookies (access_token, refresh_token, csrf_token)
    csrf_token = client.cookies.get("csrf_token")
    assert csrf_token, f"Očekáván csrf_token cookie, cookies: {client.cookies}"
    return access_token, csrf_token


@pytest.mark.asyncio
async def test_bearer_bypasses_csrf(client: AsyncClient) -> None:
    """S Authorization: Bearer header se CSRF přeskakuje (tak fungují testy)."""
    access, _csrf = await _register_and_cookies(client, "c1")
    headers = {"Authorization": f"Bearer {access}"}
    # Vymažeme cookies aby request šel čistě přes Bearer
    client.cookies.clear()
    resp = await client.post(
        "/api/v1/risks",
        json={"title": "Bearer OK", "probability": 2, "severity": 2},
        headers=headers,
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_cookie_auth_without_csrf_header_rejected(client: AsyncClient) -> None:
    """Cookie-authenticated POST bez X-CSRF-Token → 403."""
    await _register_and_cookies(client, "c2")
    # Nechme cookies (včetně access_token) a pošleme request BEZ csrf headeru
    resp = await client.post(
        "/api/v1/risks",
        json={"title": "No CSRF", "probability": 2, "severity": 2},
    )
    assert resp.status_code == 403
    assert "CSRF" in resp.text


@pytest.mark.asyncio
async def test_cookie_auth_with_mismatched_csrf_rejected(client: AsyncClient) -> None:
    await _register_and_cookies(client, "c3")
    resp = await client.post(
        "/api/v1/risks",
        json={"title": "Mismatched CSRF", "probability": 2, "severity": 2},
        headers={"X-CSRF-Token": "wrong-value"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_cookie_auth_with_correct_csrf_passes(client: AsyncClient) -> None:
    _access, csrf = await _register_and_cookies(client, "c4")
    resp = await client.post(
        "/api/v1/risks",
        json={"title": "Correct CSRF", "probability": 2, "severity": 2},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_get_request_no_csrf_needed(client: AsyncClient) -> None:
    await _register_and_cookies(client, "c5")
    # GET /users/me — cookie auth, BEZ CSRF headeru, musí projít
    resp = await client.get("/api/v1/users/me")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_auth_endpoints_exempt_from_csrf(client: AsyncClient) -> None:
    """Login/register/refresh/logout nevyžadují CSRF token (user ho ještě nemá)."""
    # Login endpoint je exempt — projde i bez cookie i bez headeru
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@me.cz", "password": "nope1234"},
    )
    # Nesprávné heslo → 401 (ne 403 z CSRF)
    assert resp.status_code == 401
