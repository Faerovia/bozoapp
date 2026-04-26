"""Modul Pravidelné kontroly — sanační sady, záchytné vany, lékárničky

Revision ID: 048
Revises: 047
Create Date: 2026-04-26

Vytváří dvě tabulky analogicky k revisions/revision_records:
  periodic_checks         — záznamy o kontrolovaných položkách
  periodic_check_records  — historie provedených kontrol

check_kind enum:
  - 'sanitation_kit'   (Sanační sady — kontrola obsahu, doplnění)
  - 'spill_tray'       (Záchytné vany — kontrola integrity, čistoty)
  - 'first_aid_kit'    (Lékárničky — kontrola obsahu, expirace léčiv)

RLS: stejný pattern jako revisions — tenant_isolation USING+WITH CHECK +
superadmin/platform_admin bypass policies.
"""

from alembic import op

revision = "048"
down_revision = "047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE periodic_checks (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

            check_kind      VARCHAR(30) NOT NULL,
            title           VARCHAR(255) NOT NULL,
            location        VARCHAR(255),

            plant_id        UUID REFERENCES plants(id) ON DELETE RESTRICT,
            workplace_id    UUID REFERENCES workplaces(id) ON DELETE SET NULL,

            -- Termín kontrol
            last_checked_at  DATE,
            valid_months     SMALLINT,
            next_check_at    DATE,

            -- Zodpovědný uživatel (volitelný)
            responsible_user_id UUID REFERENCES users(id) ON DELETE SET NULL,

            notes           TEXT,
            status          VARCHAR(20) NOT NULL DEFAULT 'active',

            created_by      UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            CONSTRAINT ck_periodic_check_kind CHECK (
                check_kind IN ('sanitation_kit', 'spill_tray', 'first_aid_kit')
            ),
            CONSTRAINT ck_periodic_check_status CHECK (
                status IN ('active', 'archived')
            ),
            CONSTRAINT ck_periodic_check_valid_months CHECK (
                valid_months IS NULL OR valid_months > 0
            )
        )
    """)
    op.execute("CREATE INDEX idx_periodic_check_tenant ON periodic_checks(tenant_id)")
    op.execute("CREATE INDEX idx_periodic_check_kind ON periodic_checks(tenant_id, check_kind)")
    op.execute("CREATE INDEX idx_periodic_check_plant ON periodic_checks(plant_id)")

    op.execute("ALTER TABLE periodic_checks ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE periodic_checks FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON periodic_checks
            USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID)
    """)
    op.execute("""
        CREATE POLICY superadmin_bypass ON periodic_checks
            USING (current_setting('app.is_superadmin', TRUE) = 'true')
            WITH CHECK (current_setting('app.is_superadmin', TRUE) = 'true')
    """)
    op.execute("""
        CREATE POLICY platform_admin_bypass ON periodic_checks
            USING (current_setting('app.is_platform_admin', TRUE) = 'true')
            WITH CHECK (current_setting('app.is_platform_admin', TRUE) = 'true')
    """)
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON periodic_checks TO bozoapp_app"
    )

    # ── Records ────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE periodic_check_records (
            id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            periodic_check_id   UUID NOT NULL REFERENCES periodic_checks(id) ON DELETE CASCADE,

            performed_at        DATE NOT NULL,
            performed_by_name   VARCHAR(255),
            -- Jednoduchý výsledek: 'ok' (vše v pořádku) | 'fixed' (doplněno/opraveno) | 'issue' (zjištěn problém)
            result              VARCHAR(20) NOT NULL DEFAULT 'ok',
            notes               TEXT,
            -- Volitelná příloha — PDF protokol nebo foto.
            file_path           VARCHAR(500),

            created_by          UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            CONSTRAINT ck_periodic_record_result CHECK (
                result IN ('ok', 'fixed', 'issue')
            )
        )
    """)
    op.execute("CREATE INDEX idx_periodic_record_check ON periodic_check_records(periodic_check_id, performed_at DESC)")

    op.execute("ALTER TABLE periodic_check_records ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE periodic_check_records FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON periodic_check_records
            USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID)
    """)
    op.execute("""
        CREATE POLICY superadmin_bypass ON periodic_check_records
            USING (current_setting('app.is_superadmin', TRUE) = 'true')
            WITH CHECK (current_setting('app.is_superadmin', TRUE) = 'true')
    """)
    op.execute("""
        CREATE POLICY platform_admin_bypass ON periodic_check_records
            USING (current_setting('app.is_platform_admin', TRUE) = 'true')
            WITH CHECK (current_setting('app.is_platform_admin', TRUE) = 'true')
    """)
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON periodic_check_records TO bozoapp_app"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS periodic_check_records CASCADE")
    op.execute("DROP TABLE IF EXISTS periodic_checks CASCADE")
