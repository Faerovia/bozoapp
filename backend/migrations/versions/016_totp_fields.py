"""2FA (TOTP) pole na users + tabulka recovery kódů

Revision ID: 016
Revises: 015
Create Date: 2026-04-24

Změny:
- users.totp_secret (VARCHAR 128, nullable): base32 secret pro TOTP.
  Ukládáme ENCRYPTED pomocí app.core.encryption (Fernet) — bez klíče z env
  nelze dešifrovat ani z DB dumpu.
- users.totp_enabled (BOOLEAN, default FALSE): vlastník secretu si ho musí
  nejprve potvrdit (setup → verify → enable), teprve pak se ptá při loginu.
- Tabulka `recovery_codes`: 10 jednorázových kódů per user, uložených jako
  SHA-256 hash. Při použití označíme `used_at`.

RLS: `recovery_codes` má tenant_isolation + FORCE RLS jako zbytek.
"""

from alembic import op

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rozšíření users
    op.execute("ALTER TABLE users ADD COLUMN totp_secret VARCHAR(256)")
    op.execute("ALTER TABLE users ADD COLUMN totp_enabled BOOLEAN NOT NULL DEFAULT FALSE")

    # Recovery codes — one-time tokens pro případ ztráty autentikátoru
    op.execute("""
        CREATE TABLE recovery_codes (
            id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            code_hash    VARCHAR(64) NOT NULL,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            used_at      TIMESTAMPTZ
        )
    """)

    op.execute("CREATE INDEX idx_rc_user ON recovery_codes(user_id)")
    op.execute(
        "CREATE INDEX idx_rc_active ON recovery_codes(user_id, code_hash) "
        "WHERE used_at IS NULL"
    )

    op.execute("ALTER TABLE recovery_codes ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE recovery_codes FORCE ROW LEVEL SECURITY")

    op.execute("""
        CREATE POLICY tenant_isolation ON recovery_codes
            USING (tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID)
    """)
    op.execute("""
        CREATE POLICY superadmin_bypass ON recovery_codes
            USING (current_setting('app.is_superadmin', TRUE) = 'true')
    """)

    # GRANT pro bozoapp_app (viz migrace 015 pattern)
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON recovery_codes TO bozoapp_app"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS recovery_codes CASCADE")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS totp_secret")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS totp_enabled")
