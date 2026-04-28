"""signatures.auth_method — přidá 'handwritten' (canvas)

Revision ID: 071
Revises: 070
Create Date: 2026-04-28

Rozšíří CHECK constraint ck_sig_auth_method o 'handwritten'. Canvas PNG
podpis se ukládá do auth_proof.signature_image_b64 a je součást payload
hashe v hash chainu — tampering by zlomil chain_hash.
"""

from alembic import op

revision = "071"
down_revision = "070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE signatures DROP CONSTRAINT IF EXISTS ck_sig_auth_method",
    )
    op.execute("""
        ALTER TABLE signatures
        ADD CONSTRAINT ck_sig_auth_method CHECK (
            auth_method IN ('password', 'sms_otp', 'handwritten')
        )
    """)


def downgrade() -> None:
    op.execute(
        "ALTER TABLE signatures DROP CONSTRAINT IF EXISTS ck_sig_auth_method",
    )
    op.execute("""
        ALTER TABLE signatures
        ADD CONSTRAINT ck_sig_auth_method CHECK (
            auth_method IN ('password', 'sms_otp')
        )
    """)
