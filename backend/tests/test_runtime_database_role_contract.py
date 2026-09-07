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
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "apply_database_permissions.sql"
    ).read_text()

    assert (
        "GRANT UPDATE (processed_at) "
        "ON TABLE telegram_updates"
        in permissions
    )

    assert (
        "GRANT SELECT, INSERT, UPDATE, DELETE "
        "ON TABLE auth_sessions"
        not in permissions
    )

    assert (
        "GRANT USAGE, SELECT "
        "ON ALL SEQUENCES IN SCHEMA public"
        not in permissions
    )

    assert (
        "pg_get_serial_sequence("
        in permissions
    )

    assert (
        "'public.movements',"
        in permissions
    )

    assert (
        "'journal_seq'"
        in permissions
    )


def test_runtime_outbox_recovery_update_is_column_scoped() -> None:
    permissions = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "apply_database_permissions.sql"
    ).read_text()

    assert "'GRANT UPDATE '" in permissions
    assert (
        "'(status, attempts, available_at, claimed_at, "
        "claim_token, last_error, updated_at) '"
        in permissions
    )
    assert (
        "'ON TABLE notification_outbox TO %I'"
        in permissions
    )

    assert (
        "'GRANT UPDATE ON TABLE notification_outbox TO %I'"
        not in permissions
    )

def test_telegram_start_state_permissions_are_column_scoped() -> None:
    permissions = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "apply_database_permissions.sql"
    ).read_text()

    assert (
        "'GRANT INSERT (chat_id, latest_start_update_id) '"
        in permissions
    )
    assert (
        "'GRANT UPDATE (latest_start_update_id, updated_at) '"
        in permissions
    )
    assert (
        "'GRANT UPDATE '"
        "\n    '(last_welcome_message_id, last_welcome_sent_at, updated_at) '"
        in permissions
    )
    assert (
        "'GRANT SELECT, INSERT, UPDATE ON TABLE telegram_chat_states TO %I'"
        not in permissions
    )
    assert (
        "'GRANT SELECT, UPDATE ON TABLE telegram_chat_states TO %I'"
        not in permissions
    )
