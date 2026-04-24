"""Role model refactor: admin + hr_manager + equipment_responsible + is_platform_admin

Revision ID: 019
Revises: 018
Create Date: 2026-04-24

CÍL:
Přejít z `ozo | manager | employee` na nový model:
- `admin`                  — platform-level (SaaS operator); spravuje tenanty.
  Pro bezpečnost je admin označen dodatečně `is_platform_admin=True`, takže
  i klasická role 'admin' v tenantu bez flagu nemá cross-tenant moc.
- `ozo`                    — tenantová všechna práva vyjma vytváření tenantů
- `hr_manager`             — renamed z `manager`; aktuálně stejná práva jako OZO,
  v budoucnu se rozdělí
- `equipment_responsible`  — zaměstnanec + správa revizí / vyhrazených zařízení
  (rozsah a permissions se řeší při revize modul refactoru)
- `employee`               — přístup jen ke svým záznamům

ZMĚNY:
1. Rename existujících `users.role='manager'` → `hr_manager`
2. CHECK constraint na role (5 hodnot)
3. Nový sloupec users.is_platform_admin BOOLEAN NOT NULL DEFAULT FALSE
4. Nová RLS policy `platform_admin_bypass` na všech tenantovaných tabulkách
   (kromě users/audit_log kde `superadmin_bypass` už existuje).
   Aplikace setuje `app.is_platform_admin='true'` v dependencies.get_current_user
   pokud přihlášený user má is_platform_admin=True.

IDEMPOTENCE:
Migrace běží jednou. Role rename se provede jen pokud existují `manager` řádky.
"""

from alembic import op

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


# Tabulky s tenant_id + existující RLS (z migrací 001-014+016), kde chceme
# doplnit platform_admin bypass policy.
_PLATFORM_ADMIN_TABLES = [
    "tenants",         # speciálně: tenants nemá tenant_id, přidáme policy ručně
    "users",
    "audit_log",
    "risks",
    "trainings",
    "revisions",
    "accident_reports",
    "oopp_assignments",
    "employees",
    "plants",
    "workplaces",
    "risk_factor_assessments",
    "job_positions",
    "medical_exams",
    "refresh_tokens",
    "password_reset_tokens",
    "recovery_codes",
]


def upgrade() -> None:
    # 1) Rename role values
    op.execute("UPDATE users SET role='hr_manager' WHERE role='manager'")

    # 2) CHECK constraint na role (ujistíme se že stávající drop neexistuje)
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_role")
    op.execute("""
        ALTER TABLE users
        ADD CONSTRAINT ck_users_role
        CHECK (role IN ('admin','ozo','hr_manager','equipment_responsible','employee'))
    """)

    # 3) is_platform_admin flag
    op.execute(
        "ALTER TABLE users ADD COLUMN is_platform_admin BOOLEAN NOT NULL DEFAULT FALSE"
    )

    # 4) platform_admin_bypass RLS policy napříč tabulkami.
    #    Speciální handling pro tenants (nemá tenant_id, ale má RLS ne-enabled zatím).
    #    Nejprve aktivujeme RLS na tenants pokud neběží.
    op.execute("ALTER TABLE tenants ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenants FORCE ROW LEVEL SECURITY")

    op.execute("""
        CREATE POLICY tenant_self_access ON tenants
            USING (id = current_setting('app.current_tenant_id', TRUE)::UUID)
    """)
    op.execute("""
        CREATE POLICY superadmin_bypass ON tenants
            USING (current_setting('app.is_superadmin', TRUE) = 'true')
    """)

    # platform_admin_bypass na všech _PLATFORM_ADMIN_TABLES
    for table in _PLATFORM_ADMIN_TABLES:
        op.execute(f"""
            CREATE POLICY platform_admin_bypass ON {table}
                USING (current_setting('app.is_platform_admin', TRUE) = 'true')
        """)

    # GRANTy pro bozoapp_app, pokud ještě nemá přístup k tenants (měl by z 015)
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON tenants TO bozoapp_app")


def downgrade() -> None:
    # Drop platform_admin_bypass policies
    for table in _PLATFORM_ADMIN_TABLES:
        op.execute(f"DROP POLICY IF EXISTS platform_admin_bypass ON {table}")

    # Tenants zpět: drop policies, disable RLS
    op.execute("DROP POLICY IF EXISTS tenant_self_access ON tenants")
    op.execute("DROP POLICY IF EXISTS superadmin_bypass ON tenants")
    op.execute("ALTER TABLE tenants DISABLE ROW LEVEL SECURITY")

    # Drop is_platform_admin
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS is_platform_admin")

    # Drop CHECK constraint
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_role")

    # Revert role rename
    op.execute("UPDATE users SET role='manager' WHERE role='hr_manager'")
