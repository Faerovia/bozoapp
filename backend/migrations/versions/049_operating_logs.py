"""Modul Provozní deníky — operating_log_devices + operating_log_entries

Revision ID: 049
Revises: 048
Create Date: 2026-04-26

Logika:
  operating_log_devices  — strojní zařízení s definovanými kontrolními body
  operating_log_entries  — denní/týdenní zápisy v deníku

Kategorie strojního zařízení (volitelné, dle přílohy):
  vzv | kotelna | tlakova_nadoba | jerab | eps | sprinklery | cov |
  diesel | regaly_sklad | vytah | stroje_riziko | other

Kontrolní body (check_items): JSONB list[str] (1-20 položek), které definuje
uživatel při založení deníku. Při zápisu (entry) se každá položka odpoví
ano/ne (capable_items[i] = bool).

Period:
  daily | weekly | monthly | shift | other (free text v notes)
"""

from alembic import op

revision = "049"
down_revision = "048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE operating_log_devices (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

            category        VARCHAR(40) NOT NULL,
            title           VARCHAR(255) NOT NULL,
            -- Identifikační kód (výrobní č., interní ID)
            device_code     VARCHAR(100),
            location        VARCHAR(255),
            plant_id        UUID REFERENCES plants(id) ON DELETE SET NULL,
            workplace_id    UUID REFERENCES workplaces(id) ON DELETE SET NULL,

            -- Pole kontrolních úkonů [str], 1-20 položek; uživatel definuje při založení.
            check_items     JSONB NOT NULL DEFAULT '[]'::jsonb,
            -- Periodicita: daily | weekly | monthly | shift | other
            period          VARCHAR(20) NOT NULL DEFAULT 'daily',
            -- Volný text upřesňující periodu (např. "1× za směnu")
            period_note     VARCHAR(255),

            notes           TEXT,
            status          VARCHAR(20) NOT NULL DEFAULT 'active',

            created_by      UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            CONSTRAINT ck_oplog_status CHECK (status IN ('active', 'archived')),
            CONSTRAINT ck_oplog_period CHECK (
                period IN ('daily', 'weekly', 'monthly', 'shift', 'other')
            )
        )
    """)
    op.execute("CREATE INDEX idx_oplog_dev_tenant ON operating_log_devices(tenant_id)")
    op.execute("CREATE INDEX idx_oplog_dev_category ON operating_log_devices(tenant_id, category)")

    op.execute("ALTER TABLE operating_log_devices ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE operating_log_devices FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON operating_log_devices
            USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID)
    """)
    op.execute("""
        CREATE POLICY superadmin_bypass ON operating_log_devices
            USING (current_setting('app.is_superadmin', TRUE) = 'true')
            WITH CHECK (current_setting('app.is_superadmin', TRUE) = 'true')
    """)
    op.execute("""
        CREATE POLICY platform_admin_bypass ON operating_log_devices
            USING (current_setting('app.is_platform_admin', TRUE) = 'true')
            WITH CHECK (current_setting('app.is_platform_admin', TRUE) = 'true')
    """)
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON operating_log_devices TO bozoapp_app"
    )

    # ── Entries ───────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE operating_log_entries (
            id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            device_id           UUID NOT NULL REFERENCES operating_log_devices(id) ON DELETE CASCADE,

            performed_at        DATE NOT NULL,
            performed_by_name   VARCHAR(255) NOT NULL,
            -- Pole bool[] paralelní k check_items v devices (capable per item).
            capable_items       JSONB NOT NULL DEFAULT '[]'::jsonb,
            -- Souhrnný "Způsobilost" — true pokud všechny items jsou capable=true.
            -- Lze přepsat manuálně (zaměstnanec může označit "nezpůsobilé"
            -- i když všechny items prošly — např. neobvyklý zvuk).
            overall_capable     BOOLEAN NOT NULL DEFAULT TRUE,
            notes               TEXT,

            created_by          UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX idx_oplog_entry_device ON operating_log_entries(device_id, performed_at DESC)")
    op.execute("CREATE INDEX idx_oplog_entry_tenant ON operating_log_entries(tenant_id, performed_at DESC)")

    op.execute("ALTER TABLE operating_log_entries ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE operating_log_entries FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON operating_log_entries
            USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID)
    """)
    op.execute("""
        CREATE POLICY superadmin_bypass ON operating_log_entries
            USING (current_setting('app.is_superadmin', TRUE) = 'true')
            WITH CHECK (current_setting('app.is_superadmin', TRUE) = 'true')
    """)
    op.execute("""
        CREATE POLICY platform_admin_bypass ON operating_log_entries
            USING (current_setting('app.is_platform_admin', TRUE) = 'true')
            WITH CHECK (current_setting('app.is_platform_admin', TRUE) = 'true')
    """)
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON operating_log_entries TO bozoapp_app"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS operating_log_entries CASCADE")
    op.execute("DROP TABLE IF EXISTS operating_log_devices CASCADE")
