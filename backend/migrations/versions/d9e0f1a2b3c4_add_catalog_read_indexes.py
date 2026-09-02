"""add catalog search, filter, and inventory-read indexes

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-09-02 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d9e0f1a2b3c4"
down_revision: str | Sequence[str] | None = "c8d9e0f1a2b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_trigram_index(table: str, column: str, name: str) -> None:
    op.create_index(
        name,
        table,
        [column],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={column: "gin_trgm_ops"},
    )


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    _create_trigram_index(
        "manufacturers",
        "normalized_name",
        "ix_manufacturers_normalized_name_trgm",
    )
    _create_trigram_index("items", "normalized_name", "ix_items_normalized_name_trgm")
    _create_trigram_index("items", "normalized_model", "ix_items_normalized_model_trgm")
    _create_trigram_index(
        "items",
        "normalized_manufacturer_part_number",
        "ix_items_normalized_mpn_trgm",
    )
    _create_trigram_index(
        "items",
        "normalized_internal_code",
        "ix_items_normalized_internal_code_trgm",
    )
    _create_trigram_index(
        "item_attribute_values",
        "text_value",
        "ix_item_attribute_values_text_trgm",
    )
    _create_trigram_index(
        "item_attribute_values",
        "enum_value",
        "ix_item_attribute_values_enum_trgm",
    )
    _create_trigram_index(
        "inventory_units",
        "normalized_serial_number",
        "ix_inventory_units_normalized_serial_trgm",
    )
    _create_trigram_index(
        "inventory_units",
        "normalized_wwn",
        "ix_inventory_units_normalized_wwn_trgm",
    )

    for name, column in (
        ("ix_item_attribute_values_integer_filter", "integer_value"),
        ("ix_item_attribute_values_decimal_filter", "decimal_value"),
        ("ix_item_attribute_values_boolean_filter", "boolean_value"),
        ("ix_item_attribute_values_enum_filter", "enum_value"),
    ):
        op.create_index(
            name,
            "item_attribute_values",
            ["category_attribute_id", column, "item_id"],
            unique=False,
            postgresql_where=sa.text(f"{column} IS NOT NULL"),
        )

    op.create_index(
        "ix_inventory_units_item_state_location",
        "inventory_units",
        ["item_id", "state", "current_location_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_inventory_units_item_state_location",
        table_name="inventory_units",
    )
    for name in (
        "ix_item_attribute_values_enum_filter",
        "ix_item_attribute_values_boolean_filter",
        "ix_item_attribute_values_decimal_filter",
        "ix_item_attribute_values_integer_filter",
        "ix_inventory_units_normalized_wwn_trgm",
        "ix_inventory_units_normalized_serial_trgm",
        "ix_item_attribute_values_enum_trgm",
        "ix_item_attribute_values_text_trgm",
        "ix_items_normalized_internal_code_trgm",
        "ix_items_normalized_mpn_trgm",
        "ix_items_normalized_model_trgm",
        "ix_items_normalized_name_trgm",
        "ix_manufacturers_normalized_name_trgm",
    ):
        op.drop_index(name)
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
