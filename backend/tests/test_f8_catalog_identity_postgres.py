"""Isolated PostgreSQL 18 regressions for f8 catalog identity invariants."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.models import Item
from app.modules.catalog.normalization import decimal_identity_text, item_signature
from app.modules.catalog.service import create_item, get_item_record, normalize_comparison
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


async def test_f8_normal_create_matches_database_signature(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    item_id = await create_item(db, cable_payload(length_m="1000"))
    await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

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


async def test_f8_rejects_forged_derived_name(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    item_id = await create_item(db, cable_payload())
    await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db.execute(text("SET CONSTRAINTS ALL DEFERRED"))

    original = await db.scalar(
        select(Item.normalized_name).where(Item.id == item_id)
    )
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
