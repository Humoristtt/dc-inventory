"""Refine SFP metadata for the authoritative inventory contract.

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-09-03
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a2b3c4d5e6f7"
down_revision: str | Sequence[str] | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SFP_CATEGORY_ID = uuid.UUID("10000000-0000-4000-8000-000000000001")
SFP_CONNECTOR_ATTRIBUTE_ID = uuid.UUID(
    "20000001-0000-4000-8000-000000000006"
)
SFP_PROFILE_ATTRIBUTE_IDS = {
    uuid.UUID("20000001-0000-4000-8000-000000000011"),
    uuid.UUID("20000001-0000-4000-8000-000000000012"),
    uuid.UUID("20000001-0000-4000-8000-000000000013"),
    uuid.UUID("20000001-0000-4000-8000-000000000014"),
}

PREVIOUS_TIMESTAMP = datetime(2026, 9, 1, 21, 0, tzinfo=UTC)
REFINEMENT_TIMESTAMP = datetime(2026, 9, 3, 21, 0, tzinfo=UTC)

PREVIOUS_CONNECTORS = [
    "LC Duplex",
    "LC Simplex",
    "SC Simplex",
    "MPO/MTP",
    "RJ45",
]
REFINED_CONNECTORS = [
    "LC Duplex",
    "LC Simplex",
    "SC Simplex",
    "MPO",
    "MPO/PC",
    "MPO/MTP",
    "RJ45",
]


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


def _item_attribute_value_table() -> sa.TableClause:
    return sa.table(
        "item_attribute_values",
        sa.column("category_attribute_id", sa.Uuid()),
        sa.column("enum_value", sa.String()),
    )


def _profile_attribute(
    attribute_id: uuid.UUID,
    key: str,
    label: str,
    sort_order: int,
    *,
    max_length: int,
    data_type: str = "TEXT",
    unit: str | None = None,
    filterable: bool = False,
) -> dict[str, Any]:
    return {
        "id": attribute_id,
        "category_id": SFP_CATEGORY_ID,
        "key": key,
        "label": label,
        "data_type": data_type,
        "unit": unit,
        "required": False,
        "filterable": filterable,
        "searchable": True,
        "card_visible": False,
        "detail_visible": True,
        "table_visible": True,
        "excel_visible": True,
        "sort_order": sort_order,
        "filter_type": "RANGE" if filterable else "NONE",
        "allowed_values": None,
        "validation_metadata": (
            {"min": 0}
            if data_type == "DECIMAL"
            else {
                "max_length": max_length,
                "preserve_whitespace": True,
            }
        ),
        "is_system": True,
        "created_at": REFINEMENT_TIMESTAMP,
        "updated_at": REFINEMENT_TIMESTAMP,
    }


def upgrade() -> None:
    attribute_table = _attribute_table()
    op.execute(
        attribute_table.update()
        .where(attribute_table.c.id == SFP_CONNECTOR_ATTRIBUTE_ID)
        .values(
            allowed_values=REFINED_CONNECTORS,
            updated_at=REFINEMENT_TIMESTAMP,
        )
    )
    op.bulk_insert(
        attribute_table,
        [
            _profile_attribute(
                uuid.UUID("20000001-0000-4000-8000-000000000011"),
                "speed_profile",
                "Профиль скорости",
                15,
                max_length=255,
            ),
            _profile_attribute(
                uuid.UUID("20000001-0000-4000-8000-000000000012"),
                "reach_profile",
                "Профиль дальности",
                45,
                max_length=2000,
            ),
            _profile_attribute(
                uuid.UUID("20000001-0000-4000-8000-000000000013"),
                "wavelength_profile",
                "Профиль длины волны",
                65,
                max_length=255,
            ),
            _profile_attribute(
                uuid.UUID("20000001-0000-4000-8000-000000000014"),
                "nominal_wavelength_nm",
                "Номинальная длина волны",
                67,
                max_length=0,
                data_type="DECIMAL",
                unit="nm",
                filterable=True,
            ),
        ],
    )


def downgrade() -> None:
    attribute_table = _attribute_table()
    item_attribute_value_table = _item_attribute_value_table()

    connection = op.get_bind()
    profile_value_exists = connection.execute(
        sa.select(sa.literal(True))
        .select_from(item_attribute_value_table)
        .where(
            item_attribute_value_table.c.category_attribute_id.in_(
                SFP_PROFILE_ATTRIBUTE_IDS
            )
        )
        .limit(1)
    ).scalar_one_or_none()

    if profile_value_exists is not None:
        raise RuntimeError(
            "Refusing destructive downgrade of a2b3c4d5e6f7: "
            "SFP profile attribute values exist. Use a forward fix or "
            "restore a verified PostgreSQL backup instead."
        )

    op.execute(
        attribute_table.delete().where(
            attribute_table.c.id.in_(SFP_PROFILE_ATTRIBUTE_IDS)
        )
    )
    op.execute(
        attribute_table.update()
        .where(attribute_table.c.id == SFP_CONNECTOR_ATTRIBUTE_ID)
        .values(
            allowed_values=PREVIOUS_CONNECTORS,
            updated_at=PREVIOUS_TIMESTAMP,
        )
    )
