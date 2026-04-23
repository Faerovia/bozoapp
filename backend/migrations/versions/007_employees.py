"""Evidence zaměstnanců (HR entita oddělená od auth Users)

Revision ID: 007
Revises: 006
Create Date: 2026-04-23

Architektonické rozhodnutí:
- employees = HR entita (kdo pracuje ve firmě, pozice, pracoviště)
- users = auth entita (kdo se může přihlásit do aplikace)
- Zaměstnanec MŮŽE, ale NEMUSÍ mít uživatelský účet (brigádník, externista)
- Vztah: employees.user_id → users.id (nullable, UNIQUE)

Napojení na ostatní tabulky:
- trainings.employee_id → employees.id   (místo původního → users.id)
- oopp_assignments.employee_id → employees.id
- accident_reports.employee_id → employees.id

GDPR/citlivá data:
- personal_id (rodné číslo) = zvláštní kategorie, šifrování bude přidáno v prod
- birth_date = osobní údaj

Budoucí FK (přidány až při vzniku cílových tabulek):
- job_position_id → job_positions.id   (migration 008)
- workplace_id    → workplaces.id      (migration 008)
"""

from alembic import op

revision: str = "007"
down_revision: str = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Tabulka zaměstnanců ────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE employees (
            id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id         UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

            -- Vazba na auth účet (volitelná)
            user_id           UUID UNIQUE REFERENCES users(id) ON DELETE SET NULL,
            -- NULL = zaměstnanec bez přístupu do aplikace

            -- Identifikace
            first_name        VARCHAR(100) NOT NULL,
            last_name         VARCHAR(100) NOT NULL,
            personal_id       VARCHAR(20),
            -- rodné číslo / datum narození ve formátu xxxxxx/xxxx
            -- GDPR: zvláštní kategorie, uchovávat šifrovaně v produkci
            birth_date        DATE,

            -- Kontakt
            email             VARCHAR(255),
            phone             VARCHAR(50),

            -- Pracovní zařazení (FK přidány v budoucích migracích)
            job_position_id   UUID,
            -- bude: REFERENCES job_positions(id) ON DELETE SET NULL
            workplace_id      UUID,
            -- bude: REFERENCES workplaces(id) ON DELETE SET NULL

            -- Typ pracovního poměru
            employment_type   VARCHAR(50) NOT NULL DEFAULT 'hpp',
            -- hodnoty: hpp | dpp | dpc | externista | brigádník

            -- Časové rozsahy
            hired_at          DATE,
            terminated_at     DATE,

            -- Stav
            status            VARCHAR(20) NOT NULL DEFAULT 'active',
            -- hodnoty: active | terminated | on_leave

            notes             TEXT,

            created_by        UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("CREATE INDEX idx_employees_tenant ON employees(tenant_id)")
    op.execute("CREATE INDEX idx_employees_status ON employees(tenant_id, status)")
    op.execute("CREATE INDEX idx_employees_user ON employees(user_id) WHERE user_id IS NOT NULL")
    op.execute("CREATE INDEX idx_employees_position ON employees(tenant_id, job_position_id) WHERE job_position_id IS NOT NULL")
    op.execute("CREATE INDEX idx_employees_workplace ON employees(tenant_id, workplace_id) WHERE workplace_id IS NOT NULL")

    op.execute("ALTER TABLE employees ENABLE ROW LEVEL SECURITY")

    op.execute("""
        CREATE POLICY tenant_isolation ON employees
            USING (
                tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID
            )
    """)

    op.execute("""
        CREATE POLICY superadmin_bypass ON employees
            USING (current_setting('app.is_superadmin', TRUE) = 'true')
    """)

    # ── 2. Přepojení FK: trainings.employee_id → employees.id ────────────────
    op.execute("ALTER TABLE trainings DROP CONSTRAINT IF EXISTS trainings_employee_id_fkey")
    op.execute("""
        ALTER TABLE trainings
            ADD CONSTRAINT trainings_employee_id_fkey
            FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE RESTRICT
    """)

    # ── 3. Přepojení FK: oopp_assignments.employee_id → employees.id ─────────
    op.execute("ALTER TABLE oopp_assignments DROP CONSTRAINT IF EXISTS oopp_assignments_employee_id_fkey")
    op.execute("""
        ALTER TABLE oopp_assignments
            ADD CONSTRAINT oopp_assignments_employee_id_fkey
            FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE RESTRICT
    """)

    # ── 4. Přepojení FK: accident_reports.employee_id → employees.id ─────────
    op.execute("ALTER TABLE accident_reports DROP CONSTRAINT IF EXISTS accident_reports_employee_id_fkey")
    op.execute("""
        ALTER TABLE accident_reports
            ADD CONSTRAINT accident_reports_employee_id_fkey
            FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE SET NULL
    """)


def downgrade() -> None:
    # Vrátit FK zpět na users
    op.execute("ALTER TABLE trainings DROP CONSTRAINT IF EXISTS trainings_employee_id_fkey")
    op.execute("""
        ALTER TABLE trainings
            ADD CONSTRAINT trainings_employee_id_fkey
            FOREIGN KEY (employee_id) REFERENCES users(id) ON DELETE RESTRICT
    """)

    op.execute("ALTER TABLE oopp_assignments DROP CONSTRAINT IF EXISTS oopp_assignments_employee_id_fkey")
    op.execute("""
        ALTER TABLE oopp_assignments
            ADD CONSTRAINT oopp_assignments_employee_id_fkey
            FOREIGN KEY (employee_id) REFERENCES users(id) ON DELETE RESTRICT
    """)

    op.execute("ALTER TABLE accident_reports DROP CONSTRAINT IF EXISTS accident_reports_employee_id_fkey")
    op.execute("""
        ALTER TABLE accident_reports
            ADD CONSTRAINT accident_reports_employee_id_fkey
            FOREIGN KEY (employee_id) REFERENCES users(id) ON DELETE SET NULL
    """)

    op.execute("DROP TABLE IF EXISTS employees CASCADE")
