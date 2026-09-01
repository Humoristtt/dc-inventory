from sqlalchemy import CheckConstraint

import app.db.models  # noqa: F401
from app.db.base import metadata
from app.modules.auth.service import hash_session_token


def _constraint_names(table_name: str) -> set[str]:
    table = metadata.tables[table_name]
    return {
        str(constraint.name)
        for constraint in table.constraints
        if constraint.name is not None
    }


def test_auth_sessions_are_registered_in_shared_metadata() -> None:
    assert "auth_sessions" in metadata.tables


def test_auth_session_constraints_have_stable_names() -> None:
    assert {
        "pk_auth_sessions",
        "uq_auth_sessions_token_hash",
        "fk_auth_sessions_user_id_users",
        "ck_auth_sessions_token_hash_sha256_length",
        "ck_auth_sessions_expiry_after_creation",
        "ck_auth_sessions_revoked_after_creation",
    } <= _constraint_names("auth_sessions")

    table = metadata.tables["auth_sessions"]
    check_expressions = {
        str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert "octet_length(token_hash) = 32" in check_expressions
    assert "expires_at > created_at" in check_expressions


def test_session_token_hash_is_sha256_and_deterministic() -> None:
    first = hash_session_token("example-session-token")
    second = hash_session_token("example-session-token")

    assert len(first) == 32
    assert first == second
    assert first != hash_session_token("different-token")
