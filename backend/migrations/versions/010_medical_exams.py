"""Lékařské prohlídky (medical exams)

Revision ID: 010
Revises: 009
Create Date: 2026-04-23

Legislativní základ:
- Zákoník práce §103 odst. 1 písm. a) – vstupní prohlídky povinné
- Zákon 373/2011 Sb. §54–58 – pracovnělékařské služby
- Vyhláška 79/2013 Sb. §11 – druhy a lhůty prohlídek

Typy prohlídek:
  vstupni    – před nástupem do práce
  periodicka – opakovaná dle kategorie práce a věku
  vystupni   – při ukončení pracovního poměru / změně práce
  mimoradna  – po úrazu, nemoci, na žádost zaměstnance

Výsledky (§ 42 vyhl. 79/2013):
  zpusobilyý            – bez omezení
  zpusobilyý_omezeni    – s podmínkami (nutno uvést v notes)
  nezpusobilyý          – práci vykonávat nemůže
  pozbyl_zpusobilosti   – ztráta způsobilosti u stávajícího zaměstnance
"""

from alembic import op

revision: str = "010"
down_revision: str = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE medical_exams (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            employee_id     UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,

            -- Volitelná vazba na pracovní pozici (pro výpočet příští prohlídky)
            job_position_id UUID REFERENCES job_positions(id) ON DELETE SET NULL,

            -- Druh prohlídky
            exam_type       VARCHAR(20) NOT NULL,
            -- hodnoty: vstupni | periodicka | vystupni | mimoradna

            CONSTRAINT ck_me_exam_type CHECK (
                exam_type IN ('vstupni', 'periodicka', 'vystupni', 'mimoradna')
            ),

            -- Datum provedení prohlídky
            exam_date       DATE NOT NULL,

            -- Výsledek prohlídky (§42 vyhl. 79/2013 Sb.)
            result          VARCHAR(30),
            -- hodnoty: zpusobilyý | zpusobilyý_omezeni | nezpusobilyý | pozbyl_zpusobilosti | NULL (čeká na výsledek)

            CONSTRAINT ck_me_result CHECK (
                result IN ('zpusobilyý', 'zpusobilyý_omezeni', 'nezpusobilyý', 'pozbyl_zpusobilosti')
                OR result IS NULL
            ),

            -- Lékař / závodní lékař
            physician_name  VARCHAR(255),

            -- Platnost prohlídky v měsících (přebírá z job_position, lze přepsat)
            valid_months    SMALLINT CHECK (valid_months > 0),

            -- Datum platnosti (computed: exam_date + valid_months, nebo ruční override)
            valid_until     DATE,

            notes           TEXT,
            status          VARCHAR(20) NOT NULL DEFAULT 'active',

            created_by      UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("CREATE INDEX idx_medical_exams_tenant ON medical_exams(tenant_id)")
    op.execute("CREATE INDEX idx_medical_exams_employee ON medical_exams(employee_id)")
    op.execute("CREATE INDEX idx_medical_exams_valid_until ON medical_exams(valid_until) WHERE valid_until IS NOT NULL")
    op.execute("ALTER TABLE medical_exams ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON medical_exams
            USING (tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID)
    """)
    op.execute("""
        CREATE POLICY superadmin_bypass ON medical_exams
            USING (current_setting('app.is_superadmin', TRUE) = 'true')
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS medical_exams CASCADE")
