"""document_folders RLS: oprava chybného setting name (app.tenant_id → app.current_tenant_id)

Revision ID: 043
Revises: 042
Create Date: 2026-04-26

PROBLÉM:
Migrace 032 vytvořila policy `tenant_isolation` s
`current_setting('app.tenant_id', true)`, ale ZBYTEK aplikace používá
`app.current_tenant_id`. Stejný bug jako u trainings (vyřešeno migrací 038).
Tenant INSERTy do document_folders padaly s "new row violates row-level
security policy".

ŘEŠENÍ:
Recreate `tenant_isolation` se správným setting name + samostatná WITH CHECK
klauzule (PG ji u INSERTu vyžaduje explicitně). Separátní `superadmin_bypass`
zůstává netknutá.
"""

from alembic import op

revision = "043"
down_revision = "042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON document_folders")
    op.execute("""
        CREATE POLICY tenant_isolation ON document_folders
        USING (
            tenant_id = NULLIF(
                current_setting('app.current_tenant_id', TRUE), ''
            )::UUID
        )
        WITH CHECK (
            tenant_id = NULLIF(
                current_setting('app.current_tenant_id', TRUE), ''
            )::UUID
        )
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON document_folders")
    op.execute("""
        CREATE POLICY tenant_isolation ON document_folders
        USING (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
    """)
