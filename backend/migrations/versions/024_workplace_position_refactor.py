"""JobPosition vázat na Workplace; RFA přesunout z Workplace na JobPosition + PDF per faktor

Revision ID: 024
Revises: 023
Create Date: 2026-04-24

DESIGN:
Stávající hierarchie:
    Plant (provozovna)
      └── Workplace (pracoviště)
             └── RiskFactorAssessment (hodnocení rizik — per workplace × profese)

    JobPosition (per tenant, bez vazby na workplace)

Nový model dle požadavku „stejná pozice na dvou různých pracovištích = dvě
různá hodnocení rizik":
    Plant
      └── Workplace
             └── JobPosition (FK workplace_id, unique (name, workplace_id))
                    └── RiskFactorAssessment  (1:1; přesun workplace_id → job_position_id)
                           + 13× PDF příloha (jeden soubor per rizikový faktor)

MIGRATION PATH:
1. job_positions: přidat workplace_id NULLABLE
2. Backfill: pro každou pozici bez workplace_id vybereme první workplace v tenantu.
   Pokud tenant nemá žádné workplaces, pozici smažeme (asi nebyla použita v praxi).
3. job_positions: workplace_id → NOT NULL, UNIQUE(tenant_id, name, workplace_id)
4. risk_factor_assessments: přidat job_position_id NULLABLE + 13× pdf_path
5. Backfill RFA: pro každé (workplace_id, profese) najdeme/vytvoříme
   JobPosition(name=profese, workplace_id=RFA.workplace_id) a nastavíme
   RFA.job_position_id.
6. risk_factor_assessments.workplace_id zůstává pro zpětnou kompat jako NULLABLE.
   job_position_id po backfillu → NOT NULL.
7. Odstranit CHECK constraint work_category na job_positions (effective period
   se přepíše v Pythonu — derive z RFA.category_proposed).
"""

from alembic import op

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. JobPosition: workplace_id ─────────────────────────────────────────
    op.execute("""
        ALTER TABLE job_positions
            ADD COLUMN workplace_id UUID REFERENCES workplaces(id) ON DELETE RESTRICT
    """)

    # Backfill: pozice bez workplace_id → první workplace v tenantu
    op.execute("""
        UPDATE job_positions jp
        SET workplace_id = (
            SELECT w.id
            FROM workplaces w
            WHERE w.tenant_id = jp.tenant_id
            ORDER BY w.created_at
            LIMIT 1
        )
        WHERE jp.workplace_id IS NULL
    """)

    # Smaž pozice, které nemohly být přiřazeny (tenant bez workplace). Tyto
    # pozice zatím nejspíš nejsou používány v produkci (MVP pre-launch).
    op.execute("""
        DELETE FROM employees
        WHERE job_position_id IN (
            SELECT id FROM job_positions WHERE workplace_id IS NULL
        )
    """)
    # Uvolni FK na smazanou pozici
    op.execute("""
        UPDATE employees SET job_position_id = NULL
        WHERE job_position_id IN (
            SELECT id FROM job_positions WHERE workplace_id IS NULL
        )
    """)
    op.execute("DELETE FROM job_positions WHERE workplace_id IS NULL")

    op.execute(
        "ALTER TABLE job_positions ALTER COLUMN workplace_id SET NOT NULL"
    )

    # Unique (tenant_id, name, workplace_id) — stejný název pozice smí existovat
    # napříč workplaces, ale v rámci jednoho workplace ne dvakrát.
    op.execute("""
        CREATE UNIQUE INDEX uq_jp_name_workplace
            ON job_positions (tenant_id, workplace_id, name)
    """)
    op.execute(
        "CREATE INDEX idx_jp_workplace ON job_positions(workplace_id)"
    )

    # Odstranit CHECK na work_category — sloupec zůstává pro legacy data,
    # ale aplikace ho přestává používat (derive z RFA).
    op.execute(
        "ALTER TABLE job_positions DROP CONSTRAINT IF EXISTS ck_jp_category"
    )

    # ── 2. RiskFactorAssessment: přidat job_position_id + 13× pdf_path ──────
    op.execute("""
        ALTER TABLE risk_factor_assessments
            ADD COLUMN job_position_id UUID REFERENCES job_positions(id) ON DELETE CASCADE,
            ADD COLUMN rf_prach_pdf_path       VARCHAR(500),
            ADD COLUMN rf_chem_pdf_path        VARCHAR(500),
            ADD COLUMN rf_hluk_pdf_path        VARCHAR(500),
            ADD COLUMN rf_vibrace_pdf_path     VARCHAR(500),
            ADD COLUMN rf_zareni_pdf_path      VARCHAR(500),
            ADD COLUMN rf_tlak_pdf_path        VARCHAR(500),
            ADD COLUMN rf_fyz_zatez_pdf_path   VARCHAR(500),
            ADD COLUMN rf_prac_poloha_pdf_path VARCHAR(500),
            ADD COLUMN rf_teplo_pdf_path       VARCHAR(500),
            ADD COLUMN rf_chlad_pdf_path       VARCHAR(500),
            ADD COLUMN rf_psych_pdf_path       VARCHAR(500),
            ADD COLUMN rf_zrak_pdf_path        VARCHAR(500),
            ADD COLUMN rf_bio_pdf_path         VARCHAR(500)
    """)

    # ── 3. Backfill RFA → JobPosition ────────────────────────────────────────
    # Pro každé (workplace_id, profese), kde neexistuje odpovídající JobPosition,
    # vytvoř ji. Poté nastav RFA.job_position_id.
    op.execute("""
        INSERT INTO job_positions (
            id, tenant_id, name, description, workplace_id, status, created_by
        )
        SELECT
            uuid_generate_v4(),
            rfa.tenant_id,
            rfa.profese,
            NULL,
            rfa.workplace_id,
            'active',
            rfa.created_by
        FROM risk_factor_assessments rfa
        WHERE NOT EXISTS (
            SELECT 1 FROM job_positions jp
            WHERE jp.tenant_id = rfa.tenant_id
              AND jp.workplace_id = rfa.workplace_id
              AND jp.name = rfa.profese
        )
    """)

    op.execute("""
        UPDATE risk_factor_assessments rfa
        SET job_position_id = jp.id
        FROM job_positions jp
        WHERE jp.tenant_id = rfa.tenant_id
          AND jp.workplace_id = rfa.workplace_id
          AND jp.name = rfa.profese
    """)

    # Po backfillu: každý RFA má job_position_id → NOT NULL + UNIQUE
    op.execute(
        "ALTER TABLE risk_factor_assessments ALTER COLUMN job_position_id SET NOT NULL"
    )
    op.execute("""
        CREATE UNIQUE INDEX uq_rfa_job_position
            ON risk_factor_assessments (job_position_id)
    """)
    op.execute(
        "CREATE INDEX idx_rfa_jp ON risk_factor_assessments(job_position_id)"
    )

    # workplace_id na RFA zůstává nullable (legacy, historie)


def downgrade() -> None:
    # 1. RFA
    op.execute("DROP INDEX IF EXISTS uq_rfa_job_position")
    op.execute("DROP INDEX IF EXISTS idx_rfa_jp")
    op.execute("""
        ALTER TABLE risk_factor_assessments
            DROP COLUMN IF EXISTS job_position_id,
            DROP COLUMN IF EXISTS rf_prach_pdf_path,
            DROP COLUMN IF EXISTS rf_chem_pdf_path,
            DROP COLUMN IF EXISTS rf_hluk_pdf_path,
            DROP COLUMN IF EXISTS rf_vibrace_pdf_path,
            DROP COLUMN IF EXISTS rf_zareni_pdf_path,
            DROP COLUMN IF EXISTS rf_tlak_pdf_path,
            DROP COLUMN IF EXISTS rf_fyz_zatez_pdf_path,
            DROP COLUMN IF EXISTS rf_prac_poloha_pdf_path,
            DROP COLUMN IF EXISTS rf_teplo_pdf_path,
            DROP COLUMN IF EXISTS rf_chlad_pdf_path,
            DROP COLUMN IF EXISTS rf_psych_pdf_path,
            DROP COLUMN IF EXISTS rf_zrak_pdf_path,
            DROP COLUMN IF EXISTS rf_bio_pdf_path
    """)

    # 2. JobPosition
    op.execute("DROP INDEX IF EXISTS uq_jp_name_workplace")
    op.execute("DROP INDEX IF EXISTS idx_jp_workplace")
    op.execute("ALTER TABLE job_positions DROP COLUMN IF EXISTS workplace_id")
    op.execute("""
        ALTER TABLE job_positions
            ADD CONSTRAINT ck_jp_category
            CHECK (work_category IN ('1','2','2R','3','4') OR work_category IS NULL)
    """)
