"""Platform settings: globální key-value konfigurace

Revision ID: 034
Revises: 033
Create Date: 2026-04-25

DESIGN:
Globální nastavení napříč všemi tenants (např. lhůty preventivních prohlídek
podle kategorie + věku, mapování rizikových faktorů → odborné prohlídky).

Klíčové vlastnosti:
- key VARCHAR PK (např. "medical_exam.periodicity")
- value JSONB (libovolná struktura)
- description TEXT pro UI
- updated_by FK na users (audit)
- BEZ tenant_id — jeden záznam = globální platnost
- BEZ RLS — jen platform admin čte/zapisuje (kontrola na app vrstvě)

Při startupu app se nastavení nahraje do paměti (cache invalidovaný při PATCH),
aby se nevolal DB dotaz pro každý create_medical_exam.
"""

from alembic import op

revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE platform_settings (
            key          VARCHAR(100) PRIMARY KEY,
            value        JSONB NOT NULL,
            description  TEXT,
            updated_by   UUID REFERENCES users(id) ON DELETE SET NULL,
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    # Inicializuj výchozí hodnoty (zrcadlí konstanty z kódu před migrací)
    # 1) Lhůty preventivních prohlídek per kategorie + věk
    op.execute("""
        INSERT INTO platform_settings (key, value, description) VALUES
        ('medical_exam.periodicity_months',
         '{
            "1":  {"under_50": null, "over_50": null},
            "2":  {"under_50": 48,   "over_50": 24},
            "2R": {"under_50": 24,   "over_50": 24},
            "3":  {"under_50": 24,   "over_50": 24},
            "4":  {"under_50": 12,   "over_50": 12}
          }'::jsonb,
         'Lhůta periodické prohlídky v měsících podle kategorie práce a věku zaměstnance (NV 79/2013 Sb.). null = dobrovolná.')
    """)

    # 2) Mapování rizikový faktor → odborná vyšetření
    op.execute("""
        INSERT INTO platform_settings (key, value, description) VALUES
        ('medical_exam.factor_to_specialties',
         '{
            "rf_hluk":      ["audiometrie"],
            "rf_prach":     ["spirometrie", "rtg_plic"],
            "rf_chem":      ["spirometrie"],
            "rf_vibrace":   ["prstova_plethysmografie"],
            "rf_psych":     ["ekg_klidove"],
            "rf_fyz_zatez": ["ekg_klidove"],
            "rf_zrak":      ["ocni_vysetreni"]
          }'::jsonb,
         'Které odborné prohlídky se přiřadí podle rizikového faktoru pozice. Faktory s ratingem 1 se ignorují (žádné riziko).')
    """)

    # 3) Periodicita odborných prohlídek per specialty + kategorie
    op.execute("""
        INSERT INTO platform_settings (key, value, description) VALUES
        ('medical_exam.specialty_periodicity_months',
         '{
            "audiometrie":             {"2": 48, "2R": 24, "3": 24, "4": 12},
            "spirometrie":             {"2": 48, "2R": 24, "3": 24, "4": 12},
            "prstova_plethysmografie": {"2": 48, "2R": 24, "3": 24},
            "ekg_klidove":             {},
            "ocni_vysetreni":          {"2": 48, "2R": 24, "3": 24, "4": 24},
            "rtg_plic":                {"2R": 36, "3": 36, "4": 24},
            "psychotesty":             {}
          }'::jsonb,
         'Periodicita odborného vyšetření v měsících podle ratingu rizikového faktoru, který ho vyvolal.')
    """)

    # 4) Varovací okno pro expirující prohlídky (dashboard alert)
    op.execute("""
        INSERT INTO platform_settings (key, value, description) VALUES
        ('medical_exam.expiring_soon_days',
         '60'::jsonb,
         'Kolik dní předem upozornit na blížící se vypršení lékařské prohlídky.')
    """)

    # 5) Throttle pro auto-generaci prohlídek (minuty)
    op.execute("""
        INSERT INTO platform_settings (key, value, description) VALUES
        ('medical_exam.auto_check_throttle_minutes',
         '30'::jsonb,
         'Minimální počet minut mezi opakovanou auto-generací prohlídek pro stejného zaměstnance.')
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS platform_settings")
