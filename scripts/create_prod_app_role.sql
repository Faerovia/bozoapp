-- ════════════════════════════════════════════════════════════════════════════
-- create_prod_app_role.sql
--
-- Vytvoří produkční DB roli `bozoapp_app` se secure passwordem.
-- Spusť JEDNOU před prvním `alembic upgrade head` v produkci.
--
-- Usage:
--   export APP_PASSWORD='...'   # secure random, min 24 chars
--   docker compose exec -T db psql -U bozoapp -d bozoapp_prod \
--     -v pwd="'$APP_PASSWORD'" -f scripts/create_prod_app_role.sql
--
-- Poznámka: migrace 015 obsahuje DO block, který VYTVOŘÍ roli bozoapp_app s
-- default heslem 'bozoapp_app_dev_secret' pokud ještě neexistuje. V produkci
-- chceš, aby TENTO skript roli vytvořil DŘÍV se secure passwordem — pak
-- migrace jen doplní GRANTy (IF NOT EXISTS skip).
-- ════════════════════════════════════════════════════════════════════════════

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT FROM pg_catalog.pg_roles WHERE rolname = 'bozoapp_app'
    ) THEN
        EXECUTE format('CREATE ROLE bozoapp_app WITH LOGIN PASSWORD %L', :pwd);
        RAISE NOTICE 'Created role bozoapp_app';
    ELSE
        -- Pokud role existuje, update password (bezpečné pro rotaci)
        EXECUTE format('ALTER ROLE bozoapp_app WITH PASSWORD %L', :pwd);
        RAISE NOTICE 'Updated password for existing role bozoapp_app';
    END IF;
END
$$;

-- GRANTy se stanou v migraci 015 automaticky, když spustíš `alembic upgrade head`.
