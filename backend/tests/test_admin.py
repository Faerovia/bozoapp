"""
Testy platform admin endpointů + permission guardů.

Pokrývá:
- /admin/tenants vyžaduje is_platform_admin=True; běžný OZO dostane 403
- POST /admin/tenants vytvoří tenant + OZO usera + spustí password-reset email
- Admin vidí všechny tenanty (cross-tenant)
- Admin může pozastavit tenant (is_active=False)
- Role model migrace: existující 'manager' → 'hr_manager' (nepřímo přes users/test_users)
"""
import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
from app.models.user import User


async def _register_regular_ozo(client: AsyncClient, suffix: str) -> str:
    """Normální self-signup OZO — vrátí access token."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"regular{suffix}@me.cz",
            "password": "heslo1234",
            "tenant_name": f"Klient {suffix}",
        },
    )
    assert resp.status_code == 201
    return resp.json()["access_token"]


async def _promote_to_platform_admin(
    db: AsyncSession, email: str
) -> str:
    """Povýší existujícího usera na platform admin — simulace CLI příkazu."""
    await db.execute(
        text("SELECT set_config('app.is_superadmin', 'true', true)")
    )
    user = (await db.execute(
        select(User).where(User.email == email)
    )).scalar_one()
    user.role = "admin"
    user.is_platform_admin = True
    await db.commit()
    return str(user.id)


@pytest.mark.asyncio
async def test_regular_ozo_cannot_access_admin_endpoints(
    client: AsyncClient,
) -> None:
    access = await _register_regular_ozo(client, "ad1")
    headers = {"Authorization": f"Bearer {access}"}

    resp = await client.get("/api/v1/admin/tenants", headers=headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_platform_admin_can_list_tenants(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Vytvoř normálního OZO a povýš ho na admin
    access = await _register_regular_ozo(client, "ad2")
    await _promote_to_platform_admin(db_session, "regularad2@me.cz")

    # Re-login — JWT musí odrážet novou roli (i když role v JWT se pro admin
    # check nepoužívá, `get_current_user` načítá user z DB, takže re-login
    # by nemusel být nutný — ale pro jistotu).
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "regularad2@me.cz", "password": "heslo1234"},
    )
    new_access = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {new_access}"}

    resp = await client.get("/api/v1/admin/tenants", headers=headers)
    assert resp.status_code == 200
    tenants = resp.json()
    assert isinstance(tenants, list)
    # Minimálně vlastní tenant (platform admin + servisní pokud vznikne)
    assert len(tenants) >= 1


@pytest.mark.asyncio
async def test_platform_admin_creates_tenant_with_ozo(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    access = await _register_regular_ozo(client, "ad3")
    await _promote_to_platform_admin(db_session, "regularad3@me.cz")

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "regularad3@me.cz", "password": "heslo1234"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await client.post(
        "/api/v1/admin/tenants",
        json={
            "tenant_name": "Nový klient s.r.o.",
            "ozo_email": "novyklient@me.cz",
            "ozo_full_name": "Jan Nový",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["tenant"]["name"] == "Nový klient s.r.o."
    assert body["onboarding_email_sent_to"] == "novyklient@me.cz"
    assert "ozo_user_id" in body

    # Ověř v DB — tenant + OZO user existují
    await db_session.execute(
        text("SELECT set_config('app.is_superadmin', 'true', true)")
    )
    t = (await db_session.execute(
        select(Tenant).where(Tenant.name == "Nový klient s.r.o.")
    )).scalar_one()
    u = (await db_session.execute(
        select(User).where(User.email == "novyklient@me.cz")
    )).scalar_one()
    assert u.tenant_id == t.id
    assert u.role == "ozo"
    assert not u.is_platform_admin


@pytest.mark.asyncio
async def test_platform_admin_rejects_duplicate_email(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    access = await _register_regular_ozo(client, "ad4")
    await _promote_to_platform_admin(db_session, "regularad4@me.cz")

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "regularad4@me.cz", "password": "heslo1234"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # První tenant projde
    r1 = await client.post(
        "/api/v1/admin/tenants",
        json={"tenant_name": "Klient A", "ozo_email": "dup@me.cz"},
        headers=headers,
    )
    assert r1.status_code == 201

    # Druhý pokus se stejným emailem → 409
    r2 = await client.post(
        "/api/v1/admin/tenants",
        json={"tenant_name": "Klient B", "ozo_email": "dup@me.cz"},
        headers=headers,
    )
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_platform_admin_suspend_tenant(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    access = await _register_regular_ozo(client, "ad5")
    await _promote_to_platform_admin(db_session, "regularad5@me.cz")

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "regularad5@me.cz", "password": "heslo1234"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # Vytvoř tenant
    create_resp = await client.post(
        "/api/v1/admin/tenants",
        json={"tenant_name": "Suspend me", "ozo_email": "suspend@me.cz"},
        headers=headers,
    )
    tenant_id = create_resp.json()["tenant"]["id"]

    # Pozastav
    patch_resp = await client.patch(
        f"/api/v1/admin/tenants/{tenant_id}",
        json={"is_active": False},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["is_active"] is False


@pytest.mark.asyncio
async def test_self_signup_disabled_blocks_register(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Když ALLOW_SELF_SIGNUP=false, /auth/register vrací 403."""
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "allow_self_signup", False)

    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "blocked@me.cz",
            "password": "heslo1234",
            "tenant_name": "Blocked",
        },
    )
    assert resp.status_code == 403
    assert "Self-signup" in resp.text
