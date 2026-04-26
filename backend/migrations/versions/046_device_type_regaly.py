"""revisions.device_type — přidá 'regaly' (regálové systémy ČSN EN 15635)

Revision ID: 046
Revises: 045
Create Date: 2026-04-26

Důvod:
- ČSN EN 15635 ukládá zaměstnavateli povinnost provádět vizuální inspekci
  regálových systémů min. 1× ročně (i v dalších kratších intervalech).
- Aplikace teď tento typ zařízení (spolu se 7 stávajícími) eviduje v Revizích.
"""

from alembic import op

revision = "046"
down_revision = "045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE revisions DROP CONSTRAINT IF EXISTS ck_revisions_device_type")
    op.execute("""
        ALTER TABLE revisions
        ADD CONSTRAINT ck_revisions_device_type CHECK (
            device_type IS NULL OR device_type IN (
                'elektro',
                'hromosvody',
                'plyn',
                'kotle',
                'tlakove_nadoby',
                'vytahy',
                'spalinove_cesty',
                'regaly'
            )
        )
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE revisions DROP CONSTRAINT IF EXISTS ck_revisions_device_type")
    op.execute("""
        ALTER TABLE revisions
        ADD CONSTRAINT ck_revisions_device_type CHECK (
            device_type IS NULL OR device_type IN (
                'elektro',
                'hromosvody',
                'plyn',
                'kotle',
                'tlakove_nadoby',
                'vytahy',
                'spalinove_cesty'
            )
        )
    """)
