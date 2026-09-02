\set ON_ERROR_STOP on

-- Production role provisioning is intentionally idempotent.
-- Role names are identifier-quoted with format(%I); passwords use format(%L).

SELECT format(
    'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS',
    :'runtime_user',
    :'runtime_password'
)
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_roles
    WHERE rolname = :'runtime_user'
)
\gexec

SELECT format(
    'ALTER ROLE %I WITH LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS',
    :'runtime_user',
    :'runtime_password'
)
\gexec

SELECT format(
    'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS',
    :'worker_user',
    :'worker_password'
)
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_roles
    WHERE rolname = :'worker_user'
)
\gexec

SELECT format(
    'ALTER ROLE %I WITH LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS',
    :'worker_user',
    :'worker_password'
)
\gexec

SELECT format(
    'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS',
    :'maintenance_user',
    :'maintenance_password'
)
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_roles
    WHERE rolname = :'maintenance_user'
)
\gexec

SELECT format(
    'ALTER ROLE %I WITH LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS',
    :'maintenance_user',
    :'maintenance_password'
)
\gexec


-- No application role may create persistent objects in public.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

SELECT format(
    'GRANT CONNECT ON DATABASE %I TO %I',
    current_database(),
    :'runtime_user'
)
\gexec

SELECT format(
    'GRANT CONNECT ON DATABASE %I TO %I',
    current_database(),
    :'worker_user'
)
\gexec

SELECT format(
    'GRANT CONNECT ON DATABASE %I TO %I',
    current_database(),
    :'maintenance_user'
)
\gexec

SELECT format(
    'GRANT USAGE ON SCHEMA public TO %I',
    :'runtime_user'
)
\gexec

SELECT format(
    'GRANT USAGE ON SCHEMA public TO %I',
    :'worker_user'
)
\gexec

SELECT format(
    'GRANT USAGE ON SCHEMA public TO %I',
    :'maintenance_user'
)
\gexec

SELECT format(
    'REVOKE CREATE ON SCHEMA public FROM %I',
    :'runtime_user'
)
\gexec

SELECT format(
    'REVOKE CREATE ON SCHEMA public FROM %I',
    :'worker_user'
)
\gexec

SELECT format(
    'REVOKE CREATE ON SCHEMA public FROM %I',
    :'maintenance_user'
)
\gexec


-- Reconcile stale grants on every deployment.
SELECT format(
    'REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM %I',
    :'runtime_user'
)
\gexec

SELECT format(
    'REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM %I',
    :'runtime_user'
)
\gexec

SELECT format(
    'REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM %I',
    :'worker_user'
)
\gexec

SELECT format(
    'REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM %I',
    :'worker_user'
)
\gexec

SELECT format(
    'REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM %I',
    :'maintenance_user'
)
\gexec

SELECT format(
    'REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM %I',
    :'maintenance_user'
)
\gexec


-- Identity/auth/access runtime.
SELECT format(
    'GRANT SELECT, INSERT, UPDATE ON TABLE users, telegram_identities, access_requests TO %I',
    :'runtime_user'
)
\gexec

SELECT format(
    'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE auth_sessions TO %I',
    :'runtime_user'
)
\gexec


-- Telegram ingress and backend-created delivery work.
SELECT format(
    'GRANT SELECT, INSERT ON TABLE telegram_updates, notification_outbox TO %I',
    :'runtime_user'
)
\gexec

SELECT format(
    'GRANT SELECT, INSERT, UPDATE ON TABLE access_decision_callbacks TO %I',
    :'runtime_user'
)
\gexec


-- Versioned catalog schema definitions are read-only at runtime.
SELECT format(
    'GRANT SELECT ON TABLE categories, category_attributes TO %I',
    :'runtime_user'
)
\gexec


-- Mutable catalog data.
SELECT format(
    'GRANT SELECT, INSERT ON TABLE manufacturers TO %I',
    :'runtime_user'
)
\gexec

SELECT format(
    'GRANT SELECT, INSERT, UPDATE ON TABLE items TO %I',
    :'runtime_user'
)
\gexec

SELECT format(
    'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE item_attribute_values TO %I',
    :'runtime_user'
)
\gexec


-- Mutable current warehouse projections.
SELECT format(
    'GRANT SELECT, INSERT, UPDATE ON TABLE locations, inventory_units TO %I',
    :'runtime_user'
)
\gexec

SELECT format(
    'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE stock_balances TO %I',
    :'runtime_user'
)
\gexec


-- Canonical movement journal is append-only from runtime.
SELECT format(
    'GRANT SELECT, INSERT ON TABLE movements, movement_lines TO %I',
    :'runtime_user'
)
\gexec

-- Identity sequence used by Movement.journal_seq.
SELECT format(
    'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO %I',
    :'runtime_user'
)
\gexec


-- Telegram delivery worker: exactly one application table.
SELECT format(
    'GRANT SELECT, UPDATE ON TABLE notification_outbox TO %I',
    :'worker_user'
)
\gexec


-- Technical retention worker.
--
-- It may read/delete only bounded technical tables. Access requests are
-- read-only because callback retention must inspect terminal decision state.
-- It intentionally has no access to the warehouse journal or projections.
SELECT format(
    'GRANT SELECT, DELETE ON TABLE auth_sessions, telegram_updates, notification_outbox, access_decision_callbacks TO %I',
    :'maintenance_user'
)
\gexec

SELECT format(
    'GRANT SELECT ON TABLE access_requests TO %I',
    :'maintenance_user'
)
\gexec
