"""Trainings refactor: šablona + přiřazení + pokusy + test + PDF + certifikát

Revision ID: 022
Revises: 021
Create Date: 2026-04-24

DESIGN:
Staré schéma: Training měl employee_id (1 zaměstnanec = 1 školení, školení je
"co zaměstnanec absolvoval"). Nová realita BOZP:

    Training (šablona)
        ├── content_pdf_path      — obsah školení (PDF)
        ├── test_questions JSONB  — [{q, correct, wrongs[]}]
        ├── pass_percentage       — min % pro certifikát
        ├── trainer_kind          — OZO_BOZP | OZO_PO | EMPLOYER
        └── N × TrainingAssignment
                ├── employee_id
                ├── assigned_at, deadline (+7 dní od assign)
                ├── last_completed_at  NULL dokud nesplní
                ├── valid_until        last_completed_at + šablona.valid_months
                ├── status             pending | completed | expired
                └── N × TrainingAttempt
                        ├── attempted_at
                        ├── score_percentage
                        ├── passed (bool)
                        └── answers JSONB  (uživatelské odpovědi)

Plus: tenants.logo_path — cesta k PNG/JPG logu v /app/uploads/tenants/{id}/,
které se vkládá do certifikátu.

MIGRATION PATH:
Stávající data v `trainings` vznikla pod starým modelem. User potvrdil
drop → start fresh. Není migrace dat, jen schéma.
"""

from alembic import op

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Zahodit starou tabulku trainings s FK závislostmi
    # calendar_items / dashboard ji sice číst, ale kód refactorujeme.
    op.execute("DROP TABLE IF EXISTS trainings CASCADE")

    # 2) Nová Training tabulka — šablona
    op.execute("""
        CREATE TABLE trainings (
            id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id        UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            title            VARCHAR(255) NOT NULL,
            training_type    VARCHAR(20)  NOT NULL,
            -- bozp | po | other
            trainer_kind     VARCHAR(20)  NOT NULL DEFAULT 'employer',
            -- ozo_bozp | ozo_po | employer
            valid_months     INTEGER NOT NULL,
            -- Perioda opakování v měsících (povinná — zaměstnanec vždy někdy expiruje)

            content_pdf_path VARCHAR(500),
            -- Relativní cesta v UPLOAD_DIR; NULL = bez PDF obsahu

            test_questions   JSONB,
            -- [{question, correct_answer, wrong_answers: [str, str, str]}]
            -- NULL = bez testu; pak není ani pass_percentage použito
            pass_percentage  INTEGER,
            -- 0–100, povinné když test_questions není NULL

            notes            TEXT,

            created_by       UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            CONSTRAINT ck_trainings_type
                CHECK (training_type IN ('bozp', 'po', 'other')),
            CONSTRAINT ck_trainings_trainer
                CHECK (trainer_kind IN ('ozo_bozp', 'ozo_po', 'employer')),
            CONSTRAINT ck_trainings_valid_months
                CHECK (valid_months > 0 AND valid_months <= 600),
            CONSTRAINT ck_trainings_pass
                CHECK (
                    pass_percentage IS NULL
                    OR (pass_percentage >= 0 AND pass_percentage <= 100)
                ),
            -- Když je test, musí být nastaven pass_percentage
            CONSTRAINT ck_trainings_test_requires_pass
                CHECK (
                    (test_questions IS NULL AND pass_percentage IS NULL)
                    OR (test_questions IS NOT NULL AND pass_percentage IS NOT NULL)
                ),
            -- Unikátnost názvu v rámci tenantu
            CONSTRAINT uq_trainings_title UNIQUE (tenant_id, title)
        )
    """)

    op.execute("CREATE INDEX idx_trainings_tenant ON trainings(tenant_id)")
    op.execute("CREATE INDEX idx_trainings_type ON trainings(tenant_id, training_type)")

    op.execute("ALTER TABLE trainings ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE trainings FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON trainings
            USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID)
    """)
    op.execute("""
        CREATE POLICY superadmin_bypass ON trainings
            USING (current_setting('app.is_superadmin', TRUE) = 'true')
    """)
    op.execute("""
        CREATE POLICY platform_admin_bypass ON trainings
            USING (current_setting('app.is_platform_admin', TRUE) = 'true')
    """)
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON trainings TO bozoapp_app")

    # 3) TrainingAssignment — přiřazení šablony konkrétnímu zaměstnanci
    op.execute("""
        CREATE TABLE training_assignments (
            id                 UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id          UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            training_id        UUID NOT NULL REFERENCES trainings(id) ON DELETE CASCADE,
            employee_id        UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,

            assigned_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            -- Deadline = assigned_at + 7 dní. Po té datum je status='expired' pokud
            -- ještě nesplněno. Po splnění se deadline už nepoužívá.
            deadline           TIMESTAMPTZ NOT NULL,

            -- Kdy naposledy zaměstnanec úspěšně splnil (test passed nebo bez testu potvrdil)
            last_completed_at  TIMESTAMPTZ,
            -- Do kdy je aktuální absolvování platné (last_completed + šablona.valid_months)
            valid_until        DATE,

            status             VARCHAR(20) NOT NULL DEFAULT 'pending',
            -- pending | completed | expired | revoked

            assigned_by        UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            CONSTRAINT ck_ta_status
                CHECK (status IN ('pending', 'completed', 'expired', 'revoked')),
            -- Jeden zaměstnanec nemůže mít stejnou šablonu 2× (update místo re-insert)
            CONSTRAINT uq_ta_employee_training UNIQUE (employee_id, training_id)
        )
    """)

    op.execute("CREATE INDEX idx_ta_tenant ON training_assignments(tenant_id)")
    op.execute("CREATE INDEX idx_ta_employee ON training_assignments(employee_id)")
    op.execute("CREATE INDEX idx_ta_training ON training_assignments(training_id)")
    op.execute(
        "CREATE INDEX idx_ta_valid_until ON training_assignments(tenant_id, valid_until) "
        "WHERE valid_until IS NOT NULL"
    )

    op.execute("ALTER TABLE training_assignments ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE training_assignments FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON training_assignments
            USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID)
    """)
    op.execute("""
        CREATE POLICY superadmin_bypass ON training_assignments
            USING (current_setting('app.is_superadmin', TRUE) = 'true')
    """)
    op.execute("""
        CREATE POLICY platform_admin_bypass ON training_assignments
            USING (current_setting('app.is_platform_admin', TRUE) = 'true')
    """)
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON training_assignments TO bozoapp_app"
    )

    # 4) TrainingAttempt — pokusy o test (každý je ostrý, neomezený počet)
    op.execute("""
        CREATE TABLE training_attempts (
            id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id         UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            assignment_id     UUID NOT NULL REFERENCES training_assignments(id) ON DELETE CASCADE,

            attempted_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            score_percentage  INTEGER NOT NULL,
            passed            BOOLEAN NOT NULL,
            answers           JSONB NOT NULL,
            -- [{question_index, chosen_answer_text, correct: bool}, ...]

            CONSTRAINT ck_attempt_score
                CHECK (score_percentage >= 0 AND score_percentage <= 100)
        )
    """)

    op.execute("CREATE INDEX idx_attempt_assignment ON training_attempts(assignment_id)")
    op.execute(
        "CREATE INDEX idx_attempt_passed ON training_attempts(assignment_id, attempted_at) "
        "WHERE passed = true"
    )

    op.execute("ALTER TABLE training_attempts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE training_attempts FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON training_attempts
            USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID)
    """)
    op.execute("""
        CREATE POLICY superadmin_bypass ON training_attempts
            USING (current_setting('app.is_superadmin', TRUE) = 'true')
    """)
    op.execute("""
        CREATE POLICY platform_admin_bypass ON training_attempts
            USING (current_setting('app.is_platform_admin', TRUE) = 'true')
    """)
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON training_attempts TO bozoapp_app"
    )

    # 5) Logo firmy pro certifikáty
    op.execute("ALTER TABLE tenants ADD COLUMN logo_path VARCHAR(500)")


def downgrade() -> None:
    op.execute("ALTER TABLE tenants DROP COLUMN IF EXISTS logo_path")
    op.execute("DROP TABLE IF EXISTS training_attempts CASCADE")
    op.execute("DROP TABLE IF EXISTS training_assignments CASCADE")
    op.execute("DROP TABLE IF EXISTS trainings CASCADE")
    # Staré schéma už nevracíme — user potvrdil fresh start.
