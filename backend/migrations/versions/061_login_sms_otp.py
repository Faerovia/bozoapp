"""login SMS OTP — passwordless login přes SMS kód

Revision ID: 061
Revises: 060
Create Date: 2026-04-27

Tabulka login_sms_otp_codes — OTP kódy pro alternativní login přes SMS.

Liší se od sms_otp_codes (signature OTP):
- Nemá tenant_id (login je cross-tenant pro platform admina)
- Nemá doc_type/doc_id (není vázaný na dokument)
- Má user_id přímo (signature OTP má employee_id)

Životní cyklus:
1. POST /auth/sms/request s identifierem (email|username|phone)
   → backend najde User a jeho phone (přes Employee.user_id)
   → vygeneruje 6místný kód, hash uloží sem, plain text pošle SMS gateway
2. POST /auth/sms/verify s identifierem + kódem
   → kontrola hash + attempts + expiry
   → po úspěchu vytvoří JWT a vyplní auth_cookies
"""

from alembic import op

revision = "061"
down_revision = "060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE login_sms_otp_codes (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            code_hash VARCHAR(255) NOT NULL,
            sent_to VARCHAR(50) NOT NULL,
            attempts SMALLINT NOT NULL DEFAULT 0,
            verified_at TIMESTAMPTZ,
            expires_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX ix_login_sms_otp_pending
        ON login_sms_otp_codes (user_id)
        WHERE verified_at IS NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_login_sms_otp_pending")
    op.execute("DROP TABLE IF EXISTS login_sms_otp_codes")
