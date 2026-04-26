"""Training signatures + outline + ZES (kvalifikovaný el. podpis volitelně)

Revision ID: 041
Revises: 040
Create Date: 2026-04-26

DESIGN:
- Training: outline_text (osnova školení), duration_hours, requires_qes,
  knowledge_test_required (zda znalosti ověřeny testem — pro prezenčku)
- TrainingAssignment: signature_image (base64 PNG canvas), signed_at,
  signature_method (simple|qes), signature_meta JSONB (IP, user agent,
  OTP timestamp pro ZES, server-side timestamp)

Validní podpis = signature_image NOT NULL AND signed_at NOT NULL.
Pokud requires_qes=true, signature_method MUSÍ být 'qes' (verifikováno
v service vrstvě před uložením).
"""

from alembic import op

revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE trainings
            ADD COLUMN outline_text TEXT,
            ADD COLUMN duration_hours NUMERIC(4, 1),
            ADD COLUMN requires_qes BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN knowledge_test_required BOOLEAN NOT NULL DEFAULT FALSE
    """)

    op.execute("""
        ALTER TABLE training_assignments
            ADD COLUMN signature_image TEXT,
            ADD COLUMN signed_at TIMESTAMPTZ,
            ADD COLUMN signature_method VARCHAR(10),
            ADD COLUMN signature_meta JSONB,
            ADD CONSTRAINT ck_training_assignment_signature_method CHECK (
                signature_method IS NULL
                OR signature_method IN ('simple', 'qes')
            )
    """)

    # OTP table pro ZES — ephemeral (lifetime ~10 min), oddělená od auth OTP.
    op.execute("""
        CREATE TABLE training_signature_otps (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            assignment_id UUID NOT NULL REFERENCES training_assignments(id) ON DELETE CASCADE,
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            code_hash   VARCHAR(255) NOT NULL,
            sent_to     VARCHAR(255) NOT NULL,  -- email nebo phone
            channel     VARCHAR(10) NOT NULL DEFAULT 'email',
            attempts    INTEGER NOT NULL DEFAULT 0,
            verified_at TIMESTAMPTZ,
            expires_at  TIMESTAMPTZ NOT NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_training_otp_channel CHECK (channel IN ('email', 'sms'))
        )
    """)
    op.execute("""
        CREATE INDEX idx_training_otp_assignment
        ON training_signature_otps (assignment_id, created_at DESC)
    """)

    # RLS na training_signature_otps — multi-tenant
    op.execute("ALTER TABLE training_signature_otps ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE training_signature_otps FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON training_signature_otps
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
    op.execute("""
        CREATE POLICY superadmin_bypass ON training_signature_otps
        USING (current_setting('app.is_superadmin', TRUE) = 'true')
        WITH CHECK (current_setting('app.is_superadmin', TRUE) = 'true')
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS superadmin_bypass ON training_signature_otps")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON training_signature_otps")
    op.execute("DROP TABLE IF EXISTS training_signature_otps CASCADE")

    op.execute("""
        ALTER TABLE training_assignments
            DROP CONSTRAINT IF EXISTS ck_training_assignment_signature_method,
            DROP COLUMN IF EXISTS signature_meta,
            DROP COLUMN IF EXISTS signature_method,
            DROP COLUMN IF EXISTS signed_at,
            DROP COLUMN IF EXISTS signature_image
    """)

    op.execute("""
        ALTER TABLE trainings
            DROP COLUMN IF EXISTS knowledge_test_required,
            DROP COLUMN IF EXISTS requires_qes,
            DROP COLUMN IF EXISTS duration_hours,
            DROP COLUMN IF EXISTS outline_text
    """)
