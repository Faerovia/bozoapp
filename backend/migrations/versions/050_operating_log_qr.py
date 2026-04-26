"""operating_log_devices.qr_token — QR kód pro načtení zařízení na místě

Revision ID: 050
Revises: 049
Create Date: 2026-04-26

Stejný pattern jako revisions.qr_token: 64-char URL-safe token, unique.
QR odkazuje na /devices/{token}/operating-log → mobilní zápis na místě.

Backfill: doplní token pro existující záznamy přes secrets.token_urlsafe.
"""

import secrets

from alembic import op
from sqlalchemy import text as sql_text

revision = "050"
down_revision = "049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE operating_log_devices
        ADD COLUMN qr_token VARCHAR(64)
    """)

    # Backfill — vygenerovat token pro existující záznamy
    bind = op.get_bind()
    rows = bind.execute(
        sql_text("SELECT id FROM operating_log_devices WHERE qr_token IS NULL")
    ).fetchall()
    for row in rows:
        token = secrets.token_urlsafe(48)[:64]
        bind.execute(
            sql_text("UPDATE operating_log_devices SET qr_token = :t WHERE id = :id"),
            {"t": token, "id": row[0]},
        )

    op.execute("""
        ALTER TABLE operating_log_devices
        ALTER COLUMN qr_token SET NOT NULL
    """)
    op.execute("""
        ALTER TABLE operating_log_devices
        ADD CONSTRAINT uq_oplog_qr_token UNIQUE (qr_token)
    """)


def downgrade() -> None:
    op.execute(
        "ALTER TABLE operating_log_devices DROP CONSTRAINT IF EXISTS uq_oplog_qr_token"
    )
    op.execute("ALTER TABLE operating_log_devices DROP COLUMN IF EXISTS qr_token")
