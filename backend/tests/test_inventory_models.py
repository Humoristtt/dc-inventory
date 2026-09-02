import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import CheckConstraint, String
from sqlalchemy.exc import DBAPIError

import app.db.models  # noqa: F401
from app.db.base import metadata
from app.main import app as application
from app.modules.identity.models import TelegramIdentity
from app.modules.inventory.api import _raise_retryable_db_conflict
from app.modules.inventory.enums import (
    InventoryUnitState,
    LocationStatus,
    MovementType,
)
from app.modules.inventory.schemas import MovementLineCreate
from app.modules.inventory.service import (
    display_identity,
    normalize_identity,
    normalize_optional_identity,
)


def _constraint_names(table_name: str) -> set[str]:
    return {
        str(constraint.name)
        for constraint in metadata.tables[table_name].constraints
        if constraint.name is not None
    }


def test_inventory_tables_are_registered_in_shared_metadata() -> None:
    assert {
        "locations",
        "inventory_units",
        "movements",
        "movement_lines",
        "stock_balances",
    } <= set(metadata.tables)


def test_inventory_enum_values_are_stable() -> None:
    assert [status.value for status in LocationStatus] == ["ACTIVE", "ARCHIVED"]
    assert [state.value for state in InventoryUnitState] == [
        "STORED",
        "ISSUED",
        "WRITTEN_OFF",
        "VOIDED",
    ]
    assert [movement_type.value for movement_type in MovementType] == [
        "RECEIPT",
        "ISSUE",
        "RETURN",
        "TRANSFER",
        "WRITE_OFF",
        "CORRECTION",
        "REVERSAL",
    ]


def test_inventory_constraints_have_stable_names() -> None:
    assert {
        "ck_locations_archive_state",
        "uq_locations_normalized_code",
    } <= _constraint_names("locations")
    assert {
        "ck_inventory_units_serial_item_only",
        "ck_inventory_units_current_position",
        "uq_inventory_units_item_id_normalized_serial_number",
        "uq_inventory_units_normalized_wwn",
    } <= _constraint_names("inventory_units")
    assert {
        "ck_movements_operation_positions",
        "ck_movements_original_relationship",
        "uq_movements_actor_user_id_client_request_id",
        "uq_movements_journal_seq",
        "ck_movements_line_count_range",
    } <= _constraint_names("movements")
    assert {
        "ck_movement_lines_accounting_shape",
        "uq_movement_lines_movement_id_inventory_unit_id",
        "uq_movement_lines_movement_id_line_no",
    } <= _constraint_names("movement_lines")
    assert {
        "ck_stock_balances_quantity_positive",
        "ck_stock_balances_single_position",
    } <= _constraint_names("stock_balances")



def test_movement_line_accounting_shape_is_null_safe() -> None:
    constraint = next(
        constraint
        for constraint in metadata.tables["movement_lines"].constraints
        if (
            isinstance(constraint, CheckConstraint)
            and constraint.name == "ck_movement_lines_accounting_shape"
        )
    )
    sql = str(constraint.sqltext)
    assert "quantity IS NOT NULL" in sql
    assert "serial_number_snapshot IS NOT NULL" in sql

def test_stock_and_serial_position_checks_use_postgresql_num_nonnulls() -> None:
    for table_name, constraint_name in (
        ("stock_balances", "ck_stock_balances_single_position"),
        ("movements", "ck_movements_position_side_exclusive"),
    ):
        constraint = next(
            constraint
            for constraint in metadata.tables[table_name].constraints
            if isinstance(constraint, CheckConstraint) and constraint.name == constraint_name
        )
        assert "num_nonnulls" in str(constraint.sqltext)


def test_movement_line_request_has_explicit_quantity_or_serial_shape() -> None:
    quantity = MovementLineCreate(item_id="00000000-0000-4000-8000-000000000001", quantity=2)
    existing_serial = MovementLineCreate(inventory_unit_id="00000000-0000-4000-8000-000000000002")
    new_serial = MovementLineCreate(
        item_id="00000000-0000-4000-8000-000000000003",
        serial_number="SN-1",
    )

    assert quantity.quantity == 2
    assert existing_serial.inventory_unit_id is not None
    assert new_serial.serial_number == "SN-1"


@pytest.mark.parametrize("quantity", [True, 1.5, "1"])
def test_movement_quantity_rejects_bool_and_coercible_non_integers(
    quantity: object,
) -> None:
    with pytest.raises(ValidationError):
        MovementLineCreate.model_validate(
            {
                "item_id": "00000000-0000-4000-8000-000000000001",
                "quantity": quantity,
            }
        )


def test_inventory_identity_normalization_checks_final_casefolded_length() -> None:
    with pytest.raises(Exception) as location_error:
        normalize_identity("ß" * 33, field="location_code", max_length=64)
    assert getattr(location_error.value, "code", None) == "location_code_too_long"

    assert normalize_identity("ß" * 127, field="serial_number", max_length=255) == ("ss" * 127)
    with pytest.raises(Exception) as serial_error:
        normalize_identity("ß" * 128, field="serial_number", max_length=255)
    assert getattr(serial_error.value, "code", None) == "serial_number_too_long"

    with pytest.raises(Exception) as wwn_error:
        normalize_optional_identity("ß" * 128, field="wwn", max_length=255)
    assert getattr(wwn_error.value, "code", None) == "wwn_too_long"


def test_telegram_display_identity_fits_warehouse_snapshot_capacity() -> None:
    identity = TelegramIdentity(
        user_id="00000000-0000-4000-8000-000000000001",
        telegram_user_id=1,
        first_name="F" * 255,
        last_name="L" * 255,
        username="u" * 64,
    )
    assert len(display_identity(identity)) == 579
    movements = metadata.tables["movements"]
    for column_name in (
        "actor_display_name_snapshot",
        "source_holder_display_name_snapshot",
        "destination_holder_display_name_snapshot",
    ):
        column_type = movements.c[column_name].type
        assert isinstance(column_type, String)
        assert column_type.length == 579


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
    assert "/api/inventory/units" in operations
    assert "/api/inventory/units/{unit_id}" in operations
    assert "/api/inventory/movements" in operations
    assert "/api/inventory/movements/{movement_id}" in operations
    assert "/api/admin/inventory/locations" in operations
    assert "/api/admin/inventory/movements" in operations
    assert "/api/admin/inventory/movements/{movement_id}/reversal" in operations
    assert "delete" not in operations["/api/inventory/movements/{movement_id}"]
    assert "patch" not in operations["/api/inventory/movements/{movement_id}"]
