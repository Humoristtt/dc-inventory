import uuid

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError

from app.main import app as application
from app.modules.inventory.api import _raise_retryable_db_conflict
from app.modules.inventory.schemas import MovementCreate, MovementLineCreate
from app.modules.inventory.service import InventoryValidationError, validate_positions


@pytest.mark.parametrize("quantity", [True, 1.5, "1", 0, -1, 2**53])
def test_quantity_requires_positive_exact_json_integer(quantity):
    with pytest.raises(ValidationError):
        MovementLineCreate(item_id=uuid.uuid4(), quantity=quantity)


@pytest.mark.parametrize(
    "kind,source,destination",
    [
        ("RECEIPT", False, True),
        ("RETURN", False, True),
        ("ISSUE", True, False),
        ("WRITE_OFF", True, False),
        ("TRANSFER", True, True),
    ],
)
def test_movement_shapes(kind, source, destination):
    for actual_source in (False, True):
        for actual_destination in (False, True):
            payload = MovementCreate(
                movement_type=kind,
                client_request_id="test",
                source_location_id=uuid.uuid4() if actual_source else None,
                destination_location_id=uuid.uuid4() if actual_destination else None,
                lines=[MovementLineCreate(item_id=uuid.uuid4(), quantity=1)],
            )
            if (source, destination) == (actual_source, actual_destination):
                validate_positions(payload)
            else:
                with pytest.raises(InventoryValidationError):
                    validate_positions(payload)


def test_transfer_rejects_same_location():
    location = uuid.uuid4()
    with pytest.raises(InventoryValidationError, match="must differ"):
        validate_positions(
            MovementCreate(
                movement_type="TRANSFER",
                client_request_id="same",
                source_location_id=location,
                destination_location_id=location,
                lines=[MovementLineCreate(item_id=uuid.uuid4(), quantity=1)],
            )
        )


class _SqlstateError(Exception):
    def __init__(self, sqlstate: str) -> None:
        super().__init__("unsafe raw database text")
        self.sqlstate = sqlstate


@pytest.mark.parametrize("sqlstate", ["40P01", "55P03", "40001"])
def test_retryable_postgres_errors_map_to_safe_stable_conflict(sqlstate: str) -> None:
    error = DBAPIError("unsafe statement", {}, _SqlstateError(sqlstate), False)
    with pytest.raises(HTTPException) as exc_info:
        _raise_retryable_db_conflict(error)
    assert exc_info.value.status_code == 409
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail == {
        "code": "inventory_concurrency_conflict",
        "message": "inventory operation conflicted with concurrent activity; retry",
    }
    assert "unsafe" not in str(exc_info.value.detail)


def test_unrelated_database_errors_are_not_converted_to_inventory_conflicts() -> None:
    error = DBAPIError("statement", {}, _SqlstateError("22003"), False)
    with pytest.raises(DBAPIError) as exc_info:
        _raise_retryable_db_conflict(error)
    assert exc_info.value is error


def test_inventory_routes_are_registered_without_history_mutation_routes() -> None:
    operations = application.openapi()["paths"]
    assert "/api/inventory/locations" in operations
    assert "/api/inventory/stock" in operations
    assert "/api/inventory/movements" in operations
    assert "/api/inventory/movements/{movement_id}" in operations
    assert "/api/admin/inventory/locations" in operations
    assert "/api/admin/inventory/movements/{movement_id}/reversal" in operations
    assert "delete" not in operations["/api/inventory/movements/{movement_id}"]
    assert "patch" not in operations["/api/inventory/movements/{movement_id}"]
