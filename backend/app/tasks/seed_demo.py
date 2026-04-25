"""
Demo seed: vytvoří kompletní dataset pro prezentaci zákazníkům.

Přihlašovací údaje (po seed):
  Platform admin:  admin@demo.cz   / demo1234
  OZO (multi):     ozo@demo.cz     / demo1234

OZO má membership ve 2 klientech:
  - Strojírny ABC s.r.o.   (výroba; 8 zaměstnanců, plná data)
  - Pekárny XYZ a.s.       (potravinářství; 4 zaměstnanci)

Spuštění:
    docker compose exec backend python -m app.tasks.seed_demo

WARNING: Skript drop existujících demo tenantů před vložením. Není
určen pro produkci — jen pro dev/staging.
"""
from __future__ import annotations

import asyncio
import logging
import random
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.security import hash_password

# Registrace všech modelů do SQLAlchemy metadata (FK targets — bez toho
# `flush` selže na NoReferencedTableError, např. accident_reports.risk_id).
from app.models import (  # noqa: F401
    audit_log,
    password_reset_token,
    recovery_code,
    refresh_token,
    risk,
)
from app.models.accident_report import AccidentReport
from app.models.employee import Employee
from app.models.job_position import JobPosition
from app.models.medical_exam import MedicalExam
from app.models.membership import UserTenantMembership
from app.models.oopp import EmployeeOoppIssue, PositionOoppItem, PositionRiskGrid
from app.models.revision import (
    EmployeePlantResponsibility,
    Revision,
    RevisionRecord,
)
from app.models.risk_factor_assessment import RiskFactorAssessment
from app.models.tenant import Tenant
from app.models.training import Training, TrainingAssignment
from app.models.user import User
from app.models.workplace import Plant, Workplace

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("seed_demo")

random.seed(42)  # reproducibilní data

PASSWORD = "demo1234"  # noqa: S105 — demo only


# ── Pomocné generátory ───────────────────────────────────────────────────────

CZECH_FIRST_NAMES = [
    "Jan", "Petr", "Pavel", "Tomáš", "Martin", "Jakub", "Lukáš", "Jiří",
    "Eva", "Jana", "Lucie", "Tereza", "Kateřina", "Anna", "Hana", "Zuzana",
]
CZECH_LAST_NAMES = [
    "Novák", "Svoboda", "Novotný", "Dvořák", "Černý", "Procházka", "Kučera",
    "Veselý", "Horák", "Marek", "Pospíšil", "Štěpánek", "Šimek", "Růžička",
]


def _emp_name() -> tuple[str, str]:
    return random.choice(CZECH_FIRST_NAMES), random.choice(CZECH_LAST_NAMES)


def _add_months(d: date, months: int) -> date:
    import calendar
    month = d.month + months
    year = d.year + (month - 1) // 12
    month = ((month - 1) % 12) + 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(d.day, last_day)
    return date(year, month, day)


# ── Cleanup ──────────────────────────────────────────────────────────────────


async def _drop_demo_tenants(db: AsyncSession) -> None:
    """Smaže existující demo tenanty (CASCADE smaže veškerá data)."""
    res = await db.execute(
        select(Tenant).where(
            Tenant.slug.in_(["strojirny-abc-s-r-o", "pekarny-xyz-a-s"])
        )
    )
    for tenant in res.scalars():
        log.info("DROP existing demo tenant: %s", tenant.name)
        await db.delete(tenant)
    await db.flush()

    # Smaž demo usery (ozo@demo.cz, admin@demo.cz)
    await db.execute(
        delete(User).where(User.email.in_(["ozo@demo.cz", "admin@demo.cz"]))
    )
    await db.flush()


# ── Seed jednotlivých modulů ─────────────────────────────────────────────────


async def _seed_workplaces(
    db: AsyncSession, tenant_id: uuid.UUID, created_by: uuid.UUID,
    plant_specs: list[dict[str, Any]],
) -> dict[str, Plant]:
    """Vytvoří provozovny a pracoviště. Vrátí dict {plant.name: Plant}."""
    plants: dict[str, Plant] = {}
    for spec in plant_specs:
        plant = Plant(
            tenant_id=tenant_id,
            created_by=created_by,
            name=spec["name"],
            address=spec.get("address"),
            city=spec.get("city"),
            zip_code=spec.get("zip"),
            ico=spec.get("ico"),
        )
        db.add(plant)
        await db.flush()
        plants[plant.name] = plant

        for wp_name in spec.get("workplaces", []):
            wp = Workplace(
                tenant_id=tenant_id,
                plant_id=plant.id,
                created_by=created_by,
                name=wp_name,
            )
            db.add(wp)
    await db.flush()
    return plants


async def _seed_positions(
    db: AsyncSession, tenant_id: uuid.UUID, created_by: uuid.UUID,
    workplace: Workplace,
    position_specs: list[dict[str, Any]],
) -> dict[str, JobPosition]:
    positions: dict[str, JobPosition] = {}
    for spec in position_specs:
        jp = JobPosition(
            tenant_id=tenant_id,
            workplace_id=workplace.id,
            created_by=created_by,
            name=spec["name"],
            description=spec.get("description"),
            work_category=spec.get("work_category"),
        )
        db.add(jp)
        await db.flush()
        positions[jp.name] = jp

        # Auto-RFA s nějakými ratings
        rfa_overrides = spec.get("rfa", {})
        rfa = RiskFactorAssessment(
            tenant_id=tenant_id,
            workplace_id=workplace.id,
            job_position_id=jp.id,
            profese=jp.name,
            worker_count=spec.get("worker_count", 5),
            women_count=spec.get("women_count", 1),
            created_by=created_by,
            **rfa_overrides,
        )
        db.add(rfa)
    await db.flush()
    return positions


async def _seed_employees(
    db: AsyncSession, tenant_id: uuid.UUID, created_by: uuid.UUID,
    plants: dict[str, Plant],
    positions: dict[str, JobPosition],
    employee_specs: list[dict[str, Any]],
) -> list[Employee]:
    employees: list[Employee] = []
    for spec in employee_specs:
        first, last = spec.get("name") or _emp_name()
        plant = plants.get(spec.get("plant", "")) if spec.get("plant") else None
        position = positions.get(spec.get("position", "")) if spec.get("position") else None

        # Auth user
        email = spec.get("email") or f"{first.lower()}.{last.lower()}@demo.cz"
        # Kontrola duplicit
        existing = (await db.execute(
            select(User).where(User.email == email)
        )).scalar_one_or_none()
        if existing:
            email = f"{first.lower()}.{last.lower()}.{tenant_id.hex[:6]}@demo.cz"

        user = User(
            tenant_id=tenant_id,
            email=email,
            hashed_password=hash_password(PASSWORD),
            full_name=f"{first} {last}",
            role=spec.get("role", "employee"),
            is_active=True,
        )
        db.add(user)
        await db.flush()

        db.add(UserTenantMembership(
            user_id=user.id,
            tenant_id=tenant_id,
            role=user.role,
            is_default=True,
        ))

        emp = Employee(
            tenant_id=tenant_id,
            user_id=user.id,
            created_by=created_by,
            first_name=first,
            last_name=last,
            email=email,
            phone=f"+4207{random.randint(10, 99)}{random.randint(100000, 999999)}",
            address_street=f"{random.choice(['Hlavní', 'Náměstí Míru', 'Vrchlického', 'Komenského'])} {random.randint(1, 200)}",
            address_city=plant.city if plant else "Praha",
            address_zip=plant.zip_code if plant else "11000",
            employment_type=spec.get("employment_type", "hpp"),
            plant_id=plant.id if plant else None,
            workplace_id=position.workplace_id if position else None,
            job_position_id=position.id if position else None,
            hired_at=date.today() - timedelta(days=random.randint(30, 365 * 5)),
            personal_number=f"P{random.randint(1000, 9999)}",
        )
        db.add(emp)
        await db.flush()
        employees.append(emp)

        # Equipment responsibility (jen pokud zaměstnanec je 'equipment_responsible')
        if user.role == "equipment_responsible" and plant:
            db.add(EmployeePlantResponsibility(
                tenant_id=tenant_id,
                employee_id=emp.id,
                plant_id=plant.id,
            ))

    await db.flush()
    return employees


async def _seed_trainings(
    db: AsyncSession, tenant_id: uuid.UUID, created_by: uuid.UUID,
    employees: list[Employee],
) -> list[Training]:
    """3 šablony školení + assignments na zaměstnance s různými stavy."""
    today = date.today()
    templates = [
        Training(
            tenant_id=tenant_id, created_by=created_by,
            title="Vstupní školení BOZP",
            training_type="bozp", trainer_kind="ozo_bozp",
            valid_months=12,
        ),
        Training(
            tenant_id=tenant_id, created_by=created_by,
            title="Školení požární ochrany",
            training_type="po", trainer_kind="ozo_po",
            valid_months=24,
        ),
        Training(
            tenant_id=tenant_id, created_by=created_by,
            title="Práce ve výškách",
            training_type="other", trainer_kind="employer",
            valid_months=12,
        ),
    ]
    for t in templates:
        db.add(t)
    await db.flush()

    # Pro každý template přiřaď polovině zaměstnanců — různé statusy
    for tpl in templates:
        for emp in employees:
            if random.random() < 0.6:  # 60% pokrytí
                status = random.choice(["completed", "completed", "completed", "pending", "expired"])
                last_completed = today - timedelta(days=random.randint(30, 400))

                # 'expired' = valid_until v minulosti; 'completed' = v budoucnu
                if status == "completed":
                    valid_until = _add_months(last_completed, tpl.valid_months)
                    last_completed_at: datetime | None = datetime(
                        last_completed.year, last_completed.month, last_completed.day,
                        tzinfo=UTC,
                    )
                elif status == "expired":
                    last_completed = today - timedelta(days=400)
                    valid_until = _add_months(last_completed, 6)
                    last_completed_at = datetime(
                        last_completed.year, last_completed.month, last_completed.day,
                        tzinfo=UTC,
                    )
                else:  # pending
                    valid_until = None
                    last_completed_at = None

                ta = TrainingAssignment(
                    tenant_id=tenant_id,
                    training_id=tpl.id,
                    employee_id=emp.id,
                    deadline=datetime.now(UTC) + timedelta(days=7),
                    last_completed_at=last_completed_at,
                    valid_until=valid_until,
                    status=status,
                    assigned_by=created_by,
                )
                db.add(ta)

    await db.flush()
    return templates


async def _seed_revisions(
    db: AsyncSession, tenant_id: uuid.UUID, created_by: uuid.UUID,
    plants: dict[str, Plant],
    device_specs: list[dict[str, Any]],
) -> list[Revision]:
    revisions: list[Revision] = []
    today = date.today()
    for spec in device_specs:
        plant = plants.get(spec["plant"])
        if plant is None:
            continue
        last_rev = today - timedelta(days=spec.get("days_since_last", 180))
        valid_months = spec.get("valid_months", 12)
        rev = Revision(
            tenant_id=tenant_id,
            created_by=created_by,
            title=spec["title"],
            plant_id=plant.id,
            device_code=spec.get("code"),
            device_type=spec.get("type"),
            location=spec.get("location"),
            last_revised_at=last_rev,
            valid_months=valid_months,
            next_revision_at=_add_months(last_rev, valid_months),
            technician_name=spec.get("technician", "Ing. Ladislav Dvořák"),
            technician_email=spec.get("tech_email", "dvorak@revize.cz"),
            technician_phone=spec.get("tech_phone", "+420603123456"),
            qr_token=uuid.uuid4().hex,
        )
        db.add(rev)
        await db.flush()
        revisions.append(rev)

        # Timeline — pár historických záznamů
        record = RevisionRecord(
            tenant_id=tenant_id,
            revision_id=rev.id,
            performed_at=last_rev,
            technician_name=rev.technician_name,
            notes="Bez závad. Zařízení v provozuschopném stavu.",
            created_by=created_by,
        )
        db.add(record)

    await db.flush()
    return revisions


async def _seed_oopp(
    db: AsyncSession, tenant_id: uuid.UUID, created_by: uuid.UUID,
    positions: dict[str, JobPosition],
    employees: list[Employee],
) -> None:
    """Pro 1-2 pozice vytvoří risk grid + OOPP items + výdeje pro zaměstnance."""
    today = date.today()
    for pos_name, jp in list(positions.items())[:2]:
        # Risk grid
        grid_data = {
            "G": [1, 6],          # ruce: náraz + odření
            "I": [2],             # nohy chodidla: uklouznutí
            "D": [13, 18],        # oči: neionizující záření + postříkání
        }
        if "Svářeč" in pos_name:
            grid_data["E"] = [9]  # obličej: teplo, oheň
            grid_data["F"] = [15] # dýchací: prach
        prg = PositionRiskGrid(
            tenant_id=tenant_id,
            job_position_id=jp.id,
            grid=grid_data,
            created_by=created_by,
        )
        db.add(prg)

        # OOPP items (2-3 per body part)
        items_specs = [
            ("G", "Pracovní rukavice odolné proti řezu", 12),
            ("I", "Pracovní obuv S3 protiskluzová", 12),
            ("D", "Ochranné brýle", 24),
        ]
        if "Svářeč" in pos_name:
            items_specs.append(("E", "Svářečská kukla samostmívací", 36))
            items_specs.append(("F", "Respirátor FFP3", 6))

        items: list[PositionOoppItem] = []
        for body_part, name, months in items_specs:
            it = PositionOoppItem(
                tenant_id=tenant_id,
                job_position_id=jp.id,
                body_part=body_part,
                name=name,
                valid_months=months,
                created_by=created_by,
            )
            db.add(it)
            items.append(it)
        await db.flush()

        # Výdeje pro zaměstnance, kteří mají tuto pozici
        for emp in employees:
            if emp.job_position_id == jp.id:
                for item in items:
                    days_ago = random.randint(30, 400)
                    issued = today - timedelta(days=days_ago)
                    valid_until = _add_months(issued, item.valid_months) if item.valid_months else None
                    db.add(EmployeeOoppIssue(
                        tenant_id=tenant_id,
                        employee_id=emp.id,
                        position_oopp_item_id=item.id,
                        issued_at=issued,
                        valid_until=valid_until,
                        quantity=1,
                        size_spec=random.choice(["L", "M", "XL", "42", "44"]),
                        created_by=created_by,
                    ))

    await db.flush()


async def _seed_medical_exams(
    db: AsyncSession, tenant_id: uuid.UUID, created_by: uuid.UUID,
    employees: list[Employee],
) -> None:
    today = date.today()
    for emp in employees[:max(3, len(employees) // 2)]:
        exam_date = today - timedelta(days=random.randint(60, 720))
        valid_months = random.choice([24, 48])
        db.add(MedicalExam(
            tenant_id=tenant_id,
            created_by=created_by,
            employee_id=emp.id,
            exam_type=random.choice(["vstupni", "periodicka"]),
            exam_date=exam_date,
            result="zpusobily",
            valid_months=valid_months,
            valid_until=_add_months(exam_date, valid_months),
            physician_name="MUDr. Karel Procházka",
        ))
    await db.flush()


async def _seed_accident(
    db: AsyncSession, tenant_id: uuid.UUID, created_by: uuid.UUID,
    employees: list[Employee],
) -> None:
    if not employees:
        return
    from datetime import time
    emp = employees[0]
    db.add(AccidentReport(
        tenant_id=tenant_id,
        created_by=created_by,
        employee_id=emp.id,
        employee_name=f"{emp.first_name} {emp.last_name}",
        workplace="Hala A — sklad nářadí",
        accident_date=date.today() - timedelta(days=45),
        accident_time=time(9, 30),
        injury_type="podvrtnutí kolene",
        injured_body_part="pravé koleno",
        injury_source="žebřík (nestabilní)",
        injury_cause=(
            "Zaměstnanec při výměně osvětlovacího tělesa stoupl na nestabilní "
            "žebřík, který se posunul."
        ),
        description=(
            "Zaměstnanec při výměně osvětlovacího tělesa stoupl na nestabilní "
            "žebřík, který se posunul. Zaměstnanec spadl ze ~1.5 m a poranil "
            "si pravé koleno. Po ošetření v nemocnici diagnostikováno "
            "podvrtnutí, 14 dní pracovní neschopnosti."
        ),
        injured_count=1,
        is_fatal=False,
        risk_review_required=True,
        witnesses=[{"name": "Petr Svoboda", "contact": "+420604111222"}],
        status="final",
    ))


# ── Main seed ────────────────────────────────────────────────────────────────


async def seed(db: AsyncSession) -> None:
    log.info("=" * 60)
    log.info("BOZOapp DEMO seed")
    log.info("=" * 60)

    await db.execute(text("SELECT set_config('app.is_superadmin', 'true', true)"))

    await _drop_demo_tenants(db)

    # ── Platform admin ───────────────────────────────────────────────
    log.info("Creating platform admin user...")
    admin_tenant = Tenant(name="Platform", slug="platform")
    db.add(admin_tenant)
    await db.flush()

    admin_user = User(
        tenant_id=admin_tenant.id,
        email="admin@demo.cz",
        hashed_password=hash_password(PASSWORD),
        full_name="Platform Admin",
        role="admin",
        is_active=True,
        is_platform_admin=True,
    )
    db.add(admin_user)
    await db.flush()
    db.add(UserTenantMembership(
        user_id=admin_user.id,
        tenant_id=admin_tenant.id,
        role="admin",
        is_default=True,
    ))
    await db.flush()

    # ── OZO user (multi-client) ──────────────────────────────────────
    log.info("Creating OZO user...")
    # Primární tenant — Strojírny ABC (vytvoříme ho jako první)
    abc = Tenant(
        name="Strojírny ABC s.r.o.",
        slug="strojirny-abc-s-r-o",
        external_login_enabled=False,
    )
    db.add(abc)
    await db.flush()

    ozo = User(
        tenant_id=abc.id,
        email="ozo@demo.cz",
        hashed_password=hash_password(PASSWORD),
        full_name="Bc. Lukáš Voráček (OZO)",
        role="ozo",
        is_active=True,
    )
    db.add(ozo)
    await db.flush()
    db.add(UserTenantMembership(
        user_id=ozo.id, tenant_id=abc.id, role="ozo", is_default=True,
    ))

    # ── Klient 1: Strojírny ABC ─────────────────────────────────────
    log.info("Seeding klient 1: Strojírny ABC s.r.o.")
    plants_abc = await _seed_workplaces(db, abc.id, ozo.id, [
        {
            "name": "Provozovna Praha",
            "address": "Vinohradská 1234/56",
            "city": "Praha", "zip": "12000", "ico": "12345678",
            "workplaces": ["Hala A", "Hala B"],
        },
        {
            "name": "Provozovna Brno",
            "address": "Veveří 100",
            "city": "Brno", "zip": "60200", "ico": "12345678",
            "workplaces": ["Sklad"],
        },
    ])

    # Pozice na Hala A
    res = await db.execute(
        select(Workplace).where(Workplace.plant_id == plants_abc["Provozovna Praha"].id)
    )
    workplaces_praha = list(res.scalars().all())
    hala_a = next(w for w in workplaces_praha if w.name == "Hala A")

    positions_abc = await _seed_positions(db, abc.id, ozo.id, hala_a, [
        {"name": "Soustružník",
         "rfa": {"rf_hluk": "3", "rf_vibrace": "2", "rf_prach": "2"}},
        {"name": "Svářeč",
         "rfa": {"rf_zareni": "3", "rf_chem": "2", "rf_hluk": "2"}},
        {"name": "Mistr",
         "rfa": {"rf_psych": "2"}},
    ])

    # Sklad pozice
    res = await db.execute(
        select(Workplace).where(Workplace.plant_id == plants_abc["Provozovna Brno"].id)
    )
    sklad = list(res.scalars().all())[0]
    positions_abc.update(await _seed_positions(db, abc.id, ozo.id, sklad, [
        {"name": "Skladník",
         "rfa": {"rf_fyz_zatez": "2", "rf_prac_poloha": "2"}},
    ]))

    employees_abc = await _seed_employees(db, abc.id, ozo.id, plants_abc, positions_abc, [
        {"name": ("Pavel", "Novák"), "plant": "Provozovna Praha", "position": "Soustružník", "role": "employee"},
        {"name": ("Jan", "Svoboda"), "plant": "Provozovna Praha", "position": "Svářeč", "role": "employee"},
        {"name": ("Tomáš", "Dvořák"), "plant": "Provozovna Praha", "position": "Soustružník", "role": "employee"},
        {"name": ("Petr", "Černý"), "plant": "Provozovna Praha", "position": "Mistr", "role": "equipment_responsible"},
        {"name": ("Eva", "Procházková"), "plant": "Provozovna Brno", "position": "Skladník", "role": "employee"},
        {"name": ("Lucie", "Veselá"), "plant": "Provozovna Brno", "position": "Skladník", "role": "employee"},
        {"name": ("Martin", "Horák"), "plant": "Provozovna Praha", "position": "Svářeč", "role": "employee"},
        {"name": ("Tereza", "Marková"), "plant": "Provozovna Praha", "position": "Mistr", "role": "hr_manager"},
    ])

    await _seed_trainings(db, abc.id, ozo.id, employees_abc)
    await _seed_revisions(db, abc.id, ozo.id, plants_abc, [
        {"title": "Hlavní rozvaděč R1", "type": "elektro", "code": "RZV-001",
         "plant": "Provozovna Praha", "location": "Hala A", "valid_months": 60,
         "days_since_last": 100},
        {"title": "Mostový jeřáb 5t", "type": "vytahy", "code": "MJ-5T",
         "plant": "Provozovna Praha", "location": "Hala B", "valid_months": 12,
         "days_since_last": 350},  # po termínu
        {"title": "Vzduchový kompresor", "type": "tlakove_nadoby",
         "plant": "Provozovna Praha", "location": "Hala A", "valid_months": 12,
         "days_since_last": 340},
        {"title": "Plynový rozvod", "type": "plyn", "code": "PR-01",
         "plant": "Provozovna Brno", "valid_months": 12,
         "days_since_last": 60},
        {"title": "Hromosvod budovy", "type": "hromosvody",
         "plant": "Provozovna Praha", "valid_months": 60,
         "days_since_last": 700},
    ])
    await _seed_oopp(db, abc.id, ozo.id, positions_abc, employees_abc)
    await _seed_medical_exams(db, abc.id, ozo.id, employees_abc)
    await _seed_accident(db, abc.id, ozo.id, employees_abc)

    # ── Klient 2: Pekárny XYZ ───────────────────────────────────────
    log.info("Seeding klient 2: Pekárny XYZ a.s.")
    xyz = Tenant(
        name="Pekárny XYZ a.s.",
        slug="pekarny-xyz-a-s",
        external_login_enabled=False,
    )
    db.add(xyz)
    await db.flush()

    db.add(UserTenantMembership(
        user_id=ozo.id, tenant_id=xyz.id, role="ozo", is_default=False,
    ))
    await db.flush()

    plants_xyz = await _seed_workplaces(db, xyz.id, ozo.id, [
        {
            "name": "Pekárna Plzeň",
            "address": "Karlovarská 30",
            "city": "Plzeň", "zip": "30100", "ico": "87654321",
            "workplaces": ["Výrobní hala"],
        },
    ])
    res = await db.execute(
        select(Workplace).where(Workplace.tenant_id == xyz.id)
    )
    wp_xyz = list(res.scalars().all())[0]
    positions_xyz = await _seed_positions(db, xyz.id, ozo.id, wp_xyz, [
        {"name": "Pekař",
         "rfa": {"rf_teplo": "3", "rf_prach": "2"}},
        {"name": "Prodavač",
         "rfa": {"rf_psych": "2", "rf_prac_poloha": "2"}},
    ])

    employees_xyz = await _seed_employees(db, xyz.id, ozo.id, plants_xyz, positions_xyz, [
        {"name": ("Jakub", "Novotný"), "plant": "Pekárna Plzeň", "position": "Pekař", "role": "employee"},
        {"name": ("Hana", "Kučerová"), "plant": "Pekárna Plzeň", "position": "Pekař", "role": "employee"},
        {"name": ("Anna", "Štěpánková"), "plant": "Pekárna Plzeň", "position": "Prodavač", "role": "employee"},
        {"name": ("Zuzana", "Šimková"), "plant": "Pekárna Plzeň", "position": "Prodavač", "role": "hr_manager"},
    ])

    await _seed_trainings(db, xyz.id, ozo.id, employees_xyz)
    await _seed_revisions(db, xyz.id, ozo.id, plants_xyz, [
        {"title": "Plynová pec PP-3", "type": "plyn", "code": "PEC-3",
         "plant": "Pekárna Plzeň", "valid_months": 12,
         "days_since_last": 200},
        {"title": "Hasicí přístroje (set)", "type": "elektro",  # legacy
         "plant": "Pekárna Plzeň", "valid_months": 12,
         "days_since_last": 320},
    ])
    await _seed_oopp(db, xyz.id, ozo.id, positions_xyz, employees_xyz)
    await _seed_medical_exams(db, xyz.id, ozo.id, employees_xyz)

    log.info("=" * 60)
    log.info("Demo seed dokončen.")
    log.info("Přihlašovací údaje:")
    log.info("  Platform admin:  admin@demo.cz / %s", PASSWORD)
    log.info("  OZO (multi):     ozo@demo.cz   / %s", PASSWORD)
    log.info("=" * 60)


async def main() -> None:
    settings = get_settings()
    db_url = settings.migration_database_url or settings.database_url
    engine = create_async_engine(db_url, echo=False)
    async_session = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )

    async with async_session() as db:
        async with db.begin():
            await seed(db)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
