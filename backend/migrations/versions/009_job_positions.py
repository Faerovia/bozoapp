"""Pracovní pozice (job positions) + FK z employees

Revision ID: 009
Revises: 008
Create Date: 2026-04-23

Legislativní základ:
- Zákoník práce §103 odst. 1 písm. a) – povinnost zařadit práci do kategorie
- NV 361/2007 Sb. – kategorizace prací (kategorie 1–4, včetně 2R)
- Vyhláška 79/2013 Sb. §11 – lhůty pracovnělékařských prohlídek dle kategorie

Kategorie práce → výchozí lhůta periodické prohlídky:
  1  → 72 měsíců (6 let, < 50 let věku; 48 měs. pro ≥ 50 let)
  2  → 48 měsíců (4 roky, < 50 let; 24 měs. pro ≥ 50 let)
  2R → 24 měsíců (2 roky)
  3  → 24 měsíců (2 roky)
  4  → 12 měsíců (1 rok)

Poznámka: medical_exam_period_months je výchozí lhůta – OZO ji může přepsat
na konkrétní pracovní pozici. Věkové korekce řeší modul lékařských prohlídek.
"""

from alembic import op

revision: str = "009"
down_revision: str = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Tabulka pracovních pozic ───────────────────────────────────────────
    op.execute("""
        CREATE TABLE job_positions (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

            name            VARCHAR(255) NOT NULL,
            -- Např. "Soustružník", "Skladník", "Vedoucí provozu"

            description     TEXT,

            -- Kategorie práce dle NV 361/2007 Sb.
            -- Určuje lhůty periodických prohlídek a rozsah sledování
            work_category   VARCHAR(3),
            -- hodnoty: '1' | '2' | '2R' | '3' | '4' | NULL (nezařazeno)

            CONSTRAINT ck_jp_category CHECK (
                work_category IN ('1','2','2R','3','4') OR work_category IS NULL
            ),

            -- Lhůta periodické prohlídky v měsících (přepisuje výchozí z kategorie)
            -- NULL = použij výchozí dle kategorie (viz CATEGORY_DEFAULT_EXAM_MONTHS)
            medical_exam_period_months  SMALLINT CHECK (medical_exam_period_months > 0),

            notes           TEXT,
            status          VARCHAR(20) NOT NULL DEFAULT 'active',

            created_by      UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("CREATE INDEX idx_job_positions_tenant ON job_positions(tenant_id)")
    op.execute("ALTER TABLE job_positions ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON job_positions
            USING (tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID)
    """)
    op.execute("""
        CREATE POLICY superadmin_bypass ON job_positions
            USING (current_setting('app.is_superadmin', TRUE) = 'true')
    """)

    # ── 2. FK employees.job_position_id → job_positions.id ───────────────────
    # Sloupec job_position_id již existuje (migration 007), jen přidáme FK
    op.execute("""
        ALTER TABLE employees
            ADD CONSTRAINT employees_job_position_id_fkey
            FOREIGN KEY (job_position_id) REFERENCES job_positions(id) ON DELETE SET NULL
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE employees DROP CONSTRAINT IF EXISTS employees_job_position_id_fkey")
    op.execute("DROP TABLE IF EXISTS job_positions CASCADE")
