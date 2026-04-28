"""generated_documents.document_type — přidá 'risk_assessment' (batch)

Revision ID: 069
Revises: 068
Create Date: 2026-04-28

Rozšíří CHECK constraint ck_doc_type o nový typ 'risk_assessment'.
Volá se z batch endpointu /documents/generate/risk-assessments-batch,
který vytvoří jeden dokument per pozice/pracoviště/provozovna se
souhrnem všech RA pro daný scope.
"""

from alembic import op

revision = "069"
down_revision = "068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE generated_documents DROP CONSTRAINT IF EXISTS ck_doc_type")
    op.execute("""
        ALTER TABLE generated_documents
        ADD CONSTRAINT ck_doc_type CHECK (
            document_type IN (
                'bozp_directive',
                'training_outline',
                'revision_schedule',
                'risk_categorization',
                'risk_assessment',
                'operating_log_summary',
                'imported'
            )
        )
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE generated_documents DROP CONSTRAINT IF EXISTS ck_doc_type")
    op.execute("""
        ALTER TABLE generated_documents
        ADD CONSTRAINT ck_doc_type CHECK (
            document_type IN (
                'bozp_directive',
                'training_outline',
                'revision_schedule',
                'risk_categorization',
                'operating_log_summary',
                'imported'
            )
        )
    """)
