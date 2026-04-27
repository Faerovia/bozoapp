"""job_positions.skip_vstupni_exam — opt-out vstupní prohlídky pro cat 1

Revision ID: 064
Revises: 063
Create Date: 2026-04-27

Důvod:
Vyhláška 79/2013 vyžaduje vstupní lékařskou prohlídku pro každého
zaměstnance při nástupu, ale **pro pozice kategorie 1 bez rizikových
faktorů** může zaměstnavatel rozhodnout, že vstupní není nutná
(např. čistě administrativní pozice, dálkový pracovník).

Default: False = vstupní se generuje (právně bezpečnější default).
True = OZO/HR nezpracovává vstupní pro tuto pozici (jen cat 1).

Pro cat 2+ je flag ignorovaný — vstupní je vždy povinná.
"""

from alembic import op

revision = "064"
down_revision = "063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE job_positions
        ADD COLUMN skip_vstupni_exam BOOLEAN NOT NULL DEFAULT FALSE
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE job_positions DROP COLUMN IF EXISTS skip_vstupni_exam")
