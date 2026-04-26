"""operating_log_entries: 3-way capability (yes/no/conditional)

Revision ID: 051
Revises: 050
Create Date: 2026-04-26

Změna:
- capable_items JSONB list[bool] → list[str] s hodnotami 'yes'|'no'|'conditional'
- overall_capable BOOLEAN → overall_status VARCHAR(20) 'yes'|'no'|'conditional'

Backfill:
- True → 'yes', False → 'no' (pro existující záznamy).
"""

from alembic import op

revision = "051"
down_revision = "050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) overall_capable BOOL → overall_status VARCHAR(20)
    op.execute("""
        ALTER TABLE operating_log_entries
        ADD COLUMN overall_status VARCHAR(20)
    """)
    op.execute("""
        UPDATE operating_log_entries
        SET overall_status = CASE WHEN overall_capable THEN 'yes' ELSE 'no' END
    """)
    op.execute("""
        ALTER TABLE operating_log_entries
        ALTER COLUMN overall_status SET NOT NULL
    """)
    op.execute("""
        ALTER TABLE operating_log_entries
        ADD CONSTRAINT ck_oplog_overall_status CHECK (
            overall_status IN ('yes', 'no', 'conditional')
        )
    """)
    op.execute("ALTER TABLE operating_log_entries DROP COLUMN overall_capable")

    # 2) capable_items bool[] → str[]
    # JSONB array element conversion: pro každý záznam nahraď bool hodnoty stringem.
    op.execute("""
        UPDATE operating_log_entries
        SET capable_items = (
            SELECT COALESCE(jsonb_agg(
                CASE
                    WHEN jsonb_typeof(val) = 'boolean' AND val::text = 'true' THEN to_jsonb('yes'::text)
                    WHEN jsonb_typeof(val) = 'boolean' AND val::text = 'false' THEN to_jsonb('no'::text)
                    ELSE val
                END
            ), '[]'::jsonb)
            FROM jsonb_array_elements(capable_items) AS val
        )
        WHERE jsonb_typeof(capable_items) = 'array'
    """)


def downgrade() -> None:
    # Reverse 1: overall_status → overall_capable (best-effort: yes=true, ostatní=false)
    op.execute("""
        ALTER TABLE operating_log_entries
        ADD COLUMN overall_capable BOOLEAN
    """)
    op.execute("""
        UPDATE operating_log_entries
        SET overall_capable = CASE WHEN overall_status = 'yes' THEN TRUE ELSE FALSE END
    """)
    op.execute("""
        ALTER TABLE operating_log_entries
        ALTER COLUMN overall_capable SET NOT NULL
    """)
    op.execute(
        "ALTER TABLE operating_log_entries DROP CONSTRAINT IF EXISTS ck_oplog_overall_status"
    )
    op.execute("ALTER TABLE operating_log_entries DROP COLUMN overall_status")

    # Reverse 2: capable_items str[] → bool[]
    op.execute("""
        UPDATE operating_log_entries
        SET capable_items = (
            SELECT COALESCE(jsonb_agg(
                CASE
                    WHEN val::text = '"yes"' THEN to_jsonb(true)
                    ELSE to_jsonb(false)
                END
            ), '[]'::jsonb)
            FROM jsonb_array_elements(capable_items) AS val
        )
        WHERE jsonb_typeof(capable_items) = 'array'
    """)
