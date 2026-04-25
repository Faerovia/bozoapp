"""Manuální fakturace: invoices tabulka + tenant billing údaje + platform issuer

Revision ID: 039
Revises: 038
Create Date: 2026-04-25

DESIGN:
- `tenants` rozšířeny o billing údaje příjemce (firma, IČO, DIČ, adresa, email)
- nová tabulka `invoices` s items v JSONB, statusy draft/sent/paid/cancelled
- RLS: tenant vidí jen své faktury, superadmin_bypass pro platform admin
- Sequence pro generování čísla faktury per rok (yyyy_seq)
- Defaultní platform_settings: issuer_* placeholders, is_vat_payer=false,
  vat_rate=21, invoice_due_days=14, invoice_number_format='{year}{seq:04d}'
"""

from alembic import op

revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── tenant billing údaje příjemce ────────────────────────────────────────
    op.execute("""
        ALTER TABLE tenants
            ADD COLUMN billing_company_name   VARCHAR(255),
            ADD COLUMN billing_ico            VARCHAR(20),
            ADD COLUMN billing_dic            VARCHAR(20),
            ADD COLUMN billing_address_street VARCHAR(255),
            ADD COLUMN billing_address_city   VARCHAR(100),
            ADD COLUMN billing_address_zip    VARCHAR(10),
            ADD COLUMN billing_email          VARCHAR(255)
    """)

    # ── invoices tabulka ─────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE invoices (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
            invoice_number  VARCHAR(20) NOT NULL UNIQUE,

            -- časové údaje
            issued_at       DATE NOT NULL,
            due_date        DATE NOT NULL,
            period_from     DATE NOT NULL,
            period_to       DATE NOT NULL,
            paid_at         DATE,
            sent_at         TIMESTAMPTZ,

            -- stav
            status          VARCHAR(20) NOT NULL DEFAULT 'draft',
            CONSTRAINT ck_invoice_status CHECK (
                status IN ('draft', 'sent', 'paid', 'cancelled')
            ),

            -- finance
            currency        VARCHAR(3) NOT NULL DEFAULT 'CZK',
            subtotal        NUMERIC(12, 2) NOT NULL,
            vat_rate        NUMERIC(5, 2) NOT NULL DEFAULT 0,
            vat_amount      NUMERIC(12, 2) NOT NULL DEFAULT 0,
            total           NUMERIC(12, 2) NOT NULL,

            -- snapshot vystavovatele (firma se může změnit, faktura ne)
            issuer_snapshot JSONB NOT NULL,
            -- snapshot příjemce (tenant)
            recipient_snapshot JSONB NOT NULL,
            -- položky [{description, quantity, unit, unit_price, total}, ...]
            items           JSONB NOT NULL,

            notes           TEXT,
            pdf_path        VARCHAR(500),

            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_by      UUID REFERENCES users(id) ON DELETE SET NULL
        )
    """)

    op.execute("CREATE INDEX idx_invoices_tenant ON invoices(tenant_id)")
    op.execute("CREATE INDEX idx_invoices_status ON invoices(tenant_id, status)")
    op.execute("CREATE INDEX idx_invoices_issued ON invoices(issued_at DESC)")
    op.execute(
        "CREATE INDEX idx_invoices_due ON invoices(due_date) "
        "WHERE status IN ('draft', 'sent')"
    )

    # ── RLS na invoices ──────────────────────────────────────────────────────
    op.execute("ALTER TABLE invoices ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE invoices FORCE ROW LEVEL SECURITY")

    op.execute("""
        CREATE POLICY tenant_isolation ON invoices
        USING (
            tenant_id = NULLIF(
                current_setting('app.current_tenant_id', TRUE), ''
            )::UUID
        )
        WITH CHECK (
            tenant_id = NULLIF(
                current_setting('app.current_tenant_id', TRUE), ''
            )::UUID
        )
    """)
    op.execute("""
        CREATE POLICY superadmin_bypass ON invoices
        USING (current_setting('app.is_superadmin', TRUE) = 'true')
        WITH CHECK (current_setting('app.is_superadmin', TRUE) = 'true')
    """)

    # ── Sequence pro číslo faktury (per rok) ─────────────────────────────────
    # Nepoužívám PG sequence (per-rok reset by byl nepříjemný), místo toho
    # tabulka invoice_counters s row-lock per rok.
    op.execute("""
        CREATE TABLE invoice_counters (
            year       INTEGER PRIMARY KEY,
            last_seq   INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # ── Defaultní platform_settings ──────────────────────────────────────────
    op.execute("""
        INSERT INTO platform_settings (key, value, description, updated_at)
        VALUES
            ('issuer_name',        '"BOZOapp s.r.o."'::jsonb,
             'Název vystavovatele faktur (tvoje firma).',
             NOW()),
            ('issuer_ico',         '""'::jsonb,
             'IČO vystavovatele (8 číslic).',
             NOW()),
            ('issuer_dic',         '""'::jsonb,
             'DIČ vystavovatele (CZ + IČO).',
             NOW()),
            ('issuer_address_street', '""'::jsonb,
             'Ulice a č.p. vystavovatele.',
             NOW()),
            ('issuer_address_city',   '""'::jsonb,
             'Město vystavovatele.',
             NOW()),
            ('issuer_address_zip',    '""'::jsonb,
             'PSČ vystavovatele.',
             NOW()),
            ('issuer_bank_account',   '""'::jsonb,
             'Číslo účtu vystavovatele (např. 123456789/0100).',
             NOW()),
            ('issuer_bank_name',      '""'::jsonb,
             'Název banky vystavovatele.',
             NOW()),
            ('issuer_iban',           '""'::jsonb,
             'IBAN vystavovatele (pro EU platby).',
             NOW()),
            ('issuer_swift',          '""'::jsonb,
             'SWIFT/BIC vystavovatele.',
             NOW()),
            ('issuer_email',          '""'::jsonb,
             'Kontaktní email vystavovatele (pro dotazy k fakturám).',
             NOW()),
            ('is_vat_payer',          'false'::jsonb,
             'Je vystavovatel plátcem DPH? Po překročení obratu přepni na true.',
             NOW()),
            ('vat_rate',              '21'::jsonb,
             'Sazba DPH v % (pro plátce DPH).',
             NOW()),
            ('invoice_due_days',      '14'::jsonb,
             'Splatnost faktury ve dnech od vystavení.',
             NOW()),
            ('invoice_number_format', '"{year}{seq:04d}"'::jsonb,
             'Formát čísla faktury. Placeholdery: {year}, {seq:04d}.',
             NOW()),
            ('invoice_footer_note',   '"Děkujeme za spolupráci."'::jsonb,
             'Pata faktury — text pod položkami.',
             NOW())
        ON CONFLICT (key) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM platform_settings WHERE key IN (" + ",".join(f"'{k}'" for k in [
        "issuer_name", "issuer_ico", "issuer_dic",
        "issuer_address_street", "issuer_address_city", "issuer_address_zip",
        "issuer_bank_account", "issuer_bank_name", "issuer_iban", "issuer_swift",
        "issuer_email", "is_vat_payer", "vat_rate",
        "invoice_due_days", "invoice_number_format", "invoice_footer_note",
    ]) + ")")

    op.execute("DROP TABLE IF EXISTS invoice_counters")

    op.execute("DROP POLICY IF EXISTS superadmin_bypass ON invoices")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON invoices")
    op.execute("DROP TABLE IF EXISTS invoices CASCADE")

    op.execute("""
        ALTER TABLE tenants
            DROP COLUMN IF EXISTS billing_email,
            DROP COLUMN IF EXISTS billing_address_zip,
            DROP COLUMN IF EXISTS billing_address_city,
            DROP COLUMN IF EXISTS billing_address_street,
            DROP COLUMN IF EXISTS billing_dic,
            DROP COLUMN IF EXISTS billing_ico,
            DROP COLUMN IF EXISTS billing_company_name
    """)
