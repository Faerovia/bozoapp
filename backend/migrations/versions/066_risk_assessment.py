"""Risk Assessment dle ČSN ISO 45001 + Zákoník práce §102

Revision ID: 066
Revises: 065
Create Date: 2026-04-27

Tabulky:
- risk_assessments              — strukturované hodnocení nebezpečí (4 scope, P×Z 5×5)
- risk_measures                 — opatření 1:N s hierarchií ISO (eliminace→ppe)
- risk_assessment_revisions     — JSONB snapshot pro audit trail

Vazby s existujícími moduly:
- accident_action_items.related_risk_assessment_id  → automaticky generovaný
  default item "Revize rizik" po finalizaci úrazu odkazuje na konkrétní hodnocení.
- risk_measures.position_oopp_item_id  → measure typu 'ppe' přidává OOPP
  do pozice + spustí výdej zaměstnancům.
- risk_measures.training_template_id   → measure typu 'administrative' může
  spustit re-školení dotčených zaměstnanců.

Score (P×Z) je GENERATED computed column. Level (low/medium/high/critical)
se odvozuje v Pythonu nebo přes platform_setting `risk.level_thresholds`.

Stávající `risks` tabulka (slabý linker pro úrazy) zůstává — postupně se
data převedou. Žádné migrace dat tady nejsou.
"""

from alembic import op

revision = "066"
down_revision = "065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE risk_assessments (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

            scope_type VARCHAR(20) NOT NULL,
            workplace_id UUID REFERENCES workplaces(id) ON DELETE SET NULL,
            job_position_id UUID REFERENCES job_positions(id) ON DELETE SET NULL,
            plant_id UUID REFERENCES plants(id) ON DELETE SET NULL,
            activity_description TEXT,

            hazard_category VARCHAR(50) NOT NULL,
            hazard_description TEXT NOT NULL,
            consequence_description TEXT NOT NULL,
            exposed_persons SMALLINT,
            exposure_frequency VARCHAR(20),

            initial_probability SMALLINT NOT NULL,
            initial_severity SMALLINT NOT NULL,
            initial_score SMALLINT GENERATED ALWAYS AS (initial_probability * initial_severity) STORED,
            initial_level VARCHAR(20),

            existing_controls TEXT,
            existing_oopp TEXT,

            residual_probability SMALLINT,
            residual_severity SMALLINT,
            residual_score SMALLINT GENERATED ALWAYS AS (
                COALESCE(residual_probability, initial_probability)
                * COALESCE(residual_severity, initial_severity)
            ) STORED,
            residual_level VARCHAR(20),

            status VARCHAR(20) NOT NULL DEFAULT 'draft',
            assessed_at DATE,
            assessed_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            review_due_date DATE,
            last_reviewed_at DATE,
            last_reviewed_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,

            related_accident_report_id UUID REFERENCES accident_reports(id) ON DELETE SET NULL,
            related_revision_id UUID REFERENCES revisions(id) ON DELETE SET NULL,

            notes TEXT,
            created_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            CONSTRAINT ck_risk_scope_type CHECK (
                scope_type IN ('workplace', 'position', 'plant', 'activity')
            ),
            CONSTRAINT ck_risk_status CHECK (
                status IN ('draft', 'open', 'in_progress', 'mitigated', 'accepted', 'archived')
            ),
            CONSTRAINT ck_risk_initial_p CHECK (initial_probability BETWEEN 1 AND 5),
            CONSTRAINT ck_risk_initial_s CHECK (initial_severity BETWEEN 1 AND 5),
            CONSTRAINT ck_risk_residual_p CHECK (
                residual_probability IS NULL OR residual_probability BETWEEN 1 AND 5
            ),
            CONSTRAINT ck_risk_residual_s CHECK (
                residual_severity IS NULL OR residual_severity BETWEEN 1 AND 5
            ),
            CONSTRAINT ck_risk_exposure_freq CHECK (
                exposure_frequency IS NULL OR exposure_frequency IN
                    ('rare', 'occasional', 'frequent', 'continuous')
            ),
            CONSTRAINT ck_risk_scope_target CHECK (
                CASE scope_type
                    WHEN 'workplace' THEN workplace_id IS NOT NULL
                    WHEN 'position'  THEN job_position_id IS NOT NULL
                    WHEN 'plant'     THEN plant_id IS NOT NULL
                    WHEN 'activity'  THEN activity_description IS NOT NULL
                                          AND char_length(activity_description) > 0
                END
            )
        )
    """)
    op.execute(
        "CREATE INDEX ix_risk_assessments_tenant_status "
        "ON risk_assessments (tenant_id, status)",
    )
    op.execute(
        "CREATE INDEX ix_risk_assessments_workplace "
        "ON risk_assessments (workplace_id) WHERE workplace_id IS NOT NULL",
    )
    op.execute(
        "CREATE INDEX ix_risk_assessments_position "
        "ON risk_assessments (job_position_id) WHERE job_position_id IS NOT NULL",
    )
    op.execute(
        "CREATE INDEX ix_risk_assessments_review_due "
        "ON risk_assessments (review_due_date) "
        "WHERE status NOT IN ('archived', 'accepted')",
    )

    # RLS
    op.execute("ALTER TABLE risk_assessments ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE risk_assessments FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY risk_assessments_tenant_isolation ON risk_assessments
        USING (
            current_setting('app.is_superadmin', true) = 'true'
            OR current_setting('app.is_platform_admin', true) = 'true'
            OR tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid
        )
        WITH CHECK (
            current_setting('app.is_superadmin', true) = 'true'
            OR current_setting('app.is_platform_admin', true) = 'true'
            OR tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid
        )
    """)

    # ── risk_measures ──────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE risk_measures (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            risk_assessment_id UUID NOT NULL REFERENCES risk_assessments(id) ON DELETE CASCADE,

            order_index SMALLINT NOT NULL DEFAULT 0,
            control_type VARCHAR(20) NOT NULL,
            description TEXT NOT NULL,

            -- Provázanost s OOPP a školeními
            position_oopp_item_id UUID REFERENCES position_oopp_items(id) ON DELETE SET NULL,
            training_template_id UUID REFERENCES trainings(id) ON DELETE SET NULL,

            responsible_employee_id UUID REFERENCES employees(id) ON DELETE SET NULL,
            responsible_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            deadline DATE,

            status VARCHAR(20) NOT NULL DEFAULT 'planned',
            completed_at DATE,
            completed_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            evidence_file_path VARCHAR(500),
            notes TEXT,

            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            CONSTRAINT ck_measure_control_type CHECK (
                control_type IN ('elimination', 'substitution', 'engineering',
                                 'administrative', 'ppe')
            ),
            CONSTRAINT ck_measure_status CHECK (
                status IN ('planned', 'in_progress', 'done', 'cancelled')
            )
        )
    """)
    op.execute(
        "CREATE INDEX ix_risk_measures_assessment "
        "ON risk_measures (risk_assessment_id, order_index)",
    )
    op.execute(
        "CREATE INDEX ix_risk_measures_deadline "
        "ON risk_measures (deadline) "
        "WHERE status NOT IN ('done', 'cancelled')",
    )

    # RLS
    op.execute("ALTER TABLE risk_measures ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE risk_measures FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY risk_measures_tenant_isolation ON risk_measures
        USING (
            current_setting('app.is_superadmin', true) = 'true'
            OR current_setting('app.is_platform_admin', true) = 'true'
            OR tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid
        )
        WITH CHECK (
            current_setting('app.is_superadmin', true) = 'true'
            OR current_setting('app.is_platform_admin', true) = 'true'
            OR tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid
        )
    """)

    # ── risk_assessment_revisions (audit trail) ────────────────────────────
    op.execute("""
        CREATE TABLE risk_assessment_revisions (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            risk_assessment_id UUID NOT NULL REFERENCES risk_assessments(id) ON DELETE CASCADE,
            revision_number SMALLINT NOT NULL,
            snapshot JSONB NOT NULL,
            change_reason TEXT,
            revised_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            revised_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(risk_assessment_id, revision_number)
        )
    """)
    op.execute(
        "CREATE INDEX ix_risk_assessment_revisions_ra "
        "ON risk_assessment_revisions (risk_assessment_id, revision_number DESC)",
    )

    op.execute("ALTER TABLE risk_assessment_revisions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE risk_assessment_revisions FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY risk_revisions_tenant_isolation ON risk_assessment_revisions
        USING (
            current_setting('app.is_superadmin', true) = 'true'
            OR current_setting('app.is_platform_admin', true) = 'true'
            OR tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid
        )
        WITH CHECK (
            current_setting('app.is_superadmin', true) = 'true'
            OR current_setting('app.is_platform_admin', true) = 'true'
            OR tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid
        )
    """)

    # ── accident_action_items: FK na risk_assessments ──────────────────────
    op.execute("""
        ALTER TABLE accident_action_items
        ADD COLUMN related_risk_assessment_id UUID
        REFERENCES risk_assessments(id) ON DELETE SET NULL
    """)


def downgrade() -> None:
    op.execute(
        "ALTER TABLE accident_action_items "
        "DROP COLUMN IF EXISTS related_risk_assessment_id",
    )
    op.execute("DROP TABLE IF EXISTS risk_assessment_revisions")
    op.execute("DROP TABLE IF EXISTS risk_measures")
    op.execute("DROP TABLE IF EXISTS risk_assessments")
