from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.bootstrap.inventory_workbook import (
    SHEETS,
    Validation,
    normalize_row,
)
from app.bootstrap.production_inventory_receipt import (
    apply_inventory_receipt,
    plan_inventory_receipt,
)
from app.modules.catalog.models import Item
from app.modules.inventory.models import Movement, StockBalance
from app.modules.inventory.schemas import LocationCreate
from app.modules.inventory.service import create_location
from tests.migration_helpers import alembic
from tests.warehouse_helpers import actor

pytestmark = pytest.mark.asyncio


def validation_fixture() -> Validation:
    stocked_row = dict(
        zip(
            SHEETS["Ethernet патч-корды"],
            [
                "Cat.6",
                "RJ-45",
                "RJ-45",
                "2 м",
                "UTP",
                "Синий",
                "7",
            ],
            strict=True,
        )
    )
    zero_stock_row = dict(
        zip(
            SHEETS["Ethernet патч-корды"],
            [
                "Cat.6",
                "RJ-45",
                "RJ-45",
                "3 м",
                "UTP",
                "Серый",
                "0",
            ],
            strict=True,
        )
    )
    items = [
        normalize_row(
            "Ethernet патч-корды",
            stocked_row,
            "Ethernet патч-корды!2",
            allow_zero_quantity=True,
        ),
        normalize_row(
            "Ethernet патч-корды",
            zero_stock_row,
            "Ethernet патч-корды!3",
            allow_zero_quantity=True,
        ),
    ]
    return Validation(
        path=Path("synthetic-incremental.xlsx"),
        sheets=["Ethernet патч-корды"],
        raw_rows=2,
        source_quantity=7,
        items=items,
    )


async def test_incremental_receipt_creates_stock_and_replays_by_source(
    migration_database: str,
) -> None:
    alembic(migration_database, "upgrade", "head")

    engine = create_async_engine(migration_database)
    validation = validation_fixture()
    source_hash = "a" * 64

    try:
        async with AsyncSession(
            engine,
            expire_on_commit=False,
        ) as db, db.begin():
            first_actor, _ = await actor(db)
            location = await create_location(
                db,
                LocationCreate(
                    code="INCREMENTAL-01",
                    name="Incremental warehouse",
                    location_type="WAREHOUSE",
                ),
            )
            first_actor_id = first_actor.id
            location_id = location.id

            dry_run = await plan_inventory_receipt(
                db,
                validation,
                target=location.code,
                actor_user_id=first_actor_id,
                source_hash=source_hash,
            )

            assert dry_run.existing_movement_id is None
            assert dry_run.existing_items == 0
            assert dry_run.new_items == 2
            assert dry_run.current_quantity == 0
            assert dry_run.desired_quantity == 7
            assert dry_run.receipt_quantity == 7
            assert dry_run.negative_delta_items == 0

            first = await apply_inventory_receipt(
                db,
                validation,
                target=location.code,
                actor_user_id=first_actor_id,
                source_hash=source_hash,
                source_name="synthetic-incremental.xlsx",
            )

            assert first["state"] == "success"
            assert first["replayed"] is False
            assert first["created_items"] == 2
            assert first["reused_items"] == 0
            assert first["receipt_quantity"] == 7
            assert first["zero_stock_items"] == 1
            assert first["projection_drift_rows"] == 0

        async with AsyncSession(
            engine,
            expire_on_commit=False,
        ) as db, db.begin():
            second_actor, _ = await actor(db)

            reconciled = await plan_inventory_receipt(
                db,
                validation,
                target=str(location_id),
                actor_user_id=second_actor.id,
                source_hash="b" * 64,
            )

            assert reconciled.existing_items == 2
            assert reconciled.new_items == 0
            assert reconciled.current_quantity == 7
            assert reconciled.desired_quantity == 7
            assert reconciled.receipt_quantity == 0
            assert reconciled.negative_delta_items == 0

            replay = await apply_inventory_receipt(
                db,
                validation,
                target=str(location_id),
                actor_user_id=second_actor.id,
                source_hash=source_hash,
                source_name="renamed-source.xlsx",
            )

            assert replay["state"] == "already_applied"
            assert replay["replayed"] is True
            assert replay["created_items"] == 0
            assert replay["reused_items"] == 2
            assert replay["receipt_quantity"] == 7
            assert replay["zero_stock_items"] == 1

        async with AsyncSession(engine) as db:
            assert await db.scalar(
                select(func.count()).select_from(Item)
            ) == 2
            assert await db.scalar(
                select(func.count()).select_from(Movement)
            ) == 1
            assert await db.scalar(
                select(func.sum(StockBalance.quantity)).where(
                    StockBalance.location_id == location_id
                )
            ) == 7
    finally:
        await engine.dispose()
