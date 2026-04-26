"""generated_documents.document_type — přidá 'operating_log_summary'

Revision ID: 053
Revises: 052
Create Date: 2026-04-26
"""

from alembic import op

revision = "053"
down_revision = "052"
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
                'imported'
            )
        )
    """)
