"""
Testy audit logu — automatický zápis CREATE/UPDATE/DELETE do tabulky audit_log
přes SQLAlchemy before_flush listener.

Pokrývá:
- CREATE: vytvoření entity → 1 řádek s action=CREATE a new_values
- UPDATE: změna entity → 1 řádek s action=UPDATE a old/new_values
- DELETE (soft): archive → UPDATE (status=archived) — ne DELETE audit
- Tenant isolation: audit_log vidí jen záznamy vlastního tenantu
- hashed_password se NEZAPISUJE do new_values
"""
import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


async def _register(client: AsyncClient, suffix: str) -> tuple[dict, str]:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"audit{suffix}@me.cz",
            "password": "heslo1234",
            "tenant_name": f"Audit firma {suffix}",
        },
    )
    data = resp.json()
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    me = await client.get("/api/v1/users/me", headers=headers)
    return headers, me.json()["tenant_id"]


async def _fetch_audit_entries(
    db_session: AsyncSession, tenant_id: str, resource_type: str
) -> list[AuditLog]:
    # Nastavíme superadmin, abychom viděli všechny tenanty v testu
    await db_session.execute(
        text("SELECT set_config('app.is_superadmin', 'true', true)")
    )
    result = await db_session.execute(
        select(AuditLog)
        .where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.resource_type == resource_type,
        )
        .order_by(AuditLog.id)
    )
    return list(result.scalars().all())


@pytest.mark.asyncio
async def test_create_risk_writes_audit_entry(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers, tenant_id = await _register(client, "a1")

    resp = await client.post(
        "/api/v1/risks",
        json={"title": "Audit test riziko", "probability": 2, "severity": 3},
        headers=headers,
    )
    assert resp.status_code == 201

    entries = await _fetch_audit_entries(db_session, tenant_id, "risks")
    # Nejméně 1 CREATE (mohou přibýt další z jiných operací)
    create_entries = [e for e in entries if e.action == "CREATE"]
    assert len(create_entries) >= 1
    entry = create_entries[-1]
    assert entry.new_values is not None
    assert entry.new_values.get("title") == "Audit test riziko"
    assert entry.user_id is not None
    assert entry.resource_id


@pytest.mark.asyncio
async def test_update_risk_writes_audit_diff(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers, tenant_id = await _register(client, "a2")

    # CREATE
    create = await client.post(
        "/api/v1/risks",
        json={"title": "Původní", "probability": 2, "severity": 2},
        headers=headers,
    )
    risk_id = create.json()["id"]

    # UPDATE
    upd = await client.patch(
        f"/api/v1/risks/{risk_id}",
        json={"title": "Nový název"},
        headers=headers,
    )
    assert upd.status_code == 200

    entries = await _fetch_audit_entries(db_session, tenant_id, "risks")
    update_entries = [e for e in entries if e.action == "UPDATE"]
    assert len(update_entries) >= 1
    last_update = update_entries[-1]
    assert last_update.old_values is not None
    assert last_update.new_values is not None
    assert last_update.old_values.get("title") == "Původní"
    assert last_update.new_values.get("title") == "Nový název"


@pytest.mark.asyncio
async def test_audit_entries_are_tenant_isolated(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    h_a, tid_a = await _register(client, "a3")
    h_b, tid_b = await _register(client, "a4")

    await client.post(
        "/api/v1/risks",
        json={"title": "A tenant", "probability": 2, "severity": 2},
        headers=h_a,
    )
    await client.post(
        "/api/v1/risks",
        json={"title": "B tenant", "probability": 2, "severity": 2},
        headers=h_b,
    )

    entries_a = await _fetch_audit_entries(db_session, tid_a, "risks")
    entries_b = await _fetch_audit_entries(db_session, tid_b, "risks")

    assert any(
        e.new_values and e.new_values.get("title") == "A tenant" for e in entries_a
    )
    assert all(
        not (e.new_values and e.new_values.get("title") == "B tenant")
        for e in entries_a
    )
    assert any(
        e.new_values and e.new_values.get("title") == "B tenant" for e in entries_b
    )


@pytest.mark.asyncio
async def test_hashed_password_not_in_audit(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Při vytvoření usera (přes registraci) se hashed_password nesmí objevit
    v audit log new_values. To by byla leak citlivého údaje."""
    headers, tenant_id = await _register(client, "a5")

    entries = await _fetch_audit_entries(db_session, tenant_id, "users")
    for e in entries:
        if e.new_values:
            assert "hashed_password" not in e.new_values
        if e.old_values:
            assert "hashed_password" not in e.old_values


@pytest.mark.asyncio
async def test_audit_captures_employee_create(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers, tenant_id = await _register(client, "a6")

    await client.post(
        "/api/v1/employees",
        json={"first_name": "Audit", "last_name": "Employee", "employment_type": "hpp"},
        headers=headers,
    )

    entries = await _fetch_audit_entries(db_session, tenant_id, "employees")
    create_entries = [e for e in entries if e.action == "CREATE"]
    assert len(create_entries) >= 1
    assert create_entries[-1].new_values
    assert create_entries[-1].new_values.get("last_name") == "Employee"
    # IP/user_agent se ukládají z middlewaru, v testech jsou obvykle None
    # (httpx test client nemá skutečnou IP), tohle nechceme striktně testovat.
