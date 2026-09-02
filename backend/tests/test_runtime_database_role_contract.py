from __future__ import annotations

import inspect
from pathlib import Path

from app.modules.inventory.service import (
    _lock_original_movement_context,
    create_movement,
    reverse_movement,
)


def test_original_movement_lock_is_advisory_not_row_update_lock() -> None:
    helper_source = inspect.getsource(
        _lock_original_movement_context
    )
    create_source = inspect.getsource(create_movement)
    reversal_source = inspect.getsource(
        reverse_movement
    )

    assert "pg_advisory_xact_lock" in helper_source
    assert "warehouse-original-movement" in helper_source

    assert (
        "_lock_original_movement_context"
        in create_source
    )
    assert (
        "_lock_original_movement_context"
        in reversal_source
    )

    # Runtime intentionally has no UPDATE privilege on the
    # append-only journal, so these paths must never require a
    # PostgreSQL row lock on Movement.
    assert ".with_for_update(" not in create_source
    assert ".with_for_update(" not in reversal_source


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
