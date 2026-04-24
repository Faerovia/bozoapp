"""Revize refactor: zařízení + timeline revizí + M:N zodpovědnost za provozovny

Revision ID: 023
Revises: 022
Create Date: 2026-04-24

DESIGN:
Modul „Revize" byl monolit: 1 řádek = 1 zařízení a zároveň 1 „stav revize".
Nový model:

    Revision (≈ Zařízení)
        ├── plant_id              — provozovna (povinná, FK)
        ├── device_code           — interní ID zařízení
        ├── device_type           — striktní enum (7 hodnot)
        ├── technician_email/phone — kontakt na revizního technika
        ├── qr_token              — unikátní token pro QR polep
        ├── last_revised_at       — datum poslední provedené revize (derived z latest record)
        ├── next_revision_at      — datum další (last + valid_months)
        └── N × RevisionRecord (timeline všech provedených kontrol)
                ├── performed_at  — datum kontroly
                ├── pdf_path / image_path  — příloha (PDF nebo obrázek)
                ├── technician_name
                ├── notes
                └── created_by (kdo to do systému zadal)

Plus: employee_plant_responsibilities (M:N) — kdo je zodpovědný za vyhrazená
zařízení v jaké provozovně. Flag is_equipment_responsible je odvozený (má
alespoň jednu vazbu).

MIGRATION PATH:
Stávající data v `revisions` zachováme — přidáme nové sloupce jako NULLABLE,
pak backfill kde to jde (location→plant pokud existuje match), pak zpřísníme.
Aktuální `last_revised_at` přenásobíme do revision_records jako první záznam.
"""

from alembic import op

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Rozšíření revisions ───────────────────────────────────────────────
    op.execute("""
        ALTER TABLE revisions
            ADD COLUMN plant_id         UUID REFERENCES plants(id) ON DELETE RESTRICT,
            ADD COLUMN device_code      VARCHAR(100),
            ADD COLUMN device_type      VARCHAR(30),
            ADD COLUMN technician_name  VARCHAR(255),
            ADD COLUMN technician_email VARCHAR(255),
            ADD COLUMN technician_phone VARCHAR(50),
            ADD COLUMN qr_token         VARCHAR(64)
    """)

    # QR token vygenerujeme pro existující záznamy (unique constraint přidáme po backfillu)
    op.execute("""
        UPDATE revisions
        SET qr_token = REPLACE(uuid_generate_v4()::text, '-', '')
        WHERE qr_token IS NULL
    """)

    op.execute("ALTER TABLE revisions ALTER COLUMN qr_token SET NOT NULL")
    op.execute(
        "ALTER TABLE revisions ADD CONSTRAINT uq_revisions_qr_token UNIQUE (qr_token)"
    )

    # device_type enum CHECK (7 hodnot + legacy 'other' pro migraci stávajících)
    op.execute("""
        ALTER TABLE revisions
            ADD CONSTRAINT ck_revisions_device_type CHECK (
                device_type IS NULL OR device_type IN (
                    'elektro',
                    'hromosvody',
                    'plyn',
                    'kotle',
                    'tlakove_nadoby',
                    'vytahy',
                    'spalinove_cesty'
                )
            )
    """)

    # Migrace 004 vytvořila idx_revisions_type nad sloupcem revision_type.
    # V novém modelu je to device_type — dropneme starý index a vytvoříme
    # nový pod stejným jménem (pro zpětnou kompat se starými dotazy).
    op.execute("DROP INDEX IF EXISTS idx_revisions_type")

    # Indexy pro filtrování podle provozovny, typu a QR lookupu
    op.execute("CREATE INDEX idx_revisions_plant ON revisions(tenant_id, plant_id)")
    op.execute("CREATE INDEX idx_revisions_type ON revisions(tenant_id, device_type)")
    op.execute("CREATE INDEX idx_revisions_qr ON revisions(qr_token)")

    # ── 2. RevisionRecord — timeline provedených kontrol ─────────────────────
    op.execute("""
        CREATE TABLE revision_records (
            id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id        UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            revision_id      UUID NOT NULL REFERENCES revisions(id) ON DELETE CASCADE,

            performed_at     DATE NOT NULL,
            pdf_path         VARCHAR(500),
            image_path       VARCHAR(500),
            -- Alespoň jedno z pdf_path / image_path nebo obojí NULL (manuální záznam)

            technician_name  VARCHAR(255),
            notes            TEXT,

            created_by       UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            CONSTRAINT ck_record_attachment
                CHECK (
                    pdf_path IS NULL OR image_path IS NULL
                )
            -- Buď PDF, nebo obrázek, ne obojí najednou (v MVP zjednodušení)
        )
    """)

    op.execute("CREATE INDEX idx_rr_tenant ON revision_records(tenant_id)")
    op.execute(
        "CREATE INDEX idx_rr_revision ON revision_records(revision_id, performed_at DESC)"
    )

    op.execute("ALTER TABLE revision_records ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE revision_records FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON revision_records
            USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID)
    """)
    op.execute("""
        CREATE POLICY superadmin_bypass ON revision_records
            USING (current_setting('app.is_superadmin', TRUE) = 'true')
    """)
    op.execute("""
        CREATE POLICY platform_admin_bypass ON revision_records
            USING (current_setting('app.is_platform_admin', TRUE) = 'true')
    """)
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON revision_records TO bozoapp_app"
    )

    # ── 3. Migrace: existující revisions.last_revised_at → první revision_record ──
    op.execute("""
        INSERT INTO revision_records (
            tenant_id, revision_id, performed_at, technician_name, created_by, created_at
        )
        SELECT tenant_id, id, last_revised_at, contractor, created_by, created_at
        FROM revisions
        WHERE last_revised_at IS NOT NULL
    """)

    # ── 4. Employee ↔ Plant responsibility (M:N) ─────────────────────────────
    op.execute("""
        CREATE TABLE employee_plant_responsibilities (
            id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id     UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            employee_id   UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            plant_id      UUID NOT NULL REFERENCES plants(id) ON DELETE CASCADE,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            CONSTRAINT uq_epr_pair UNIQUE (employee_id, plant_id)
        )
    """)

    op.execute("CREATE INDEX idx_epr_employee ON employee_plant_responsibilities(employee_id)")
    op.execute("CREATE INDEX idx_epr_plant ON employee_plant_responsibilities(plant_id)")
    op.execute("CREATE INDEX idx_epr_tenant ON employee_plant_responsibilities(tenant_id)")

    op.execute(
        "ALTER TABLE employee_plant_responsibilities ENABLE ROW LEVEL SECURITY"
    )
    op.execute(
        "ALTER TABLE employee_plant_responsibilities FORCE ROW LEVEL SECURITY"
    )
    op.execute("""
        CREATE POLICY tenant_isolation ON employee_plant_responsibilities
            USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID)
    """)
    op.execute("""
        CREATE POLICY superadmin_bypass ON employee_plant_responsibilities
            USING (current_setting('app.is_superadmin', TRUE) = 'true')
    """)
    op.execute("""
        CREATE POLICY platform_admin_bypass ON employee_plant_responsibilities
            USING (current_setting('app.is_platform_admin', TRUE) = 'true')
    """)
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON employee_plant_responsibilities "
        "TO bozoapp_app"
    )

    # Backfill: každý user s role='equipment_responsible' → dostane vazbu na
    # primární provozovnu zaměstnance (pokud ji má). Ostatní plants musí admin
    # doplnit manuálně přes UI — žádný automatický globální přístup.
    op.execute("""
        INSERT INTO employee_plant_responsibilities (tenant_id, employee_id, plant_id)
        SELECT e.tenant_id, e.id, e.plant_id
        FROM employees e
        JOIN users u ON u.id = e.user_id
        WHERE u.role = 'equipment_responsible'
          AND e.plant_id IS NOT NULL
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS employee_plant_responsibilities CASCADE")
    op.execute("DROP TABLE IF EXISTS revision_records CASCADE")
    op.execute("DROP INDEX IF EXISTS idx_revisions_plant")
    op.execute("DROP INDEX IF EXISTS idx_revisions_type")
    op.execute("DROP INDEX IF EXISTS idx_revisions_qr")
    op.execute(
        "ALTER TABLE revisions DROP CONSTRAINT IF EXISTS ck_revisions_device_type"
    )
    op.execute(
        "ALTER TABLE revisions DROP CONSTRAINT IF EXISTS uq_revisions_qr_token"
    )
    op.execute("""
        ALTER TABLE revisions
            DROP COLUMN IF EXISTS plant_id,
            DROP COLUMN IF EXISTS device_code,
            DROP COLUMN IF EXISTS device_type,
            DROP COLUMN IF EXISTS technician_name,
            DROP COLUMN IF EXISTS technician_email,
            DROP COLUMN IF EXISTS technician_phone,
            DROP COLUMN IF EXISTS qr_token
    """)
