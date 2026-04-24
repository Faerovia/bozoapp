"""Password reset tokens

Revision ID: 014
Revises: 013
Create Date: 2026-04-24

Reset flow:
1. POST /auth/forgot-password {email}
   → Server vygeneruje random token (32 bytů), uloží HASH tokenu (ne cleartext!)
     + user_id + expires_at (1h), vyšle email s URL obsahující cleartext token.
   → Odpověď VŽDY 204 (enumeration-resistant — neprozradíme zda email existuje).

2. POST /auth/reset-password {token, new_password}
   → Server hashuje token, vyhledá active row, ověří expiraci, aktualizuje
     user.hashed_password, označí token.used_at, revoke všechny refresh tokens
     usera.

Bezpečnostní rozhodnutí:
- Token se ukládá jako SHA-256 hash, ne cleartext. I kdyby DB unikla, token
  nejde zpětně odvodit.
- TTL 1 hodina — minimalizuje attack window.
- Row je per-token, NE per-user — user může mít více aktivních reset tokenů
  (klient požádal vícekrát). Všechny ale musí expirovat nebo být použity.
"""

from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE password_reset_tokens (
            id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            -- SHA-256 hash tokenu jako hex (64 chars). NIKDY cleartext.
            token_hash   VARCHAR(64) NOT NULL,
            issued_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at   TIMESTAMPTZ NOT NULL,
            used_at      TIMESTAMPTZ,
            -- Debug: IP z requestu pro forenzní
            request_ip   INET
        )
    """)

    op.execute("CREATE INDEX idx_prt_user ON password_reset_tokens(user_id)")
    op.execute("CREATE UNIQUE INDEX idx_prt_token_hash ON password_reset_tokens(token_hash)")
    op.execute(
        "CREATE INDEX idx_prt_active ON password_reset_tokens(token_hash) "
        "WHERE used_at IS NULL"
    )

    op.execute("ALTER TABLE password_reset_tokens ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE password_reset_tokens FORCE ROW LEVEL SECURITY")

    op.execute("""
        CREATE POLICY tenant_isolation ON password_reset_tokens
            USING (tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID)
    """)
    op.execute("""
        CREATE POLICY superadmin_bypass ON password_reset_tokens
            USING (current_setting('app.is_superadmin', TRUE) = 'true')
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS password_reset_tokens CASCADE")
