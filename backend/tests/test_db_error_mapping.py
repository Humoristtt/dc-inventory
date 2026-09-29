from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock

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
from app.modules.procurement.api import (
    _mutate as mutate_procurement,
)
from app.modules.procurement.api import (
    _raise_db_error as raise_procurement_db_error,
)


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
    assert cast(object, exc_info.value.detail) == {
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
    assert cast(object, exc_info.value.detail) == {
        "code": "inventory_concurrency_conflict",
        "message": ("inventory operation conflicted with concurrent activity; retry"),
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
    assert cast(object, exc_info.value.detail) == {
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


@pytest.mark.parametrize("sqlstate", ["40P01", "55P03", "40001"])
def test_procurement_retryable_database_error_is_retryable_conflict(
    sqlstate: str,
) -> None:
    error = make_dbapi_error(sqlstate)

    with pytest.raises(HTTPException) as exc_info:
        raise_procurement_db_error(error)

    assert exc_info.value.status_code == 409
    assert cast(object, exc_info.value.detail) == {
        "code": "procurement_concurrency_conflict",
        "message": "procurement operation conflicted with concurrent activity; retry",
    }


@pytest.mark.parametrize("sqlstate", ["23505", "23503"])
def test_procurement_constraint_conflict_is_safe_conflict(
    sqlstate: str,
) -> None:
    error = make_integrity_error(sqlstate)

    with pytest.raises(HTTPException) as exc_info:
        raise_procurement_db_error(error)

    assert exc_info.value.status_code == 409
    assert cast(object, exc_info.value.detail) == {
        "code": "procurement_database_conflict",
        "message": "procurement operation conflicts with current state",
    }


@pytest.mark.parametrize("sqlstate", ["08006", "57014", "57P03"])
def test_procurement_database_unavailability_is_safe_503(
    sqlstate: str,
) -> None:
    error = make_dbapi_error(sqlstate)

    with pytest.raises(HTTPException) as exc_info:
        raise_procurement_db_error(error)

    assert exc_info.value.status_code == 503
    assert cast(object, exc_info.value.detail) == {
        "code": "procurement_database_unavailable",
        "message": "procurement database is temporarily unavailable",
    }


@pytest.mark.parametrize("sqlstate", ["42P01", None])
def test_procurement_unexpected_database_error_is_safe_500(
    sqlstate: str | None,
) -> None:
    error = make_dbapi_error(sqlstate)

    with pytest.raises(HTTPException) as exc_info:
        raise_procurement_db_error(error)

    assert exc_info.value.status_code == 500
    assert cast(object, exc_info.value.detail) == {
        "code": "procurement_database_error",
        "message": "unexpected procurement database error",
    }
    assert "synthetic" not in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_procurement_database_failure_rolls_back_before_mapping() -> None:
    error = make_dbapi_error("08006")
    db = AsyncMock()

    async def failing_call() -> Any:
        raise error

    with pytest.raises(HTTPException) as exc_info:
        await mutate_procurement(failing_call(), db)

    assert exc_info.value.status_code == 503
    db.rollback.assert_awaited_once_with()
    db.commit.assert_not_awaited()
