"""Audit log partitioning (RANGE by month)

Revision ID: 017
Revises: 016
Create Date: 2026-04-24

MOTIVACE:
audit_log je append-only tabulka která roste monotónně. Za pár měsíců
může mít desítky milionů řádků. Bez partitioningu bude:
- indexy stále pomalejší
- DELETE retence (5 let) vyžaduje full table scan + VACUUM
- SELECT za období skenuje víc než potřeba

ŘEŠENÍ:
PostgreSQL declarative partitioning RANGE by `created_at` month. Každý měsíc
jedna partition. Retence = DROP TABLE té partition (O(1)).

IMPLEMENTACE:
1. Přejmenovat existující `audit_log` → `audit_log_legacy` (drží stará data).
2. Vytvořit nový `audit_log` jako partitioned (parent bez dat).
3. Vytvořit default partition pro minulost (catch-all) + partitions pro
   current + next month.
4. Překopírovat data z legacy do nové tabulky (partitions si vyberou samy).
5. Drop legacy.

Pro automatické vytváření budoucích partitions: APP-level cron volá
`ensure_monthly_partition()` (nebo pg_cron, pokud je k dispozici). Zde
jen seedneme current + next.

POZOR:
- Partitioning v PG vyžaduje aby sloupce partition key byly součástí primary
  key. `audit_log.id` je BIGSERIAL (original PK). Musí se rozšířit na
  composite PK (id, created_at).
- SERIAL/IDENTITY nad partitioned table funguje jen s nextval('seq'); parent
  nemůže mít IDENTITY column. Použijeme DEFAULT nextval().
"""

from alembic import op

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Přejmenuj existující tabulku. Policies a indexy jdou s ní, ale
    #    zachovávají si původní jména — pro nové objekty pod stejným jménem
    #    je přejmenujeme.
    op.execute("ALTER TABLE audit_log RENAME TO audit_log_legacy")

    # BIGSERIAL z migrace 001 vytvořil sekvenci "audit_log_id_seq" automaticky.
    op.execute("ALTER SEQUENCE audit_log_id_seq RENAME TO audit_log_legacy_id_seq")

    # Indexy z migrace 001 si zachovávají jména — rename aby nekolidovaly
    # s identickými jmény v nové tabulce.
    op.execute("ALTER INDEX idx_audit_tenant_id RENAME TO idx_audit_tenant_id_legacy")
    op.execute("ALTER INDEX idx_audit_resource RENAME TO idx_audit_resource_legacy")
    op.execute("ALTER INDEX idx_audit_created_at RENAME TO idx_audit_created_at_legacy")

    # 2) Vytvoř sequence explicitně (nechceme SERIAL na parent partition).
    op.execute("CREATE SEQUENCE audit_log_id_seq")

    # 3) Nová partitioned tabulka (PK = id + created_at, kvůli partition key).
    op.execute("""
        CREATE TABLE audit_log (
            id            BIGINT NOT NULL DEFAULT nextval('audit_log_id_seq'),
            tenant_id     UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            user_id       UUID REFERENCES users(id) ON DELETE SET NULL,
            action        VARCHAR(50) NOT NULL,
            resource_type VARCHAR(100) NOT NULL,
            resource_id   VARCHAR(255),
            old_values    JSONB,
            new_values    JSONB,
            ip_address    INET,
            user_agent    TEXT,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at)
    """)

    op.execute("ALTER SEQUENCE audit_log_id_seq OWNED BY audit_log.id")

    # Indexy (vytvářejí se automaticky i na partitions když je budeme přidávat)
    op.execute("CREATE INDEX idx_audit_tenant_id ON audit_log(tenant_id)")
    op.execute(
        "CREATE INDEX idx_audit_resource "
        "ON audit_log(tenant_id, resource_type, resource_id)"
    )
    op.execute("CREATE INDEX idx_audit_created_at ON audit_log(created_at)")

    # RLS
    op.execute("ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_log FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON audit_log
            USING (tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID)
    """)
    op.execute("""
        CREATE POLICY superadmin_bypass ON audit_log
            USING (current_setting('app.is_superadmin', TRUE) = 'true')
    """)

    # 4) Default partition pro data mimo aktuální okno (starší řádky z legacy)
    op.execute("""
        CREATE TABLE audit_log_default PARTITION OF audit_log DEFAULT
    """)

    # Current month + next month jako explicit partitions
    # (použijeme date_trunc na server-side pro konzistenci)
    op.execute("""
        DO $$
        DECLARE
            start_curr DATE := date_trunc('month', CURRENT_DATE)::DATE;
            start_next DATE := (date_trunc('month', CURRENT_DATE) + INTERVAL '1 month')::DATE;
            start_after DATE := (date_trunc('month', CURRENT_DATE) + INTERVAL '2 month')::DATE;
            partition_curr TEXT := 'audit_log_' || to_char(start_curr, 'YYYY_MM');
            partition_next TEXT := 'audit_log_' || to_char(start_next, 'YYYY_MM');
        BEGIN
            EXECUTE format(
                'CREATE TABLE %I PARTITION OF audit_log FOR VALUES FROM (%L) TO (%L)',
                partition_curr, start_curr, start_next
            );
            EXECUTE format(
                'CREATE TABLE %I PARTITION OF audit_log FOR VALUES FROM (%L) TO (%L)',
                partition_next, start_next, start_after
            );
        END $$;
    """)

    # 5) Překopíruj data z legacy (partitions si vyberou samy podle created_at,
    #    data mimo budou v default partition)
    op.execute("""
        INSERT INTO audit_log (
            id, tenant_id, user_id, action, resource_type, resource_id,
            old_values, new_values, ip_address, user_agent, created_at
        )
        SELECT
            id, tenant_id, user_id, action, resource_type, resource_id,
            old_values, new_values, ip_address, user_agent, created_at
        FROM audit_log_legacy
    """)

    # Aktualizuj sequence aby další INSERT navazoval
    op.execute("""
        SELECT setval(
            'audit_log_id_seq',
            COALESCE((SELECT MAX(id) FROM audit_log), 1),
            true
        )
    """)

    # 6) Drop legacy
    op.execute("DROP TABLE audit_log_legacy")

    # GRANT pro bozoapp_app (partitions dědí grants z parent)
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON audit_log TO bozoapp_app"
    )
    op.execute("GRANT USAGE, SELECT ON audit_log_id_seq TO bozoapp_app")


def downgrade() -> None:
    # Downgrade: zkopíruj data zpět do non-partitioned a dropni partitions.
    # Přejmenuj partitioned table + sekvenci + indexy aby neblokovaly.
    op.execute("ALTER TABLE audit_log RENAME TO audit_log_partitioned")
    op.execute("ALTER SEQUENCE audit_log_id_seq RENAME TO audit_log_partitioned_id_seq")
    op.execute("ALTER INDEX idx_audit_tenant_id RENAME TO idx_audit_tenant_id_partitioned")
    op.execute("ALTER INDEX idx_audit_resource RENAME TO idx_audit_resource_partitioned")
    op.execute("ALTER INDEX idx_audit_created_at RENAME TO idx_audit_created_at_partitioned")

    op.execute("""
        CREATE TABLE audit_log (
            id            BIGSERIAL PRIMARY KEY,
            tenant_id     UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            user_id       UUID REFERENCES users(id) ON DELETE SET NULL,
            action        VARCHAR(50)  NOT NULL,
            resource_type VARCHAR(100) NOT NULL,
            resource_id   VARCHAR(255),
            old_values    JSONB,
            new_values    JSONB,
            ip_address    INET,
            user_agent    TEXT,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        INSERT INTO audit_log (
            tenant_id, user_id, action, resource_type, resource_id,
            old_values, new_values, ip_address, user_agent, created_at
        )
        SELECT
            tenant_id, user_id, action, resource_type, resource_id,
            old_values, new_values, ip_address, user_agent, created_at
        FROM audit_log_partitioned
    """)

    op.execute("DROP TABLE audit_log_partitioned CASCADE")
    # audit_log_partitioned_id_seq byl OWNED BY dropnuté sloupec → zmizí s DROP TABLE
