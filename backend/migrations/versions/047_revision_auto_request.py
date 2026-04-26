"""revisions.auto_request_enabled + auto_request_sent_at

Revision ID: 047
Revises: 046
Create Date: 2026-04-26

Účel:
- Per-revize zapínatelná automatická poptávka revize emailem na technika.
- Cron job běží denně, 30 dní před expirací revize odešle email na
  Revision.technician_email, CC odpovědné osoby (přes
  EmployeePlantResponsibility na Revision.plant_id).
- auto_request_sent_at zaznamenává, kdy proběhl poslední odeslaný request,
  aby se neopakovaně neposílalo (idempotence per cyklus revize).
"""

from alembic import op

revision = "047"
down_revision = "046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE revisions
        ADD COLUMN auto_request_enabled BOOLEAN NOT NULL DEFAULT FALSE
    """)
    op.execute("""
        ALTER TABLE revisions
        ADD COLUMN auto_request_sent_at DATE
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE revisions DROP COLUMN IF EXISTS auto_request_sent_at")
    op.execute("ALTER TABLE revisions DROP COLUMN IF EXISTS auto_request_enabled")
