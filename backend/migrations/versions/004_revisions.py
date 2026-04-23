"""Kalendář revizí zařízení

Revision ID: 004
Revises: 003
Create Date: 2026-04-23

Legislativní základ (vybrané příklady zákonných lhůt):
- Vyhláška 50/1978 Sb. + NV 194/2022 Sb. – elektrorevize (1–5 let dle prostředí)
- Zákon 22/1997 Sb. + NV 26/2003 Sb.    – tlakové nádoby (roční/dvouletý/pětiletý cyklus)
- Vyhláška 246/2001 Sb. §7              – hasicí přístroje (1 rok)
- NV 378/2001 Sb.                        – zdvihací zařízení (roční odborná prohlídka)
- ČSN EN 131                             – žebříky (dle rizika, typicky 1 rok)

Tabulka revisions slouží pro standalone záznamy o revizích zařízení a
ostatních zákonných lhůtách které nejsou přímo vázány na rizika nebo školení.

Agregovaný pohled (endpoint /calendar) sbírá termíny z:
  revisions.next_revision_at + risks.review_date + trainings.valid_until
"""

from alembic import op

revision: str = "004"
down_revision: str = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE revisions (
            id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

            -- Co je revidováno
            title               VARCHAR(255) NOT NULL,
            revision_type       VARCHAR(50) NOT NULL DEFAULT 'other',
            -- hodnoty: electrical | pressure_vessel | fire_equipment | gas |
            --          lifting_equipment | ladder | other

            location            VARCHAR(255),   -- umístění zařízení

            -- Kdy bylo naposled revidováno
            last_revised_at     DATE,

            -- Platnost a plánovaný termín příští revize
            valid_months        SMALLINT CHECK (valid_months > 0),
            next_revision_at    DATE,
            -- NULL = termín nezadán (jen archivní záznam)

            -- Kdo provedl / kdo je zodpovědný
            contractor          VARCHAR(255),   -- firma/osoba která prováděla revizi
            responsible_user_id UUID REFERENCES users(id) ON DELETE SET NULL,

            notes               TEXT,

            -- Správa záznamu
            status              VARCHAR(20) NOT NULL DEFAULT 'active',
            -- hodnoty: active | archived

            created_by          UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("CREATE INDEX idx_revisions_tenant ON revisions(tenant_id)")
    op.execute("CREATE INDEX idx_revisions_next ON revisions(tenant_id, next_revision_at) WHERE next_revision_at IS NOT NULL")
    op.execute("CREATE INDEX idx_revisions_type ON revisions(tenant_id, revision_type)")

    op.execute("ALTER TABLE revisions ENABLE ROW LEVEL SECURITY")

    op.execute("""
        CREATE POLICY tenant_isolation ON revisions
            USING (
                tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID
            )
    """)

    op.execute("""
        CREATE POLICY superadmin_bypass ON revisions
            USING (current_setting('app.is_superadmin', TRUE) = 'true')
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS revisions CASCADE")
