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
    row = dict(
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
    item = normalize_row(
        "Ethernet патч-корды",
        row,
        "Ethernet патч-корды!2",
    )
    return Validation(
        path=Path("synthetic-incremental.xlsx"),
        sheets=["Ethernet патч-корды"],
        raw_rows=1,
        source_quantity=7,
        items=[item],
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
            assert dry_run.new_items == 1

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
            assert first["created_items"] == 1
            assert first["reused_items"] == 0
            assert first["receipt_quantity"] == 7
            assert first["projection_drift_rows"] == 0

        async with AsyncSession(
            engine,
            expire_on_commit=False,
        ) as db, db.begin():
            second_actor, _ = await actor(db)

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
            assert replay["receipt_quantity"] == 7

        async with AsyncSession(engine) as db:
            assert await db.scalar(
                select(func.count()).select_from(Item)
            ) == 1
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
