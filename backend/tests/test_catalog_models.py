from sqlalchemy import CheckConstraint

import app.db.models  # noqa: F401  # регистрирует ORM-модели в metadata
from app.db.base import metadata
from app.main import app as application
from app.modules.catalog.enums import (
    AccountingMode,
    AttributeDataType,
    FilterType,
    ItemStatus,
)


def _constraint_names(table_name: str) -> set[str]:
    return {
        str(constraint.name)
        for constraint in metadata.tables[table_name].constraints
        if constraint.name is not None
    }


def test_catalog_tables_are_registered_in_shared_metadata() -> None:
    assert {
        "categories",
        "manufacturers",
        "category_attributes",
        "items",
        "item_attribute_values",
    } <= set(metadata.tables)


def test_catalog_structural_enum_values_are_stable() -> None:
    assert [mode.value for mode in AccountingMode] == ["QUANTITY", "SERIAL"]
    assert [status.value for status in ItemStatus] == ["ACTIVE", "ARCHIVED"]
    assert [data_type.value for data_type in AttributeDataType] == [
        "TEXT",
        "INTEGER",
        "DECIMAL",
        "BOOLEAN",
        "ENUM",
    ]
    assert [filter_type.value for filter_type in FilterType] == [
        "NONE",
        "EXACT",
        "RANGE",
    ]


def test_catalog_constraints_have_stable_names() -> None:
    assert {
        "pk_categories",
        "uq_categories_key",
        "ck_categories_default_accounting_mode",
    } <= _constraint_names("categories")
    assert {
        "pk_manufacturers",
        "uq_manufacturers_normalized_name",
    } <= _constraint_names("manufacturers")
    assert {
        "uq_category_attributes_category_id_key",
        "ck_category_attributes_allowed_values_match_data_type",
    } <= _constraint_names("category_attributes")
    assert {
        "ck_items_archive_state",
        "uq_items_normalized_internal_code",
    } <= _constraint_names("items")
    assert {
        "uq_item_attribute_values_item_id_category_attribute_id",
        "ck_item_attribute_values_exactly_one_typed_value",
    } <= _constraint_names("item_attribute_values")


def test_exactly_one_typed_value_check_uses_postgresql_num_nonnulls() -> None:
    constraint = next(
        constraint
        for constraint in metadata.tables["item_attribute_values"].constraints
        if isinstance(constraint, CheckConstraint)
        and constraint.name == "ck_item_attribute_values_exactly_one_typed_value"
    )
    assert "num_nonnulls" in str(constraint.sqltext)


def test_catalog_routes_are_registered_without_item_delete() -> None:
    operations = application.openapi()["paths"]
    assert "/api/catalog/categories" in operations
    assert "/api/catalog/categories/{category_key}" in operations
    assert "/api/catalog/manufacturers" in operations
    assert "/api/catalog/items" in operations
    assert "/api/catalog/items/{item_id}" in operations
    assert "/api/admin/catalog/manufacturers" in operations
    assert "/api/admin/catalog/items" in operations
    assert "/api/admin/catalog/items/check-duplicates" in operations
    assert "/api/admin/catalog/items/{item_id}" in operations
    assert "/api/admin/catalog/items/{item_id}/archive" in operations
    assert "/api/admin/catalog/items/{item_id}/unarchive" in operations
    assert "delete" not in operations["/api/admin/catalog/items/{item_id}"]
