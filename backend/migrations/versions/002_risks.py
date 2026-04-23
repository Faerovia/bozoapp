"""Registr rizik

Revision ID: 002
Revises: 001
Create Date: 2026-04-23

Datový model vychází z české metodiky hodnocení rizik:
- pravděpodobnost (1–5) × závažnost (1–5) = skóre rizika
- skóre 1–6:   nízké riziko (přijatelné)
- skóre 8–12:  střední riziko (sledovat)
- skóre 15–25: vysoké riziko (okamžitá opatření)

Legislativní základ: zákoník práce §102, NV 101/2005 Sb.
"""

from alembic import op

revision: str = "002"
down_revision: str = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE risks (
            id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id            UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

            -- Základní popis rizika
            title                VARCHAR(255) NOT NULL,
            description          TEXT,
            location             VARCHAR(255),   -- pracoviště / místo výskytu
            activity             VARCHAR(255),   -- činnost / proces

            -- Typ nebezpečí (česká klasifikace)
            hazard_type          VARCHAR(50) NOT NULL DEFAULT 'other',
            -- hodnoty: physical | chemical | biological | mechanical |
            --          electrical | ergonomic | psychosocial | fire | other

            -- Hodnocení PŘED opatřeními
            probability          SMALLINT NOT NULL CHECK (probability BETWEEN 1 AND 5),
            severity             SMALLINT NOT NULL CHECK (severity BETWEEN 1 AND 5),

            -- Opatření ke snížení rizika
            control_measures     TEXT,

            -- Hodnocení PO opatřeních (zbytková rizika)
            residual_probability SMALLINT CHECK (residual_probability BETWEEN 1 AND 5),
            residual_severity    SMALLINT CHECK (residual_severity BETWEEN 1 AND 5),

            -- Správa záznamu
            responsible_user_id  UUID REFERENCES users(id) ON DELETE SET NULL,
            review_date          DATE,           -- datum příští revize (pro kalendář)
            status               VARCHAR(20) NOT NULL DEFAULT 'active',
            -- hodnoty: active | archived

            created_by           UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("CREATE INDEX idx_risks_tenant_id ON risks(tenant_id)")
    op.execute("CREATE INDEX idx_risks_status ON risks(tenant_id, status)")
    op.execute("CREATE INDEX idx_risks_review_date ON risks(tenant_id, review_date) WHERE review_date IS NOT NULL")

    # RLS – tenant izolace
    op.execute("ALTER TABLE risks ENABLE ROW LEVEL SECURITY")

    op.execute("""
        CREATE POLICY tenant_isolation ON risks
            USING (
                tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID
            )
    """)

    op.execute("""
        CREATE POLICY superadmin_bypass ON risks
            USING (current_setting('app.is_superadmin', TRUE) = 'true')
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS risks CASCADE")
