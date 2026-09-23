\set ON_ERROR_STOP on

-- Non-transactional cutover step: only execute after role NOLOGIN and
-- all privilege revocations have committed successfully.
-- The role name is passed through psql's safely quoted literal parameter.
SELECT set_config(
    'dc_inventory.legacy_worker_user',
    :'legacy_worker_user',
    false
);

SELECT pg_terminate_backend(pid, 5000)
FROM pg_stat_activity
WHERE usename = current_setting('dc_inventory.legacy_worker_user')
  AND pid <> pg_backend_pid();

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_stat_activity
        WHERE usename = current_setting('dc_inventory.legacy_worker_user')
          AND pid <> pg_backend_pid()
    ) THEN
        RAISE EXCEPTION 'legacy worker sessions remain after revocation';
    END IF;
END;
$$;
