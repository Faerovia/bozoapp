"""Lékařské prohlídky: kategorizace, odborné prohlídky, upload zprávy

Revision ID: 030
Revises: 029
Create Date: 2026-04-25

Rozdělení na preventivní vs. odborné prohlídky:
  - exam_category   = 'preventivni' | 'odborna'
  - specialty       = volný string identifikující typ odborné prohlídky
                      (audiometrie, spirometrie, prstova_plethysmografie,
                       ekg_klidove, ocni, rtg_plic, psychotesty)
  - report_path     = relativní cesta k uploadnuté zprávě (PDF/sken),
                      povinná dokumentace dle vyhlášky 79/2013 Sb.

Migrace nastavuje exam_category='preventivni' u všech existujících záznamů
(předpokládáme, že před tímto release byly výhradně preventivní typy).
"""

from alembic import op

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE medical_exams
            ADD COLUMN exam_category VARCHAR(20) NOT NULL DEFAULT 'preventivni',
            ADD COLUMN specialty VARCHAR(50),
            ADD COLUMN report_path VARCHAR(500),
            ADD CONSTRAINT ck_me_exam_category
                CHECK (exam_category IN ('preventivni', 'odborna')),
            ADD CONSTRAINT ck_me_specialty_when_odborna
                CHECK (
                    (exam_category = 'odborna' AND specialty IS NOT NULL)
                    OR exam_category = 'preventivni'
                )
    """)
    # Pro preventivni necháme exam_type validní (vstupni/periodicka/...)
    # Pro odborne typ přepneme na 'odborna' aby check_exam_type prošel —
    # rozšíříme constraint ck_me_exam_type
    op.execute("""
        ALTER TABLE medical_exams DROP CONSTRAINT IF EXISTS ck_me_exam_type
    """)
    op.execute("""
        ALTER TABLE medical_exams
            ADD CONSTRAINT ck_me_exam_type
            CHECK (exam_type IN (
                'vstupni','periodicka','vystupni','mimoradna','odborna'
            ))
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE medical_exams
            DROP CONSTRAINT IF EXISTS ck_me_specialty_when_odborna,
            DROP CONSTRAINT IF EXISTS ck_me_exam_category,
            DROP CONSTRAINT IF EXISTS ck_me_exam_type
    """)
    op.execute("""
        ALTER TABLE medical_exams
            ADD CONSTRAINT ck_me_exam_type
            CHECK (exam_type IN ('vstupni','periodicka','vystupni','mimoradna'))
    """)
    op.execute("""
        ALTER TABLE medical_exams
            DROP COLUMN IF EXISTS report_path,
            DROP COLUMN IF EXISTS specialty,
            DROP COLUMN IF EXISTS exam_category
    """)
