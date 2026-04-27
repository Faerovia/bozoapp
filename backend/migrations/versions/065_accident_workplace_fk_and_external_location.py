"""accident_reports — workplace_id FK + workplace_external_description

Revision ID: 065
Revises: 064
Create Date: 2026-04-27

Stávající sloupec `workplace VARCHAR(255) NOT NULL` byl free-text. UI ho teď
mění na dropdown z `workplaces` tenantu + položka „Místo úrazu mimo provozovnu".

Změny:
- ADD COLUMN workplace_id UUID NULL REFERENCES workplaces(id) ON DELETE SET NULL
- ADD COLUMN workplace_external_description TEXT NULL
  (vyplněno když uživatel vybral "mimo provozovnu" → popis kde se úraz stal)

Stávající `workplace` text sloupec zůstává (snapshot názvu pracoviště pro PDF).
- workplace_id != NULL → workplace = Workplace.name
- workplace_id == NULL → workplace = workplace_external_description (nebo legacy text)
"""

from alembic import op

revision = "065"
down_revision = "064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE accident_reports
        ADD COLUMN workplace_id UUID
        REFERENCES workplaces(id) ON DELETE SET NULL
    """)
    op.execute("""
        ALTER TABLE accident_reports
        ADD COLUMN workplace_external_description TEXT
    """)
    op.execute("""
        CREATE INDEX ix_accident_reports_workplace_id
        ON accident_reports (workplace_id)
        WHERE workplace_id IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_accident_reports_workplace_id")
    op.execute("ALTER TABLE accident_reports DROP COLUMN IF EXISTS workplace_external_description")
    op.execute("ALTER TABLE accident_reports DROP COLUMN IF EXISTS workplace_id")
