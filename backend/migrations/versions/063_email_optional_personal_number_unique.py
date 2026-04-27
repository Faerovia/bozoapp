"""email optional + personal_number unique per tenant (subdomain login)

Revision ID: 063
Revises: 062
Create Date: 2026-04-27

Důvod (#subdomain login):
Subdomain-based login model umožňuje přihlášení přes osobní číslo
zaměstnance. Email už není povinný — uživatel se může přihlásit:
1. Emailem (pokud ho má v users.email)
2. Osobním číslem (přes employees.personal_number → user_id)
3. Username (jen platform admin, globálně unikátní)

Změny:
- users.email NULLABLE (zaměstnanec bez emailu má jen personal_number)
- users (tenant_id, email) UNIQUE — partial index, nově ignoruje NULL
- employees (tenant_id, personal_number) UNIQUE — partial index
  (NULL personal_number znamená neeviduje se, např. brigádník bez čísla)

Stávající `UNIQUE (tenant_id, email)` constraint v 001 nelze prostě
zachovat protože některé řádky budou mít NULL email — Postgres `UNIQUE`
constraint NULL netreatuje jako duplicate, ale lepší je explicitní
partial unique index.
"""

from alembic import op

revision = "063"
down_revision = "062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) email nullable
    op.execute("ALTER TABLE users ALTER COLUMN email DROP NOT NULL")

    # 2) Drop původní UNIQUE constraint na (tenant_id, email).
    #    Konstraint v 001 je inline UNIQUE(tenant_id, email) — Postgres mu dá
    #    auto-generovaný název (typicky users_tenant_id_email_key).
    op.execute("""
        DO $$
        DECLARE
            cn TEXT;
        BEGIN
            SELECT conname INTO cn
            FROM pg_constraint
            WHERE conrelid = 'users'::regclass
              AND contype = 'u'
              AND pg_get_constraintdef(oid) ILIKE 'UNIQUE (tenant_id, email)';
            IF cn IS NOT NULL THEN
                EXECUTE format('ALTER TABLE users DROP CONSTRAINT %I', cn);
            END IF;
        END $$
    """)

    # 3) Partial unique index: jen non-null emaily
    op.execute("""
        CREATE UNIQUE INDEX uq_users_tenant_email
        ON users (tenant_id, email)
        WHERE email IS NOT NULL
    """)

    # 4) employees: per-tenant unique personal_number (partial pro NULL)
    op.execute("""
        CREATE UNIQUE INDEX uq_employees_tenant_personal_number
        ON employees (tenant_id, personal_number)
        WHERE personal_number IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_employees_tenant_personal_number")
    op.execute("DROP INDEX IF EXISTS uq_users_tenant_email")
    # Pozor: bez NOT NULL ENforcementu nelze přidat zpět původní UNIQUE
    # constraint, takže downgrade je lossy.
    op.execute("""
        ALTER TABLE users
        ADD CONSTRAINT users_tenant_email_unique UNIQUE (tenant_id, email)
    """)
    op.execute("ALTER TABLE users ALTER COLUMN email SET NOT NULL")
