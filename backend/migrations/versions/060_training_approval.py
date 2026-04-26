"""trainings — approval workflow + autor/OZO signatures

Revision ID: 060
Revises: 059
Create Date: 2026-04-26

Workflow:
- Pokud školení vytvoří OZO → status='active' rovnou, autor podepíše.
- Pokud vytvoří někdo jiný (HR manager, lead_worker) a zaškrtne
  „Nechat schválit OZO" → status='pending_approval', autor podepíše,
  školení nelze přiřazovat zaměstnancům dokud OZO neschválí. OZO pak
  podepíše také (ozo_approval_signature_id).
- Změna obsahu → opět vyžaduje podpis autora a (pokud requires_ozo_approval)
  re-approval OZO.

Přidání:
- trainings.status ('active' | 'pending_approval' | 'archived', default 'active')
- trainings.requires_ozo_approval (bool, default false)
- trainings.author_signature_id (FK signatures.id, ON DELETE SET NULL)
- trainings.ozo_approval_signature_id (FK signatures.id, ON DELETE SET NULL)
- trainings.approved_at (timestamptz, nullable)
- trainings.approved_by_user_id (FK users.id, ON DELETE SET NULL)

Rozšíření doc_type CHECK v signatures: přidání 'training_content'
(pro podpis obsahu školení autorem / OZO; existuje vedle 'training_attempt'
pro podpis absolvování zaměstnancem).
"""

from alembic import op

revision = "060"
down_revision = "059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE trainings
        ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'active'
    """)
    op.execute("""
        ALTER TABLE trainings
        ADD CONSTRAINT ck_trainings_status
        CHECK (status IN ('active', 'pending_approval', 'archived'))
    """)
    op.execute("""
        ALTER TABLE trainings
        ADD COLUMN requires_ozo_approval BOOLEAN NOT NULL DEFAULT FALSE
    """)
    op.execute("""
        ALTER TABLE trainings
        ADD COLUMN author_signature_id UUID
            REFERENCES signatures(id) ON DELETE SET NULL
    """)
    op.execute("""
        ALTER TABLE trainings
        ADD COLUMN ozo_approval_signature_id UUID
            REFERENCES signatures(id) ON DELETE SET NULL
    """)
    op.execute("""
        ALTER TABLE trainings
        ADD COLUMN approved_at TIMESTAMPTZ
    """)
    op.execute("""
        ALTER TABLE trainings
        ADD COLUMN approved_by_user_id UUID
            REFERENCES users(id) ON DELETE SET NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_trainings_pending_approval
        ON trainings (tenant_id) WHERE status = 'pending_approval'
    """)

    # Rozšíření doc_type enum v signatures table — přidat 'training_content'.
    # CHECK constraint musí být dropnut a recreatean.
    op.execute("ALTER TABLE signatures DROP CONSTRAINT ck_sig_doc_type")
    op.execute("""
        ALTER TABLE signatures
        ADD CONSTRAINT ck_sig_doc_type CHECK (
            doc_type IN (
                'oopp_issue',
                'accident_report',
                'training_attempt',
                'training_content'
            )
        )
    """)
    # Stejné pro sms_otp_codes
    op.execute("ALTER TABLE sms_otp_codes DROP CONSTRAINT ck_sms_otp_doc_type")
    op.execute("""
        ALTER TABLE sms_otp_codes
        ADD CONSTRAINT ck_sms_otp_doc_type CHECK (
            doc_type IN (
                'oopp_issue',
                'accident_report',
                'training_attempt',
                'training_content'
            )
        )
    """)


def downgrade() -> None:
    # Restore old enum constraints (without 'training_content')
    op.execute("ALTER TABLE sms_otp_codes DROP CONSTRAINT ck_sms_otp_doc_type")
    op.execute("""
        ALTER TABLE sms_otp_codes
        ADD CONSTRAINT ck_sms_otp_doc_type CHECK (
            doc_type IN ('oopp_issue', 'accident_report', 'training_attempt')
        )
    """)
    op.execute("ALTER TABLE signatures DROP CONSTRAINT ck_sig_doc_type")
    op.execute("""
        ALTER TABLE signatures
        ADD CONSTRAINT ck_sig_doc_type CHECK (
            doc_type IN ('oopp_issue', 'accident_report', 'training_attempt')
        )
    """)

    op.execute("DROP INDEX IF EXISTS ix_trainings_pending_approval")
    op.execute("ALTER TABLE trainings DROP COLUMN IF EXISTS approved_by_user_id")
    op.execute("ALTER TABLE trainings DROP COLUMN IF EXISTS approved_at")
    op.execute(
        "ALTER TABLE trainings DROP COLUMN IF EXISTS ozo_approval_signature_id"
    )
    op.execute(
        "ALTER TABLE trainings DROP COLUMN IF EXISTS author_signature_id"
    )
    op.execute(
        "ALTER TABLE trainings DROP COLUMN IF EXISTS requires_ozo_approval"
    )
    op.execute("ALTER TABLE trainings DROP CONSTRAINT IF EXISTS ck_trainings_status")
    op.execute("ALTER TABLE trainings DROP COLUMN IF EXISTS status")
