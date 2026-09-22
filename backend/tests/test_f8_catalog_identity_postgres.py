"""Isolated PostgreSQL 18 regressions for f8 catalog identity invariants."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.models import Category, CategoryAttribute, Item, ItemAttributeValue
from app.modules.catalog.normalization import (
    decimal_identity_text,
    identity_text,
    item_signature,
)
from app.modules.catalog.schemas import ItemPatch
from app.modules.catalog.service import (
    create_item,
    get_item_record,
    normalize_comparison,
    update_item,
)
from tests.warehouse_helpers import cable_payload

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(
    "raw",
    ["1000.0000000000", "123000.0000000000", "0.0000001000", "-25.5000000000"],
)
async def test_f8_decimal_identity_matches_postgres(
    warehouse_db: AsyncSession, raw: str
) -> None:
    actual = await warehouse_db.scalar(
        text("SELECT catalog_decimal_identity(CAST(:raw AS numeric))"),
        {"raw": raw},
    )
    assert actual == decimal_identity_text(Decimal(raw))


async def test_f8_comparison_normalization_matches_postgres(
    warehouse_db: AsyncSession,
) -> None:
    raw = "  Straße   MÖDEL  "
    actual = await warehouse_db.scalar(
        text("SELECT catalog_normalize_comparison(CAST(:raw AS text))"),
        {"raw": raw},
    )
    assert actual == normalize_comparison(raw)


async def test_f8_nfkc_identity_normalization_matches_postgres(
    warehouse_db: AsyncSession,
) -> None:
    raw = "  Ｆｏｏ   Straße  "
    actual = await warehouse_db.scalar(
        text("SELECT catalog_identity_text(CAST(:raw AS text))"),
        {"raw": raw},
    )
    assert actual == identity_text(raw) == "foo strasse"


async def _assert_signatures_match(db: AsyncSession, item_id: object) -> None:
    record = await get_item_record(db, item_id)
    expected = item_signature(
        record.category.key,
        record.manufacturer.name if record.manufacturer else None,
        record.item.model,
        record.attributes,
    )
    actual = await db.scalar(
        text("SELECT catalog_item_signature(CAST(:item_id AS uuid))"),
        {"item_id": str(item_id)},
    )
    assert actual == expected == record.item.identity_signature


async def test_f8_normal_create_matches_database_signature(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    item_id = await create_item(db, cable_payload(length_m="1000"))
    await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await _assert_signatures_match(db, item_id)


async def test_f8_normal_catalog_update_preserves_identity_invariant(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    payload = cable_payload(length_m="1000")
    item_id = await create_item(db, payload)
    patch = ItemPatch(
        name="CP08 Straße cable",
        model="MÖDEL-ß",
        attributes={**payload.attributes, "length_m": "123000"},
    )
    await update_item(db, item_id, patch, fields_set=patch.model_fields_set)
    await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await _assert_signatures_match(db, item_id)


async def test_f8_rejects_forged_derived_name(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    item_id = await create_item(db, cable_payload())
    await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db.execute(text("SET CONSTRAINTS ALL DEFERRED"))

    original = await db.scalar(select(Item.normalized_name).where(Item.id == item_id))
    assert original is not None

    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(
                update(Item)
                .where(Item.id == item_id)
                .values(normalized_name="forged-derived-value")
            )
            await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

    assert await db.scalar(
        select(Item.normalized_name).where(Item.id == item_id)
    ) == original


async def test_f8_rejects_direct_eav_change_with_stale_signature(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    item_id = await create_item(db, cable_payload())
    await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db.execute(text("SET CONSTRAINTS ALL DEFERRED"))

    value_id = await db.scalar(
        select(ItemAttributeValue.id)
        .join(CategoryAttribute, CategoryAttribute.id == ItemAttributeValue.category_attribute_id)
        .join(Category, Category.id == CategoryAttribute.category_id)
        .where(
            ItemAttributeValue.item_id == item_id,
            Category.key == "optical_patch_cord",
            CategoryAttribute.key == "length_m",
        )
    )
    assert value_id is not None

    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(
                update(ItemAttributeValue)
                .where(ItemAttributeValue.id == value_id)
                .values(decimal_value=Decimal("6"))
            )
            await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

    await _assert_signatures_match(db, item_id)
