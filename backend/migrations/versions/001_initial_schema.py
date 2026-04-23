"""Initial schema: tenants, users, audit_log, RLS, pgvector

Revision ID: 001
Revises:
Create Date: 2026-04-23

"""

from alembic import op

revision: str = "001"
down_revision: None = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Extensions ────────────────────────────────────────────────────────────
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── Tenants ───────────────────────────────────────────────────────────────
    # Tenant = jeden klient OZO (firma). OZO poradce má vlastní tenant a
    # spravuje pod-tenants svých klientů (multi-tenant model se řeší v Fázi 1).
    op.execute("""
        CREATE TABLE tenants (
            id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            name        VARCHAR(255) NOT NULL,
            slug        VARCHAR(100) NOT NULL UNIQUE,
            is_active   BOOLEAN NOT NULL DEFAULT TRUE,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # ── Users ─────────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE users (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            email           VARCHAR(255) NOT NULL,
            hashed_password VARCHAR(255) NOT NULL,
            full_name       VARCHAR(255),
            role            VARCHAR(50) NOT NULL DEFAULT 'employee',
            -- role: 'superadmin' | 'ozo' | 'manager' | 'employee'
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            last_login_at   TIMESTAMPTZ,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(tenant_id, email)
        )
    """)

    op.execute("CREATE INDEX idx_users_tenant_id ON users(tenant_id)")
    op.execute("CREATE INDEX idx_users_email ON users(email)")

    # ── Audit Log ─────────────────────────────────────────────────────────────
    # GDPR: zvláštní kategorie dat (zdravotní záznamy, úrazy) vyžadují audit trail.
    # Tento log je append-only – nikdy nemazat záznamy, jen archivovat.
    op.execute("""
        CREATE TABLE audit_log (
            id            BIGSERIAL PRIMARY KEY,
            tenant_id     UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            user_id       UUID REFERENCES users(id) ON DELETE SET NULL,
            action        VARCHAR(50)  NOT NULL,
            -- action: 'CREATE' | 'UPDATE' | 'DELETE' | 'VIEW' | 'EXPORT'
            resource_type VARCHAR(100) NOT NULL,
            -- resource_type: 'risk' | 'training' | 'incident' | 'document' | ...
            resource_id   VARCHAR(255),
            old_values    JSONB,
            new_values    JSONB,
            ip_address    INET,
            user_agent    TEXT,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("CREATE INDEX idx_audit_tenant_id ON audit_log(tenant_id)")
    op.execute(
        "CREATE INDEX idx_audit_resource ON audit_log(tenant_id, resource_type, resource_id)"
    )
    op.execute("CREATE INDEX idx_audit_created_at ON audit_log(created_at)")

    # ── Row-Level Security ────────────────────────────────────────────────────
    # Aplikace nastaví `SET LOCAL app.current_tenant_id = '<uuid>'` na začátku
    # každého requestu. RLS pak automaticky filtruje všechny queries.
    # POZOR: superadmin role (OZO správce) obchází RLS přes BYPASSRLS nebo
    # explicitní SET pro každého klienta zvlášť.

    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY")

    # Politika pro users: vidíš jen uživatele svého tenantu
    op.execute("""
        CREATE POLICY tenant_isolation ON users
            USING (
                tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID
            )
    """)

    # Politika pro audit_log: vidíš jen záznamy svého tenantu
    op.execute("""
        CREATE POLICY tenant_isolation ON audit_log
            USING (
                tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID
            )
    """)

    # Výjimka: superadmin aplikace může vidět vše (pro support/debug)
    op.execute("""
        CREATE POLICY superadmin_bypass ON users
            USING (current_setting('app.is_superadmin', TRUE) = 'true')
    """)

    op.execute("""
        CREATE POLICY superadmin_bypass ON audit_log
            USING (current_setting('app.is_superadmin', TRUE) = 'true')
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_log CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")
    op.execute("DROP TABLE IF EXISTS tenants CASCADE")
    op.execute("DROP EXTENSION IF EXISTS vector")
    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp"')
