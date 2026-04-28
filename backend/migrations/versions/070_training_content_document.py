"""trainings + training_assignments: content_document_id (school po změně rizik)

Revision ID: 070
Revises: 069
Create Date: 2026-04-28

Pro auto-generované školení 'Změna rizik' (singleton šablona per tenant)
přidáváme dvě FK na generated_documents:

- Training.content_document_id           — fallback content pro šablonu
                                            (pokud assignment.content_document_id je NULL)
- TrainingAssignment.content_document_id — per-zaměstnanec konkrétní dokument
                                            (jiné pracoviště → jiný dokument)

Když se změní hodnocení rizik (přidání měřítka, změna statusu na mitigated
nebo accepted), service `_assign_change_training` regeneruje GeneratedDocument
'Hodnocení rizik — <scope>' a aktualizuje všechny otevřené assignmenty
dotčených zaměstnanců, aby ukazovaly na novou verzi. Completed assignmenty
zůstávají s původním content_document_id pro audit (co konkrétně absolvoval).
"""

import sqlalchemy as sa
from alembic import op

revision = "070"
down_revision = "069"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "trainings",
        sa.Column(
            "content_document_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("generated_documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "training_assignments",
        sa.Column(
            "content_document_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("generated_documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_training_assignments_content_document",
        "training_assignments",
        ["content_document_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_training_assignments_content_document",
        table_name="training_assignments",
    )
    op.drop_column("training_assignments", "content_document_id")
    op.drop_column("trainings", "content_document_id")
