import asyncio
import os

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
)

from app.modules.catalog.models import Item, ItemAttributeValue
from app.modules.catalog.service import (
    CatalogItemInUseError,
    create_item,
    delete_unused_item,
)
from app.modules.inventory.models import MovementLine
from tests.warehouse_helpers import (
    cable_payload,
    move,
    scenario,
)

pytestmark = pytest.mark.asyncio


async def test_delete_unused_item_removes_never_used_item(
    warehouse_db: AsyncSession,
) -> None:
    item_id = await create_item(
        warehouse_db,
        cable_payload(),
    )

    attribute_count = await warehouse_db.scalar(
        select(func.count())
        .select_from(ItemAttributeValue)
        .where(ItemAttributeValue.item_id == item_id)
    )
    assert attribute_count
    assert attribute_count > 0

    await delete_unused_item(
        warehouse_db,
        item_id,
    )

    assert await warehouse_db.get(Item, item_id) is None

    remaining_attributes = await warehouse_db.scalar(
        select(func.count())
        .select_from(ItemAttributeValue)
        .where(ItemAttributeValue.item_id == item_id)
    )
    assert remaining_attributes == 0


async def test_delete_unused_item_rejects_item_with_movement_history(
    warehouse_db: AsyncSession,
) -> None:
    seed = await scenario(warehouse_db)

    await move(
        warehouse_db,
        seed,
        "RECEIPT",
        1,
        destination=seed[2],
    )

    with pytest.raises(
        CatalogItemInUseError,
        match="warehouse history",
    ):
        await delete_unused_item(
            warehouse_db,
            seed[1],
        )

    assert await warehouse_db.get(Item, seed[1]) is not None

async def test_delete_unused_item_serializes_with_first_movement() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("requires migrated disposable PostgreSQL")

    engine = create_async_engine(
        os.environ["DATABASE_URL"],
    )

    try:
        async with AsyncSession(
            engine,
            expire_on_commit=False,
        ) as setup_db:
            seed = await scenario(setup_db)
            await setup_db.commit()

        async with AsyncSession(
            engine,
            expire_on_commit=False,
        ) as movement_db:
            locked_item = await movement_db.scalar(
                select(Item)
                .where(Item.id == seed[1])
                .with_for_update()
            )
            assert locked_item is not None

            async def attempt_delete() -> str:
                async with AsyncSession(
                    engine,
                    expire_on_commit=False,
                ) as delete_db:
                    try:
                        await delete_unused_item(
                            delete_db,
                            seed[1],
                        )
                        await delete_db.commit()
                    except CatalogItemInUseError:
                        await delete_db.rollback()
                        return "in_use"
                    return "deleted"

            delete_task = asyncio.create_task(
                attempt_delete(),
            )

            await asyncio.sleep(0.05)
            assert not delete_task.done()

            await move(
                movement_db,
                seed,
                "RECEIPT",
                1,
                destination=seed[2],
            )
            await movement_db.commit()

            result = await asyncio.wait_for(
                delete_task,
                timeout=2,
            )
            assert result == "in_use"

        async with AsyncSession(
            engine,
            expire_on_commit=False,
        ) as verify_db:
            assert (
                await verify_db.get(
                    Item,
                    seed[1],
                )
                is not None
            )

            movement_line_count = await verify_db.scalar(
                select(func.count())
                .select_from(MovementLine)
                .where(
                    MovementLine.item_id
                    == seed[1]
                )
            )
            assert movement_line_count == 1
    finally:
        await engine.dispose()

