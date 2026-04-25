"""User M:N tenant memberships (OZO multi-client) + tenant.external_login_enabled

Revision ID: 026
Revises: 025
Create Date: 2026-04-25

DESIGN:
OZO (poradce BOZP) si přivede více klientů. Každý klient = vlastní tenant
(s vlastními daty, izolovanými RLS). Aby se OZO nemusel logovat zvlášť do
každého, zavádíme M:N memberships:

    User ──< UserTenantMembership >── Tenant
                  ├── role (per-tenant; OZO může být v jednom tenantu
                  │   "ozo" a v jiném "hr_manager")
                  └── is_default (po loginu se vybere tento)

User.tenant_id zůstává jako "primární" tenant pro zpětnou kompat;
backfill vytvoří 1 membership per existing user.

Tenant.external_login_enabled = klient si může vytvořit vlastní logins
(pokud True, OZO + HR/employees klienta sdílí tenant). Pokud False,
tenant je OZO-only a klient se neloguje (OZO všechno spravuje za něj).

JWT po loginu obsahuje VYBRANÝ tenant_id (z memberships). Přepínání
přes POST /auth/select-tenant.
"""

from alembic import op

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Tenants: external_login_enabled ─────────────────────────────────────
    op.execute("""
        ALTER TABLE tenants
            ADD COLUMN external_login_enabled BOOLEAN NOT NULL DEFAULT FALSE
    """)

    # ── UserTenantMembership ─────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE user_tenant_memberships (
            id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            tenant_id    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            role         VARCHAR(50) NOT NULL,
            -- True = po loginu se preselectuje. Maximálně 1 per user
            -- (vynuceno parciálním unique indexem níž).
            is_default   BOOLEAN NOT NULL DEFAULT FALSE,

            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            CONSTRAINT uq_utm_pair UNIQUE (user_id, tenant_id)
        )
    """)
    op.execute("CREATE INDEX idx_utm_user ON user_tenant_memberships(user_id)")
    op.execute("CREATE INDEX idx_utm_tenant ON user_tenant_memberships(tenant_id)")
    op.execute("""
        CREATE UNIQUE INDEX uq_utm_default_per_user
            ON user_tenant_memberships(user_id)
            WHERE is_default = TRUE
    """)

    # Cross-tenant tabulka — RLS by zde komplikovala lookup memberships
    # při loginu (kdy ještě nemáme tenant kontext). Necháme bez RLS;
    # ochranu řeší aplikace (user vidí jen memberships kde user_id = sebe).
    # Platform admin / superadmin bypass není potřeba.
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON user_tenant_memberships TO bozoapp_app")

    # ── Backfill: pro každého user vytvoř membership na user.tenant_id ─────
    op.execute("""
        INSERT INTO user_tenant_memberships (user_id, tenant_id, role, is_default)
        SELECT id, tenant_id, role, TRUE
        FROM users
        ON CONFLICT (user_id, tenant_id) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_tenant_memberships CASCADE")
    op.execute("ALTER TABLE tenants DROP COLUMN IF EXISTS external_login_enabled")
