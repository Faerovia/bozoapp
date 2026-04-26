"""tenants.service_level + frozen_at

Revision ID: 055
Revises: 054
Create Date: 2026-04-26

Přidá:
- service_level VARCHAR(20) — úroveň služeb (free|basic|standard|pro|enterprise),
  konfiguruje admin v /admin/settings/service-levels
- frozen_at TIMESTAMP — pokud nastaven, tenant je „zmražený" (read-only přístup,
  nelze provádět změny). Reaktivace = SET frozen_at = NULL.

is_active už existuje a slouží pro úplnou deaktivaci (login zakázán).
"""

from alembic import op

revision = "055"
down_revision = "054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE tenants
        ADD COLUMN service_level VARCHAR(20)
    """)
    op.execute("""
        ALTER TABLE tenants
        ADD COLUMN frozen_at TIMESTAMPTZ
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE tenants DROP COLUMN IF EXISTS frozen_at")
    op.execute("ALTER TABLE tenants DROP COLUMN IF EXISTS service_level")
