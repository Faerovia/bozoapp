"""users.role — přidá 'lead_worker' (vedoucí pracovník)

Revision ID: 054
Revises: 053
Create Date: 2026-04-26

Vedoucí pracovník = mid-level role mezi employee a hr_manager. Vidí
přiřazení své skupiny + může schvalovat/potvrzovat zápisy v rámci
svého pracoviště, ale nemá plný přístup k cross-tenant datům.
"""

from alembic import op

revision = "054"
down_revision = "053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check")
    op.execute("""
        ALTER TABLE users
        ADD CONSTRAINT users_role_check CHECK (
            role IN ('admin','ozo','hr_manager','lead_worker','equipment_responsible','employee')
        )
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check")
    op.execute("""
        ALTER TABLE users
        ADD CONSTRAINT users_role_check CHECK (
            role IN ('admin','ozo','hr_manager','equipment_responsible','employee')
        )
    """)
