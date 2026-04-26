"""Reminder settings: platform_settings pro email upozornění

Revision ID: 040
Revises: 039
Create Date: 2026-04-26

DESIGN:
Globální nastavení pro email reminders napříč moduly. V1 jsou globální
(stejné pro všechny tenanty). Per-tenant override můžeme přidat později
přidáním tabulky tenant_settings, ale pro 5-10 klientů stačí globální.

Pokrývá:
- Frekvenci (cron expression)
- Prahy v dnech pro každý modul (training, medical_exam, accident_followup)
- Master switch (on/off)
- Příjemci (managers, equipment_responsible)
"""

from alembic import op

revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO platform_settings (key, value, description, updated_at)
        VALUES
            ('reminders.enabled',
             'true'::jsonb,
             'Master switch pro všechny email reminders. Vypnout = žádné maily.',
             NOW()),
            ('reminders.cron_schedule',
             '"0 5 * * MON"'::jsonb,
             'Cron expression pro spouštění (default: pondělí 5:00). '
             'Přepsání má smysl jen když si admin pustí systemd timer s vlastním schedule.',
             NOW()),
            ('reminders.thresholds.training',
             '[30, 14, 7]'::jsonb,
             'Prahy v dnech před expirací školení, kdy poslat upozornění. '
             'Ke každému prahu se připočítají i už propadlé záznamy.',
             NOW()),
            ('reminders.thresholds.medical_exam',
             '[30, 14, 7]'::jsonb,
             'Prahy v dnech před expirací lékařské prohlídky.',
             NOW()),
            ('reminders.thresholds.accident_followup',
             '[14, 7, 0]'::jsonb,
             'Prahy v dnech před deadline akcí v akčním plánu úrazů. '
             '0 = pošli upozornění v den deadline.',
             NOW()),
            ('reminders.send_to_managers',
             'true'::jsonb,
             'Posílat agregovaný email OZO + HR manažerům? Standardně ano.',
             NOW()),
            ('reminders.send_to_equipment_responsible',
             'true'::jsonb,
             'Posílat reminders zaměstnancům s rolí equipment_responsible '
             'o jejich přiřazených OOPP/revizi?',
             NOW()),
            ('reminders.last_run_at',
             'null'::jsonb,
             'Časové razítko posledního běhu reminders cronu (ISO 8601). '
             'Aktualizuje cron, slouží pro monitoring v admin UI.',
             NOW())
        ON CONFLICT (key) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM platform_settings
        WHERE key IN (
            'reminders.enabled',
            'reminders.cron_schedule',
            'reminders.thresholds.training',
            'reminders.thresholds.medical_exam',
            'reminders.thresholds.accident_followup',
            'reminders.send_to_managers',
            'reminders.send_to_equipment_responsible',
            'reminders.last_run_at'
        )
    """)
