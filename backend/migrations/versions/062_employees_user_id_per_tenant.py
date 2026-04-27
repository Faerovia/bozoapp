"""employees.user_id — composite unique (tenant_id, user_id) místo globálního

Revision ID: 062
Revises: 061
Create Date: 2026-04-27

Důvod:
OZO multi-client scénář vyžaduje, aby OZO uživatel měl Employee záznam
v každém tenantu, kde má membership (jinak signature flow nefunguje
v daném tenantu — services/signatures vyžaduje employee.user_id == user.id
filtrované přes tenant_id).

Stávající globální UNIQUE constraint `employees_user_id_key` to blokuje.

Změna:
- DROP constraint employees_user_id_key
- ADD partial UNIQUE (tenant_id, user_id) WHERE user_id IS NOT NULL

Partial je proto, že user_id je nullable (bulk import zaměstnanců bez
auth accountu). Bez partial by NULL × NULL nebyly v Postgresu duplicitní,
ale pro čistotu je partial striktnější.
"""

from alembic import op

revision = "062"
down_revision = "061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE employees DROP CONSTRAINT IF EXISTS employees_user_id_key")
    op.execute("""
        CREATE UNIQUE INDEX uq_employees_tenant_user
        ON employees (tenant_id, user_id)
        WHERE user_id IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_employees_tenant_user")
    # Nelze obnovit globální UNIQUE pokud existují per-tenant duplikáty.
    op.execute("""
        ALTER TABLE employees
        ADD CONSTRAINT employees_user_id_key UNIQUE (user_id)
    """)
