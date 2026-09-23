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


@pytest.mark.parametrize(
    "raw",
    [
        "1000.0000000000",
        "123000.0000000000",
        "0.0000001000",
        "5.0000000000",
        "-25.5000000000",
    ],
)
async def test_cp02_decimal_identity_python_and_db_match(
    warehouse_db: AsyncSession,
    raw: str,
) -> None:
    from app.modules.catalog.normalization import (
        decimal_identity_text,
    )

    db = warehouse_db

    python_value = decimal_identity_text(Decimal(raw))

    database_value = await db.scalar(
        text(
            """
            SELECT catalog_decimal_identity(
                CAST(:value AS numeric)
            )
            """
        ),
        {"value": raw},
    )

    assert database_value == python_value


async def test_cp02_normal_catalog_service_satisfies_identity_guard(
    warehouse_db: AsyncSession,
) -> None:
    from app.modules.catalog.schemas import ItemPatch
    from app.modules.catalog.service import update_item

    db = warehouse_db

    payload = cable_payload(
        length_m="1000",
    )

    item_id = await create_item(
        db,
        payload,
    )

    await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

    stored_signature = await db.scalar(select(Item.identity_signature).where(Item.id == item_id))

    database_signature = await db.scalar(
        text(
            """
            SELECT catalog_item_signature(
                CAST(:item_id AS uuid)
            )
            """
        ),
        {"item_id": str(item_id)},
    )

    assert stored_signature == database_signature

    await db.execute(text("SET CONSTRAINTS ALL DEFERRED"))

    attributes = dict(payload.attributes)
    attributes["length_m"] = "123000"

    patch = ItemPatch(
        name="CP02 Straße Cable",
        model="MÖDEL-ß",
        attributes=attributes,
    )

    await update_item(
        db,
        item_id,
        patch,
        fields_set=patch.model_fields_set,
    )

    await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

    record = await get_item_record(
        db,
        item_id,
    )

    assert record.item.normalized_name == normalize_comparison(
        record.item.name,
        field="name",
        max_length=255,
    )

    assert record.item.normalized_model == normalize_comparison(
        record.item.model or "",
        field="model",
        max_length=255,
    )

    assert record.item.identity_signature == await _expected_signature(
        db,
        item_id,
    )

    assert record.item.identity_signature == await db.scalar(
        text(
            """
                SELECT catalog_item_signature(
                    CAST(:item_id AS uuid)
                )
                """
        ),
        {"item_id": str(item_id)},
    )


async def test_cp02_readiness_rejects_missing_identity_helper_function(
    migration_database: str,
) -> None:
    from sqlalchemy.ext.asyncio import (
        create_async_engine,
    )

    from app.db.health import (
        DatabaseUnavailableError,
        ensure_database_ready,
    )
    from tests.migration_helpers import alembic

    alembic(
        migration_database,
        "upgrade",
        "head",
    )

    engine = create_async_engine(
        migration_database,
        pool_pre_ping=True,
    )

    try:
        await ensure_database_ready(engine)

        async with engine.begin() as connection:
            await connection.execute(text("DROP FUNCTION catalog_item_signature(uuid)"))

        with pytest.raises(DatabaseUnavailableError):
            await ensure_database_ready(engine)

    finally:
        await engine.dispose()
