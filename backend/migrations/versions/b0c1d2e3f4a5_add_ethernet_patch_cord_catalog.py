"""Add the Ethernet patch-cord catalog schema.

Revision ID: b0c1d2e3f4a5
Revises: a9c0d1e2f3a4
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from alembic import op

revision: str = "b0c1d2e3f4a5"
down_revision: str | Sequence[str] | None = "a9c0d1e2f3a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FAMILY_KEY = "copper_cabling"
LEAF_KEY = "ethernet_patch_cord"

FAMILY_ID = str(
    uuid5(
        NAMESPACE_URL,
        "spikatel:category:" + FAMILY_KEY,
    )
)
LEAF_ID = str(
    uuid5(
        NAMESPACE_URL,
        "spikatel:category:" + LEAF_KEY,
    )
)

ATTRIBUTES = (
    ("cable_category", "Категория", "TEXT", None, True),
    ("connector_a", "Разъём A", "TEXT", None, True),
    ("connector_b", "Разъём B", "TEXT", None, True),
    ("length_m", "Длина", "DECIMAL", "м", True),
    ("shielding", "Экранирование", "TEXT", None, True),
    ("color", "Цвет", "TEXT", None, True),
)


def _attribute_id(key: str) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            "spikatel:attribute:" + LEAF_KEY + ":" + key,
        )
    )


def upgrade() -> None:
    connection = op.get_bind()

    connection.execute(
        sa.text(
            """
            INSERT INTO categories (
                id,
                key,
                display_name,
                description,
                sort_order,
                is_system
            )
            VALUES (
                :id,
                :key,
                :display_name,
                :description,
                :sort_order,
                true
            )
            """
        ),
        {
            "id": FAMILY_ID,
            "key": FAMILY_KEY,
            "display_name": "Медные кабели",
            "description": (
                "Ethernet-патч-корды и другие медные "
                "сетевые соединения."
            ),
            "sort_order": 7,
        },
    )

    connection.execute(
        sa.text(
            """
            INSERT INTO categories (
                id,
                key,
                display_name,
                parent_id,
                sort_order,
                is_system
            )
            VALUES (
                :id,
                :key,
                :display_name,
                :parent_id,
                :sort_order,
                true
            )
            """
        ),
        {
            "id": LEAF_ID,
            "key": LEAF_KEY,
            "display_name": "Ethernet патч-корды",
            "parent_id": FAMILY_ID,
            "sort_order": 11,
        },
    )

    for sort_order, (
        key,
        label,
        data_type,
        unit,
        required,
    ) in enumerate(ATTRIBUTES):
        numeric = data_type in {"INTEGER", "DECIMAL"}
        metadata = (
            {"min": 0.0000000001}
            if data_type == "DECIMAL"
            else {"min": 1}
            if data_type == "INTEGER"
            else {"max_length": 2000}
        )

        connection.execute(
            sa.text(
                """
                INSERT INTO category_attributes (
                    id,
                    category_id,
                    key,
                    label,
                    data_type,
                    unit,
                    required,
                    filterable,
                    searchable,
                    card_visible,
                    detail_visible,
                    table_visible,
                    excel_visible,
                    sort_order,
                    filter_type,
                    validation_metadata,
                    is_system
                )
                VALUES (
                    :id,
                    :category_id,
                    :key,
                    :label,
                    :data_type,
                    :unit,
                    :required,
                    true,
                    true,
                    true,
                    true,
                    true,
                    true,
                    :sort_order,
                    :filter_type,
                    CAST(:validation_metadata AS jsonb),
                    true
                )
                """
            ),
            {
                "id": _attribute_id(key),
                "category_id": LEAF_ID,
                "key": key,
                "label": label,
                "data_type": data_type,
                "unit": unit,
                "required": required,
                "sort_order": sort_order,
                "filter_type": "RANGE" if numeric else "EXACT",
                "validation_metadata": json.dumps(metadata),
            },
        )


def downgrade() -> None:
    connection = op.get_bind()

    item_count = connection.scalar(
        sa.text(
            """
            SELECT count(*)
            FROM items
            WHERE category_id = CAST(:category_id AS uuid)
            """
        ),
        {"category_id": LEAF_ID},
    )
    procurement_line_count = connection.scalar(
        sa.text(
            """
            SELECT count(*)
            FROM procurement_revision_lines
            WHERE display_snapshot ->> 'category_key' = :category_key
            """
        ),
        {"category_key": LEAF_KEY},
    )

    if item_count or procurement_line_count:
        raise RuntimeError(
            "cannot remove ethernet_patch_cord while catalog or "
            "procurement history references it"
        )

    connection.execute(
        sa.text(
            """
            DELETE FROM category_attributes
            WHERE category_id = CAST(:category_id AS uuid)
            """
        ),
        {"category_id": LEAF_ID},
    )
    connection.execute(
        sa.text(
            """
            DELETE FROM categories
            WHERE id = CAST(:category_id AS uuid)
            """
        ),
        {"category_id": LEAF_ID},
    )

    family_children = connection.scalar(
        sa.text(
            """
            SELECT count(*)
            FROM categories
            WHERE parent_id = CAST(:family_id AS uuid)
            """
        ),
        {"family_id": FAMILY_ID},
    )
    if family_children:
        raise RuntimeError(
            "cannot remove copper_cabling while child categories remain"
        )

    connection.execute(
        sa.text(
            """
            DELETE FROM categories
            WHERE id = CAST(:family_id AS uuid)
            """
        ),
        {"family_id": FAMILY_ID},
    )
