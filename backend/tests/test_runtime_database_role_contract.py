from __future__ import annotations

import inspect
from pathlib import Path

from app.modules.inventory.service import (
    _lock_original_movement_context,
)


def test_original_movement_lock_is_advisory_not_row_update_lock() -> None:
    source = inspect.getsource(_lock_original_movement_context)
    assert "pg_advisory_xact_lock" in source
    assert ".with_for_update(" not in source


def test_runtime_database_permission_source_is_least_privilege() -> None:
    permissions = (
        Path(__file__).resolve().parents[1] / "scripts" / "apply_database_permissions.sql"
    ).read_text()

    assert "GRANT UPDATE (processed_at) ON TABLE telegram_updates" in permissions

    assert (
        "'GRANT SELECT ON TABLE alembic_version TO %I'"
        in permissions
    )
    assert (
        "GRANT INSERT ON TABLE alembic_version"
        not in permissions
    )
    assert (
        "GRANT UPDATE ON TABLE alembic_version"
        not in permissions
    )
    assert (
        "GRANT DELETE ON TABLE alembic_version"
        not in permissions
    )

    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE auth_sessions" not in permissions

    assert "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public" not in permissions

    assert "pg_get_serial_sequence(" in permissions

    assert "'public.movements'," in permissions

    assert "'journal_seq'" in permissions

    assert (
        "'GRANT SELECT ON TABLE stock_balances, '"
        "\n    'user_item_custody_balances TO %I'" in permissions
    )
    assert (
        "'GRANT EXECUTE ON FUNCTION '"
        "\n    'public.refresh_warehouse_projection(uuid, uuid) TO %I'"
        in permissions
    )
    assert (
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE stock_balances"
        not in permissions
    )
    assert (
        "GRANT SELECT, INSERT, UPDATE, DELETE "
        "\n    'ON TABLE user_item_custody_balances TO %I'"
        not in permissions
    )
    assert "GRANT SELECT, INSERT ON TABLE user_access_events, user_role_events" in permissions
    assert "UPDATE ON TABLE user_role_events" not in permissions
    assert "DELETE ON TABLE user_role_events" not in permissions
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE items TO %I" in permissions
    assert (
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE movements, movement_lines" not in permissions
    )


def test_runtime_outbox_recovery_update_is_column_scoped() -> None:
    permissions = (
        Path(__file__).resolve().parents[1] / "scripts" / "apply_database_permissions.sql"
    ).read_text()

    assert "'GRANT UPDATE '" in permissions
    assert (
        "'(status, attempts, available_at, claimed_at, "
        "claim_token, last_error, updated_at) '" in permissions
    )
    assert "'ON TABLE notification_outbox TO %I'" in permissions

    assert "'GRANT UPDATE ON TABLE notification_outbox TO %I'" not in permissions


def test_telegram_worker_outbox_update_is_column_scoped() -> None:
    permissions = (
        Path(__file__).resolve().parents[1] / "scripts" / "apply_database_permissions.sql"
    ).read_text()

    assert "'GRANT SELECT ON TABLE notification_outbox TO %I'" in permissions
    assert (
        "'GRANT UPDATE (status, attempts, available_at, claimed_at, claim_token, '"
        "\n    'sent_at, last_error, updated_at) ON TABLE notification_outbox TO %I'"
        in permissions
    )
    assert "'GRANT SELECT, UPDATE ON TABLE notification_outbox TO %I'" not in permissions


def test_telegram_start_state_permissions_are_column_scoped() -> None:
    permissions = (
        Path(__file__).resolve().parents[1] / "scripts" / "apply_database_permissions.sql"
    ).read_text()

    assert "'GRANT INSERT (chat_id, latest_start_update_id) '" in permissions
    assert "'GRANT UPDATE (latest_start_update_id, updated_at) '" in permissions
    assert (
        "'GRANT UPDATE '"
        "\n    '(last_welcome_message_id, last_welcome_sent_at, updated_at) '" in permissions
    )
    assert "'GRANT SELECT, INSERT, UPDATE ON TABLE telegram_chat_states TO %I'" not in permissions
    assert "'GRANT SELECT, UPDATE ON TABLE telegram_chat_states TO %I'" not in permissions


def test_delivery_workers_have_separate_least_privilege_roles() -> None:
    permissions = (
        Path(__file__).resolve().parents[1] / "scripts" / "apply_database_permissions.sql"
    ).read_text()

    assert ":'telegram_worker_user'" in permissions
    assert ":'email_worker_user'" in permissions
    assert ":'worker_user'" not in permissions
    telegram_section, email_section = permissions.split(
        "-- Procurement email delivery worker: email outbox only."
    )
    assert "notification_outbox" in telegram_section
    assert "email_outbox TO %I',\n    :'telegram_worker_user'" not in telegram_section
    assert "email_outbox" in email_section
    assert "notification_outbox TO %I',\n    :'email_worker_user'" not in email_section


def test_legacy_delivery_worker_is_retired_fail_closed() -> None:
    permissions = (
        Path(__file__).resolve().parents[1] / "scripts" / "apply_database_permissions.sql"
    ).read_text()

    assert ":'legacy_worker_user'" in permissions
    assert "WITH NOLOGIN NOSUPERUSER" in permissions
    assert "pg_terminate_backend(" not in permissions
    assert "REVOKE ALL PRIVILEGES ON DATABASE %I FROM %I" in permissions
    assert "REVOKE ALL PRIVILEGES ON SCHEMA public FROM %I" in permissions
    assert "REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM %I" in permissions
    assert "REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM %I" in permissions


def test_identity_runtime_update_grants_are_column_scoped() -> None:
    permissions = (
        Path(__file__).resolve().parents[1] / "scripts" / "apply_database_permissions.sql"
    ).read_text()

    assert (
        "GRANT SELECT, INSERT, UPDATE ON TABLE "
        "users, telegram_identities, access_requests" not in permissions
    )

    assert "'GRANT SELECT, INSERT ON TABLE users TO %I'" in permissions
    assert (
        "'GRANT UPDATE '\n"
        "    '(role, access_status, updated_at, approved_at, approved_by_user_id) '\n"
        "    'ON TABLE users TO %I'" in permissions
    )

    assert "'GRANT SELECT, INSERT ON TABLE telegram_identities TO %I'" in permissions
    assert (
        "'GRANT UPDATE '\n"
        "    '(username, first_name, last_name, language_code, updated_at, last_auth_at) '\n"
        "    'ON TABLE telegram_identities TO %I'" in permissions
    )

    assert "'GRANT SELECT, INSERT ON TABLE access_requests TO %I'" in permissions
    assert (
        "'GRANT UPDATE '\n"
        "    '(status, decided_at, decided_by_user_id, decision_note) '\n"
        "    'ON TABLE access_requests TO %I'" in permissions
    )

    assert "UPDATE (id" not in permissions
    assert "UPDATE (created_at" not in permissions
    assert "UPDATE (telegram_user_id" not in permissions
    assert "UPDATE (user_id" not in permissions
    assert "UPDATE (requested_at" not in permissions


def test_permission_install_commits_before_legacy_session_termination() -> None:
    root = Path(__file__).resolve().parents[2]

    compose = (root / "compose.yaml").read_text()
    grants = (
        root
        / "backend/scripts/apply_database_permissions.sql"
    ).read_text()
    terminator = (
        root
        / "backend/scripts/terminate_legacy_worker_sessions.sql"
    ).read_text()

    section = compose.split(
        "\n  db-permissions:\n",
        1,
    )[1].split(
        "\n  backend:\n",
        1,
    )[0]

    transaction = (
        "psql -X --single-transaction "
        "-v ON_ERROR_STOP=1"
    )
    apply_file = (
        "-f /scripts/"
        "apply_database_permissions.sql"
    )
    terminate_command = (
        "psql -X -v ON_ERROR_STOP=1"
    )
    terminate_file = (
        "-f /scripts/"
        "terminate_legacy_worker_sessions.sql"
    )

    assert section.count(transaction) == 1
    assert section.count(apply_file) == 1

    assert section.count(
        terminate_command
    ) == 1

    assert section.count(
        terminate_file
    ) == 1

    assert (
        section.index(transaction)
        < section.index(apply_file)
        < section.index(terminate_command)
        < section.index(terminate_file)
    )

    assert (
        "./backend/scripts/"
        "terminate_legacy_worker_sessions.sql:"
        "/scripts/"
        "terminate_legacy_worker_sessions.sql:ro"
    ) in section

    assert "pg_terminate_backend(" not in grants
    assert "\\gexec" in grants

    assert (
        "pg_terminate_backend(pid, 5000)"
        in terminator
    )

    assert (
        "legacy worker sessions remain after revocation"
        in terminator
    )
