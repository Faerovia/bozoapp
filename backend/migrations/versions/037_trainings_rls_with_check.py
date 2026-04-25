"""Trainings RLS: přidat WITH CHECK pro INSERT/UPDATE

Revision ID: 037
Revises: 036
Create Date: 2026-04-25

V migraci 036 jsme nastavili novou USING klauzuli, ale Postgres pro
INSERT/UPDATE vyžaduje samostatnou WITH CHECK klauzuli — bez ní jakýkoliv
INSERT do trainings selhal s "new row violates row-level security policy".
"""

from alembic import op

revision = "037"
down_revision = "036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON trainings")
    op.execute("""
        CREATE POLICY tenant_isolation ON trainings
        USING (
            is_global = TRUE
            OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        WITH CHECK (
            is_global = TRUE
            OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON trainings")
    op.execute("""
        CREATE POLICY tenant_isolation ON trainings
        USING (
            is_global = TRUE
            OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
    """)
