"""Generator BOZP/PO dokumentů — tabulka generated_documents

Revision ID: 027
Revises: 026
Create Date: 2026-04-25

Tabulka uchovává všechny vygenerované dokumenty (Směrnice BOZP, Osnovy
školení, Harmonogramy, atd.) s Markdown obsahem a metadaty.

document_type enum:
- bozp_directive          (AI: směrnice BOZP firmy)
- training_outline        (AI: osnova školení BOZP per pozice)
- revision_schedule       (data: harmonogram revizí — bez AI)
- risk_categorization     (data: tabulka kategorie rizik per pozice — bez AI)
"""

from alembic import op

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE generated_documents (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

            document_type   VARCHAR(40) NOT NULL,
            title           VARCHAR(255) NOT NULL,
            -- Markdown obsah dokumentu (editovatelný uživatelem)
            content_md      TEXT NOT NULL,
            -- JSON s parametry generování (např. {"position_id": "..."}). Pro regen.
            params          JSONB NOT NULL DEFAULT '{}'::jsonb,

            -- AI metadata (počet input/output tokenů; pro fair-use limit)
            ai_input_tokens   INTEGER,
            ai_output_tokens  INTEGER,

            created_by      UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            CONSTRAINT ck_doc_type CHECK (
                document_type IN (
                    'bozp_directive',
                    'training_outline',
                    'revision_schedule',
                    'risk_categorization'
                )
            )
        )
    """)
    op.execute("CREATE INDEX idx_doc_tenant ON generated_documents(tenant_id)")
    op.execute(
        "CREATE INDEX idx_doc_type ON generated_documents(tenant_id, document_type)"
    )

    op.execute("ALTER TABLE generated_documents ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE generated_documents FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON generated_documents
            USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID)
    """)
    op.execute("""
        CREATE POLICY superadmin_bypass ON generated_documents
            USING (current_setting('app.is_superadmin', TRUE) = 'true')
    """)
    op.execute("""
        CREATE POLICY platform_admin_bypass ON generated_documents
            USING (current_setting('app.is_platform_admin', TRUE) = 'true')
    """)
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON generated_documents TO bozoapp_app"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS generated_documents CASCADE")
