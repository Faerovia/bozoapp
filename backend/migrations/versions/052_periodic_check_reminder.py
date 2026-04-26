"""platform_settings: prahy pro reminder pravidelných kontrol

Revision ID: 052
Revises: 051
Create Date: 2026-04-26

Přidá klíč reminders.thresholds.periodic_check (sanační sady, záchytné vany,
lékárničky) do platform_settings — analogicky k revisions, training, medical.
Default [30, 14, 7] dní před vypršením next_check_at.
"""

from alembic import op

revision = "052"
down_revision = "051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO platform_settings (key, value, description, updated_at)
        VALUES (
            'reminders.thresholds.periodic_check',
            '[30, 14, 7]'::jsonb,
            'Prahy v dnech před expirací pravidelné kontroly (sanační sady, '
            'záchytné vany, lékárničky). Po vypršení se reminder posílá '
            'zodpovědným osobám provozovny.',
            NOW()
        )
        ON CONFLICT (key) DO NOTHING
    """)


def downgrade() -> None:
    op.execute(
        "DELETE FROM platform_settings WHERE key = 'reminders.thresholds.periodic_check'"
    )
