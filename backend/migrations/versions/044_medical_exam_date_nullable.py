"""medical_exams.exam_date → nullable (auto-generované prohlídky neproběhly)

Revision ID: 044
Revises: 043
Create Date: 2026-04-26

PROBLÉM:
generate_initial_exam_requests() automaticky nastavovala exam_date=today
na auto-generované prohlídky. Uživatel pak měl seznam povinných prohlídek
s falešným datem provedení (jako by proběhly). Auditor by to mohl považovat
za podvodné záznamy.

ŘEŠENÍ:
exam_date → nullable. Pokud NULL = prohlídka byla naplánována ale neproběhla.
validity_status property pak vyhodnotí jako "expired" (= musí být provedena).
"""

from alembic import op

revision = "044"
down_revision = "043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE medical_exams ALTER COLUMN exam_date DROP NOT NULL")


def downgrade() -> None:
    # Pozor: pokud existují řádky s NULL, downgrade by selhal — vyplníme dnes.
    op.execute("UPDATE medical_exams SET exam_date = CURRENT_DATE WHERE exam_date IS NULL")
    op.execute("ALTER TABLE medical_exams ALTER COLUMN exam_date SET NOT NULL")
