from sqlalchemy import CheckConstraint

import app.db.models  # noqa: F401  # регистрирует ORM-модели в metadata
from app.db.base import metadata
from app.modules.identity.enums import (
    AccessRequestStatus,
    UserAccessStatus,
    UserRole,
)


def _constraint_names(table_name: str) -> set[str]:
    table = metadata.tables[table_name]
    return {
        str(constraint.name)
        for constraint in table.constraints
        if constraint.name is not None
    }


def test_identity_tables_are_registered_in_shared_metadata() -> None:
    assert {"users", "telegram_identities", "access_requests"} <= set(
        metadata.tables
    )


def test_identity_enum_values_are_stable() -> None:
    assert [role.value for role in UserRole] == ["USER", "ADMIN"]
    assert [status.value for status in UserAccessStatus] == [
        "PENDING",
        "APPROVED",
        "REJECTED",
        "BLOCKED",
    ]
    assert [status.value for status in AccessRequestStatus] == [
        "PENDING",
        "APPROVED",
        "REJECTED",
    ]


def test_identity_constraints_have_stable_names() -> None:
    assert {
        "pk_users",
        "ck_users_user_role",
        "ck_users_user_access_status",
        "fk_users_approved_by_user_id_users",
    } <= _constraint_names("users")

    assert {
        "pk_telegram_identities",
        "uq_telegram_identities_user_id",
        "uq_telegram_identities_telegram_user_id",
        "ck_telegram_identities_telegram_user_id_positive",
        "fk_telegram_identities_user_id_users",
    } <= _constraint_names("telegram_identities")

    assert {
        "pk_access_requests",
        "ck_access_requests_access_request_status",
        "ck_access_requests_decision_state",
        "fk_access_requests_user_id_users",
        "fk_access_requests_decided_by_user_id_users",
    } <= _constraint_names("access_requests")


def test_access_request_has_single_pending_request_guard() -> None:
    table = metadata.tables["access_requests"]
    index = next(
        item for item in table.indexes if item.name == "ux_access_requests_user_pending"
    )

    assert index.unique is True
    assert [column.name for column in index.columns] == ["user_id"]
    assert str(index.dialect_options["postgresql"]["where"]) == "status = 'PENDING'"


def test_access_request_decision_state_is_database_enforced() -> None:
    table = metadata.tables["access_requests"]
    constraint = next(
        item
        for item in table.constraints
        if isinstance(item, CheckConstraint)
        and item.name == "ck_access_requests_decision_state"
    )
    expression = str(constraint.sqltext)

    assert "status = 'PENDING'" in expression
    assert "decided_at IS NULL" in expression
    assert "decided_by_user_id IS NULL" in expression
    assert "status IN ('APPROVED', 'REJECTED')" in expression
    assert "decided_at IS NOT NULL" in expression
    assert "decided_by_user_id IS NOT NULL" in expression
