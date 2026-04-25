"""Trainings RLS: oprava chybného názvu nastavení (app.tenant_id → app.current_tenant_id)

Revision ID: 038
Revises: 037
Create Date: 2026-04-25

PROBLÉM:
Migrace 036 a 037 nastavily policy `tenant_isolation` na trainings s
`current_setting('app.tenant_id', true)`, ale ZBYTEK aplikace (a všechny
ostatní tabulky, viz migrace 021) používá `app.current_tenant_id`. Service
vrstva volá `set_config('app.current_tenant_id', tenant_id, true)`, takže
naše policy vždy evaluovala FALSE (NULLIF na neexistující setting → NULL)
a INSERTy do trainings padaly s "new row violates row-level security policy".

ŘEŠENÍ:
Recreate `tenant_isolation` policy se správným setting name a se
samostatnou WITH CHECK klauzulí (PG ji u INSERTu vyžaduje explicitně,
když je policy definovaná přes USING + WITH CHECK).

POZNÁMKA:
Separátní `superadmin_bypass` policy z migrace 003 zůstává netknutá.
Obě policy jsou PERMISSIVE, takže se OR-ují — superadmin (login flow,
admin endpointy) nadále projde přes svou bypass policy.
"""

from alembic import op

revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON trainings")
    op.execute("""
        CREATE POLICY tenant_isolation ON trainings
        USING (
            is_global = TRUE
            OR tenant_id = NULLIF(
                current_setting('app.current_tenant_id', TRUE), ''
            )::UUID
        )
        WITH CHECK (
            is_global = TRUE
            OR tenant_id = NULLIF(
                current_setting('app.current_tenant_id', TRUE), ''
            )::UUID
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
        WITH CHECK (
            is_global = TRUE
            OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
    """)
