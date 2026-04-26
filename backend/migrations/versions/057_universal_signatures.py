"""universal signature infrastructure (OOPP + accident + trainings)

Revision ID: 057
Revises: 056
Create Date: 2026-04-26

Tabulky:
- signatures           — append-only log s hash chain (tamper-evidence)
- signature_anchors    — denní RFC 3161 TSA kotvy (přes cron)
- sms_otp_codes        — OTP kódy pro autentizaci podpisu

FK rozšíření:
- employee_oopp_issues.signature_id → 1:1 s podpisem
- accident_reports.signature_required (bool) — false pokud je v záznamu externí

Doc types pro signatures.doc_type:
- 'oopp_issue'
- 'accident_report'
- 'training_attempt' (pro budoucí přechod školení na univerzální systém)
"""

from alembic import op

revision = "057"
down_revision = "056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # signatures — append-only s hash chain.
    # seq je BIGSERIAL napříč všemi tenanty (globální chain).
    # Per-tenant chain by byl bezpečnější (kompromitace 1 tenant nevadí
    # jiným), ale globální je jednodušší pro TSA kotvení a verifikaci.
    op.execute("""
        CREATE TABLE signatures (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
            doc_type VARCHAR(50) NOT NULL,
            doc_id UUID NOT NULL,
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE RESTRICT,
            employee_full_name_snapshot VARCHAR(255) NOT NULL,
            payload_canonical JSONB NOT NULL,
            payload_hash CHAR(64) NOT NULL,
            auth_method VARCHAR(20) NOT NULL,
            auth_proof JSONB NOT NULL DEFAULT '{}'::jsonb,
            seq BIGSERIAL NOT NULL UNIQUE,
            prev_hash CHAR(64) NOT NULL,
            chain_hash CHAR(64) NOT NULL,
            signed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_sig_doc_type CHECK (
                doc_type IN ('oopp_issue', 'accident_report', 'training_attempt')
            ),
            CONSTRAINT ck_sig_auth_method CHECK (
                auth_method IN ('password', 'sms_otp')
            )
        )
    """)
    op.execute("""
        CREATE INDEX ix_signatures_doc ON signatures (doc_type, doc_id)
    """)
    op.execute("""
        CREATE INDEX ix_signatures_tenant ON signatures (tenant_id, signed_at)
    """)
    op.execute("""
        CREATE INDEX ix_signatures_employee ON signatures (employee_id)
    """)

    # Tamper-evidence pojistka: zákaz UPDATE/DELETE na signatures.
    # Append-only enforcement na DB úrovni (lze obejít jen DROP TRIGGER).
    op.execute("""
        CREATE OR REPLACE FUNCTION signatures_no_update_delete()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'signatures je append-only (TG_OP=%)', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_signatures_immutable
        BEFORE UPDATE OR DELETE ON signatures
        FOR EACH ROW EXECUTE FUNCTION signatures_no_update_delete()
    """)

    # signature_anchors — denní TSA kotvy. Cross-tenant (jeden anchor per den).
    op.execute("""
        CREATE TABLE signature_anchors (
            id UUID PRIMARY KEY,
            anchored_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seq BIGINT NOT NULL,
            last_chain_hash CHAR(64) NOT NULL,
            tsa_provider VARCHAR(50) NOT NULL,
            tsa_token BYTEA NOT NULL,
            tsa_serial VARCHAR(100),
            CONSTRAINT ck_anchor_provider CHECK (
                tsa_provider IN ('freetsa', 'postsignum', 'ica', 'mock')
            )
        )
    """)
    op.execute("""
        CREATE INDEX ix_anchors_seq ON signature_anchors (last_seq)
    """)

    # sms_otp_codes — OTP pro auth_method='sms_otp'.
    # 6 číslic, TTL 5 min, max 3 attempts.
    op.execute("""
        CREATE TABLE sms_otp_codes (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            doc_type VARCHAR(50) NOT NULL,
            doc_id UUID NOT NULL,
            code_hash VARCHAR(255) NOT NULL,
            sent_to VARCHAR(50) NOT NULL,
            attempts SMALLINT NOT NULL DEFAULT 0,
            verified_at TIMESTAMPTZ,
            expires_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_sms_otp_doc_type CHECK (
                doc_type IN ('oopp_issue', 'accident_report', 'training_attempt')
            )
        )
    """)
    op.execute("""
        CREATE INDEX ix_sms_otp_pending
        ON sms_otp_codes (employee_id, doc_type, doc_id)
        WHERE verified_at IS NULL
    """)

    # FK z employee_oopp_issues na signature
    op.execute("""
        ALTER TABLE employee_oopp_issues
        ADD COLUMN signature_id UUID REFERENCES signatures(id) ON DELETE SET NULL
    """)
    op.execute("""
        CREATE INDEX ix_eoi_signature ON employee_oopp_issues (signature_id)
        WHERE signature_id IS NOT NULL
    """)

    # accident_reports.signature_required — false pokud je v záznamu externí
    op.execute("""
        ALTER TABLE accident_reports
        ADD COLUMN signature_required BOOLEAN NOT NULL DEFAULT TRUE
    """)
    # accident_reports.required_signer_employee_ids — pole employee IDs,
    # kteří musí podepsat (postižený + svědci + vedoucí). Pokud někdo není
    # interní, tady NEBUDE a signature_required = FALSE.
    op.execute("""
        ALTER TABLE accident_reports
        ADD COLUMN required_signer_employee_ids JSONB NOT NULL DEFAULT '[]'::jsonb
    """)


def downgrade() -> None:
    op.execute(
        "ALTER TABLE accident_reports "
        "DROP COLUMN IF EXISTS required_signer_employee_ids"
    )
    op.execute(
        "ALTER TABLE accident_reports DROP COLUMN IF EXISTS signature_required"
    )
    op.execute("DROP INDEX IF EXISTS ix_eoi_signature")
    op.execute(
        "ALTER TABLE employee_oopp_issues DROP COLUMN IF EXISTS signature_id"
    )
    op.execute("DROP TABLE IF EXISTS sms_otp_codes")
    op.execute("DROP TABLE IF EXISTS signature_anchors")
    op.execute("DROP TRIGGER IF EXISTS trg_signatures_immutable ON signatures")
    op.execute("DROP FUNCTION IF EXISTS signatures_no_update_delete()")
    op.execute("DROP TABLE IF EXISTS signatures")
