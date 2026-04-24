"""Rozšíření zaměstnance: osobní číslo, trvalé bydliště, plant_id

Revision ID: 020
Revises: 019
Create Date: 2026-04-24

Změny:
- employees.personal_number VARCHAR(50) — unikátní osobní číslo v rámci tenantu
- employees.address_city, address_street, address_zip — trvalé bydliště
- employees.plant_id FK → plants.id (cascading Plant → Workplace v UI;
  workplace_id už FK má z migrace 008, plant_id dosud chyběl)

personal_number má unikátní index (tenant_id, personal_number) kde NOT NULL —
dva zaměstnanci ve stejné firmě nemohou mít stejné osobní číslo, ale NULL je
povoleno (dočasní brigádníci nemusí mít přiděleno).
"""

from alembic import op

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Osobní číslo (oddělené od rodného čísla personal_id)
    op.execute("ALTER TABLE employees ADD COLUMN personal_number VARCHAR(50)")
    op.execute(
        "CREATE UNIQUE INDEX idx_employees_personal_number "
        "ON employees(tenant_id, personal_number) "
        "WHERE personal_number IS NOT NULL"
    )

    # Trvalé bydliště
    op.execute("ALTER TABLE employees ADD COLUMN address_street VARCHAR(200)")
    op.execute("ALTER TABLE employees ADD COLUMN address_city VARCHAR(100)")
    op.execute("ALTER TABLE employees ADD COLUMN address_zip VARCHAR(10)")

    # Plant FK (workplace_id už existuje z 008)
    op.execute("ALTER TABLE employees ADD COLUMN plant_id UUID REFERENCES plants(id) ON DELETE SET NULL")
    op.execute(
        "CREATE INDEX idx_employees_plant ON employees(tenant_id, plant_id) "
        "WHERE plant_id IS NOT NULL"
    )

    # GRANTy (migrace 015 default privileges by to měly zařídit, explicit pro jistotu)
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON employees TO bozoapp_app")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_employees_plant")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS plant_id")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS address_zip")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS address_city")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS address_street")
    op.execute("DROP INDEX IF EXISTS idx_employees_personal_number")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS personal_number")
