-- ============================================================
-- Aegis Quant AI — PostgreSQL initialization script
-- Run once on a fresh cluster:
--   psql -U postgres -f database/postgres/init.sql
-- ============================================================

-- Application role (adjust password via environment)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aegis') THEN
        CREATE ROLE aegis LOGIN PASSWORD 'changeme';
    END IF;
END$$;

-- Application database
SELECT 'CREATE DATABASE aegis_quant OWNER aegis'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'aegis_quant')\gexec

\c aegis_quant

-- Run schema
\i database/postgres/schema.sql
