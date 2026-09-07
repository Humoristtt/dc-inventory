import asyncio
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.modules.catalog.service import set_item_archived
from app.modules.inventory.models import Movement, MovementLine, StockBalance
from app.modules.inventory.schemas import MovementReversalCreate
from app.modules.inventory.service import (
    InventoryConflictError,
    InventoryValidationError,
    reverse_movement,
    set_location_archived,
)
from tests.warehouse_helpers import move, scenario

pytestmark = pytest.mark.asyncio


async def quantity(db: AsyncSession, item: uuid.UUID, location: uuid.UUID) -> int:
    return (
        await db.scalar(
            select(StockBalance.quantity).where(
                StockBalance.item_id == item, StockBalance.location_id == location
            )
        )
        or 0
    )


async def test_lifecycle_idempotency_and_reconciliation(warehouse_db: AsyncSession) -> None:
    db = warehouse_db
    s = await scenario(db)
    receipt = await move(db, s, "RECEIPT", 20, destination=s[2], key="receipt")
    replay = await move(db, s, "RECEIPT", 20, destination=s[2], key=" receipt ")
    assert replay.replayed and replay.record.movement.id == receipt.record.movement.id
    with pytest.raises(InventoryConflictError, match="different payload"):
        await move(db, s, "RECEIPT", 21, destination=s[2], key="receipt")
    await move(db, s, "ISSUE", 20, source=s[2])
    assert await quantity(db, s[1], s[2]) == 0
    assert not await db.scalar(select(StockBalance.id).where(StockBalance.item_id == s[1]))
    # A return is independent of earlier actions, including a return greater than issued.
    await move(db, s, "RETURN", 23, destination=s[2])
    await move(db, s, "TRANSFER", 4, source=s[2], destination=s[3])
    await move(db, s, "WRITE_OFF", 2, source=s[3])
    assert await quantity(db, s[1], s[2]) == 19
    assert await quantity(db, s[1], s[3]) == 2
    await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    sql = (Path(__file__).parents[1] / "scripts/reconcile_inventory_projections.sql").read_text()
    assert not (await db.execute(text(sql))).all()
    await db.execute(
        update(StockBalance)
        .where(StockBalance.item_id == s[1], StockBalance.location_id == s[3])
        .values(quantity=3)
    )
    drift = (await db.execute(text(sql))).mappings().all()
    assert len(drift) == 1 and drift[0]["journal_quantity"] == 2
    assert drift[0]["projected_quantity"] == 3


@pytest.mark.parametrize(
    "kind", ["RECEIPT", "ISSUE", "TRANSFER", "RETURN", "WRITE_OFF", "CORRECTION"]
)
async def test_reversal_restores_stock_and_is_idempotent(
    warehouse_db: AsyncSession,
    kind: str,
) -> None:
    db = warehouse_db
    s = await scenario(db)
    initial = await move(db, s, "RECEIPT", 10, destination=s[2])
    original = await move(
        db,
        s,
        kind,
        3,
        source=s[2] if kind in {"ISSUE", "TRANSFER", "WRITE_OFF", "CORRECTION"} else None,
        destination=s[3] if kind == "TRANSFER" else s[2] if kind in {"RECEIPT", "RETURN"} else None,
        original=initial.record.movement.id if kind == "CORRECTION" else None,
    )
    result = await reverse_movement(
        db,
        original.record.movement.id,
        MovementReversalCreate(client_request_id="reverse"),
        actor_user_id=s[0],
        actor_display_name="Synthetic actor",
    )
    assert result.record.movement.original_movement_id == original.record.movement.id
    assert result.record.lines[0].quantity == 3
    assert await quantity(db, s[1], s[2]) == 10
    assert await quantity(db, s[1], s[3]) == 0
    replay = await reverse_movement(
        db,
        original.record.movement.id,
        MovementReversalCreate(client_request_id="reverse"),
        actor_user_id=s[0],
        actor_display_name="Synthetic actor",
    )
    assert replay.replayed and replay.record.movement.id == result.record.movement.id
    with pytest.raises(InventoryConflictError, match="already reversed"):
        await reverse_movement(
            db,
            original.record.movement.id,
            MovementReversalCreate(client_request_id="second"),
            actor_user_id=s[0],
            actor_display_name="Synthetic actor",
        )
    with pytest.raises(InventoryValidationError, match="invalid"):
        await reverse_movement(
            db,
            result.record.movement.id,
            MovementReversalCreate(client_request_id="reverse-reversal"),
            actor_user_id=s[0],
            actor_display_name="Synthetic actor",
        )
    await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


@pytest.mark.parametrize("kind", ["RECEIPT", "TRANSFER"])
async def test_reversal_insufficient_stock_is_atomic(
    warehouse_db: AsyncSession,
    kind: str,
) -> None:
    db = warehouse_db
    s = await scenario(db)
    original = await move(db, s, "RECEIPT", 5, destination=s[2])
    destination = s[2]
    if kind == "TRANSFER":
        original = await move(db, s, kind, 5, source=s[2], destination=s[3])
        destination = s[3]
    await move(db, s, "ISSUE", 1, source=destination)
    async with db.begin_nested() as savepoint:
        with pytest.raises(InventoryConflictError, match="insufficient"):
            await reverse_movement(
                db,
                original.record.movement.id,
                MovementReversalCreate(client_request_id="insufficient"),
                actor_user_id=s[0],
                actor_display_name="Synthetic actor",
            )
        await savepoint.rollback()
    assert await quantity(db, s[1], destination) == 4
    assert not await db.scalar(
        select(Movement.id).where(Movement.client_request_id == "insufficient")
    )


async def test_archive_policy(warehouse_db: AsyncSession) -> None:
    db = warehouse_db
    s = await scenario(db)
    original = await move(db, s, "RECEIPT", 10, destination=s[2])
    with pytest.raises(InventoryConflictError, match="stock"):
        await set_location_archived(db, s[2], archived=True)
    await set_item_archived(db, s[1], archived=True)
    for kind in ("RECEIPT", "ISSUE"):
        with pytest.raises(InventoryConflictError, match="archived"):
            await move(
                db,
                s,
                kind,
                1,
                source=s[2] if kind == "ISSUE" else None,
                destination=s[2] if kind == "RECEIPT" else None,
            )
    await move(db, s, "RETURN", 2, destination=s[2])
    await move(db, s, "TRANSFER", 1, source=s[2], destination=s[3])
    await move(db, s, "WRITE_OFF", 1, source=s[3])
    correction = await move(
        db, s, "CORRECTION", 1, source=s[2], original=original.record.movement.id
    )
    await reverse_movement(
        db,
        correction.record.movement.id,
        MovementReversalCreate(client_request_id="archive-reversal"),
        actor_user_id=s[0],
        actor_display_name="Synthetic actor",
    )
    await set_location_archived(db, s[3], archived=True)
    with pytest.raises(InventoryConflictError, match="archived location"):
        await move(db, s, "RETURN", 1, destination=s[3])
    assert await quantity(db, s[1], s[2]) == 11


@pytest.mark.parametrize("table", [Movement, MovementLine])
@pytest.mark.parametrize("operation", ["update", "delete", "truncate", "append"])
async def test_journal_is_immutable_at_database_level(
    warehouse_db: AsyncSession,
    table: type[Movement] | type[MovementLine],
    operation: str,
) -> None:
    db = warehouse_db
    s = await scenario(db)
    result = await move(db, s, "RECEIPT", 1, destination=s[2])
    await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    ident = result.record.movement.id if table is Movement else result.record.lines[0].id
    async with db.begin_nested() as savepoint:
        with pytest.raises(DBAPIError):
            if operation == "update":
                await db.execute(update(table).where(table.id == ident).values(id=ident))
            elif operation == "delete":
                await db.execute(delete(table).where(table.id == ident))
            elif operation == "truncate":
                await db.execute(text("TRUNCATE movements, movement_lines"))
            elif table is Movement:
                # A header cannot commit without its declared lines.
                row = result.record.movement
                db.add(
                    Movement(
                        movement_type="RETURN",
                        line_count=1,
                        actor_user_id=s[0],
                        actor_display_name_snapshot="Synthetic",
                        client_request_id=uuid.uuid4().hex,
                        request_fingerprint="a" * 64,
                        destination_location_id=s[2],
                        destination_location_code_snapshot=row.destination_location_code_snapshot,
                        destination_location_name_snapshot=row.destination_location_name_snapshot,
                    )
                )
                await db.flush()
            else:
                db.add(
                    MovementLine(
                        movement_id=result.record.movement.id,
                        line_no=2,
                        item_id=s[1],
                        quantity=1,
                        item_name_snapshot="extra",
                    )
                )
                await db.flush()
        await savepoint.rollback()


async def test_database_rejects_direct_sql_correction_for_unrelated_location(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    s = await scenario(db)
    original = await move(db, s, "RECEIPT", 5, destination=s[2])
    row = original.record.movement

    async with db.begin_nested() as savepoint:
        with pytest.raises(DBAPIError):
            db.add(
                Movement(
                    movement_type="CORRECTION",
                    line_count=1,
                    actor_user_id=s[0],
                    actor_display_name_snapshot="Synthetic actor",
                    client_request_id=uuid.uuid4().hex,
                    request_fingerprint="b" * 64,
                    original_movement_id=row.id,
                    source_location_id=s[3],
                    source_location_code_snapshot="unrelated",
                    source_location_name_snapshot="Unrelated",
                )
            )
            await db.flush()
        await savepoint.rollback()


async def test_database_rejects_direct_sql_reversal_with_wrong_quantity(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    s = await scenario(db)
    original = await move(db, s, "RECEIPT", 5, destination=s[2])
    row = original.record.movement

    async with db.begin_nested() as savepoint:
        reversal = Movement(
            movement_type="REVERSAL",
            line_count=1,
            actor_user_id=s[0],
            actor_display_name_snapshot="Synthetic actor",
            client_request_id=uuid.uuid4().hex,
            request_fingerprint="c" * 64,
            original_movement_id=row.id,
            source_location_id=row.destination_location_id,
            source_location_code_snapshot=row.destination_location_code_snapshot,
            source_location_name_snapshot=row.destination_location_name_snapshot,
        )
        db.add(reversal)
        await db.flush()

        with pytest.raises(DBAPIError):
            db.add(
                MovementLine(
                    movement_id=reversal.id,
                    line_no=1,
                    item_id=s[1],
                    quantity=4,
                    item_name_snapshot=original.record.lines[0].item_name_snapshot,
                )
            )
            await db.flush()
        await savepoint.rollback()


@pytest.mark.parametrize("quantity_value", [0, -1])
async def test_stock_database_rejects_nonpositive_balances(
    warehouse_db: AsyncSession,
    quantity_value: int,
) -> None:
    db = warehouse_db
    s = await scenario(db)
    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            db.add(StockBalance(item_id=s[1], location_id=s[2], quantity=quantity_value))
            await db.flush()


async def test_concurrent_issues_cannot_overspend() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("requires disposable PostgreSQL")
    engine = create_async_engine(os.environ["DATABASE_URL"])
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            s = await scenario(db)
            await move(db, s, "RECEIPT", 5, destination=s[2])
            await db.commit()

        async def issue() -> str:
            async with AsyncSession(engine, expire_on_commit=False) as db:
                try:
                    await move(db, s, "ISSUE", 4, source=s[2])
                    await db.commit()
                    return "ok"
                except InventoryConflictError as error:
                    await db.rollback()
                    return error.code

        assert sorted(await asyncio.gather(issue(), issue())) == ["insufficient_stock", "ok"]
        async with AsyncSession(engine) as db:
            assert await quantity(db, s[1], s[2]) == 1
    finally:
        await engine.dispose()
