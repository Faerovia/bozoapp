"""Employee: last_exam_auto_check_at pro throttling auto-generace prohlídek

Revision ID: 031
Revises: 030
Create Date: 2026-04-25
"""

from alembic import op

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE employees
            ADD COLUMN last_exam_auto_check_at TIMESTAMPTZ
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE employees DROP COLUMN IF EXISTS last_exam_auto_check_at
    """)
