"""Document folders: hierarchy + folder_id na generated_documents

Revision ID: 032
Revises: 031
Create Date: 2026-04-25

DESIGN:
Adresářová struktura pro provozní/procesní dokumentaci:

  document_folders
    - parent_id          self-FK (NULL = root level)
    - code               full path "000" / "000.001" / "000.001.005"
    - name               lidsky čitelný název
    - domain             "bozp" | "po"
    - sort_order         pro UI řazení v rámci stejného parenta

Číslování je automatické: při vytvoření nové složky se najde nejvyšší
code prefix v parent (nebo root) a inkrementuje se. Code obsahuje plnou
cestu, takže přejmenování parent neovlivní podsložky.

generated_documents.folder_id (nullable) — dokumenty mohou být přiřazeny
do složky, nebo zůstat na "kořeni" (legacy záznamy zůstanou s NULL).
"""

from alembic import op

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE document_folders (
            id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            parent_id   UUID REFERENCES document_folders(id) ON DELETE RESTRICT,
            code        VARCHAR(50) NOT NULL,
            name        VARCHAR(255) NOT NULL,
            domain      VARCHAR(10) NOT NULL,
            sort_order  SMALLINT NOT NULL DEFAULT 0,
            created_by  UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_df_domain CHECK (domain IN ('bozp', 'po')),
            CONSTRAINT uq_df_tenant_code UNIQUE (tenant_id, code, domain)
        )
    """)
    op.execute("""
        CREATE INDEX idx_document_folders_parent ON document_folders (parent_id)
    """)
    op.execute("""
        CREATE INDEX idx_document_folders_tenant_domain
        ON document_folders (tenant_id, domain)
    """)

    # RLS izolace tenantů
    op.execute("ALTER TABLE document_folders ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE document_folders FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON document_folders
        USING (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
    """)

    # Vazba na generated_documents (nullable — root úroveň)
    op.execute("""
        ALTER TABLE generated_documents
            ADD COLUMN folder_id UUID
                REFERENCES document_folders(id) ON DELETE SET NULL
    """)
    op.execute("""
        CREATE INDEX idx_generated_documents_folder
        ON generated_documents (folder_id)
    """)

    # Rozšíření document_type CHECK o 'imported'
    op.execute("ALTER TABLE generated_documents DROP CONSTRAINT IF EXISTS ck_doc_type")
    op.execute("""
        ALTER TABLE generated_documents
            ADD CONSTRAINT ck_doc_type
            CHECK (document_type IN (
                'bozp_directive', 'training_outline',
                'revision_schedule', 'risk_categorization',
                'imported'
            ))
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_generated_documents_folder")
    op.execute("ALTER TABLE generated_documents DROP COLUMN IF EXISTS folder_id")
    op.execute("DROP INDEX IF EXISTS idx_document_folders_tenant_domain")
    op.execute("DROP INDEX IF EXISTS idx_document_folders_parent")
    op.execute("DROP TABLE IF EXISTS document_folders")
