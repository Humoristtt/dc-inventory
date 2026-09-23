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
    :'telegram_worker_user',
    :'telegram_worker_password'
)
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_roles
    WHERE rolname = :'telegram_worker_user'
)
\gexec

SELECT format(
    'ALTER ROLE %I WITH LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS',
    :'telegram_worker_user',
    :'telegram_worker_password'
)
\gexec

SELECT format(
    'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS',
    :'email_worker_user',
    :'email_worker_password'
)
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_roles
    WHERE rolname = :'email_worker_user'
)
\gexec

SELECT format(
    'ALTER ROLE %I WITH LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS',
    :'email_worker_user',
    :'email_worker_password'
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


-- One-way cutover from the pre-split delivery-worker credential.
-- Fresh installations normally have no such role. Existing installations
-- disable login and revoke legacy privileges in one transaction.
-- Existing sessions are terminated separately after commit.
SELECT format(
    'ALTER ROLE %I WITH NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS',
    :'legacy_worker_user'
)
WHERE EXISTS (
    SELECT 1
    FROM pg_roles
    WHERE rolname = :'legacy_worker_user'
)
\gexec

SELECT format(
    'REVOKE ALL PRIVILEGES ON DATABASE %I FROM %I',
    current_database(),
    :'legacy_worker_user'
)
WHERE EXISTS (
    SELECT 1
    FROM pg_roles
    WHERE rolname = :'legacy_worker_user'
)
\gexec

SELECT format(
    'REVOKE ALL PRIVILEGES ON SCHEMA public FROM %I',
    :'legacy_worker_user'
)
WHERE EXISTS (
    SELECT 1
    FROM pg_roles
    WHERE rolname = :'legacy_worker_user'
)
\gexec

SELECT format(
    'REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM %I',
    :'legacy_worker_user'
)
WHERE EXISTS (
    SELECT 1
    FROM pg_roles
    WHERE rolname = :'legacy_worker_user'
)
\gexec

SELECT format(
    'REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM %I',
    :'legacy_worker_user'
)
WHERE EXISTS (
    SELECT 1
    FROM pg_roles
    WHERE rolname = :'legacy_worker_user'
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
    :'telegram_worker_user'
)
\gexec

SELECT format(
    'GRANT CONNECT ON DATABASE %I TO %I',
    current_database(),
    :'email_worker_user'
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
    :'telegram_worker_user'
)
\gexec

SELECT format(
    'GRANT USAGE ON SCHEMA public TO %I',
    :'email_worker_user'
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
    :'telegram_worker_user'
)
\gexec

SELECT format(
    'REVOKE CREATE ON SCHEMA public FROM %I',
    :'email_worker_user'
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
    :'telegram_worker_user'
)
\gexec

SELECT format(
    'REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM %I',
    :'telegram_worker_user'
)
\gexec

SELECT format(
    'REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM %I',
    :'email_worker_user'
)
\gexec

SELECT format(
    'REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM %I',
    :'email_worker_user'
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
-- Runtime may create identity/access records, but UPDATE is deliberately
-- column-scoped. Immutable identifiers and creation/request timestamps are
-- not writable by the application database principal.
SELECT format(
    'GRANT SELECT, INSERT ON TABLE users TO %I',
    :'runtime_user'
)
\gexec

SELECT format(
    'GRANT UPDATE '
    '(role, access_status, updated_at, approved_at, approved_by_user_id) '
    'ON TABLE users TO %I',
    :'runtime_user'
)
\gexec

SELECT format(
    'GRANT SELECT, INSERT ON TABLE telegram_identities TO %I',
    :'runtime_user'
)
\gexec

SELECT format(
    'GRANT UPDATE '
    '(username, first_name, last_name, language_code, updated_at, last_auth_at) '
    'ON TABLE telegram_identities TO %I',
    :'runtime_user'
)
\gexec

SELECT format(
    'GRANT SELECT, INSERT ON TABLE access_requests TO %I',
    :'runtime_user'
)
\gexec

SELECT format(
    'GRANT UPDATE '
    '(status, decided_at, decided_by_user_id, decision_note) '
    'ON TABLE access_requests TO %I',
    :'runtime_user'
)
\gexec

SELECT format(
    'GRANT SELECT, INSERT, UPDATE ON TABLE auth_sessions TO %I',
    :'runtime_user'
)
\gexec


-- Account reset can detach identities and remove pending access requests.
-- Immutable users/audit/warehouse/procurement rows remain undeletable.
SELECT format(
    'GRANT DELETE ON TABLE telegram_identities, access_requests TO %I',
    :'runtime_user'
)
\gexec


-- Administrative user lifecycle and role history are append-only.
SELECT format(
    'GRANT SELECT, INSERT ON TABLE user_access_events, user_role_events TO %I',
    :'runtime_user'
)
\gexec


-- Telegram ingress and backend-created delivery work.
SELECT format(
    'GRANT SELECT, INSERT ON TABLE telegram_updates TO %I',
    :'runtime_user'
)
\gexec

SELECT format(
    'GRANT UPDATE (processed_at) ON TABLE telegram_updates TO %I',
    :'runtime_user'
)
\gexec

SELECT format(
    'GRANT SELECT, INSERT ON TABLE notification_outbox TO %I',
    :'runtime_user'
)
\gexec

SELECT format(
    'GRANT SELECT ON TABLE telegram_chat_states TO %I',
    :'runtime_user'
)
\gexec

SELECT format(
    'GRANT INSERT (chat_id, latest_start_update_id) '
    'ON TABLE telegram_chat_states TO %I',
    :'runtime_user'
)
\gexec

SELECT format(
    'GRANT UPDATE (latest_start_update_id, updated_at) '
    'ON TABLE telegram_chat_states TO %I',
    :'runtime_user'
)
\gexec

-- Backend may only revive a terminal DEAD delivery when the
-- same business request is explicitly retried. It does not
-- receive table-level UPDATE on the outbox.
SELECT format(
    'GRANT UPDATE '
    '(status, attempts, available_at, claimed_at, claim_token, last_error, updated_at) '
    'ON TABLE notification_outbox TO %I',
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
    'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE items TO %I',
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
    'GRANT SELECT, INSERT, UPDATE ON TABLE locations TO %I',
    :'runtime_user'
)
\gexec

SELECT format(
    'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE stock_balances TO %I',
    :'runtime_user'
)
\gexec


SELECT format(
    'GRANT SELECT, INSERT, UPDATE, DELETE '
    'ON TABLE user_item_custody_balances TO %I',
    :'runtime_user'
)
\gexec


-- Canonical movement journal is append-only from runtime.
SELECT format(
    'GRANT SELECT, INSERT ON TABLE movements, movement_lines TO %I',
    :'runtime_user'
)
\gexec


-- Procurement workflow: mutable request header plus append-only history.
SELECT format(
    'GRANT SELECT, INSERT ON TABLE procurement_requests TO %I',
    :'runtime_user'
)
\gexec

SELECT format(
    'GRANT UPDATE (status, assigned_manager_user_id, current_revision_id, '
    'final_movement_id, state_version, updated_at, completed_at) '
    'ON TABLE procurement_requests TO %I',
    :'runtime_user'
)
\gexec

SELECT format(
    'GRANT SELECT, INSERT ON TABLE procurement_revisions, '
    'procurement_revision_lines, procurement_line_catalog_bindings, '
    'procurement_events, email_outbox TO %I',
    :'runtime_user'
)
\gexec

SELECT format(
    'GRANT USAGE, SELECT ON SEQUENCE procurement_request_number_seq TO %I',
    :'runtime_user'
)
\gexec

-- Exact identity sequence used by Movement.journal_seq.
-- Runtime does not receive blanket access to every sequence in public.
SELECT format(
    'GRANT USAGE ON SEQUENCE %s TO %I',
    pg_get_serial_sequence(
        'public.movements',
        'journal_seq'
    ),
    :'runtime_user'
)
WHERE pg_get_serial_sequence(
    'public.movements',
    'journal_seq'
) IS NOT NULL
\gexec


-- Telegram delivery worker: outbox plus start-welcome chat state.
SELECT format(
    'GRANT SELECT, UPDATE ON TABLE notification_outbox TO %I',
    :'telegram_worker_user'
)
\gexec

SELECT format(
    'GRANT SELECT ON TABLE telegram_chat_states TO %I',
    :'telegram_worker_user'
)
\gexec

SELECT format(
    'GRANT UPDATE '
    '(last_welcome_message_id, last_welcome_sent_at, updated_at) '
    'ON TABLE telegram_chat_states TO %I',
    :'telegram_worker_user'
)
\gexec


-- Procurement email delivery worker: email outbox only.
SELECT format(
    'GRANT SELECT ON TABLE email_outbox TO %I',
    :'email_worker_user'
)
\gexec

SELECT format(
    'GRANT UPDATE (status, attempts, available_at, claimed_at, claim_token, '
    'sent_at, last_error, updated_at) ON TABLE email_outbox TO %I',
    :'email_worker_user'
)
\gexec


-- Technical retention worker.
--
-- It may read/delete only bounded technical tables. Access requests are
-- read-only because callback retention must inspect terminal decision state.
-- It intentionally has no access to the warehouse journal or projections.
SELECT format(
    'GRANT SELECT, DELETE ON TABLE auth_sessions, telegram_updates, notification_outbox, email_outbox, access_decision_callbacks TO %I',
    :'maintenance_user'
)
\gexec

SELECT format(
    'GRANT SELECT ON TABLE access_requests TO %I',
    :'maintenance_user'
)
\gexec
