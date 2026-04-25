"""OOPP refactor: risk grid (NV 390/2021) + per-position OOPP items + employee issues

Revision ID: 025
Revises: 024
Create Date: 2026-04-25

DESIGN:
Modul OOPP přechází ze "ploché" tabulky výdejů k struktuře vázané na
pracovní pozici a vyhodnocení rizik dle NV 390/2021 Sb. Příloha č. 2:

  JobPosition (pozice)
    ├── PositionRiskGrid (1:1) — matrix 14 částí těla × 26 typů rizik
    ├── PositionOoppItem (N) — pro každou body part libovolný počet
    │     OOPP s textovým názvem + periodou výdeje
    └── EmployeeOoppIssue (N přes OoppItem) — záznam vydání zaměstnanci
          s last_issued_at, valid_until, quantity, size

Existující data v `oopp_assignments` byla v rámci MVP testovací — drop.

MIGRATION PATH:
1. DROP TABLE oopp_assignments (CASCADE — odstraní indexy a RLS).
2. CREATE position_risk_grids — JSONB pole `grid` ukládá { "<body_part>": [<risk_col>...] }
3. CREATE position_oopp_items
4. CREATE employee_oopp_issues
"""

from alembic import op

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Drop staré OOPP tabulky ───────────────────────────────────────────
    op.execute("DROP TABLE IF EXISTS oopp_assignments CASCADE")

    # ── 2. PositionRiskGrid — matrix per pozice (NV 390/2021 příloha č. 2) ─
    op.execute("""
        CREATE TABLE position_risk_grids (
            id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id        UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            job_position_id  UUID NOT NULL REFERENCES job_positions(id) ON DELETE CASCADE,

            -- JSONB struktura: { "A": [1, 2, 6], "G": [1, 6], ... }
            -- Klíč = body_part (A-N), hodnota = list zaškrtnutých sloupců (1-26)
            grid             JSONB NOT NULL DEFAULT '{}'::jsonb,

            created_by       UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            CONSTRAINT uq_prg_position UNIQUE (job_position_id)
        )
    """)
    op.execute("CREATE INDEX idx_prg_tenant ON position_risk_grids(tenant_id)")
    op.execute("CREATE INDEX idx_prg_grid ON position_risk_grids USING gin(grid)")

    op.execute("ALTER TABLE position_risk_grids ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE position_risk_grids FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON position_risk_grids
            USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID)
    """)
    op.execute("""
        CREATE POLICY superadmin_bypass ON position_risk_grids
            USING (current_setting('app.is_superadmin', TRUE) = 'true')
    """)
    op.execute("""
        CREATE POLICY platform_admin_bypass ON position_risk_grids
            USING (current_setting('app.is_platform_admin', TRUE) = 'true')
    """)
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON position_risk_grids TO bozoapp_app"
    )

    # ── 3. PositionOoppItem — co všechno je pozice povinná dostat ──────────
    op.execute("""
        CREATE TABLE position_oopp_items (
            id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id        UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            job_position_id  UUID NOT NULL REFERENCES job_positions(id) ON DELETE CASCADE,

            -- Část těla (A-N dle BODY_PARTS), jednoznačný key z přílohy
            body_part        VARCHAR(2) NOT NULL,
            -- Volný textový název OOPP (např. "Pracovní rukavice odolné proti řezu")
            name             VARCHAR(255) NOT NULL,
            -- Perioda výdeje v měsících (např. 12 = každoroční výměna)
            valid_months     SMALLINT,

            notes            TEXT,
            status           VARCHAR(20) NOT NULL DEFAULT 'active',
            created_by       UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            CONSTRAINT ck_poi_body_part CHECK (
                body_part IN ('A','B','C','D','E','F','G','H','I','J','K','L','M','N')
            ),
            CONSTRAINT ck_poi_valid_months CHECK (
                valid_months IS NULL OR valid_months > 0
            )
        )
    """)
    op.execute("CREATE INDEX idx_poi_tenant ON position_oopp_items(tenant_id)")
    op.execute("CREATE INDEX idx_poi_position ON position_oopp_items(job_position_id)")
    op.execute(
        "CREATE INDEX idx_poi_position_body ON position_oopp_items(job_position_id, body_part)"
    )

    op.execute("ALTER TABLE position_oopp_items ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE position_oopp_items FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON position_oopp_items
            USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID)
    """)
    op.execute("""
        CREATE POLICY superadmin_bypass ON position_oopp_items
            USING (current_setting('app.is_superadmin', TRUE) = 'true')
    """)
    op.execute("""
        CREATE POLICY platform_admin_bypass ON position_oopp_items
            USING (current_setting('app.is_platform_admin', TRUE) = 'true')
    """)
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON position_oopp_items TO bozoapp_app"
    )

    # ── 4. EmployeeOoppIssue — záznam výdeje OOPP zaměstnanci ──────────────
    op.execute("""
        CREATE TABLE employee_oopp_issues (
            id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id               UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            employee_id             UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            position_oopp_item_id   UUID NOT NULL REFERENCES position_oopp_items(id) ON DELETE CASCADE,

            issued_at               DATE NOT NULL,
            valid_until             DATE,
            quantity                SMALLINT NOT NULL DEFAULT 1,
            size_spec               VARCHAR(50),
            serial_number           VARCHAR(100),

            notes                   TEXT,
            -- active = vydáno, returned = vráceno, discarded = vyřazeno
            status                  VARCHAR(20) NOT NULL DEFAULT 'active',

            created_by              UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            CONSTRAINT ck_eoi_status CHECK (
                status IN ('active', 'returned', 'discarded')
            ),
            CONSTRAINT ck_eoi_quantity CHECK (quantity > 0)
        )
    """)
    op.execute("CREATE INDEX idx_eoi_tenant ON employee_oopp_issues(tenant_id)")
    op.execute("CREATE INDEX idx_eoi_employee ON employee_oopp_issues(employee_id)")
    op.execute("CREATE INDEX idx_eoi_item ON employee_oopp_issues(position_oopp_item_id)")
    op.execute(
        "CREATE INDEX idx_eoi_valid_until ON employee_oopp_issues(tenant_id, valid_until) "
        "WHERE valid_until IS NOT NULL"
    )

    op.execute("ALTER TABLE employee_oopp_issues ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE employee_oopp_issues FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON employee_oopp_issues
            USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID)
    """)
    op.execute("""
        CREATE POLICY superadmin_bypass ON employee_oopp_issues
            USING (current_setting('app.is_superadmin', TRUE) = 'true')
    """)
    op.execute("""
        CREATE POLICY platform_admin_bypass ON employee_oopp_issues
            USING (current_setting('app.is_platform_admin', TRUE) = 'true')
    """)
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON employee_oopp_issues TO bozoapp_app"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS employee_oopp_issues CASCADE")
    op.execute("DROP TABLE IF EXISTS position_oopp_items CASCADE")
    op.execute("DROP TABLE IF EXISTS position_risk_grids CASCADE")
    # oopp_assignments se nevrací — staré schéma už nepoužíváme
