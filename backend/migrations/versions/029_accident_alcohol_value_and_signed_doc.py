"""Pracovní úrazy: alcohol_test_value (promile) + signed_document_path

Revision ID: 029
Revises: 028
Create Date: 2026-04-25

Po legislativní revizi formuláře:
- pokud test alkoholu vyšel pozitivní, je třeba uvést konkrétní hodnotu
  (promile, např. 0.45). Sloupec NUMERIC(4,2) — rozsah 0.00–99.99.
- pro archivaci podepsaného papírového záznamu je třeba úložiště
  pro nahraný PDF / sken (max 1 soubor per úraz, ukládá se vedle fotek).
"""

from alembic import op

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE accident_reports
            ADD COLUMN alcohol_test_value NUMERIC(4, 2),
            ADD COLUMN signed_document_path VARCHAR(500),
            ADD CONSTRAINT ck_accident_reports_alcohol_value
                CHECK (alcohol_test_value IS NULL OR alcohol_test_value >= 0)
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE accident_reports
            DROP CONSTRAINT IF EXISTS ck_accident_reports_alcohol_value,
            DROP COLUMN IF EXISTS signed_document_path,
            DROP COLUMN IF EXISTS alcohol_test_value
    """)
