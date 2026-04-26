"""responsible_employee_id pro operating_log_devices a periodic_checks

Revision ID: 056
Revises: 055
Create Date: 2026-04-26

Přidá responsible_employee_id (FK employees.id) na:
- operating_log_devices  — zaměstnanec, kterému chodí no-entry alert
- periodic_checks         — zaměstnanec, kterému chodí due-soon/overdue alert

Pozn.: periodic_checks už má responsible_user_id (FK users.id) z migrace 053
(commit 76). Necháváme pro backward-compat, ale nově preferujeme
responsible_employee_id, protože „kterýkoliv pracovník" obvykle není
auth user (jen zaměstnanec).
"""

from alembic import op

revision = "056"
down_revision = "055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE operating_log_devices
        ADD COLUMN responsible_employee_id UUID
            REFERENCES employees(id) ON DELETE SET NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_oplog_devices_responsible_emp
        ON operating_log_devices(responsible_employee_id)
        WHERE responsible_employee_id IS NOT NULL
    """)

    op.execute("""
        ALTER TABLE periodic_checks
        ADD COLUMN responsible_employee_id UUID
            REFERENCES employees(id) ON DELETE SET NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_periodic_checks_responsible_emp
        ON periodic_checks(responsible_employee_id)
        WHERE responsible_employee_id IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_periodic_checks_responsible_emp")
    op.execute(
        "ALTER TABLE periodic_checks DROP COLUMN IF EXISTS responsible_employee_id"
    )
    op.execute("DROP INDEX IF EXISTS ix_oplog_devices_responsible_emp")
    op.execute(
        "ALTER TABLE operating_log_devices DROP COLUMN IF EXISTS responsible_employee_id"
    )
