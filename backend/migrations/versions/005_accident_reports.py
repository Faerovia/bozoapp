"""Záznamy o pracovních úrazech

Revision ID: 005
Revises: 004
Create Date: 2026-04-23

Legislativní základ:
- Zákoník práce §105        – povinnosti zaměstnavatele při pracovních úrazech
- NV 201/2010 Sb.           – způsob evidence, hlášení a zasílání záznamu o úrazu
- Zákon 262/2006 Sb. §272   – definice těžkého pracovního úrazu

Workflow:
  draft → final → archived
  Při finalizaci: risk_review_required = TRUE (OZO musí zkontrolovat rizika)
  Final záznamy jsou immutable.
"""

from alembic import op

revision: str = "005"
down_revision: str = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE accident_reports (
            id                        UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id                 UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

            -- Zaměstnanec (FK nullable pro externy, text povinný vždy)
            employee_id               UUID REFERENCES users(id) ON DELETE SET NULL,
            employee_name             VARCHAR(255) NOT NULL,
            workplace                 VARCHAR(255) NOT NULL,

            -- Čas úrazu
            accident_date             DATE NOT NULL,
            accident_time             TIME NOT NULL,
            shift_start_time          TIME,

            -- Charakter zranění (free text – bez SÚIP kódů v MVP)
            injury_type               VARCHAR(255) NOT NULL,
            injured_body_part         VARCHAR(255) NOT NULL,
            injury_source             VARCHAR(255) NOT NULL,
            injury_cause              TEXT NOT NULL,
            injured_count             SMALLINT NOT NULL DEFAULT 1 CHECK (injured_count >= 1),
            is_fatal                  BOOLEAN NOT NULL DEFAULT FALSE,
            has_other_injuries        BOOLEAN NOT NULL DEFAULT FALSE,

            -- Popis okolností
            description               TEXT NOT NULL,

            -- Krevní patogeny
            blood_pathogen_exposure   BOOLEAN NOT NULL DEFAULT FALSE,
            blood_pathogen_persons    TEXT,   -- vyplněno jen pokud exposure=TRUE

            -- Porušené předpisy
            violated_regulations      TEXT,

            -- Testy (NULL = neproveden)
            alcohol_test_performed    BOOLEAN NOT NULL DEFAULT FALSE,
            alcohol_test_result       VARCHAR(20),   -- negative | positive | NULL
            drug_test_performed       BOOLEAN NOT NULL DEFAULT FALSE,
            drug_test_result          VARCHAR(20),   -- negative | positive | NULL

            -- Podpisy: fyzické (na papíře), zde ukládáme jméno + datum
            injured_signed_at         DATE,
            witnesses                 JSONB NOT NULL DEFAULT '[]'::jsonb,
            -- [{name: str, signed_at: date|null}]
            supervisor_name           VARCHAR(255),
            supervisor_signed_at      DATE,

            -- Vazba na registr rizik (volitelná, OZO doplní po šetření)
            risk_id                   UUID REFERENCES risks(id) ON DELETE SET NULL,

            -- Risk review workflow
            risk_review_required      BOOLEAN NOT NULL DEFAULT FALSE,
            risk_review_completed_at  TIMESTAMPTZ,

            -- Workflow
            status                    VARCHAR(20) NOT NULL DEFAULT 'draft',
            -- hodnoty: draft | final | archived

            created_by                UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("CREATE INDEX idx_accident_reports_tenant ON accident_reports(tenant_id)")
    op.execute("CREATE INDEX idx_accident_reports_status ON accident_reports(tenant_id, status)")
    op.execute("CREATE INDEX idx_accident_reports_risk_review ON accident_reports(tenant_id, risk_review_required) WHERE risk_review_required = TRUE")
    op.execute("CREATE INDEX idx_accident_reports_date ON accident_reports(tenant_id, accident_date DESC)")

    op.execute("ALTER TABLE accident_reports ENABLE ROW LEVEL SECURITY")

    op.execute("""
        CREATE POLICY tenant_isolation ON accident_reports
            USING (
                tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID
            )
    """)

    op.execute("""
        CREATE POLICY superadmin_bypass ON accident_reports
            USING (current_setting('app.is_superadmin', TRUE) = 'true')
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS accident_reports CASCADE")
