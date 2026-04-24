"""
Testy refresh token rotation + reuse detection.

Pokrývá:
- /auth/refresh rotuje: starý jti se označí used, nový jti se vydá
- Opakované použití starého (already-used) tokenu → revoke celé family +
  401 pro všechny následné requesty ze stejné family
- /auth/logout revokuje všechny aktivní refresh tokeny usera
- Rotation probíhá přes httpOnly cookie, nikoli Bearer
"""
import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.models.refresh_token import RefreshToken


async def _register(client: AsyncClient, suffix: str) -> tuple[str, str]:
    """Zaregistruje a vrátí (access_token, refresh_token z responsu)."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"rot{suffix}@me.cz",
            "password": "heslo1234",
            "tenant_name": f"Rotation firma {suffix}",
        },
    )
    data = resp.json()
    # httpx AsyncClient si cookies sám udržuje; refresh_token se vrací i v body
    return data["access_token"], data["refresh_token"]


@pytest.mark.asyncio
async def test_refresh_rotation_issues_new_token(client: AsyncClient) -> None:
    _, old_refresh = await _register(client, "r1")

    resp = await client.post("/api/v1/auth/refresh")
    assert resp.status_code == 200, resp.text
    new_refresh = resp.json()["refresh_token"]

    assert new_refresh != old_refresh
    # Stejná family, nové jti
    old_payload = decode_token(old_refresh)
    new_payload = decode_token(new_refresh)
    assert old_payload["family_id"] == new_payload["family_id"]
    assert old_payload["jti"] != new_payload["jti"]


@pytest.mark.asyncio
async def test_refresh_reuse_triggers_family_revocation(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, old_refresh = await _register(client, "r2")
    family_id = decode_token(old_refresh)["family_id"]

    # První rotation — projde
    r1 = await client.post("/api/v1/auth/refresh")
    assert r1.status_code == 200

    # Znovu pošleme stejný STARÝ refresh token v cookie — reuse!
    # httpx si po prvním refresh uložil novou cookie; musíme starou vnutit.
    r2 = await client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": old_refresh},
    )
    assert r2.status_code == 401

    # V DB: všechny tokeny s tím family_id musí být revoked
    await db_session.execute(
        text("SELECT set_config('app.is_superadmin', 'true', true)")
    )
    rows = (await db_session.execute(
        select(RefreshToken).where(RefreshToken.family_id == family_id)
    )).scalars().all()
    assert len(rows) >= 2
    assert all(r.revoked_at is not None for r in rows)
    # Alespoň jeden má reason=reuse_detected
    assert any(r.revoked_reason == "reuse_detected" for r in rows)


@pytest.mark.asyncio
async def test_refresh_after_family_revoke_fails(client: AsyncClient) -> None:
    """Po reuse detection už žádný token z té family nefunguje."""
    _, old_refresh = await _register(client, "r3")

    # První rotation — získá NEW refresh token (uložen v httpx cookies)
    await client.post("/api/v1/auth/refresh")

    # Trigger reuse: starý refresh token v cookie
    await client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": old_refresh},
    )

    # Teď zkusit refresh s aktuálním (už vydaným) tokenem — family je revoked
    # → rotate() vrátí None → 401
    resp = await client.post("/api/v1/auth/refresh")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_all_user_tokens(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    access, refresh = await _register(client, "r4")
    headers = {"Authorization": f"Bearer {access}"}

    # Získej user_id
    me = await client.get("/api/v1/users/me", headers=headers)
    user_id = me.json()["id"]

    # Logout (vyžaduje auth)
    resp = await client.post("/api/v1/auth/logout", headers=headers)
    assert resp.status_code == 204

    # V DB všechny tokeny usera musí být revoked
    await db_session.execute(
        text("SELECT set_config('app.is_superadmin', 'true', true)")
    )
    rows = (await db_session.execute(
        select(RefreshToken).where(RefreshToken.user_id == user_id)
    )).scalars().all()
    assert len(rows) >= 1
    assert all(r.revoked_at is not None for r in rows)

    # Starý refresh token už nesmí fungovat
    resp2 = await client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": refresh},
    )
    assert resp2.status_code == 401


@pytest.mark.asyncio
async def test_refresh_without_jti_rejected(client: AsyncClient) -> None:
    """Staré tokeny bez jti/family_id (pre-migration 013) nesmí projít."""
    from app.core.security import create_refresh_token

    # Vytvoř token bez jti — simulace legacy tokenu
    import uuid
    legacy = create_refresh_token(uuid.uuid4(), uuid.uuid4())
    resp = await client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": legacy},
    )
    assert resp.status_code == 401
