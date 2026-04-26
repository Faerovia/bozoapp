"""employees.gender — přidá sloupec pohlaví (M/F/X)

Revision ID: 045
Revises: 044
Create Date: 2026-04-26

Důvod:
- Filtrování zaměstnanců dle pohlaví (počet žen ve firmě, ženy na rizikových
  pracovištích pro NV 361/2007 reporting).
- Nepovinné pole — existující záznamy zůstanou NULL ("neuvedeno").

Hodnoty: 'M' (muž) | 'F' (žena) | 'X' (jiné/neuvedeno)
"""

from alembic import op

revision = "045"
down_revision = "044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE employees
        ADD COLUMN gender VARCHAR(1)
        CHECK (gender IN ('M', 'F', 'X') OR gender IS NULL)
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE employees DROP COLUMN gender")
