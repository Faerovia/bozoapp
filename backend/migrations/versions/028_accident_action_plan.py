"""Pracovní úrazy: action plan + photos

Revision ID: 028
Revises: 027
Create Date: 2026-04-25

DESIGN:
Po nahlášení pracovního úrazu (status="final" nebo již "draft") se vytvoří
„živý dokument" Akční plán:

  AccidentActionItem (N per AccidentReport)
    - title         (např. "Revize a případná změna rizik")
    - description   (manuální popis protiopatření)
    - status        pending | in_progress | done | cancelled
    - due_date      cílový termín
    - assigned_to   FK na User (volitelné)
    - completed_at  datetime kdy bylo done
    - is_default    True pro auto-vytvořený řádek "Revize a případná změna rizik"
    - sort_order    pro UI řazení

K úrazu lze nahrát max 2 fotky:

  AccidentPhoto (max 2 per AccidentReport)
    - photo_path    relativní cesta v UPLOAD_DIR
    - caption       volitelný popisek
"""

from alembic import op

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Action plan items ────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE accident_action_items (
            id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            accident_report_id  UUID NOT NULL REFERENCES accident_reports(id) ON DELETE CASCADE,

            title               VARCHAR(255) NOT NULL,
            description         TEXT,

            status              VARCHAR(20) NOT NULL DEFAULT 'pending',
            due_date            DATE,
            assigned_to         UUID REFERENCES users(id) ON DELETE SET NULL,
            completed_at        TIMESTAMPTZ,

            -- True pro automaticky vytvořený výchozí řádek
            -- "Revize a případná změna rizik". Nelze smazat (může být done).
            is_default          BOOLEAN NOT NULL DEFAULT FALSE,
            sort_order          SMALLINT NOT NULL DEFAULT 0,

            created_by          UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            CONSTRAINT ck_aai_status CHECK (
                status IN ('pending', 'in_progress', 'done', 'cancelled')
            )
        )
    """)
    op.execute("CREATE INDEX idx_aai_tenant ON accident_action_items(tenant_id)")
    op.execute(
        "CREATE INDEX idx_aai_report ON accident_action_items(accident_report_id, sort_order)"
    )

    op.execute("ALTER TABLE accident_action_items ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE accident_action_items FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON accident_action_items
            USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID)
    """)
    op.execute("""
        CREATE POLICY superadmin_bypass ON accident_action_items
            USING (current_setting('app.is_superadmin', TRUE) = 'true')
    """)
    op.execute("""
        CREATE POLICY platform_admin_bypass ON accident_action_items
            USING (current_setting('app.is_platform_admin', TRUE) = 'true')
    """)
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON accident_action_items TO bozoapp_app"
    )

    # ── Photos (max 2 per účaz, vynuceno aplikací — DB CHECK by vyžadoval trigger) ──
    op.execute("""
        CREATE TABLE accident_photos (
            id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            accident_report_id  UUID NOT NULL REFERENCES accident_reports(id) ON DELETE CASCADE,

            photo_path          VARCHAR(500) NOT NULL,
            caption             VARCHAR(255),

            created_by          UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX idx_aph_report ON accident_photos(accident_report_id)"
    )
    op.execute("CREATE INDEX idx_aph_tenant ON accident_photos(tenant_id)")

    op.execute("ALTER TABLE accident_photos ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE accident_photos FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON accident_photos
            USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID)
    """)
    op.execute("""
        CREATE POLICY superadmin_bypass ON accident_photos
            USING (current_setting('app.is_superadmin', TRUE) = 'true')
    """)
    op.execute("""
        CREATE POLICY platform_admin_bypass ON accident_photos
            USING (current_setting('app.is_platform_admin', TRUE) = 'true')
    """)
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON accident_photos TO bozoapp_app"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS accident_photos CASCADE")
    op.execute("DROP TABLE IF EXISTS accident_action_items CASCADE")
