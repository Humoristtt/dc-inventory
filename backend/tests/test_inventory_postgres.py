import asyncio
import os
import uuid
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.modules.catalog.service import set_item_archived
from app.modules.identity.admin_service import (
    OutstandingCustodyInvariantError,
    update_user_access,
)
from app.modules.identity.enums import UserAccessStatus, UserRole
from app.modules.identity.models import User
from app.modules.inventory.models import (
    Movement,
    MovementLine,
    StockBalance,
    UserItemCustodyBalance,
)
from app.modules.inventory.schemas import MovementReversalCreate
from app.modules.inventory.service import (
    InventoryConflictError,
    InventoryValidationError,
    acquire_movement_feed_snapshot,
    list_movements_cursor,
    reverse_movement,
    set_location_archived,
)
from tests.warehouse_helpers import actor, move, scenario

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


async def custody_quantity(db: AsyncSession, user: uuid.UUID, item: uuid.UUID) -> int:
    return (
        await db.scalar(
            select(UserItemCustodyBalance.quantity).where(
                UserItemCustodyBalance.user_id == user,
                UserItemCustodyBalance.item_id == item,
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
    # Administrative warehouse returns intentionally have no custody context.
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


async def test_user_custody_lifecycle_idempotency_failure_and_reconciliation(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    s = await scenario(db, UserRole.USER)
    await move(db, s, "RECEIPT", 10, destination=s[2])

    issue = await move(
        db,
        s,
        "ISSUE",
        4,
        source=s[2],
        key="custody-issue",
        custody_user_id=s[0],
    )
    assert issue.record.movement.custody_user_id == s[0]
    assert await quantity(db, s[1], s[2]) == 6
    assert await custody_quantity(db, s[0], s[1]) == 4

    issue_replay = await move(
        db,
        s,
        "ISSUE",
        4,
        source=s[2],
        key="custody-issue",
        custody_user_id=s[0],
    )
    assert issue_replay.replayed
    assert await quantity(db, s[1], s[2]) == 6
    assert await custody_quantity(db, s[0], s[1]) == 4
    with pytest.raises(InventoryConflictError, match="different payload"):
        await move(
            db,
            s,
            "ISSUE",
            4,
            source=s[2],
            key="custody-issue",
        )

    returned = await move(
        db,
        s,
        "RETURN",
        3,
        destination=s[2],
        key="custody-return",
        custody_user_id=s[0],
    )
    assert returned.record.movement.custody_user_id == s[0]
    assert await quantity(db, s[1], s[2]) == 9
    assert await custody_quantity(db, s[0], s[1]) == 1

    return_replay = await move(
        db,
        s,
        "RETURN",
        3,
        destination=s[2],
        key="custody-return",
        custody_user_id=s[0],
    )
    assert return_replay.replayed
    assert await quantity(db, s[1], s[2]) == 9
    assert await custody_quantity(db, s[0], s[1]) == 1

    before_count = await db.scalar(select(func.count()).select_from(Movement))
    with pytest.raises(InventoryConflictError) as error:
        async with db.begin_nested():
            await move(
                db,
                s,
                "RETURN",
                2,
                destination=s[2],
                key="custody-return-too-large",
                custody_user_id=s[0],
            )
    assert error.value.code == "insufficient_custody"
    assert await quantity(db, s[1], s[2]) == 9
    assert await custody_quantity(db, s[0], s[1]) == 1
    assert await db.scalar(select(func.count()).select_from(Movement)) == before_count

    sql = (Path(__file__).parents[1] / "scripts/reconcile_inventory_projections.sql").read_text()
    assert not (await db.execute(text(sql))).all()
    await db.execute(
        update(UserItemCustodyBalance)
        .where(
            UserItemCustodyBalance.user_id == s[0],
            UserItemCustodyBalance.item_id == s[1],
        )
        .values(quantity=2)
    )
    drift = (await db.execute(text(sql))).mappings().all()
    assert len(drift) == 1
    assert drift[0]["projection"] == "custody"
    assert drift[0]["journal_quantity"] == 1
    assert drift[0]["projected_quantity"] == 2
    await db.execute(
        update(UserItemCustodyBalance)
        .where(
            UserItemCustodyBalance.user_id == s[0],
            UserItemCustodyBalance.item_id == s[1],
        )
        .values(quantity=1)
    )

    await move(
        db,
        s,
        "RETURN",
        1,
        destination=s[2],
        custody_user_id=s[0],
    )
    assert await quantity(db, s[1], s[2]) == 10
    assert await custody_quantity(db, s[0], s[1]) == 0
    assert not await db.scalar(
        select(UserItemCustodyBalance.id).where(
            UserItemCustodyBalance.user_id == s[0],
            UserItemCustodyBalance.item_id == s[1],
        )
    )
    assert not (await db.execute(text(sql))).all()


async def test_outstanding_custody_blocks_access_transition(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    s = await scenario(db, UserRole.USER)
    admin, _ = await actor(db, UserRole.ADMIN)

    admin_scenario = (
        admin.id,
        s[1],
        s[2],
        s[3],
    )

    await move(
        db,
        admin_scenario,
        "RECEIPT",
        1,
        destination=s[2],
    )

    await move(
        db,
        s,
        "ISSUE",
        1,
        source=s[2],
        custody_user_id=s[0],
    )

    with pytest.raises(
        OutstandingCustodyInvariantError,
        match="outstanding equipment custody",
    ):
        await update_user_access(
            db,
            actor_user_id=admin.id,
            target_user_id=s[0],
            access_status=UserAccessStatus.BLOCKED,
            recovery_telegram_user_id=None,
        )

    target = await db.get(User, s[0])
    assert target is not None
    assert target.access_status == UserAccessStatus.APPROVED
    assert await custody_quantity(db, s[0], s[1]) == 1

    returned = await move(
        db,
        s,
        "RETURN",
        1,
        destination=s[2],
        custody_user_id=s[0],
    )

    assert await custody_quantity(db, s[0], s[1]) == 0

    changed, event = await update_user_access(
        db,
        actor_user_id=admin.id,
        target_user_id=s[0],
        access_status=UserAccessStatus.BLOCKED,
        recovery_telegram_user_id=None,
    )

    assert changed.access_status == UserAccessStatus.BLOCKED
    assert event is not None

    with pytest.raises(InventoryConflictError) as blocked_issue:
        await move(
            db,
            s,
            "ISSUE",
            1,
            source=s[2],
            custody_user_id=s[0],
        )

    assert blocked_issue.value.code == "custody_user_not_approved"

    with pytest.raises(InventoryConflictError) as blocked_reversal:
        await reverse_movement(
            db,
            returned.record.movement.id,
            MovementReversalCreate(
                client_request_id="blocked-return-reversal"
            ),
            actor_user_id=admin.id,
            actor_display_name="Synthetic admin",
        )

    assert blocked_reversal.value.code == "custody_user_not_approved"
    assert await custody_quantity(db, s[0], s[1]) == 0
    assert await quantity(db, s[1], s[2]) == 1


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


async def test_custody_reversals_and_correction_fail_closed(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    s = await scenario(db, UserRole.USER)
    receipt = await move(db, s, "RECEIPT", 10, destination=s[2])
    issue = await move(
        db,
        s,
        "ISSUE",
        4,
        source=s[2],
        custody_user_id=s[0],
    )
    issue_reversal = await reverse_movement(
        db,
        issue.record.movement.id,
        MovementReversalCreate(client_request_id="reverse-custody-issue"),
        actor_user_id=s[0],
        actor_display_name="Synthetic actor",
    )
    assert issue_reversal.record.movement.custody_user_id == s[0]
    assert await quantity(db, s[1], s[2]) == 10
    assert await custody_quantity(db, s[0], s[1]) == 0

    second_issue = await move(
        db,
        s,
        "ISSUE",
        4,
        source=s[2],
        custody_user_id=s[0],
    )
    returned = await move(
        db,
        s,
        "RETURN",
        3,
        destination=s[2],
        custody_user_id=s[0],
    )
    return_reversal = await reverse_movement(
        db,
        returned.record.movement.id,
        MovementReversalCreate(client_request_id="reverse-custody-return"),
        actor_user_id=s[0],
        actor_display_name="Synthetic actor",
    )
    assert return_reversal.record.movement.custody_user_id == s[0]
    assert await quantity(db, s[1], s[2]) == 6
    assert await custody_quantity(db, s[0], s[1]) == 4

    with pytest.raises(InventoryValidationError) as error:
        await move(
            db,
            s,
            "CORRECTION",
            1,
            source=s[2],
            original=second_issue.record.movement.id,
        )
    assert error.value.code == "custody_correction_forbidden"
    assert receipt.record.movement.custody_user_id is None


async def test_admin_issue_and_return_do_not_mutate_custody(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    s = await scenario(db)
    await move(db, s, "RECEIPT", 5, destination=s[2])
    issue = await move(db, s, "ISSUE", 2, source=s[2])
    returned = await move(db, s, "RETURN", 2, destination=s[2])
    assert issue.record.movement.custody_user_id is None
    assert returned.record.movement.custody_user_id is None
    assert not await db.scalar(select(UserItemCustodyBalance.id))


async def test_custody_reversal_failure_is_atomic(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    s = await scenario(db, UserRole.USER)
    await move(db, s, "RECEIPT", 1, destination=s[2])
    issue = await move(
        db,
        s,
        "ISSUE",
        1,
        source=s[2],
        custody_user_id=s[0],
    )
    await move(
        db,
        s,
        "RETURN",
        1,
        destination=s[2],
        custody_user_id=s[0],
    )
    request_id = "reverse-issue-without-custody"
    with pytest.raises(InventoryConflictError) as error:
        async with db.begin_nested():
            await reverse_movement(
                db,
                issue.record.movement.id,
                MovementReversalCreate(client_request_id=request_id),
                actor_user_id=s[0],
                actor_display_name="Synthetic actor",
            )
    assert error.value.code == "insufficient_custody"
    assert await quantity(db, s[1], s[2]) == 1
    assert await custody_quantity(db, s[0], s[1]) == 0
    assert not await db.scalar(
        select(Movement.id).where(Movement.client_request_id == request_id)
    )


async def test_database_rejects_invalid_custody_relationships(
    warehouse_db: AsyncSession,
) -> None:
    from tests.warehouse_helpers import actor

    db = warehouse_db
    s = await scenario(db, UserRole.USER)
    other, _ = await actor(db)
    receipt = await move(db, s, "RECEIPT", 5, destination=s[2])

    invalid_issue = Movement(
        movement_type="ISSUE",
        line_count=1,
        actor_user_id=s[0],
        custody_user_id=other.id,
        actor_display_name_snapshot="Synthetic actor",
        client_request_id=uuid.uuid4().hex,
        request_fingerprint="d" * 64,
        source_location_id=s[2],
        source_location_code_snapshot=receipt.record.movement.destination_location_code_snapshot,
        source_location_name_snapshot=receipt.record.movement.destination_location_name_snapshot,
    )
    async with db.begin_nested() as savepoint:
        with pytest.raises(DBAPIError):
            db.add(invalid_issue)
            await db.flush()
        await savepoint.rollback()

    for actor_id, custody_id in ((s[0], None), (other.id, other.id)):
        raw_issue = Movement(
            movement_type="ISSUE",
            line_count=1,
            actor_user_id=actor_id,
            custody_user_id=custody_id,
            actor_display_name_snapshot="Synthetic actor",
            client_request_id=uuid.uuid4().hex,
            request_fingerprint="1" * 64,
            source_location_id=s[2],
            source_location_code_snapshot=(
                receipt.record.movement.destination_location_code_snapshot
            ),
            source_location_name_snapshot=(
                receipt.record.movement.destination_location_name_snapshot
            ),
        )
        async with db.begin_nested() as savepoint:
            with pytest.raises(DBAPIError):
                db.add(raw_issue)
                await db.flush()
            await savepoint.rollback()

    issue = await move(
        db,
        s,
        "ISSUE",
        1,
        source=s[2],
        custody_user_id=s[0],
    )
    row = issue.record.movement
    invalid_reversal = Movement(
        movement_type="REVERSAL",
        line_count=1,
        actor_user_id=other.id,
        custody_user_id=other.id,
        actor_display_name_snapshot="Synthetic actor",
        client_request_id=uuid.uuid4().hex,
        request_fingerprint="e" * 64,
        original_movement_id=row.id,
        destination_location_id=row.source_location_id,
        destination_location_code_snapshot=row.source_location_code_snapshot,
        destination_location_name_snapshot=row.source_location_name_snapshot,
    )
    async with db.begin_nested() as savepoint:
        with pytest.raises(DBAPIError):
            db.add(invalid_reversal)
            await db.flush()
        await savepoint.rollback()

    invalid_correction = Movement(
        movement_type="CORRECTION",
        line_count=1,
        actor_user_id=other.id,
        actor_display_name_snapshot="Synthetic actor",
        client_request_id=uuid.uuid4().hex,
        request_fingerprint="f" * 64,
        original_movement_id=row.id,
        source_location_id=row.source_location_id,
        source_location_code_snapshot=row.source_location_code_snapshot,
        source_location_name_snapshot=row.source_location_name_snapshot,
    )
    async with db.begin_nested() as savepoint:
        with pytest.raises(DBAPIError):
            db.add(invalid_correction)
            await db.flush()
        await savepoint.rollback()


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


async def test_concurrent_last_unit_returns_exactly_once() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("requires disposable PostgreSQL")
    engine = create_async_engine(os.environ["DATABASE_URL"])
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            s = await scenario(db, UserRole.USER)
            await move(db, s, "RECEIPT", 1, destination=s[2])
            await move(
                db,
                s,
                "ISSUE",
                1,
                source=s[2],
                custody_user_id=s[0],
            )
            await db.commit()

        async def return_last_unit() -> str:
            async with AsyncSession(engine, expire_on_commit=False) as db:
                try:
                    await move(
                        db,
                        s,
                        "RETURN",
                        1,
                        destination=s[2],
                        custody_user_id=s[0],
                    )
                    await db.commit()
                    return "ok"
                except InventoryConflictError as error:
                    await db.rollback()
                    return error.code

        results = await asyncio.wait_for(
            asyncio.gather(return_last_unit(), return_last_unit()),
            timeout=10,
        )
        assert sorted(results) == ["insufficient_custody", "ok"]
        async with AsyncSession(engine) as db:
            assert await quantity(db, s[1], s[2]) == 1
            assert await custody_quantity(db, s[0], s[1]) == 0
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(Movement)
                    .where(
                        Movement.movement_type == "RETURN",
                        Movement.custody_user_id == s[0],
                    )
                )
                == 1
            )
    finally:
        await engine.dispose()


async def test_concurrent_issue_serializes_with_user_block() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("requires disposable PostgreSQL")

    engine = create_async_engine(os.environ["DATABASE_URL"])
    issue_has_user_lock = asyncio.Event()
    allow_issue_commit = asyncio.Event()

    try:
        async with AsyncSession(
            engine,
            expire_on_commit=False,
        ) as db:
            s = await scenario(db, UserRole.USER)
            admin, _ = await actor(db, UserRole.ADMIN)

            admin_scenario = (
                admin.id,
                s[1],
                s[2],
                s[3],
            )

            await move(
                db,
                admin_scenario,
                "RECEIPT",
                1,
                destination=s[2],
            )
            await db.commit()

        async def issue() -> str:
            async with AsyncSession(
                engine,
                expire_on_commit=False,
            ) as db:
                await move(
                    db,
                    s,
                    "ISSUE",
                    1,
                    source=s[2],
                    custody_user_id=s[0],
                )

                issue_has_user_lock.set()
                await allow_issue_commit.wait()
                await db.commit()
                return "issued"

        async def block() -> str:
            await issue_has_user_lock.wait()

            async with AsyncSession(
                engine,
                expire_on_commit=False,
            ) as db:
                try:
                    await update_user_access(
                        db,
                        actor_user_id=admin.id,
                        target_user_id=s[0],
                        access_status=UserAccessStatus.BLOCKED,
                        recovery_telegram_user_id=None,
                    )
                    await db.commit()
                    return "blocked"
                except OutstandingCustodyInvariantError:
                    await db.rollback()
                    return "outstanding_custody"

        issue_task = asyncio.create_task(issue())

        await asyncio.wait_for(
            issue_has_user_lock.wait(),
            timeout=5,
        )

        block_task = asyncio.create_task(block())

        # Blocking must wait on the same users-row lock instead of observing
        # stale zero custody while ISSUE is still uncommitted.
        await asyncio.sleep(0.1)
        assert not block_task.done()

        allow_issue_commit.set()

        assert await asyncio.wait_for(
            issue_task,
            timeout=5,
        ) == "issued"

        assert await asyncio.wait_for(
            block_task,
            timeout=5,
        ) == "outstanding_custody"

        async with AsyncSession(engine) as db:
            target = await db.get(User, s[0])
            assert target is not None
            assert target.access_status == UserAccessStatus.APPROVED
            assert await custody_quantity(db, s[0], s[1]) == 1

    finally:
        allow_issue_commit.set()
        await engine.dispose()


async def test_journal_snapshot_barrier_orders_concurrent_commits() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("requires disposable PostgreSQL")

    engine = create_async_engine(os.environ["DATABASE_URL"])
    writer_ready = asyncio.Event()
    allow_writer_commit = asyncio.Event()

    try:
        async with AsyncSession(
            engine,
            expire_on_commit=False,
        ) as db:
            s = await scenario(db)
            await move(
                db,
                s,
                "RECEIPT",
                1,
                destination=s[2],
            )
            await db.commit()

        async def existing_writer() -> uuid.UUID:
            async with AsyncSession(
                engine,
                expire_on_commit=False,
            ) as db:
                result = await move(
                    db,
                    s,
                    "RECEIPT",
                    1,
                    destination=s[2],
                    key="snapshot-existing-writer",
                )

                # create_movement() already holds the shared journal lock.
                writer_ready.set()
                await allow_writer_commit.wait()
                await db.commit()

                return result.record.movement.id

        writer_task = asyncio.create_task(
            existing_writer()
        )

        await asyncio.wait_for(
            writer_ready.wait(),
            timeout=5,
        )

        async def first_page_snapshot() -> tuple[
            datetime,
            set[uuid.UUID],
        ]:
            async with AsyncSession(
                engine,
                expire_on_commit=False,
            ) as db:
                snapshot = (
                    await acquire_movement_feed_snapshot(db)
                )

                page = await list_movements_cursor(
                    db,
                    actor_user_id=s[0],
                    until=snapshot,
                    limit=100,
                )

                ids = {
                    record.movement.id
                    for record in page.items
                }

                await db.commit()
                return snapshot, ids

        snapshot_task = asyncio.create_task(
            first_page_snapshot()
        )

        # Snapshot must wait for the transaction that was already writing
        # the journal when the first-page request started.
        await asyncio.sleep(0.1)
        assert not snapshot_task.done()

        allow_writer_commit.set()

        existing_id = await asyncio.wait_for(
            writer_task,
            timeout=5,
        )
        snapshot, snapshot_ids = await asyncio.wait_for(
            snapshot_task,
            timeout=5,
        )

        # The writer that existed before the snapshot barrier is part of the
        # snapshot rather than appearing unexpectedly on a later page.
        assert existing_id in snapshot_ids

        async with AsyncSession(
            engine,
            expire_on_commit=False,
        ) as snapshot_db:
            second_snapshot = (
                await acquire_movement_feed_snapshot(
                    snapshot_db
                )
            )

            async def new_writer() -> uuid.UUID:
                async with AsyncSession(
                    engine,
                    expire_on_commit=False,
                ) as db:
                    result = await move(
                        db,
                        s,
                        "RECEIPT",
                        1,
                        destination=s[2],
                        key="snapshot-new-writer",
                    )
                    await db.commit()
                    return result.record.movement.id

            new_writer_task = asyncio.create_task(
                new_writer()
            )

            # New journal writers cannot enter while the exclusive snapshot
            # barrier is held.
            await asyncio.sleep(0.1)
            assert not new_writer_task.done()

            await snapshot_db.commit()

        new_id = await asyncio.wait_for(
            new_writer_task,
            timeout=5,
        )

        async with AsyncSession(engine) as db:
            new_movement = await db.get(
                Movement,
                new_id,
            )
            assert new_movement is not None
            assert (
                new_movement.occurred_at
                > second_snapshot
            )

            old_snapshot_page = (
                await list_movements_cursor(
                    db,
                    actor_user_id=s[0],
                    until=second_snapshot,
                    limit=100,
                )
            )

            assert new_id not in {
                record.movement.id
                for record in old_snapshot_page.items
            }

    finally:
        allow_writer_commit.set()
        await engine.dispose()


@pytest.mark.parametrize("line_count", [1, 40])
async def test_balance_locks_are_batched_and_transfer_reconciles(
    warehouse_db: AsyncSession, line_count: int
) -> None:
    from app.modules.catalog.service import create_item
    from app.modules.inventory.schemas import MovementCreate, MovementLineCreate
    from app.modules.inventory.service import create_movement
    from tests.sql_capture import capture_sql
    from tests.warehouse_helpers import cable_payload

    db = warehouse_db
    s = await scenario(db)
    item_ids = [s[1]] + [await create_item(db, cable_payload()) for _ in range(line_count - 1)]
    connection = await db.connection()
    for kind in ["RECEIPT", "TRANSFER"]:
        payload = MovementCreate(
            movement_type=kind,
            client_request_id=uuid.uuid4().hex,
            source_location_id=s[2] if kind == "TRANSFER" else None,
            destination_location_id=s[3] if kind == "TRANSFER" else s[2],
            lines=[MovementLineCreate(item_id=item, quantity=3) for item in reversed(item_ids)],
        )
        with capture_sql(connection) as statements:
            await create_movement(db, payload, actor_user_id=s[0], actor_display_name="Synthetic")
        balance_selects = [sql for sql in statements if sql.startswith("SELECT stock_balances.")]
        assert len(balance_selects) == 1
        assert (
            "ORDER BY stock_balances.item_id, stock_balances.location_id FOR UPDATE"
            in (balance_selects[0])
        )
    balances = (
        await db.scalars(select(StockBalance).where(StockBalance.item_id.in_(item_ids)))
    ).all()
    assert {(b.item_id, b.location_id, b.quantity) for b in balances} == {
        (item, s[3], 3) for item in item_ids
    }
    await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    sql = (Path(__file__).parents[1] / "scripts/reconcile_inventory_projections.sql").read_text()
    assert not (await db.execute(text(sql))).all()


async def test_concurrent_transfers_create_missing_destinations_safely() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("requires disposable PostgreSQL")
    engine = create_async_engine(os.environ["DATABASE_URL"])
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            s = await scenario(db)
            await move(db, s, "RECEIPT", 10, destination=s[2])
            await db.commit()

        async def transfer() -> None:
            async with AsyncSession(engine, expire_on_commit=False) as db, db.begin():
                await move(db, s, "TRANSFER", 3, source=s[2], destination=s[3])

        await asyncio.wait_for(asyncio.gather(transfer(), transfer()), timeout=10)
        async with AsyncSession(engine) as db:
            assert await quantity(db, s[1], s[2]) == 4
            assert await quantity(db, s[1], s[3]) == 6
    finally:
        await engine.dispose()


async def test_multiline_transfer_failure_rolls_back_journal_and_projection(
    warehouse_db: AsyncSession,
) -> None:
    from app.modules.catalog.service import create_item
    from app.modules.inventory.schemas import MovementCreate, MovementLineCreate
    from app.modules.inventory.service import create_movement
    from tests.warehouse_helpers import cable_payload

    db = warehouse_db
    s = await scenario(db)
    stocked, empty = sorted([s[1], await create_item(db, cable_payload())])
    await move(db, (s[0], stocked, s[2], s[3]), "RECEIPT", 3, destination=s[2])
    request_id = uuid.uuid4().hex
    with pytest.raises(InventoryConflictError, match="insufficient stock"):
        async with db.begin_nested():
            await create_movement(
                db,
                MovementCreate(
                    movement_type="TRANSFER",
                    client_request_id=request_id,
                    source_location_id=s[2],
                    destination_location_id=s[3],
                    lines=[
                        MovementLineCreate(item_id=item, quantity=2) for item in [stocked, empty]
                    ],
                ),
                actor_user_id=s[0],
                actor_display_name="Synthetic",
            )
    assert await quantity(db, stocked, s[2]) == 3
    assert await quantity(db, stocked, s[3]) == 0
    assert not await db.scalar(select(Movement.id).where(Movement.client_request_id == request_id))
    await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
