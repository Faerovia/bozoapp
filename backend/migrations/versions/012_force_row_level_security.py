"""FORCE Row-Level Security na všech tenantovaných tabulkách

Revision ID: 012
Revises: 011
Create Date: 2026-04-24

PROBLÉM:
PostgreSQL RLS defaultně NEPLATÍ pro vlastníka tabulky (table owner).
Aplikace se připojuje jako 'bozoapp', což je POSTGRES_USER a tedy i vlastník
všech tabulek vytvořených přes Alembic. Důsledek: RLS policy definované
v migracích 001-010 byly reálně neefektivní — tenant isolation závisela
výlučně na explicitním `where tenant_id = ?` v aplikačním kódu.

ŘEŠENÍ:
ALTER TABLE ... FORCE ROW LEVEL SECURITY vynutí RLS i pro vlastníka.
Od této migrace RLS funguje jako defense-in-depth vrstva — pokud vývojář
zapomene tenant_id filter ve where klauzuli, DB vrátí prázdný výsledek
místo dat z cizího tenantu.

POZOR: Pro registraci/login je potřeba set_config('app.is_superadmin', 'true')
v rámci transakce (již implementováno v app/services/auth.py).
"""

from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


# Tabulky s tenant_id, které mají RLS policy a potřebují FORCE
TENANT_TABLES = [
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
]


def upgrade() -> None:
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
