"""Уточнить versioned catalog metadata по source reference.

Revision ID: a6b7c8d9e0f1
Revises: f4a5b6c7d8e9
Create Date: 2026-09-01
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a6b7c8d9e0f1"
down_revision: str | Sequence[str] | None = "f4a5b6c7d8e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FOUNDATION_TIMESTAMP = datetime(2026, 9, 1, tzinfo=UTC)
REFINEMENT_TIMESTAMP = datetime(2026, 9, 1, 21, 0, tzinfo=UTC)

SFP_CATEGORY_ID = uuid.UUID("10000000-0000-4000-8000-000000000001")
POWER_CABLE_CATEGORY_ID = uuid.UUID("10000000-0000-4000-8000-000000000003")
COPPER_NETWORK_CABLE_CATEGORY_ID = uuid.UUID(
    "10000000-0000-4000-8000-000000000006"
)

POWER_CABLE_ATTRIBUTE_IDS = {
    uuid.UUID("20000003-0000-4000-8000-000000000007"),
    uuid.UUID("20000003-0000-4000-8000-000000000008"),
}
COPPER_NETWORK_CABLE_ATTRIBUTE_IDS = {
    uuid.UUID(f"20000006-0000-4000-8000-{sequence:012d}")
    for sequence in range(1, 6)
}

FOUNDATION_SFP_FORM_FACTORS = [
    "SFP",
    "SFP+",
    "SFP28",
    "QSFP+",
    "QSFP28",
    "QSFP56",
    "QSFP-DD",
]
REFINED_SFP_FORM_FACTORS = [
    "SFP",
    "SFP+",
    "SFP28",
    "XFP",
    "QSFP+",
    "QSFP28",
    "QSFP56",
    "QSFP-DD",
]
FOUNDATION_SFP_CONNECTORS = [
    "LC Duplex",
    "LC Simplex",
    "MPO/MTP",
    "RJ45",
]
REFINED_SFP_CONNECTORS = [
    "LC Duplex",
    "LC Simplex",
    "SC Simplex",
    "MPO/MTP",
    "RJ45",
]


def _attribute(
    attribute_id: uuid.UUID,
    category_id: uuid.UUID,
    sequence: int,
    key: str,
    label: str,
    data_type: str,
    *,
    unit: str | None = None,
    required: bool = False,
    filterable: bool = False,
    searchable: bool = False,
    card_visible: bool = False,
    table_visible: bool = False,
    allowed_values: list[str] | None = None,
    validation_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": attribute_id,
        "category_id": category_id,
        "key": key,
        "label": label,
        "data_type": data_type,
        "unit": unit,
        "required": required,
        "filterable": filterable,
        "searchable": searchable,
        "card_visible": card_visible,
        "detail_visible": True,
        "table_visible": table_visible,
        "excel_visible": True,
        "sort_order": sequence * 10,
        "filter_type": (
            "RANGE"
            if filterable and data_type in {"INTEGER", "DECIMAL"}
            else "EXACT"
            if filterable
            else "NONE"
        ),
        "allowed_values": allowed_values,
        "validation_metadata": validation_metadata,
        "is_system": True,
        "created_at": REFINEMENT_TIMESTAMP,
        "updated_at": REFINEMENT_TIMESTAMP,
    }


def _refined_attributes() -> list[dict[str, Any]]:
    return [
        _attribute(
            uuid.UUID("20000003-0000-4000-8000-000000000007"),
            POWER_CABLE_CATEGORY_ID,
            7,
            "conductor_count",
            "Количество проводников",
            "INTEGER",
            filterable=True,
            table_visible=True,
            validation_metadata={"min": 1},
        ),
        _attribute(
            uuid.UUID("20000003-0000-4000-8000-000000000008"),
            POWER_CABLE_CATEGORY_ID,
            8,
            "conductor_cross_section_mm2",
            "Сечение проводника",
            "DECIMAL",
            unit="mm2",
            filterable=True,
            table_visible=True,
            validation_metadata={"min": 0},
        ),
        _attribute(
            uuid.UUID("20000006-0000-4000-8000-000000000001"),
            COPPER_NETWORK_CABLE_CATEGORY_ID,
            1,
            "connector_a",
            "Разъём A",
            "TEXT",
            required=True,
            filterable=True,
            searchable=True,
            card_visible=True,
            table_visible=True,
            validation_metadata={"max_length": 255},
        ),
        _attribute(
            uuid.UUID("20000006-0000-4000-8000-000000000002"),
            COPPER_NETWORK_CABLE_CATEGORY_ID,
            2,
            "connector_b",
            "Разъём B",
            "TEXT",
            required=True,
            filterable=True,
            searchable=True,
            card_visible=True,
            table_visible=True,
            validation_metadata={"max_length": 255},
        ),
        _attribute(
            uuid.UUID("20000006-0000-4000-8000-000000000003"),
            COPPER_NETWORK_CABLE_CATEGORY_ID,
            3,
            "length_m",
            "Длина",
            "DECIMAL",
            unit="m",
            required=True,
            filterable=True,
            card_visible=True,
            table_visible=True,
            validation_metadata={"min": 0},
        ),
        _attribute(
            uuid.UUID("20000006-0000-4000-8000-000000000004"),
            COPPER_NETWORK_CABLE_CATEGORY_ID,
            4,
            "cable_category",
            "Категория кабеля",
            "TEXT",
            required=True,
            filterable=True,
            searchable=True,
            card_visible=True,
            table_visible=True,
            validation_metadata={"max_length": 100},
        ),
        _attribute(
            uuid.UUID("20000006-0000-4000-8000-000000000005"),
            COPPER_NETWORK_CABLE_CATEGORY_ID,
            5,
            "shielding",
            "Экранирование",
            "TEXT",
            filterable=True,
            searchable=True,
            card_visible=True,
            table_visible=True,
            validation_metadata={"max_length": 100},
        ),
    ]


def _category_table() -> sa.TableClause:
    return sa.table(
        "categories",
        sa.column("id", sa.Uuid()),
        sa.column("key", sa.String()),
        sa.column("display_name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("default_accounting_mode", sa.String()),
        sa.column("sort_order", sa.Integer()),
        sa.column("is_system", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )


def _attribute_table() -> sa.TableClause:
    return sa.table(
        "category_attributes",
        sa.column("id", sa.Uuid()),
        sa.column("category_id", sa.Uuid()),
        sa.column("key", sa.String()),
        sa.column("label", sa.String()),
        sa.column("data_type", sa.String()),
        sa.column("unit", sa.String()),
        sa.column("required", sa.Boolean()),
        sa.column("filterable", sa.Boolean()),
        sa.column("searchable", sa.Boolean()),
        sa.column("card_visible", sa.Boolean()),
        sa.column("detail_visible", sa.Boolean()),
        sa.column("table_visible", sa.Boolean()),
        sa.column("excel_visible", sa.Boolean()),
        sa.column("sort_order", sa.Integer()),
        sa.column("filter_type", sa.String()),
        sa.column("allowed_values", postgresql.JSONB(none_as_null=True)),
        sa.column("validation_metadata", postgresql.JSONB(none_as_null=True)),
        sa.column("is_system", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )


def _set_sfp_allowed_values(
    attribute_table: sa.TableClause,
    *,
    form_factors: list[str],
    connectors: list[str],
    updated_at: datetime,
) -> None:
    op.execute(
        attribute_table.update()
        .where(
            attribute_table.c.category_id == SFP_CATEGORY_ID,
            attribute_table.c.key == "form_factor",
        )
        .values(allowed_values=form_factors, updated_at=updated_at)
    )
    op.execute(
        attribute_table.update()
        .where(
            attribute_table.c.category_id == SFP_CATEGORY_ID,
            attribute_table.c.key == "connector",
        )
        .values(allowed_values=connectors, updated_at=updated_at)
    )


def upgrade() -> None:
    category_table = _category_table()
    attribute_table = _attribute_table()

    _set_sfp_allowed_values(
        attribute_table,
        form_factors=REFINED_SFP_FORM_FACTORS,
        connectors=REFINED_SFP_CONNECTORS,
        updated_at=REFINEMENT_TIMESTAMP,
    )

    op.bulk_insert(
        category_table,
        [
            {
                "id": COPPER_NETWORK_CABLE_CATEGORY_ID,
                "key": "copper_network_cable",
                "display_name": "Медные сетевые кабели",
                "description": (
                    "Медные сетевые патч-корды и аналогичная кабельная продукция."
                ),
                "default_accounting_mode": "QUANTITY",
                "sort_order": 25,
                "is_system": True,
                "created_at": REFINEMENT_TIMESTAMP,
                "updated_at": REFINEMENT_TIMESTAMP,
            }
        ],
    )
    op.bulk_insert(attribute_table, _refined_attributes())


def downgrade() -> None:
    category_table = _category_table()
    attribute_table = _attribute_table()

    op.execute(
        attribute_table.delete().where(
            attribute_table.c.id.in_(POWER_CABLE_ATTRIBUTE_IDS)
        )
    )
    op.execute(
        attribute_table.delete().where(
            attribute_table.c.id.in_(COPPER_NETWORK_CABLE_ATTRIBUTE_IDS)
        )
    )
    op.execute(
        category_table.delete().where(
            category_table.c.id == COPPER_NETWORK_CABLE_CATEGORY_ID
        )
    )

    _set_sfp_allowed_values(
        attribute_table,
        form_factors=FOUNDATION_SFP_FORM_FACTORS,
        connectors=FOUNDATION_SFP_CONNECTORS,
        updated_at=FOUNDATION_TIMESTAMP,
    )
