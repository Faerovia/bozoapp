"""
Testy pro email reminders (commit 19c).
"""

from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.email import EmailMessage
from app.core.security import decode_token
from app.models.training import Training, TrainingAssignment
from app.models.user import User
from app.services.reminders import (
    ReminderModule,
    collect_all_reminders_for_tenant,
    collect_expiring_trainings,
)
from app.services.reminders_email import build_email_body


async def _register_ozo(client: AsyncClient, suffix: str) -> tuple[str, str]:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"r{suffix}@me.cz",
            "password": "heslo1234",
            "tenant_name": f"Klient {suffix}",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    payload = decode_token(body["access_token"])
    return body["access_token"], str(payload["tenant_id"])


async def _promote_to_admin(db: AsyncSession, email: str) -> None:
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))
    user = (await db.execute(select(User).where(User.email == email))).scalar_one()
    user.role = "admin"
    user.is_platform_admin = True
    await db.commit()


async def _create_employee_with_expiring_training(
    db: AsyncSession,
    tenant_id: str,
    *,
    valid_until_offset_days: int,
    suffix: str = "",
) -> None:
    """Pomocná funkce: vytvoří zaměstnance + training + assignment s daným offsetem."""
    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))
    await db.execute(text(f"SELECT set_config('app.current_tenant_id', '{tenant_id}', true)"))

    # Najdi prvního usera tenantu (potřebujeme created_by)
    user = (await db.execute(
        select(User).where(User.tenant_id == tenant_id)
    )).scalar_one()

    # Vytvoř zaměstnance přímo (bypass Pydantic validace)
    emp_id = uuid4()
    await db.execute(
        text(
            """INSERT INTO employees (
                id, tenant_id, first_name, last_name, status,
                employment_type, created_by, created_at, updated_at
            ) VALUES (
                :id, :tid, :fn, :ln, 'active',
                'hpp', :uid, NOW(), NOW()
            )"""
        ),
        {
            "id": emp_id,
            "tid": tenant_id,
            "fn": f"Anna{suffix}",
            "ln": "Nováková",
            "uid": user.id,
        },
    )

    # Training šablona
    training = Training(
        id=uuid4(),
        tenant_id=tenant_id,
        title=f"BOZP základní {suffix}",
        training_type="bozp",
        trainer_kind="employer",
        valid_months=12,
        is_global=False,
        created_by=user.id,
    )
    db.add(training)
    await db.flush()

    # Assignment s valid_until
    today = date.today()
    valid_until = today + timedelta(days=valid_until_offset_days)
    now = datetime.now(UTC)
    assignment = TrainingAssignment(
        id=uuid4(),
        tenant_id=tenant_id,
        training_id=training.id,
        employee_id=emp_id,
        valid_until=valid_until,
        last_completed_at=now,
        deadline=now + timedelta(days=7),
        status="completed",
        assigned_by=user.id,
    )
    db.add(assignment)
    await db.commit()


@pytest.mark.asyncio
async def test_collect_expiring_trainings_within_threshold(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    _, tid = await _register_ozo(client, "et1")
    await _create_employee_with_expiring_training(
        db_session, tid, valid_until_offset_days=15, suffix="A",
    )
    await _create_employee_with_expiring_training(
        db_session, tid, valid_until_offset_days=60, suffix="B",  # mimo threshold
    )

    items = await collect_expiring_trainings(
        db_session, tid, today=date.today(), threshold_days=30,
    )
    assert len(items) == 1
    assert "Anna" in items[0].person_name
    assert items[0].module == ReminderModule.TRAINING
    assert 0 < items[0].days_until <= 30


@pytest.mark.asyncio
async def test_collect_includes_overdue(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    _, tid = await _register_ozo(client, "ov1")
    await _create_employee_with_expiring_training(
        db_session, tid, valid_until_offset_days=-5, suffix="X",
    )
    items = await collect_expiring_trainings(
        db_session, tid, today=date.today(), threshold_days=30,
    )
    assert len(items) == 1
    assert items[0].days_until == -5


@pytest.mark.asyncio
async def test_email_body_groups_by_module(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    _, tid = await _register_ozo(client, "eb1")
    await _create_employee_with_expiring_training(
        db_session, tid, valid_until_offset_days=10, suffix="C",
    )
    items = await collect_all_reminders_for_tenant(
        db_session, tid, today=date.today(),
    )
    subject, body = build_email_body(items, "Klient eb1")
    assert "Klient eb1" in subject
    assert "Anna" in body
    assert "Školení" in body


@pytest.mark.asyncio
async def test_admin_run_reminders_dry_run(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    _, tid = await _register_ozo(client, "ar1")
    await _promote_to_admin(db_session, "rar1@me.cz")
    await _create_employee_with_expiring_training(
        db_session, tid, valid_until_offset_days=20, suffix="D",
    )

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "rar1@me.cz", "password": "heslo1234"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # dry_run = True → žádný email
    captured: list[EmailMessage] = []

    class _Capture:
        async def send(self, message: EmailMessage) -> None:
            captured.append(message)

    with patch(
        "app.services.reminders_email.get_email_sender",
        return_value=_Capture(),
    ):
        resp = await client.post(
            "/api/v1/admin/reminders/run-now?dry_run=true", headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["dry_run"] is True
    assert data["items_total"] >= 1
    assert len(captured) == 0  # dry run


@pytest.mark.asyncio
async def test_admin_preview_returns_subject_and_body(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    _, tid = await _register_ozo(client, "pv1")
    await _promote_to_admin(db_session, "rpv1@me.cz")
    await _create_employee_with_expiring_training(
        db_session, tid, valid_until_offset_days=5, suffix="E",
    )

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "rpv1@me.cz", "password": "heslo1234"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await client.get(
        f"/api/v1/admin/reminders/preview/{tid}", headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["items_count"] >= 1
    assert data["subject"] is not None
    assert "Anna" in data["body_text"]
