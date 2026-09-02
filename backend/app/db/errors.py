from __future__ import annotations

from sqlalchemy.exc import DBAPIError

POSTGRES_UNIQUE_VIOLATION_SQLSTATE = "23505"

RETRYABLE_POSTGRES_SQLSTATES = frozenset(
    {
        "40P01",  # deadlock_detected
        "55P03",  # lock_not_available
        "40001",  # serialization_failure
    }
)


def postgres_sqlstate(error: DBAPIError) -> str | None:
    """Return PostgreSQL SQLSTATE without exposing raw database errors."""
    candidate: object | None = error.orig
    seen: set[int] = set()

    while candidate is not None and id(candidate) not in seen:
        seen.add(id(candidate))

        sqlstate = getattr(candidate, "sqlstate", None) or getattr(
            candidate,
            "pgcode",
            None,
        )
        if isinstance(sqlstate, str):
            return sqlstate

        candidate = getattr(candidate, "__cause__", None) or getattr(
            candidate,
            "__context__",
            None,
        )

    return None
