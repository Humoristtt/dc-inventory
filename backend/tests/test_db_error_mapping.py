from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.db.errors import postgres_sqlstate
from app.modules.catalog.api import (
    _raise_integrity_conflict as raise_catalog_integrity_conflict,
)
from app.modules.inventory.api import (
    _raise_integrity_conflict as raise_inventory_integrity_conflict,
)
from app.modules.inventory.api import _raise_retryable_db_conflict


class FakePostgresError(Exception):
    def __init__(self, sqlstate: str | None) -> None:
        super().__init__("synthetic database error")
        self.sqlstate = sqlstate


def make_integrity_error(sqlstate: str | None) -> IntegrityError:
    return IntegrityError(
        "synthetic statement",
        {},
        FakePostgresError(sqlstate),
    )


def make_dbapi_error(sqlstate: str | None) -> DBAPIError:
    return DBAPIError(
        "synthetic statement",
        {},
        FakePostgresError(sqlstate),
    )


def test_postgres_sqlstate_reads_nested_driver_error() -> None:
    outer = FakePostgresError(None)
    inner = FakePostgresError("23505")
    outer.__cause__ = inner

    error = IntegrityError(
        "synthetic statement",
        {},
        outer,
    )

    assert postgres_sqlstate(error) == "23505"


def test_inventory_unique_violation_is_safe_conflict() -> None:
    error = make_integrity_error("23505")

    with pytest.raises(HTTPException) as exc_info:
        raise_inventory_integrity_conflict(error)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == {
        "code": "inventory_conflict",
        "message": "inventory operation conflicts with current state",
    }


@pytest.mark.parametrize("sqlstate", ["23514", "23503", None])
def test_inventory_unexpected_integrity_error_is_not_masked(
    sqlstate: str | None,
) -> None:
    error = make_integrity_error(sqlstate)

    with pytest.raises(IntegrityError) as exc_info:
        raise_inventory_integrity_conflict(error)

    assert exc_info.value is error


@pytest.mark.parametrize("sqlstate", ["40P01", "55P03", "40001"])
def test_inventory_retryable_database_error_is_retryable_conflict(
    sqlstate: str,
) -> None:
    error = make_dbapi_error(sqlstate)

    with pytest.raises(HTTPException) as exc_info:
        _raise_retryable_db_conflict(error)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == {
        "code": "inventory_concurrency_conflict",
        "message": (
            "inventory operation conflicted with concurrent activity; retry"
        ),
    }


def test_inventory_non_retryable_dbapi_error_is_not_masked() -> None:
    error = make_dbapi_error("23514")

    with pytest.raises(DBAPIError) as exc_info:
        _raise_retryable_db_conflict(error)

    assert exc_info.value is error


def test_catalog_unique_violation_is_safe_conflict() -> None:
    error = make_integrity_error("23505")

    with pytest.raises(HTTPException) as exc_info:
        raise_catalog_integrity_conflict(error)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == {
        "code": "catalog_conflict",
        "message": "catalog data conflicts with an existing record",
    }


@pytest.mark.parametrize("sqlstate", ["23514", "23503", None])
def test_catalog_unexpected_integrity_error_is_not_masked(
    sqlstate: str | None,
) -> None:
    error = make_integrity_error(sqlstate)

    with pytest.raises(IntegrityError) as exc_info:
        raise_catalog_integrity_conflict(error)

    assert exc_info.value is error
