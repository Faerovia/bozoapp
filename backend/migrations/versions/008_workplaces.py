"""Pracoviště – závody, pracoviště, hodnocení rizikových faktorů

Revision ID: 008
Revises: 007
Create Date: 2026-04-23

Legislativní základ:
- Zákoník práce §102 – povinnost vyhledávat a hodnotit rizika
- NV 361/2007 Sb.  – kategorizace prací (13 standardizovaných rizikových faktorů)
- Zákon 258/2000 Sb. §37 – povinnost kategorizace prací

Hierarchie:
  tenant → plant (závod) → workplace (pracoviště)

Rizikové faktory (pevně dáno NV 361/2007):
  Prach, Chemické látky, Hluk, Vibrace, Neionizující záření a EM pole,
  Práce ve zvýšeném tlaku vzduchu, Fyzická zátěž, Pracovní poloha,
  Zátěž teplem, Zátěž chladem, Psychická zátěž, Zraková zátěž,
  Práce s biologickými činiteli

Hodnocení: 1 | 2 | 2R | 3 | 4
  2R = kategorie 2 riziková (výskyt/hrozba nemoci z povolání)
  Celková kategorie = MAX(všech faktorů)
"""

from alembic import op

revision: str = "008"
down_revision: str = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Závody (plants) ────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE plants (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

            name            VARCHAR(255) NOT NULL,
            -- Např. "závod č. 1", "IACG s.r.o., závod Přeštice"

            address         VARCHAR(255),
            city            VARCHAR(100),
            zip_code        VARCHAR(10),
            ico             VARCHAR(20),
            plant_number    VARCHAR(50),
            -- Identifikátor závodu v rámci skupiny (č. 1, č. 2, ...)

            notes           TEXT,
            status          VARCHAR(20) NOT NULL DEFAULT 'active',
            -- hodnoty: active | archived

            created_by      UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("CREATE INDEX idx_plants_tenant ON plants(tenant_id)")
    op.execute("ALTER TABLE plants ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON plants
            USING (tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID)
    """)
    op.execute("""
        CREATE POLICY superadmin_bypass ON plants
            USING (current_setting('app.is_superadmin', TRUE) = 'true')
    """)

    # ── 2. Pracoviště (workplaces) ────────────────────────────────────────────
    op.execute("""
        CREATE TABLE workplaces (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            plant_id        UUID NOT NULL REFERENCES plants(id) ON DELETE CASCADE,

            name            VARCHAR(255) NOT NULL,
            -- Např. "Odpad. hospodářství", "Základní výroba LH", "Údržba"

            notes           TEXT,
            status          VARCHAR(20) NOT NULL DEFAULT 'active',
            -- hodnoty: active | archived

            created_by      UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("CREATE INDEX idx_workplaces_tenant ON workplaces(tenant_id)")
    op.execute("CREATE INDEX idx_workplaces_plant ON workplaces(plant_id)")
    op.execute("ALTER TABLE workplaces ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON workplaces
            USING (tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID)
    """)
    op.execute("""
        CREATE POLICY superadmin_bypass ON workplaces
            USING (current_setting('app.is_superadmin', TRUE) = 'true')
    """)

    # ── 3. Hodnocení rizikových faktorů (risk_factor_assessments) ─────────────
    #
    # Každý řádek = jeden řádek v dokumentu "Seznam rizikových faktorů"
    # (kombinace pracoviště + profese s hodnoceními 13 faktorů)
    op.execute("""
        CREATE TABLE risk_factor_assessments (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            workplace_id    UUID NOT NULL REFERENCES workplaces(id) ON DELETE CASCADE,

            -- Profese (zatím text, v budoucnu FK na job_positions)
            profese         VARCHAR(255) NOT NULL,

            -- Obsluha – jména konkrétních pracovníků (volitelné)
            operator_names  TEXT,

            -- Počty pracovníků
            worker_count    SMALLINT NOT NULL DEFAULT 0 CHECK (worker_count >= 0),
            women_count     SMALLINT NOT NULL DEFAULT 0 CHECK (women_count >= 0),

            -- 13 standardizovaných rizikových faktorů (NV 361/2007)
            -- Hodnoty: '1' | '2' | '2R' | '3' | '4' | NULL (neuplatňuje se)
            rf_prach                VARCHAR(3),  -- Prach
            rf_chem                 VARCHAR(3),  -- Chemické látky
            rf_hluk                 VARCHAR(3),  -- Hluk
            rf_vibrace              VARCHAR(3),  -- Vibrace
            rf_zareni               VARCHAR(3),  -- Neionizující záření a EM pole
            rf_tlak                 VARCHAR(3),  -- Práce ve zvýšeném tlaku vzduchu
            rf_fyz_zatez            VARCHAR(3),  -- Fyzická zátěž
            rf_prac_poloha          VARCHAR(3),  -- Pracovní poloha
            rf_teplo                VARCHAR(3),  -- Zátěž teplem
            rf_chlad                VARCHAR(3),  -- Zátěž chladem
            rf_psych                VARCHAR(3),  -- Psychická zátěž
            rf_zrak                 VARCHAR(3),  -- Zraková zátěž
            rf_bio                  VARCHAR(3),  -- Práce s biologickými činiteli

            -- Navržená celková kategorie (computed nebo ruční override)
            -- NULL = automaticky z MAX faktorů
            category_override       VARCHAR(3),

            -- Pořadí v dokumentu (pro správné řazení při exportu)
            sort_order      SMALLINT NOT NULL DEFAULT 0,

            notes           TEXT,
            status          VARCHAR(20) NOT NULL DEFAULT 'active',

            created_by      UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            CONSTRAINT ck_rfa_ratings CHECK (
                rf_prach IN ('1','2','2R','3','4') OR rf_prach IS NULL
            )
        )
    """)

    op.execute("CREATE INDEX idx_rfa_tenant ON risk_factor_assessments(tenant_id)")
    op.execute("CREATE INDEX idx_rfa_workplace ON risk_factor_assessments(workplace_id)")
    op.execute("ALTER TABLE risk_factor_assessments ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON risk_factor_assessments
            USING (tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID)
    """)
    op.execute("""
        CREATE POLICY superadmin_bypass ON risk_factor_assessments
            USING (current_setting('app.is_superadmin', TRUE) = 'true')
    """)

    # ── 4. Napojení employees.workplace_id → workplaces.id ───────────────────
    op.execute("""
        ALTER TABLE employees
            ADD CONSTRAINT employees_workplace_id_fkey
            FOREIGN KEY (workplace_id) REFERENCES workplaces(id) ON DELETE SET NULL
    """)

    # ── 5. Přidání workplace_id na tabulku risks ──────────────────────────────
    op.execute("ALTER TABLE risks ADD COLUMN workplace_id UUID REFERENCES workplaces(id) ON DELETE SET NULL")
    op.execute("CREATE INDEX idx_risks_workplace ON risks(workplace_id) WHERE workplace_id IS NOT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE risks DROP COLUMN IF EXISTS workplace_id")
    op.execute("ALTER TABLE employees DROP CONSTRAINT IF EXISTS employees_workplace_id_fkey")
    op.execute("DROP TABLE IF EXISTS risk_factor_assessments CASCADE")
    op.execute("DROP TABLE IF EXISTS workplaces CASCADE")
    op.execute("DROP TABLE IF EXISTS plants CASCADE")
