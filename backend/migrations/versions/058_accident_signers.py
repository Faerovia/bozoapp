"""accident_reports — supervisor_employee_id + injured_external

Revision ID: 058
Revises: 057
Create Date: 2026-04-26

Rozšíření modulu Pracovní úraz pro digitální podpis (#105):
- supervisor_employee_id  — FK na employees, vedoucí pracovník (lead_worker
  role) z evidence. Slouží jako jeden z required signers.
- injured_external        — true = postižený je externí (např. brigádník bez
  evidence), pak digitální podpis nelze. Jinak postižený = employee_id z
  evidence (existující sloupec).

Pole `witnesses` (JSONB) zůstává — rozšiřujeme ho jen schematicky o klíč
`employee_id` (volitelný; None = externí). Žádná DDL změna není potřeba,
JSONB to absorbuje.

`signature_required` se updatuje computed funkcí v service vrstvě:
- True pokud všichni účastníci jsou interní (employees s employee_id)
- False pokud kdokoliv je externí → fyzický tisk + ruční podpis
"""

from alembic import op

revision = "058"
down_revision = "057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE accident_reports
        ADD COLUMN supervisor_employee_id UUID
            REFERENCES employees(id) ON DELETE SET NULL
    """)
    op.execute("""
        ALTER TABLE accident_reports
        ADD COLUMN injured_external BOOLEAN NOT NULL DEFAULT FALSE
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_accident_supervisor_emp
        ON accident_reports (supervisor_employee_id)
        WHERE supervisor_employee_id IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_accident_supervisor_emp")
    op.execute(
        "ALTER TABLE accident_reports DROP COLUMN IF EXISTS injured_external"
    )
    op.execute(
        "ALTER TABLE accident_reports DROP COLUMN IF EXISTS supervisor_employee_id"
    )
