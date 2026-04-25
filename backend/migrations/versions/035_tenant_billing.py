"""Tenant billing: typ platby + měsíční částka + měna

Revision ID: 035
Revises: 034
Create Date: 2026-04-25

Pole pro správu platby zákazníka (billing_type, billing_amount, billing_currency,
billing_note). Edituje pouze platform admin.
"""

from alembic import op

revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE tenants
            ADD COLUMN billing_type      VARCHAR(20),
            ADD COLUMN billing_amount    NUMERIC(10, 2),
            ADD COLUMN billing_currency  VARCHAR(3) NOT NULL DEFAULT 'CZK',
            ADD COLUMN billing_note      TEXT,
            ADD CONSTRAINT ck_tenant_billing_type
                CHECK (
                    billing_type IS NULL
                    OR billing_type IN ('monthly', 'yearly', 'per_employee', 'custom', 'free')
                )
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE tenants
            DROP CONSTRAINT IF EXISTS ck_tenant_billing_type,
            DROP COLUMN IF EXISTS billing_note,
            DROP COLUMN IF EXISTS billing_currency,
            DROP COLUMN IF EXISTS billing_amount,
            DROP COLUMN IF EXISTS billing_type
    """)
