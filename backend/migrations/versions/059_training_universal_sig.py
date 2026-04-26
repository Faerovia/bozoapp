"""training_assignments — universal_signature_id link

Revision ID: 059
Revises: 058
Create Date: 2026-04-26

Univerzální digitální podpis (#104, #105) doplněn i pro školení. Stávající
flow s canvas signature_image a TrainingSignatureOTP zůstává funkční pro
backward compat — staré podpisy se nemigrují. Pro nové podpisy přes
heslo/SMS frontend volá /signatures/initiate + /signatures/verify a pak
/trainings/assignments/{id}/attach-signature.

Přidání:
- training_assignments.universal_signature_id (FK signatures.id, ON DELETE SET NULL)
- partial index pro efektivní filter „digitálně podepsaná školení"
"""

from alembic import op

revision = "059"
down_revision = "058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE training_assignments
        ADD COLUMN universal_signature_id UUID
            REFERENCES signatures(id) ON DELETE SET NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_ta_universal_signature
        ON training_assignments (universal_signature_id)
        WHERE universal_signature_id IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_ta_universal_signature")
    op.execute(
        "ALTER TABLE training_assignments "
        "DROP COLUMN IF EXISTS universal_signature_id"
    )
