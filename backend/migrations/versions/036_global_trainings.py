"""Global trainings: marketplace školení vytvořených platform adminem

Revision ID: 036
Revises: 035
Create Date: 2026-04-25

DESIGN:
Platform admin může vytvářet globální školení (is_global=true, tenant_id=NULL).
Tenanti je vidí na marketplace a mohou je „aktivovat" — vytvoří se kopie
do tenantu (is_global=false, tenant_id=jejich) která se pak chová jako běžné
tenant školení (přiřazení zaměstnancům, validity, atd.).
"""

from alembic import op

revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Změň tenant_id na nullable + přidej is_global
    op.execute("""
        ALTER TABLE trainings
            ALTER COLUMN tenant_id DROP NOT NULL,
            ADD COLUMN is_global BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN global_source_id UUID
                REFERENCES trainings(id) ON DELETE SET NULL
    """)
    # Constraint: globální školení nesmí mít tenant_id; tenant školení musí mít
    op.execute("""
        ALTER TABLE trainings
            ADD CONSTRAINT ck_training_global_consistency
            CHECK (
                (is_global = TRUE AND tenant_id IS NULL)
                OR (is_global = FALSE AND tenant_id IS NOT NULL)
            )
    """)
    op.execute("""
        CREATE INDEX idx_trainings_is_global
        ON trainings (is_global)
        WHERE is_global = TRUE
    """)
    # RLS na trainings je třeba upravit aby globální záznamy byly viditelné všem
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
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
    """)
    op.execute("DROP INDEX IF EXISTS idx_trainings_is_global")
    op.execute("""
        ALTER TABLE trainings
            DROP CONSTRAINT IF EXISTS ck_training_global_consistency,
            DROP COLUMN IF EXISTS global_source_id,
            DROP COLUMN IF EXISTS is_global,
            ALTER COLUMN tenant_id SET NOT NULL
    """)
