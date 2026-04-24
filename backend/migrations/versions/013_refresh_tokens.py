"""Refresh token rotation s detekcí reuse

Revision ID: 013
Revises: 012
Create Date: 2026-04-24

Přidává tabulku refresh_tokens pro zajištění:
1. Rotation — každý /refresh request vymění refresh token za nový. Starý
   je označen jako `used`.
2. Reuse detection — pokud už použitý (used) nebo revoked token přijde
   znovu, revoke celou "family" (všechny tokeny z téhož login session)
   a vynutíme re-login. Signalizuje to buď (a) útočníka který získal
   refresh token, nebo (b) bug v klientu.

Family design:
- Při login/register → vygeneruje se family_id (UUID).
- Každý nový refresh token v rámci stejné family zdědí family_id.
- Když zjistíme reuse → UPDATE všechny tokeny s family_id SET revoked_at.

Tabulka má RLS + FORCE RLS jako ostatní tenantované tabulky.
"""

from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE refresh_tokens (
            jti          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            family_id    UUID NOT NULL,
            -- Kdy byl token vystaven
            issued_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            -- Kdy expiruje (absolutní čas, stejný jako JWT exp claim)
            expires_at   TIMESTAMPTZ NOT NULL,
            -- Kdy byl token použit k výměně za nový (NULL = nepoužitý)
            used_at      TIMESTAMPTZ,
            -- Kdy byl revoked (útok / logout / expirace family)
            revoked_at   TIMESTAMPTZ,
            -- Důvod revocation pro audit
            revoked_reason VARCHAR(50)
            -- 'reuse_detected' | 'logout' | 'manual' | 'family_revoked'
        )
    """)

    op.execute("CREATE INDEX idx_rt_user ON refresh_tokens(user_id)")
    op.execute("CREATE INDEX idx_rt_family ON refresh_tokens(family_id)")
    op.execute(
        "CREATE INDEX idx_rt_expires ON refresh_tokens(expires_at) "
        "WHERE revoked_at IS NULL"
    )

    op.execute("ALTER TABLE refresh_tokens ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE refresh_tokens FORCE ROW LEVEL SECURITY")

    op.execute("""
        CREATE POLICY tenant_isolation ON refresh_tokens
            USING (tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID)
    """)
    op.execute("""
        CREATE POLICY superadmin_bypass ON refresh_tokens
            USING (current_setting('app.is_superadmin', TRUE) = 'true')
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS refresh_tokens CASCADE")
