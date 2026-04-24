"""Dedikovaný DB role pro aplikaci (bozoapp_app) + GRANT práv

Revision ID: 015
Revises: 014
Create Date: 2026-04-24

MOTIVACE:
Do migrace 014 aplikace běžela jako `bozoapp` — vlastník všech tabulek.
I s FORCE ROW LEVEL SECURITY (migrace 012) je to suboptimální pattern:
owner může DDL (CREATE/DROP/ALTER), může měnit policies, obejít schema
integrity checks přes SET ROLE, atd. Defense-in-depth = app se má
připojovat pod role s minimálními právy.

TENTO PŘECHOD:
- Role `bozoapp_app` (LOGIN, no superuser, no CREATE privileges) pro runtime
- Role `bozoapp` (existující) zůstává jen pro alembic migrace + admin
- Aplikace: DATABASE_URL → bozoapp_app
- Alembic: MIGRATION_DATABASE_URL → bozoapp (owner)

V produkci DBA vytvoří role `bozoapp_app` se svým secure password před
spuštěním migrace. DO block níž skip-ne CREATE pokud role existuje.

V dev/CI používáme stejný defaultní password pro jednoduchost — hardcoded
v migraci a v docker-compose / CI env. V prod to NEPOUŽÍVAT.
"""

from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


# Tenantované tabulky, na kterých potřebuje app plná data práva
_APP_TABLES = [
    "tenants",
    "users",
    "audit_log",
    "risks",
    "trainings",
    "revisions",
    "accident_reports",
    "oopp_assignments",
    "employees",
    "plants",
    "workplaces",
    "risk_factor_assessments",
    "job_positions",
    "medical_exams",
    "refresh_tokens",
    "password_reset_tokens",
]


def upgrade() -> None:
    # 1) Vytvoř role jen pokud neexistuje (prod DBA ji bude mít pre-created)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT FROM pg_catalog.pg_roles WHERE rolname = 'bozoapp_app'
            ) THEN
                CREATE ROLE bozoapp_app WITH LOGIN PASSWORD 'bozoapp_app_dev_secret';
            END IF;
        END
        $$;
    """)

    # 2) Grant USAGE na schema (PG16 default = public)
    op.execute("GRANT USAGE ON SCHEMA public TO bozoapp_app")

    # 3) Data-level práva na všech tabulkách
    for table in _APP_TABLES:
        op.execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO bozoapp_app"
        )

    # 4) Sequence usage (audit_log.id je BIGSERIAL)
    op.execute(
        "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO bozoapp_app"
    )

    # 5) Default privileges pro budoucí tabulky/sekvence, aby si DBA nemusel
    #    při každé nové migraci pamatovat na GRANT. Platí pro objekty vytvořené
    #    rolí bozoapp (která typicky spouští migrace).
    op.execute("""
        ALTER DEFAULT PRIVILEGES FOR ROLE bozoapp IN SCHEMA public
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO bozoapp_app
    """)
    op.execute("""
        ALTER DEFAULT PRIVILEGES FOR ROLE bozoapp IN SCHEMA public
        GRANT USAGE, SELECT ON SEQUENCES TO bozoapp_app
    """)


def downgrade() -> None:
    # Revoke všechno co jsme dali
    for table in _APP_TABLES:
        op.execute(f"REVOKE ALL ON {table} FROM bozoapp_app")
    op.execute("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM bozoapp_app")
    op.execute("REVOKE USAGE ON SCHEMA public FROM bozoapp_app")
    op.execute("""
        ALTER DEFAULT PRIVILEGES FOR ROLE bozoapp IN SCHEMA public
        REVOKE ALL ON TABLES FROM bozoapp_app
    """)
    op.execute("""
        ALTER DEFAULT PRIVILEGES FOR ROLE bozoapp IN SCHEMA public
        REVOKE ALL ON SEQUENCES FROM bozoapp_app
    """)
    # Role necháváme — DBA ji smaže ručně pokud chce
