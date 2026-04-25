"""Platform admin: users.username + is_platform_admin

Revision ID: 033
Revises: 032
Create Date: 2026-04-25

DESIGN:
Platform admin (super-admin) je samostatný typ uživatele odděleny od běžných
tenant rolí. Slouží pro provozovatele SaaS platformy ke správě tenantů,
sledování počtu zákazníků (employees), nastavování globálních pravidel
(prohlídky, školení) a billing rozhodnutí.

Klíčové vlastnosti:
- Loguje se přes `username` (krátký řetězec, ne email)
- Má `is_platform_admin = True`
- Nemá běžný tenant — může mít pseudo-tenant nebo NULL (model už pravděpodobně
  vyžaduje tenant_id NOT NULL, takže ponecháme tenant_id na nějakém systémovém
  tenantu, ale logika ignoruje toto omezení skrze is_platform_admin flag)
- RLS bypass: dotazy z admin endpointů vypisuji všechny tenants
- Audit: každý přístup je logován s admin_user_id
"""

from alembic import op

revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Sloupec is_platform_admin už existuje od migrace 019 (role refactor).
    # Tato migrace pouze přidá username login pro platform admina.
    op.execute("""
        ALTER TABLE users ADD COLUMN username VARCHAR(50)
    """)
    # Username je unikátní napříč tenantů (na rozdíl od email který je per-tenant)
    op.execute("""
        CREATE UNIQUE INDEX uq_users_username
        ON users (username)
        WHERE username IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_users_username")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS username")
