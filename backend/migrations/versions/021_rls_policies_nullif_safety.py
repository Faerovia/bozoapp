"""RLS policies: NULLIF safety wrap proti prázdnému current_setting

Revision ID: 021
Revises: 020
Create Date: 2026-04-24

PROBLÉM:
Všechny `tenant_isolation` policies používají
    USING (tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID)

Když app flow zavolá `set_config('app.is_superadmin', 'true', true)` bez nastavení
`app.current_tenant_id`, PG `current_setting(..., TRUE)` vrátí buď NULL nebo
prázdný string. Cast prázdného stringu na UUID selže s
`invalid input syntax for type uuid: ""` a CELÝ SELECT padne (i když by
superadmin_bypass mel projít přes OR permissive policy).

Konkrétní reprodukce: `POST /auth/login` → set_config(is_superadmin, true) →
SELECT users WHERE email=... → RLS evaluates tenant_isolation USING → UUID
cast na "" → 500.

ŘEŠENÍ:
Wrap cast v `NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID`.
NULLIF vrátí NULL pro prázdný string; NULL porovnání s tenant_id je FALSE
(což je OK pro permissive policy), žádný cast error.

TABULKY:
Všechny tenantované tabulky s tenant_isolation policy. Tenants má
tenant_self_access (id = ...) — taky se musí fixnout.
"""

from alembic import op

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


# (tabulka, název policy, sloupec který porovnáváme se setting-em)
# Pro tenants to je `id`, pro ostatní `tenant_id`.
_POLICIES: list[tuple[str, str, str]] = [
    ("tenants",                  "tenant_self_access",  "id"),
    ("users",                    "tenant_isolation",    "tenant_id"),
    ("audit_log",                "tenant_isolation",    "tenant_id"),
    ("risks",                    "tenant_isolation",    "tenant_id"),
    ("trainings",                "tenant_isolation",    "tenant_id"),
    ("revisions",                "tenant_isolation",    "tenant_id"),
    ("accident_reports",         "tenant_isolation",    "tenant_id"),
    ("oopp_assignments",         "tenant_isolation",    "tenant_id"),
    ("employees",                "tenant_isolation",    "tenant_id"),
    ("plants",                   "tenant_isolation",    "tenant_id"),
    ("workplaces",               "tenant_isolation",    "tenant_id"),
    ("risk_factor_assessments",  "tenant_isolation",    "tenant_id"),
    ("job_positions",            "tenant_isolation",    "tenant_id"),
    ("medical_exams",            "tenant_isolation",    "tenant_id"),
    ("refresh_tokens",           "tenant_isolation",    "tenant_id"),
    ("password_reset_tokens",    "tenant_isolation",    "tenant_id"),
    ("recovery_codes",           "tenant_isolation",    "tenant_id"),
]


def upgrade() -> None:
    for table, policy_name, column in _POLICIES:
        op.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table}")
        op.execute(f"""
            CREATE POLICY {policy_name} ON {table}
                USING (
                    {column} = NULLIF(
                        current_setting('app.current_tenant_id', TRUE), ''
                    )::UUID
                )
        """)


def downgrade() -> None:
    for table, policy_name, column in _POLICIES:
        op.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table}")
        op.execute(f"""
            CREATE POLICY {policy_name} ON {table}
                USING (
                    {column} = current_setting('app.current_tenant_id', TRUE)::UUID
                )
        """)
