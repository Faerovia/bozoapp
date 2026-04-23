"""Evidence školení BOZP/PO

Revision ID: 003
Revises: 002
Create Date: 2026-04-23

Legislativní základ:
- Zákoník práce §37, §103 odst. 2 – povinnost školit zaměstnance
- Zákon 133/1985 Sb. §16 – školení PO
- NV 495/2001 Sb. – rozsah a bližší podmínky

Datový model (flat records pro MVP):
- Každý záznam = jedno absolvování školení jedním zaměstnancem
- Platnost se odvozuje od trained_at + valid_months
- valid_months NULL = školení bez expiry (např. vstupní, jednorázové)
"""

from alembic import op

revision: str = "003"
down_revision: str = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE trainings (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

            -- Kdo byl školen
            employee_id     UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,

            -- Co bylo školení
            title           VARCHAR(255) NOT NULL,
            training_type   VARCHAR(50) NOT NULL DEFAULT 'other',
            -- hodnoty: bozp_initial | bozp_periodic | fire_protection |
            --          first_aid | equipment | other

            -- Kdy
            trained_at      DATE NOT NULL,

            -- Platnost
            valid_months    SMALLINT CHECK (valid_months > 0),
            -- NULL = bez expiry (platí trvale / do odvolání)
            valid_until     DATE,
            -- NULL buď proto že valid_months=NULL, nebo ruční override

            -- Kdo školil
            trainer_name    VARCHAR(255),

            -- Doplňující informace
            notes           TEXT,

            -- Správa záznamu
            status          VARCHAR(20) NOT NULL DEFAULT 'active',
            -- hodnoty: active | archived

            created_by      UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # Indexy pro typické dotazy
    op.execute("CREATE INDEX idx_trainings_tenant ON trainings(tenant_id)")
    op.execute("CREATE INDEX idx_trainings_employee ON trainings(tenant_id, employee_id)")
    op.execute("CREATE INDEX idx_trainings_valid_until ON trainings(tenant_id, valid_until) WHERE valid_until IS NOT NULL")
    op.execute("CREATE INDEX idx_trainings_type ON trainings(tenant_id, training_type)")

    # RLS – tenant izolace
    op.execute("ALTER TABLE trainings ENABLE ROW LEVEL SECURITY")

    op.execute("""
        CREATE POLICY tenant_isolation ON trainings
            USING (
                tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID
            )
    """)

    op.execute("""
        CREATE POLICY superadmin_bypass ON trainings
            USING (current_setting('app.is_superadmin', TRUE) = 'true')
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS trainings CASCADE")
