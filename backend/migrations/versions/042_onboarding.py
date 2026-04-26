"""Onboarding tracking na tenantu

Revision ID: 042
Revises: 041
Create Date: 2026-04-26

DESIGN:
- onboarding_step1_completed_at — kdy uživatel prošel úvodním 2-krokovým wizardem
- onboarding_completed_at — kdy uživatel označil onboarding za hotový
  (auto: 6/9 done; manual: tlačítko 'Mám hotovo, skrýt')
- onboarding_dismissed — uživatel skryl checklist navždy

Žádný extra checklist tracker — progress se počítá v service vrstvě
z reálných dat (count(plants), count(employees), atd.). Jediný flag
v DB je dismissed/completed.
"""

from alembic import op

revision = "042"
down_revision = "041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE tenants
            ADD COLUMN onboarding_step1_completed_at TIMESTAMPTZ,
            ADD COLUMN onboarding_completed_at TIMESTAMPTZ,
            ADD COLUMN onboarding_dismissed BOOLEAN NOT NULL DEFAULT FALSE
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE tenants
            DROP COLUMN IF EXISTS onboarding_dismissed,
            DROP COLUMN IF EXISTS onboarding_completed_at,
            DROP COLUMN IF EXISTS onboarding_step1_completed_at
    """)
