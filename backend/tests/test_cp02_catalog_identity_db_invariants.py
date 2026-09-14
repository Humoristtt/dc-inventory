from __future__ import annotations

import uuid
from contextlib import suppress
from decimal import Decimal

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.models import (
    Category,
    CategoryAttribute,
    Item,
    ItemAttributeValue,
)
from app.modules.catalog.normalization import item_signature
from app.modules.catalog.service import (
    create_item,
    get_item_record,
    normalize_comparison,
)
from tests.warehouse_helpers import cable_payload

pytestmark = pytest.mark.asyncio


async def _expected_signature(
    db: AsyncSession,
    item_id: uuid.UUID,
) -> str:
    record = await get_item_record(db, item_id)

    return item_signature(
        record.category.key,
        record.manufacturer.name if record.manufacturer else None,
        record.item.model,
        record.attributes,
    )


async def test_cp02_direct_name_change_cannot_leave_normalized_name_stale(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db

    item_id = await create_item(
        db,
        cable_payload(),
    )

    new_name = "CP02 Straße Cable"
    expected = normalize_comparison(
        new_name,
        field="name",
        max_length=255,
    )

    with suppress(DBAPIError):
        async with db.begin_nested():
            await db.execute(update(Item).where(Item.id == item_id).values(name=new_name))

            await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

            actual = await db.scalar(select(Item.normalized_name).where(Item.id == item_id))

            assert actual == expected


async def test_cp02_direct_normalized_name_change_cannot_diverge_from_name(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db

    item_id = await create_item(
        db,
        cable_payload(),
    )

    record = await get_item_record(db, item_id)

    expected = normalize_comparison(
        record.item.name,
        field="name",
        max_length=255,
    )

    with suppress(DBAPIError):
        async with db.begin_nested():
            await db.execute(
                update(Item)
                .where(Item.id == item_id)
                .values(normalized_name="cp02-forged-normalized-name")
            )

            await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

            actual = await db.scalar(select(Item.normalized_name).where(Item.id == item_id))

            assert actual == expected


async def test_cp02_direct_model_change_cannot_leave_identity_stale(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db

    item_id = await create_item(
        db,
        cable_payload(),
    )

    new_model = "MÖDEL-ß"

    expected_normalized_model = normalize_comparison(
        new_model,
        field="model",
        max_length=255,
    )

    with suppress(DBAPIError):
        async with db.begin_nested():
            await db.execute(update(Item).where(Item.id == item_id).values(model=new_model))

            await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

            record = await get_item_record(
                db,
                item_id,
            )

            expected_signature = await _expected_signature(
                db,
                item_id,
            )

            assert record.item.normalized_model == expected_normalized_model
            assert record.item.identity_signature == expected_signature


async def test_cp02_direct_eav_change_cannot_leave_identity_signature_stale(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db

    item_id = await create_item(
        db,
        cable_payload(),
    )

    length_attribute_id = await db.scalar(
        select(CategoryAttribute.id)
        .join(
            Category,
            Category.id == CategoryAttribute.category_id,
        )
        .where(
            Category.key == "optical_patch_cord",
            CategoryAttribute.key == "length_m",
        )
    )

    assert length_attribute_id is not None

    value_id = await db.scalar(
        select(ItemAttributeValue.id).where(
            ItemAttributeValue.item_id == item_id,
            ItemAttributeValue.category_attribute_id == length_attribute_id,
        )
    )

    assert value_id is not None

    with suppress(DBAPIError):
        async with db.begin_nested():
            await db.execute(
                update(ItemAttributeValue)
                .where(ItemAttributeValue.id == value_id)
                .values(decimal_value=Decimal("6"))
            )

            await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

            actual_signature = await db.scalar(
                select(Item.identity_signature).where(Item.id == item_id)
            )

            expected_signature = await _expected_signature(
                db,
                item_id,
            )

            assert actual_signature == expected_signature


async def test_cp02_direct_identity_signature_change_cannot_diverge_from_data(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db

    item_id = await create_item(
        db,
        cable_payload(),
    )

    forged_signature = uuid.uuid4().hex * 2

    with suppress(DBAPIError):
        async with db.begin_nested():
            await db.execute(
                update(Item).where(Item.id == item_id).values(identity_signature=forged_signature)
            )

            await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

            actual_signature = await db.scalar(
                select(Item.identity_signature).where(Item.id == item_id)
            )

            expected_signature = await _expected_signature(
                db,
                item_id,
            )

            assert actual_signature == expected_signature
