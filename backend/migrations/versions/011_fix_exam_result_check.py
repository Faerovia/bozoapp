"""Oprava CHECK constraintu ck_me_result – typo zpusobilyý → zpusobily

Revision ID: 011
Revises: 010
Create Date: 2026-04-24

Původní hodnoty obsahovaly typo 'zpusobilyý' (y + ý).
Správná ASCII transliterace 'způsobilý' je 'zpusobily'.
"""

from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Smaž starý constraint se špatnými hodnotami
    op.drop_constraint("ck_me_result", "medical_exams", type_="check")

    # Přidej opravený constraint
    op.create_check_constraint(
        "ck_me_result",
        "medical_exams",
        "result IN ('zpusobily','zpusobily_omezeni','nezpusobily','pozbyl_zpusobilosti') OR result IS NULL",
    )


def downgrade() -> None:
    op.drop_constraint("ck_me_result", "medical_exams", type_="check")
    op.create_check_constraint(
        "ck_me_result",
        "medical_exams",
        "result IN ('zpusobilyý','zpusobilyý_omezeni','nezpusobilyý','pozbyl_zpusobilosti') OR result IS NULL",
    )
