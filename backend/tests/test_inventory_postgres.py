import asyncio
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.modules.catalog.enums import AccountingMode, ItemStatus
from app.modules.catalog.models import Category, Item
from app.modules.catalog.service import set_item_archived
from app.modules.identity.enums import UserAccessStatus, UserRole
from app.modules.identity.models import TelegramIdentity, User
from app.modules.inventory.enums import InventoryUnitState, MovementType
from app.modules.inventory.models import (
    InventoryUnit,
    Movement,
    MovementLine,
    StockBalance,
)
from app.modules.inventory.schemas import (
    LocationCreate,
    MovementCreate,
    MovementLineCreate,
    MovementReversalCreate,
)
from app.modules.inventory.service import (
    POSTGRES_BIGINT_MAX,
    InventoryConflictError,
    InventoryValidationError,
    create_location,
    create_movement,
    get_movement_record,
    reverse_movement,
    set_location_archived,
)

DATABASE_URL = os.environ["DATABASE_URL"]
POSTGRES_INTEGRATION_ENABLED = os.getenv("RUN_POSTGRES_INTEGRATION") == "1"

pytestmark = pytest.mark.skipif(
    not POSTGRES_INTEGRATION_ENABLED,
    reason="set RUN_POSTGRES_INTEGRATION=1 against a migrated PostgreSQL test DB",
)


@dataclass(frozen=True, slots=True)
class InventoryScenario:
    actor_id: uuid.UUID
    holder_one_id: uuid.UUID
    holder_two_id: uuid.UUID
    quantity_item_id: uuid.UUID
    serial_item_id: uuid.UUID
    location_one_id: uuid.UUID
    location_two_id: uuid.UUID
    marker: str


async def _create_scenario(db: AsyncSession) -> InventoryScenario:
    marker = uuid.uuid4().hex
    quantity_category = await db.scalar(select(Category).where(Category.key == "sfp"))
    serial_category = await db.scalar(select(Category).where(Category.key == "nic"))
    assert quantity_category is not None
    assert serial_category is not None

    actor_id = uuid.uuid4()
    holder_one_id = uuid.uuid4()
    holder_two_id = uuid.uuid4()
    quantity_item_id = uuid.uuid4()
    serial_item_id = uuid.uuid4()
    actor = User(
        id=actor_id,
        role=UserRole.ADMIN,
        access_status=UserAccessStatus.APPROVED,
        approved_at=datetime.now(UTC),
    )
    holder_one = User(
        id=holder_one_id,
        role=UserRole.USER,
        access_status=UserAccessStatus.APPROVED,
        approved_at=datetime.now(UTC),
    )
    holder_two = User(
        id=holder_two_id,
        role=UserRole.USER,
        access_status=UserAccessStatus.APPROVED,
        approved_at=datetime.now(UTC),
    )
    telegram_seed = 6_000_000_000 + (uuid.UUID(marker).int % 1_000_000_000)
    db.add_all(
        [
            actor,
            holder_one,
            holder_two,
            TelegramIdentity(
                user=actor,
                user_id=actor_id,
                telegram_user_id=telegram_seed,
                username=f"admin_{marker[:8]}",
                first_name="Warehouse",
                last_name="Admin",
            ),
            TelegramIdentity(
                user=holder_one,
                user_id=holder_one_id,
                telegram_user_id=telegram_seed + 1,
                username=f"holder1_{marker[:8]}",
                first_name="Holder",
                last_name="One",
            ),
            TelegramIdentity(
                user=holder_two,
                user_id=holder_two_id,
                telegram_user_id=telegram_seed + 2,
                username=f"holder2_{marker[:8]}",
                first_name="Holder",
                last_name="Two",
            ),
            Item(
                id=quantity_item_id,
                category_id=quantity_category.id,
                name=f"Quantity item {marker}",
                normalized_name=f"quantity item {marker}",
                accounting_mode=AccountingMode.QUANTITY,
                status=ItemStatus.ACTIVE,
            ),
            Item(
                id=serial_item_id,
                category_id=serial_category.id,
                name=f"Serial item {marker}",
                normalized_name=f"serial item {marker}",
                accounting_mode=AccountingMode.SERIAL,
                status=ItemStatus.ACTIVE,
            ),
        ]
    )
    await db.flush()
    location_one = await create_location(
        db,
        LocationCreate(code=f"WH-{marker[:10]}", name="Primary warehouse"),
    )
    location_two = await create_location(
        db,
        LocationCreate(code=f"ROOM-{marker[:10]}", name="Secondary room"),
    )
    await db.commit()
    return InventoryScenario(
        actor_id=actor_id,
        holder_one_id=holder_one_id,
        holder_two_id=holder_two_id,
        quantity_item_id=quantity_item_id,
        serial_item_id=serial_item_id,
        location_one_id=location_one.id,
        location_two_id=location_two.id,
        marker=marker,
    )


async def _create_and_commit(
    db: AsyncSession,
    payload: MovementCreate,
    scenario: InventoryScenario,
) -> uuid.UUID:
    result = await create_movement(
        db,
        payload,
        actor_user_id=scenario.actor_id,
        actor_display_name="Warehouse Admin (@admin)",
    )
    movement_id = result.record.movement.id
    await db.commit()
    return movement_id


async def _quantity_at(
    db: AsyncSession,
    item_id: uuid.UUID,
    *,
    location_id: uuid.UUID | None = None,
    holder_user_id: uuid.UUID | None = None,
) -> int:
    value = await db.scalar(
        select(StockBalance.quantity).where(
            StockBalance.item_id == item_id,
            (
                StockBalance.location_id == location_id
                if location_id is not None
                else StockBalance.location_id.is_(None)
            ),
            (
                StockBalance.holder_user_id == holder_user_id
                if holder_user_id is not None
                else StockBalance.holder_user_id.is_(None)
            ),
        )
    )
    return value or 0


@pytest.mark.asyncio
async def test_quantity_ledger_lifecycle_idempotency_and_append_only_history() -> None:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            scenario = await _create_scenario(db)

        receipt_payload = MovementCreate(
            movement_type=MovementType.RECEIPT,
            destination_location_id=scenario.location_one_id,
            client_request_id=f"receipt-{scenario.marker}",
            purpose="Initial verified receipt",
            lines=[MovementLineCreate(item_id=scenario.quantity_item_id, quantity=5)],
        )
        async with AsyncSession(engine, expire_on_commit=False) as db:
            receipt_result = await create_movement(
                db,
                receipt_payload,
                actor_user_id=scenario.actor_id,
                actor_display_name="Warehouse Admin (@admin)",
            )
            receipt_id = receipt_result.record.movement.id
            receipt_line_id = receipt_result.record.lines[0].id
            original_item_snapshot = receipt_result.record.lines[0].item_name_snapshot
            assert receipt_result.replayed is False
            await db.commit()

        async with AsyncSession(engine, expire_on_commit=False) as db:
            replay = await create_movement(
                db,
                receipt_payload,
                actor_user_id=scenario.actor_id,
                actor_display_name="Changed Actor Display",
            )
            assert replay.replayed is True
            assert replay.record.movement.id == receipt_id
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(Movement)
                    .where(
                        Movement.actor_user_id == scenario.actor_id,
                        Movement.client_request_id == receipt_payload.client_request_id,
                    )
                )
                == 1
            )
            await db.commit()

        canonical_key_replay = receipt_payload.model_copy(deep=True)
        canonical_key_replay.client_request_id = f"  {receipt_payload.client_request_id}  "
        async with AsyncSession(engine, expire_on_commit=False) as db:
            replay = await create_movement(
                db,
                canonical_key_replay,
                actor_user_id=scenario.actor_id,
                actor_display_name="Warehouse Admin (@admin)",
            )
            assert replay.replayed is True
            assert replay.record.movement.id == receipt_id
            await db.commit()

        conflicting_replay = receipt_payload.model_copy(deep=True)
        conflicting_replay.lines[0].quantity = 6
        async with AsyncSession(engine, expire_on_commit=False) as db:
            with pytest.raises(InventoryConflictError) as conflict:
                await create_movement(
                    db,
                    conflicting_replay,
                    actor_user_id=scenario.actor_id,
                    actor_display_name="Warehouse Admin (@admin)",
                )
            assert conflict.value.code == "idempotency_payload_conflict"
            await db.rollback()

        issue_payload = MovementCreate(
            movement_type=MovementType.ISSUE,
            source_location_id=scenario.location_one_id,
            destination_holder_user_id=scenario.holder_one_id,
            client_request_id=f"issue-{scenario.marker}",
            comment="Issued for installation",
            lines=[MovementLineCreate(item_id=scenario.quantity_item_id, quantity=2)],
        )
        async with AsyncSession(engine, expire_on_commit=False) as db:
            issue_id = await _create_and_commit(db, issue_payload, scenario)
            issue = await get_movement_record(db, issue_id)
            assert issue.movement.actor_user_id == scenario.actor_id
            assert issue.movement.actor_display_name_snapshot == ("Warehouse Admin (@admin)")
            assert issue.movement.destination_holder_user_id == scenario.holder_one_id
            assert "Holder One" in (issue.movement.destination_holder_display_name_snapshot or "")
            assert issue.movement.occurred_at.tzinfo is not None
            assert issue.lines[0].quantity == 2
            assert (
                await _quantity_at(
                    db,
                    scenario.quantity_item_id,
                    location_id=scenario.location_one_id,
                )
                == 3
            )
            assert (
                await _quantity_at(
                    db,
                    scenario.quantity_item_id,
                    holder_user_id=scenario.holder_one_id,
                )
                == 2
            )

        over_issue = issue_payload.model_copy(deep=True)
        over_issue.client_request_id = f"over-issue-{scenario.marker}"
        over_issue.lines[0].quantity = 4
        async with AsyncSession(engine, expire_on_commit=False) as db:
            with pytest.raises(InventoryConflictError) as conflict:
                await create_movement(
                    db,
                    over_issue,
                    actor_user_id=scenario.actor_id,
                    actor_display_name="Warehouse Admin (@admin)",
                )
            assert conflict.value.code == "insufficient_stock"
            await db.rollback()

        operations = [
            MovementCreate(
                movement_type=MovementType.RETURN,
                source_holder_user_id=scenario.holder_one_id,
                destination_location_id=scenario.location_one_id,
                client_request_id=f"return-{scenario.marker}",
                lines=[
                    MovementLineCreate(
                        item_id=scenario.quantity_item_id,
                        quantity=1,
                    )
                ],
            ),
            MovementCreate(
                movement_type=MovementType.TRANSFER,
                source_location_id=scenario.location_one_id,
                destination_location_id=scenario.location_two_id,
                client_request_id=f"transfer-{scenario.marker}",
                lines=[
                    MovementLineCreate(
                        item_id=scenario.quantity_item_id,
                        quantity=2,
                    )
                ],
            ),
            MovementCreate(
                movement_type=MovementType.WRITE_OFF,
                source_location_id=scenario.location_two_id,
                client_request_id=f"writeoff-{scenario.marker}",
                lines=[
                    MovementLineCreate(
                        item_id=scenario.quantity_item_id,
                        quantity=1,
                    )
                ],
            ),
        ]
        async with AsyncSession(engine, expire_on_commit=False) as db:
            for payload in operations:
                await _create_and_commit(db, payload, scenario)
            assert (
                await _quantity_at(
                    db,
                    scenario.quantity_item_id,
                    location_id=scenario.location_one_id,
                )
                == 2
            )
            assert (
                await _quantity_at(
                    db,
                    scenario.quantity_item_id,
                    location_id=scenario.location_two_id,
                )
                == 1
            )
            assert (
                await _quantity_at(
                    db,
                    scenario.quantity_item_id,
                    holder_user_id=scenario.holder_one_id,
                )
                == 1
            )

        correction_payload = MovementCreate(
            movement_type=MovementType.CORRECTION,
            source_location_id=scenario.location_one_id,
            original_movement_id=receipt_id,
            client_request_id=f"correction-{scenario.marker}",
            purpose="Correct one excess received unit",
            lines=[MovementLineCreate(item_id=scenario.quantity_item_id, quantity=1)],
        )
        async with AsyncSession(engine, expire_on_commit=False) as db:
            correction_id = await _create_and_commit(db, correction_payload, scenario)
            assert (
                await _quantity_at(
                    db,
                    scenario.quantity_item_id,
                    location_id=scenario.location_one_id,
                )
                == 1
            )
            correction = await get_movement_record(db, correction_id)
            assert correction.movement.original_movement_id == receipt_id

        reversal_payload = MovementReversalCreate(
            client_request_id=f"reverse-correction-{scenario.marker}",
            purpose="Restore corrected unit",
        )
        async with AsyncSession(engine, expire_on_commit=False) as db:
            reversal = await reverse_movement(
                db,
                correction_id,
                reversal_payload,
                actor_user_id=scenario.actor_id,
                actor_display_name="Warehouse Admin (@admin)",
            )
            reversal_id = reversal.record.movement.id
            assert reversal.record.movement.movement_type == MovementType.REVERSAL
            assert reversal.record.movement.original_movement_id == correction_id
            await db.commit()
            assert (
                await _quantity_at(
                    db,
                    scenario.quantity_item_id,
                    location_id=scenario.location_one_id,
                )
                == 2
            )

        async with AsyncSession(engine, expire_on_commit=False) as db:
            with pytest.raises(InventoryConflictError) as conflict:
                await reverse_movement(
                    db,
                    correction_id,
                    MovementReversalCreate(client_request_id=f"repeat-reversal-{scenario.marker}"),
                    actor_user_id=scenario.actor_id,
                    actor_display_name="Warehouse Admin (@admin)",
                )
            assert conflict.value.code == "movement_already_reversed"
            await db.rollback()

        async with AsyncSession(engine, expire_on_commit=False) as db:
            item = await db.get(Item, scenario.quantity_item_id)
            assert item is not None
            item.name = f"Renamed item {scenario.marker}"
            item.normalized_name = item.name.casefold()
            await db.commit()
            historical_receipt = await get_movement_record(db, receipt_id)
            assert historical_receipt.lines[0].item_name_snapshot == original_item_snapshot

        async with AsyncSession(engine, expire_on_commit=False) as db:
            with pytest.raises(DBAPIError):
                await db.execute(
                    update(Movement)
                    .where(Movement.id == receipt_id)
                    .values(comment="forbidden rewrite")
                )
                await db.flush()
            await db.rollback()
        async with AsyncSession(engine, expire_on_commit=False) as db:
            with pytest.raises(DBAPIError):
                await db.execute(delete(MovementLine).where(MovementLine.id == receipt_line_id))
                await db.flush()
            await db.rollback()

        async with AsyncSession(engine) as db:
            assert await db.get(Movement, reversal_id) is not None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_serial_ledger_lifecycle_identity_and_reversal_rules() -> None:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            scenario = await _create_scenario(db)

        receipt = MovementCreate(
            movement_type=MovementType.RECEIPT,
            destination_location_id=scenario.location_one_id,
            client_request_id=f"serial-receipt-{scenario.marker}",
            lines=[
                MovementLineCreate(
                    item_id=scenario.serial_item_id,
                    serial_number=" SN-001 ",
                    wwn="10:00:00:00:00:01",
                    unit_comment="Verified label",
                )
            ],
        )
        async with AsyncSession(engine, expire_on_commit=False) as db:
            receipt_id = await _create_and_commit(db, receipt, scenario)
            receipt_record = await get_movement_record(db, receipt_id)
            unit_id = receipt_record.lines[0].inventory_unit_id
            assert unit_id is not None
            unit = await db.get(InventoryUnit, unit_id)
            assert unit is not None
            assert unit.serial_number == "SN-001"
            assert unit.state == InventoryUnitState.STORED
            assert unit.current_location_id == scenario.location_one_id

        duplicate = receipt.model_copy(deep=True)
        duplicate.client_request_id = f"duplicate-serial-{scenario.marker}"
        duplicate.lines[0].serial_number = "sn-001"
        async with AsyncSession(engine, expire_on_commit=False) as db:
            with pytest.raises(InventoryConflictError) as conflict:
                await create_movement(
                    db,
                    duplicate,
                    actor_user_id=scenario.actor_id,
                    actor_display_name="Warehouse Admin (@admin)",
                )
            assert conflict.value.code == "serial_identity_conflict"
            await db.rollback()

        duplicate_wwn = receipt.model_copy(deep=True)
        duplicate_wwn.client_request_id = f"duplicate-wwn-{scenario.marker}"
        duplicate_wwn.lines[0].serial_number = "SN-002"
        async with AsyncSession(engine, expire_on_commit=False) as db:
            with pytest.raises(InventoryConflictError) as conflict:
                await create_movement(
                    db,
                    duplicate_wwn,
                    actor_user_id=scenario.actor_id,
                    actor_display_name="Warehouse Admin (@admin)",
                )
            assert conflict.value.code == "wwn_identity_conflict"
            await db.rollback()

        issue = MovementCreate(
            movement_type=MovementType.ISSUE,
            source_location_id=scenario.location_one_id,
            destination_holder_user_id=scenario.holder_one_id,
            client_request_id=f"serial-issue-{scenario.marker}",
            lines=[MovementLineCreate(inventory_unit_id=unit_id)],
        )
        async with AsyncSession(engine, expire_on_commit=False) as db:
            await _create_and_commit(db, issue, scenario)
            unit = await db.get(InventoryUnit, unit_id)
            assert unit is not None
            assert unit.state == InventoryUnitState.ISSUED
            assert unit.current_holder_user_id == scenario.holder_one_id

        repeated_issue = issue.model_copy(deep=True)
        repeated_issue.client_request_id = f"repeated-issue-{scenario.marker}"
        async with AsyncSession(engine, expire_on_commit=False) as db:
            with pytest.raises(InventoryConflictError) as conflict:
                await create_movement(
                    db,
                    repeated_issue,
                    actor_user_id=scenario.actor_id,
                    actor_display_name="Warehouse Admin (@admin)",
                )
            assert conflict.value.code == "serial_source_mismatch"
            await db.rollback()

        invalid_return = MovementCreate(
            movement_type=MovementType.RETURN,
            source_holder_user_id=scenario.holder_two_id,
            destination_location_id=scenario.location_one_id,
            client_request_id=f"invalid-return-{scenario.marker}",
            lines=[MovementLineCreate(inventory_unit_id=unit_id)],
        )
        async with AsyncSession(engine, expire_on_commit=False) as db:
            with pytest.raises(InventoryConflictError) as conflict:
                await create_movement(
                    db,
                    invalid_return,
                    actor_user_id=scenario.actor_id,
                    actor_display_name="Warehouse Admin (@admin)",
                )
            assert conflict.value.code == "serial_source_mismatch"
            await db.rollback()

        lifecycle = [
            MovementCreate(
                movement_type=MovementType.RETURN,
                source_holder_user_id=scenario.holder_one_id,
                destination_location_id=scenario.location_one_id,
                client_request_id=f"serial-return-{scenario.marker}",
                lines=[MovementLineCreate(inventory_unit_id=unit_id)],
            ),
            MovementCreate(
                movement_type=MovementType.TRANSFER,
                source_location_id=scenario.location_one_id,
                destination_location_id=scenario.location_two_id,
                client_request_id=f"serial-transfer-{scenario.marker}",
                lines=[MovementLineCreate(inventory_unit_id=unit_id)],
            ),
        ]
        async with AsyncSession(engine, expire_on_commit=False) as db:
            for payload in lifecycle:
                await _create_and_commit(db, payload, scenario)
            unit = await db.get(InventoryUnit, unit_id)
            assert unit is not None
            assert unit.state == InventoryUnitState.STORED
            assert unit.current_location_id == scenario.location_two_id

        source_mismatch = lifecycle[-1].model_copy(deep=True)
        source_mismatch.client_request_id = f"source-mismatch-{scenario.marker}"
        async with AsyncSession(engine, expire_on_commit=False) as db:
            with pytest.raises(InventoryConflictError) as conflict:
                await create_movement(
                    db,
                    source_mismatch,
                    actor_user_id=scenario.actor_id,
                    actor_display_name="Warehouse Admin (@admin)",
                )
            assert conflict.value.code == "serial_source_mismatch"
            await db.rollback()

        write_off = MovementCreate(
            movement_type=MovementType.WRITE_OFF,
            source_location_id=scenario.location_two_id,
            client_request_id=f"serial-writeoff-{scenario.marker}",
            lines=[MovementLineCreate(inventory_unit_id=unit_id)],
        )
        async with AsyncSession(engine, expire_on_commit=False) as db:
            writeoff_id = await _create_and_commit(db, write_off, scenario)
            unit = await db.get(InventoryUnit, unit_id)
            assert unit is not None
            assert unit.state == InventoryUnitState.WRITTEN_OFF
            assert unit.current_location_id is None
            assert unit.current_holder_user_id is None

        post_writeoff_issue = MovementCreate(
            movement_type=MovementType.ISSUE,
            source_location_id=scenario.location_two_id,
            destination_holder_user_id=scenario.holder_two_id,
            client_request_id=f"post-writeoff-issue-{scenario.marker}",
            lines=[MovementLineCreate(inventory_unit_id=unit_id)],
        )
        async with AsyncSession(engine, expire_on_commit=False) as db:
            with pytest.raises(InventoryConflictError) as conflict:
                await create_movement(
                    db,
                    post_writeoff_issue,
                    actor_user_id=scenario.actor_id,
                    actor_display_name="Warehouse Admin (@admin)",
                )
            assert conflict.value.code == "serial_source_mismatch"
            await db.rollback()

        async with AsyncSession(engine, expire_on_commit=False) as db:
            await reverse_movement(
                db,
                writeoff_id,
                MovementReversalCreate(client_request_id=f"reverse-writeoff-{scenario.marker}"),
                actor_user_id=scenario.actor_id,
                actor_display_name="Warehouse Admin (@admin)",
            )
            await db.commit()
            unit = await db.get(InventoryUnit, unit_id)
            assert unit is not None
            assert unit.state == InventoryUnitState.STORED
            assert unit.current_location_id == scenario.location_two_id

        reactivation_receipt = receipt.model_copy(deep=True)
        reactivation_receipt.client_request_id = f"reactivation-{scenario.marker}"
        reactivation_receipt.lines[0].serial_number = "SN-REACTIVE"
        reactivation_receipt.lines[0].wwn = None
        async with AsyncSession(engine, expire_on_commit=False) as db:
            activation_id = await _create_and_commit(db, reactivation_receipt, scenario)
            activation = await get_movement_record(db, activation_id)
            reactivated_unit_id = activation.lines[0].inventory_unit_id
            assert reactivated_unit_id is not None
        async with AsyncSession(engine, expire_on_commit=False) as db:
            await reverse_movement(
                db,
                activation_id,
                MovementReversalCreate(client_request_id=f"reverse-activation-{scenario.marker}"),
                actor_user_id=scenario.actor_id,
                actor_display_name="Warehouse Admin (@admin)",
            )
            await db.commit()
            unit = await db.get(InventoryUnit, reactivated_unit_id)
            assert unit is not None
            assert unit.state == InventoryUnitState.VOIDED
        async with AsyncSession(engine, expire_on_commit=False) as db:
            second_activation = reactivation_receipt.model_copy(deep=True)
            second_activation.client_request_id = f"second-activation-{scenario.marker}"
            await _create_and_commit(db, second_activation, scenario)
            unit = await db.get(InventoryUnit, reactivated_unit_id)
            assert unit is not None
            assert unit.state == InventoryUnitState.STORED
            assert unit.current_location_id == scenario.location_one_id

        async with AsyncSession(engine) as db:
            with pytest.raises(IntegrityError):
                async with db.begin_nested():
                    db.add(
                        InventoryUnit(
                            item_id=scenario.quantity_item_id,
                            item_accounting_mode=AccountingMode.SERIAL,
                            serial_number="INVALID",
                            normalized_serial_number="invalid",
                            state=InventoryUnitState.STORED,
                            current_location_id=scenario.location_one_id,
                        )
                    )
                    await db.flush()
            with pytest.raises(IntegrityError):
                async with db.begin_nested():
                    db.add(
                        StockBalance(
                            item_id=scenario.quantity_item_id,
                            item_accounting_mode=AccountingMode.QUANTITY,
                            location_id=scenario.location_one_id,
                            quantity=0,
                        )
                    )
                    await db.flush()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_archived_location_blocks_reversal_destination_until_unarchived() -> None:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            scenario = await _create_scenario(db)
            await _create_and_commit(
                db,
                MovementCreate(
                    movement_type=MovementType.RECEIPT,
                    destination_location_id=scenario.location_one_id,
                    client_request_id=f"archive-receipt-{scenario.marker}",
                    lines=[
                        MovementLineCreate(
                            item_id=scenario.quantity_item_id,
                            quantity=1,
                        )
                    ],
                ),
                scenario,
            )
            transfer_id = await _create_and_commit(
                db,
                MovementCreate(
                    movement_type=MovementType.TRANSFER,
                    source_location_id=scenario.location_one_id,
                    destination_location_id=scenario.location_two_id,
                    client_request_id=f"archive-transfer-{scenario.marker}",
                    lines=[
                        MovementLineCreate(
                            item_id=scenario.quantity_item_id,
                            quantity=1,
                        )
                    ],
                ),
                scenario,
            )
            await set_location_archived(
                db,
                scenario.location_one_id,
                archived=True,
            )
            await db.commit()

        async with AsyncSession(engine, expire_on_commit=False) as db:
            with pytest.raises(InventoryConflictError) as conflict:
                await reverse_movement(
                    db,
                    transfer_id,
                    MovementReversalCreate(
                        client_request_id=f"archived-reversal-{scenario.marker}"
                    ),
                    actor_user_id=scenario.actor_id,
                    actor_display_name="Warehouse Admin (@admin)",
                )
            assert conflict.value.code == "location_archived"
            await db.rollback()

        async with AsyncSession(engine, expire_on_commit=False) as db:
            await set_location_archived(
                db,
                scenario.location_one_id,
                archived=False,
            )
            await db.commit()
            await reverse_movement(
                db,
                transfer_id,
                MovementReversalCreate(client_request_id=f"unarchived-reversal-{scenario.marker}"),
                actor_user_id=scenario.actor_id,
                actor_display_name="Warehouse Admin (@admin)",
            )
            await db.commit()
            assert (
                await _quantity_at(
                    db,
                    scenario.quantity_item_id,
                    location_id=scenario.location_one_id,
                )
                == 1
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_archived_item_quantity_and_serial_inventory_remains_manageable() -> None:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            scenario = await _create_scenario(db)
            quantity_receipt_id = await _create_and_commit(
                db,
                MovementCreate(
                    movement_type=MovementType.RECEIPT,
                    destination_location_id=scenario.location_one_id,
                    client_request_id=f"archived-item-q-receipt-{scenario.marker}",
                    lines=[
                        MovementLineCreate(
                            item_id=scenario.quantity_item_id,
                            quantity=5,
                        )
                    ],
                ),
                scenario,
            )
            await _create_and_commit(
                db,
                MovementCreate(
                    movement_type=MovementType.ISSUE,
                    source_location_id=scenario.location_one_id,
                    destination_holder_user_id=scenario.holder_one_id,
                    client_request_id=f"archived-item-q-issue-{scenario.marker}",
                    lines=[
                        MovementLineCreate(
                            item_id=scenario.quantity_item_id,
                            quantity=1,
                        )
                    ],
                ),
                scenario,
            )
            serial_receipt_id = await _create_and_commit(
                db,
                MovementCreate(
                    movement_type=MovementType.RECEIPT,
                    destination_location_id=scenario.location_one_id,
                    client_request_id=f"archived-item-s-receipt-{scenario.marker}",
                    lines=[
                        MovementLineCreate(
                            item_id=scenario.serial_item_id,
                            serial_number=f"ARCH-S1-{scenario.marker}",
                        ),
                        MovementLineCreate(
                            item_id=scenario.serial_item_id,
                            serial_number=f"ARCH-S2-{scenario.marker}",
                        ),
                    ],
                ),
                scenario,
            )
            serial_receipt = await get_movement_record(db, serial_receipt_id)
            issued_unit_id = serial_receipt.lines[0].inventory_unit_id
            stored_unit_id = serial_receipt.lines[1].inventory_unit_id
            assert issued_unit_id is not None and stored_unit_id is not None
            await _create_and_commit(
                db,
                MovementCreate(
                    movement_type=MovementType.ISSUE,
                    source_location_id=scenario.location_one_id,
                    destination_holder_user_id=scenario.holder_one_id,
                    client_request_id=f"archived-item-s-issue-{scenario.marker}",
                    lines=[MovementLineCreate(inventory_unit_id=issued_unit_id)],
                ),
                scenario,
            )
            await set_item_archived(db, scenario.quantity_item_id, archived=True)
            await set_item_archived(db, scenario.serial_item_id, archived=True)
            await db.commit()

        blocked_payloads = [
            MovementCreate(
                movement_type=MovementType.RECEIPT,
                destination_location_id=scenario.location_one_id,
                client_request_id=f"archived-item-q-new-receipt-{scenario.marker}",
                lines=[
                    MovementLineCreate(
                        item_id=scenario.quantity_item_id,
                        quantity=1,
                    )
                ],
            ),
            MovementCreate(
                movement_type=MovementType.ISSUE,
                source_location_id=scenario.location_one_id,
                destination_holder_user_id=scenario.holder_two_id,
                client_request_id=f"archived-item-q-new-issue-{scenario.marker}",
                lines=[
                    MovementLineCreate(
                        item_id=scenario.quantity_item_id,
                        quantity=1,
                    )
                ],
            ),
            MovementCreate(
                movement_type=MovementType.RECEIPT,
                destination_location_id=scenario.location_one_id,
                client_request_id=f"archived-item-s-new-receipt-{scenario.marker}",
                lines=[
                    MovementLineCreate(
                        item_id=scenario.serial_item_id,
                        serial_number=f"ARCH-NEW-{scenario.marker}",
                    )
                ],
            ),
            MovementCreate(
                movement_type=MovementType.ISSUE,
                source_location_id=scenario.location_one_id,
                destination_holder_user_id=scenario.holder_two_id,
                client_request_id=f"archived-item-s-new-issue-{scenario.marker}",
                lines=[MovementLineCreate(inventory_unit_id=stored_unit_id)],
            ),
            MovementCreate(
                movement_type=MovementType.CORRECTION,
                destination_location_id=scenario.location_one_id,
                original_movement_id=quantity_receipt_id,
                client_request_id=f"archived-item-q-external-correction-{scenario.marker}",
                lines=[
                    MovementLineCreate(
                        item_id=scenario.quantity_item_id,
                        quantity=1,
                    )
                ],
            ),
            MovementCreate(
                movement_type=MovementType.CORRECTION,
                destination_location_id=scenario.location_one_id,
                original_movement_id=serial_receipt_id,
                client_request_id=f"archived-item-s-external-correction-{scenario.marker}",
                lines=[
                    MovementLineCreate(
                        item_id=scenario.serial_item_id,
                        serial_number=f"ARCH-CORRECTION-{scenario.marker}",
                    )
                ],
            ),
        ]
        for payload in blocked_payloads:
            async with AsyncSession(engine, expire_on_commit=False) as db:
                with pytest.raises(InventoryConflictError) as conflict:
                    await create_movement(
                        db,
                        payload,
                        actor_user_id=scenario.actor_id,
                        actor_display_name="Warehouse Admin (@admin)",
                    )
                assert conflict.value.code == "item_archived"
                await db.rollback()

        async with AsyncSession(engine, expire_on_commit=False) as db:
            quantity_correction_id = await _create_and_commit(
                db,
                MovementCreate(
                    movement_type=MovementType.CORRECTION,
                    source_location_id=scenario.location_one_id,
                    original_movement_id=quantity_receipt_id,
                    client_request_id=f"archived-item-q-correction-{scenario.marker}",
                    lines=[
                        MovementLineCreate(
                            item_id=scenario.quantity_item_id,
                            quantity=1,
                        )
                    ],
                ),
                scenario,
            )
            await reverse_movement(
                db,
                quantity_correction_id,
                MovementReversalCreate(
                    client_request_id=f"archived-item-q-correction-reverse-{scenario.marker}"
                ),
                actor_user_id=scenario.actor_id,
                actor_display_name="Warehouse Admin (@admin)",
            )
            await db.commit()

            serial_correction_id = await _create_and_commit(
                db,
                MovementCreate(
                    movement_type=MovementType.CORRECTION,
                    source_location_id=scenario.location_one_id,
                    original_movement_id=serial_receipt_id,
                    client_request_id=f"archived-item-s-correction-{scenario.marker}",
                    lines=[MovementLineCreate(inventory_unit_id=stored_unit_id)],
                ),
                scenario,
            )
            stored_unit = await db.get(InventoryUnit, stored_unit_id)
            assert stored_unit is not None
            assert stored_unit.state == InventoryUnitState.VOIDED
            await reverse_movement(
                db,
                serial_correction_id,
                MovementReversalCreate(
                    client_request_id=f"archived-item-s-correction-reverse-{scenario.marker}"
                ),
                actor_user_id=scenario.actor_id,
                actor_display_name="Warehouse Admin (@admin)",
            )
            await db.commit()
            restored_unit = await db.get(
                InventoryUnit,
                stored_unit_id,
                populate_existing=True,
            )
            assert restored_unit is not None
            assert restored_unit.state == InventoryUnitState.STORED

            await _create_and_commit(
                db,
                MovementCreate(
                    movement_type=MovementType.RETURN,
                    source_holder_user_id=scenario.holder_one_id,
                    destination_location_id=scenario.location_one_id,
                    client_request_id=f"archived-item-return-{scenario.marker}",
                    lines=[
                        MovementLineCreate(
                            item_id=scenario.quantity_item_id,
                            quantity=1,
                        ),
                        MovementLineCreate(inventory_unit_id=issued_unit_id),
                    ],
                ),
                scenario,
            )
            await _create_and_commit(
                db,
                MovementCreate(
                    movement_type=MovementType.TRANSFER,
                    source_location_id=scenario.location_one_id,
                    destination_location_id=scenario.location_two_id,
                    client_request_id=f"archived-item-transfer-{scenario.marker}",
                    lines=[
                        MovementLineCreate(
                            item_id=scenario.quantity_item_id,
                            quantity=1,
                        ),
                        MovementLineCreate(inventory_unit_id=issued_unit_id),
                    ],
                ),
                scenario,
            )
            write_off_id = await _create_and_commit(
                db,
                MovementCreate(
                    movement_type=MovementType.WRITE_OFF,
                    source_location_id=scenario.location_two_id,
                    client_request_id=f"archived-item-writeoff-{scenario.marker}",
                    lines=[
                        MovementLineCreate(
                            item_id=scenario.quantity_item_id,
                            quantity=1,
                        ),
                        MovementLineCreate(inventory_unit_id=issued_unit_id),
                    ],
                ),
                scenario,
            )
            written_off = await db.get(InventoryUnit, issued_unit_id)
            assert written_off is not None
            assert written_off.state == InventoryUnitState.WRITTEN_OFF
            await reverse_movement(
                db,
                write_off_id,
                MovementReversalCreate(
                    client_request_id=f"archived-item-writeoff-reverse-{scenario.marker}"
                ),
                actor_user_id=scenario.actor_id,
                actor_display_name="Warehouse Admin (@admin)",
            )
            await db.commit()
            restored_written_off = await db.get(
                InventoryUnit,
                issued_unit_id,
                populate_existing=True,
            )
            assert restored_written_off is not None
            assert restored_written_off.state == InventoryUnitState.STORED
            assert restored_written_off.current_location_id == scenario.location_two_id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_line_order_global_wwn_and_wwn_history_are_stable() -> None:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            scenario = await _create_scenario(db)
            serial_category = await db.scalar(select(Category).where(Category.key == "nic"))
            assert serial_category is not None
            other_serial_item_id = uuid.uuid4()
            db.add(
                Item(
                    id=other_serial_item_id,
                    category_id=serial_category.id,
                    name=f"Other serial item {scenario.marker}",
                    normalized_name=f"other serial item {scenario.marker}",
                    accounting_mode=AccountingMode.SERIAL,
                    status=ItemStatus.ACTIVE,
                )
            )
            await db.commit()

            receipt_payload = MovementCreate(
                movement_type=MovementType.RECEIPT,
                destination_location_id=scenario.location_one_id,
                client_request_id=f"ordered-receipt-{scenario.marker}",
                lines=[
                    MovementLineCreate(
                        item_id=scenario.serial_item_id,
                        serial_number=f"ORDER-A-{scenario.marker}",
                        wwn=f"WWN-A-{scenario.marker}",
                    ),
                    MovementLineCreate(
                        item_id=scenario.quantity_item_id,
                        quantity=2,
                    ),
                    MovementLineCreate(
                        item_id=scenario.serial_item_id,
                        serial_number=f"ORDER-B-{scenario.marker}",
                        wwn=f"WWN-B-{scenario.marker}",
                    ),
                ],
            )
            receipt_result = await create_movement(
                db,
                receipt_payload,
                actor_user_id=scenario.actor_id,
                actor_display_name="Warehouse Admin (@admin)",
            )
            await db.commit()
            receipt_id = receipt_result.record.movement.id
            assert [line.line_no for line in receipt_result.record.lines] == [1, 2, 3]
            assert [line.item_id for line in receipt_result.record.lines] == [
                scenario.serial_item_id,
                scenario.quantity_item_id,
                scenario.serial_item_id,
            ]
            first_unit_id = receipt_result.record.lines[0].inventory_unit_id
            assert first_unit_id is not None
            assert receipt_result.record.lines[0].wwn_snapshot == (f"WWN-A-{scenario.marker}")

        async with AsyncSession(engine, expire_on_commit=False) as db:
            replay = await create_movement(
                db,
                receipt_payload,
                actor_user_id=scenario.actor_id,
                actor_display_name="Warehouse Admin (@admin)",
            )
            assert replay.replayed is True
            assert [line.line_no for line in replay.record.lines] == [1, 2, 3]
            await db.commit()

        async with AsyncSession(engine, expire_on_commit=False) as db:
            duplicate_wwn = MovementCreate(
                movement_type=MovementType.RECEIPT,
                destination_location_id=scenario.location_two_id,
                client_request_id=f"cross-item-wwn-{scenario.marker}",
                lines=[
                    MovementLineCreate(
                        item_id=other_serial_item_id,
                        serial_number=f"OTHER-{scenario.marker}",
                        wwn=f"wwn-a-{scenario.marker}",
                    )
                ],
            )
            with pytest.raises(InventoryConflictError) as conflict:
                await create_movement(
                    db,
                    duplicate_wwn,
                    actor_user_id=scenario.actor_id,
                    actor_display_name="Warehouse Admin (@admin)",
                )
            assert conflict.value.code == "wwn_identity_conflict"
            await db.rollback()

        async with AsyncSession(engine, expire_on_commit=False) as db:
            reversal = await reverse_movement(
                db,
                receipt_id,
                MovementReversalCreate(client_request_id=f"ordered-reversal-{scenario.marker}"),
                actor_user_id=scenario.actor_id,
                actor_display_name="Warehouse Admin (@admin)",
            )
            await db.commit()
            assert [line.line_no for line in reversal.record.lines] == [1, 2, 3]
            assert reversal.record.lines[0].wwn_snapshot == f"WWN-A-{scenario.marker}"
            unit = await db.get(InventoryUnit, first_unit_id)
            assert unit is not None and unit.state == InventoryUnitState.VOIDED

        async with AsyncSession(engine, expire_on_commit=False) as db:
            changed_wwn = MovementCreate(
                movement_type=MovementType.RECEIPT,
                destination_location_id=scenario.location_two_id,
                client_request_id=f"changed-wwn-{scenario.marker}",
                lines=[
                    MovementLineCreate(
                        item_id=scenario.serial_item_id,
                        serial_number=f"ORDER-A-{scenario.marker}",
                        wwn=f"WWN-CHANGED-{scenario.marker}",
                    )
                ],
            )
            with pytest.raises(InventoryConflictError) as conflict:
                await create_movement(
                    db,
                    changed_wwn,
                    actor_user_id=scenario.actor_id,
                    actor_display_name="Warehouse Admin (@admin)",
                )
            assert conflict.value.code == "wwn_replacement_conflict"
            await db.rollback()

        async with AsyncSession(engine, expire_on_commit=False) as db:
            retained_wwn = MovementCreate(
                movement_type=MovementType.RECEIPT,
                destination_location_id=scenario.location_two_id,
                client_request_id=f"retained-wwn-{scenario.marker}",
                lines=[
                    MovementLineCreate(
                        item_id=scenario.serial_item_id,
                        serial_number=f"ORDER-A-{scenario.marker}",
                    )
                ],
            )
            result = await create_movement(
                db,
                retained_wwn,
                actor_user_id=scenario.actor_id,
                actor_display_name="Warehouse Admin (@admin)",
            )
            await db.commit()
            assert result.record.lines[0].wwn_snapshot == f"WWN-A-{scenario.marker}"
            unit = await db.get(InventoryUnit, first_unit_id)
            assert unit is not None
            assert unit.wwn == f"WWN-A-{scenario.marker}"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_quantity_bigint_overflow_and_correction_relationship_are_controlled() -> None:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            scenario = await _create_scenario(db)
            receipt_id = await _create_and_commit(
                db,
                MovementCreate(
                    movement_type=MovementType.RECEIPT,
                    destination_location_id=scenario.location_one_id,
                    client_request_id=f"bigint-receipt-{scenario.marker}",
                    lines=[
                        MovementLineCreate(
                            item_id=scenario.quantity_item_id,
                            quantity=POSTGRES_BIGINT_MAX,
                        )
                    ],
                ),
                scenario,
            )

        async with AsyncSession(engine, expire_on_commit=False) as db:
            with pytest.raises(InventoryConflictError) as overflow:
                await create_movement(
                    db,
                    MovementCreate(
                        movement_type=MovementType.RECEIPT,
                        destination_location_id=scenario.location_one_id,
                        client_request_id=f"bigint-overflow-{scenario.marker}",
                        lines=[
                            MovementLineCreate(
                                item_id=scenario.quantity_item_id,
                                quantity=1,
                            )
                        ],
                    ),
                    actor_user_id=scenario.actor_id,
                    actor_display_name="Warehouse Admin (@admin)",
                )
            assert overflow.value.code == "quantity_overflow"
            await db.rollback()

        async with AsyncSession(engine, expire_on_commit=False) as db:
            with pytest.raises(InventoryValidationError) as unrelated_position:
                await create_movement(
                    db,
                    MovementCreate(
                        movement_type=MovementType.CORRECTION,
                        source_location_id=scenario.location_two_id,
                        original_movement_id=receipt_id,
                        client_request_id=f"unrelated-correction-{scenario.marker}",
                        lines=[
                            MovementLineCreate(
                                item_id=scenario.quantity_item_id,
                                quantity=1,
                            )
                        ],
                    ),
                    actor_user_id=scenario.actor_id,
                    actor_display_name="Warehouse Admin (@admin)",
                )
            assert unrelated_position.value.code == "correction_relationship_invalid"
            await db.rollback()

        too_large = MovementCreate(
            movement_type=MovementType.RECEIPT,
            destination_location_id=scenario.location_two_id,
            client_request_id=f"too-large-{scenario.marker}",
            lines=[
                MovementLineCreate(
                    item_id=scenario.quantity_item_id,
                    quantity=POSTGRES_BIGINT_MAX + 1,
                )
            ],
        )
        async with AsyncSession(engine, expire_on_commit=False) as db:
            with pytest.raises(InventoryValidationError) as too_large_error:
                await create_movement(
                    db,
                    too_large,
                    actor_user_id=scenario.actor_id,
                    actor_display_name="Warehouse Admin (@admin)",
                )
            assert too_large_error.value.code == "quantity_too_large"
            await db.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_stage6_postgresql_constraints_and_migration_state() -> None:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    try:
        async with AsyncSession(engine) as db:
            tables = set(
                (
                    await db.scalars(
                        text("SELECT tablename FROM pg_tables WHERE schemaname = current_schema()")
                    )
                ).all()
            )
            assert {
                "locations",
                "inventory_units",
                "movements",
                "movement_lines",
                "stock_balances",
            } <= tables
            triggers = set(
                (
                    await db.scalars(
                        text(
                            "SELECT tgname FROM pg_trigger "
                            "WHERE NOT tgisinternal AND tgname LIKE "
                            "'trg_movement%_append_only'"
                        )
                    )
                ).all()
            )
            assert triggers == {
                "trg_movements_append_only",
                "trg_movement_lines_append_only",
            }
            correction_triggers = set(
                (
                    await db.scalars(
                        text(
                            "SELECT tgname FROM pg_trigger "
                            "WHERE NOT tgisinternal "
                            "AND tgname LIKE 'trg_movement%validate_correction'"
                        )
                    )
                ).all()
            )
            assert correction_triggers == {
                "trg_movements_validate_correction",
                "trg_movement_lines_validate_correction",
            }
            indexes = set(
                (
                    await db.scalars(
                        text("SELECT indexname FROM pg_indexes WHERE schemaname = current_schema()")
                    )
                ).all()
            )
            assert {
                "ux_movements_original_reversal",
                "ux_stock_balances_item_location",
                "ux_stock_balances_item_holder",
            } <= indexes
            constraints = set(
                (
                    await db.scalars(
                        text(
                            "SELECT conname FROM pg_constraint "
                            "WHERE connamespace = current_schema()::regnamespace"
                        )
                    )
                ).all()
            )
            assert {
                "uq_inventory_units_normalized_wwn",
                "uq_movements_journal_seq",
                "ck_movements_line_count_range",
                "uq_movement_lines_movement_id_line_no",
                "ck_movement_lines_line_no_positive",
            } <= constraints
            movement_line_columns = set(
                (
                    await db.scalars(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_schema = current_schema() "
                            "AND table_name = 'movement_lines'"
                        )
                    )
                ).all()
            )
            assert {"line_no", "wwn_snapshot"} <= movement_line_columns

            movement_columns = {
                row.column_name: (row.is_identity, row.identity_generation)
                for row in (
                    await db.execute(
                        text(
                            "SELECT column_name, is_identity, identity_generation "
                            "FROM information_schema.columns "
                            "WHERE table_schema = current_schema() "
                            "AND table_name = 'movements'"
                        )
                    )
                ).all()
            }
            assert movement_columns["journal_seq"] == ("YES", "ALWAYS")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_quantity_issue_allocates_last_unit_exactly_once() -> None:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            scenario = await _create_scenario(db)
            await _create_and_commit(
                db,
                MovementCreate(
                    movement_type=MovementType.RECEIPT,
                    destination_location_id=scenario.location_one_id,
                    client_request_id=f"race-receipt-{scenario.marker}",
                    lines=[
                        MovementLineCreate(
                            item_id=scenario.quantity_item_id,
                            quantity=1,
                        )
                    ],
                ),
                scenario,
            )

        barrier = asyncio.Barrier(2)

        async def issue(holder_id: uuid.UUID, request_suffix: str) -> bool:
            try:
                async with AsyncSession(engine, expire_on_commit=False) as db:
                    await barrier.wait()
                    async with db.begin():
                        await create_movement(
                            db,
                            MovementCreate(
                                movement_type=MovementType.ISSUE,
                                source_location_id=scenario.location_one_id,
                                destination_holder_user_id=holder_id,
                                client_request_id=(
                                    f"quantity-race-{request_suffix}-{scenario.marker}"
                                ),
                                lines=[
                                    MovementLineCreate(
                                        item_id=scenario.quantity_item_id,
                                        quantity=1,
                                    )
                                ],
                            ),
                            actor_user_id=scenario.actor_id,
                            actor_display_name="Warehouse Admin (@admin)",
                        )
                return True
            except InventoryConflictError as error:
                assert error.code == "insufficient_stock"
                return False

        outcomes = await asyncio.gather(
            issue(scenario.holder_one_id, "one"),
            issue(scenario.holder_two_id, "two"),
        )
        assert sorted(outcomes) == [False, True]

        async with AsyncSession(engine) as db:
            assert (
                await _quantity_at(
                    db,
                    scenario.quantity_item_id,
                    location_id=scenario.location_one_id,
                )
                == 0
            )
            held_total = await db.scalar(
                select(func.coalesce(func.sum(StockBalance.quantity), 0)).where(
                    StockBalance.item_id == scenario.quantity_item_id,
                    StockBalance.holder_user_id.is_not(None),
                )
            )
            assert held_total == 1
            issue_count = await db.scalar(
                select(func.count())
                .select_from(Movement)
                .where(
                    Movement.movement_type == MovementType.ISSUE,
                    Movement.id.in_(
                        select(MovementLine.movement_id).where(
                            MovementLine.item_id == scenario.quantity_item_id
                        )
                    ),
                )
            )
            assert issue_count == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_serial_issue_allocates_unit_exactly_once() -> None:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            scenario = await _create_scenario(db)
            receipt_id = await _create_and_commit(
                db,
                MovementCreate(
                    movement_type=MovementType.RECEIPT,
                    destination_location_id=scenario.location_one_id,
                    client_request_id=f"serial-race-receipt-{scenario.marker}",
                    lines=[
                        MovementLineCreate(
                            item_id=scenario.serial_item_id,
                            serial_number=f"RACE-{scenario.marker}",
                        )
                    ],
                ),
                scenario,
            )
            receipt = await get_movement_record(db, receipt_id)
            unit_id = receipt.lines[0].inventory_unit_id
            assert unit_id is not None

        barrier = asyncio.Barrier(2)

        async def issue(holder_id: uuid.UUID, request_suffix: str) -> bool:
            try:
                async with AsyncSession(engine, expire_on_commit=False) as db:
                    await barrier.wait()
                    async with db.begin():
                        await create_movement(
                            db,
                            MovementCreate(
                                movement_type=MovementType.ISSUE,
                                source_location_id=scenario.location_one_id,
                                destination_holder_user_id=holder_id,
                                client_request_id=(
                                    f"serial-race-{request_suffix}-{scenario.marker}"
                                ),
                                lines=[MovementLineCreate(inventory_unit_id=unit_id)],
                            ),
                            actor_user_id=scenario.actor_id,
                            actor_display_name="Warehouse Admin (@admin)",
                        )
                return True
            except InventoryConflictError as error:
                assert error.code == "serial_source_mismatch"
                return False

        outcomes = await asyncio.gather(
            issue(scenario.holder_one_id, "one"),
            issue(scenario.holder_two_id, "two"),
        )
        assert sorted(outcomes) == [False, True]

        async with AsyncSession(engine) as db:
            unit = await db.get(InventoryUnit, unit_id)
            assert unit is not None
            assert unit.state == InventoryUnitState.ISSUED
            assert unit.current_holder_user_id in {
                scenario.holder_one_id,
                scenario.holder_two_id,
            }
            issue_count = await db.scalar(
                select(func.count())
                .select_from(Movement)
                .where(
                    Movement.movement_type == MovementType.ISSUE,
                    Movement.id.in_(
                        select(MovementLine.movement_id).where(
                            MovementLine.inventory_unit_id == unit_id
                        )
                    ),
                )
            )
            assert issue_count == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_serial_reactivation_racing_reversal_has_no_lock_order_deadlock() -> None:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            scenario = await _create_scenario(db)
            receipt_id = await _create_and_commit(
                db,
                MovementCreate(
                    movement_type=MovementType.RECEIPT,
                    destination_location_id=scenario.location_two_id,
                    client_request_id=f"reactivation-race-receipt-{scenario.marker}",
                    lines=[
                        MovementLineCreate(
                            item_id=scenario.serial_item_id,
                            serial_number=f"REACTIVATION-RACE-{scenario.marker}",
                        )
                    ],
                ),
                scenario,
            )
            receipt = await get_movement_record(db, receipt_id)
            unit_id = receipt.lines[0].inventory_unit_id
            assert unit_id is not None
            correction_id = await _create_and_commit(
                db,
                MovementCreate(
                    movement_type=MovementType.CORRECTION,
                    source_location_id=scenario.location_two_id,
                    original_movement_id=receipt_id,
                    client_request_id=f"reactivation-race-correction-{scenario.marker}",
                    lines=[MovementLineCreate(inventory_unit_id=unit_id)],
                ),
                scenario,
            )
            unit = await db.get(InventoryUnit, unit_id)
            assert unit is not None and unit.state == InventoryUnitState.VOIDED

        barrier = asyncio.Barrier(2)

        async def reactivate() -> str:
            try:
                async with AsyncSession(engine, expire_on_commit=False) as db:
                    await barrier.wait()
                    async with db.begin():
                        await create_movement(
                            db,
                            MovementCreate(
                                movement_type=MovementType.RECEIPT,
                                destination_location_id=scenario.location_one_id,
                                client_request_id=(f"reactivation-race-new-{scenario.marker}"),
                                lines=[
                                    MovementLineCreate(
                                        item_id=scenario.serial_item_id,
                                        serial_number=(f"REACTIVATION-RACE-{scenario.marker}"),
                                    )
                                ],
                            ),
                            actor_user_id=scenario.actor_id,
                            actor_display_name="Warehouse Admin (@admin)",
                        )
                return "reactivated"
            except InventoryConflictError as error:
                assert error.code == "serial_identity_conflict"
                return "reactivation_conflict"

        async def reverse_correction() -> str:
            try:
                async with AsyncSession(engine, expire_on_commit=False) as db:
                    await barrier.wait()
                    async with db.begin():
                        await reverse_movement(
                            db,
                            correction_id,
                            MovementReversalCreate(
                                client_request_id=(f"reactivation-race-reversal-{scenario.marker}")
                            ),
                            actor_user_id=scenario.actor_id,
                            actor_display_name="Warehouse Admin (@admin)",
                        )
                return "reversed"
            except InventoryConflictError as error:
                assert error.code == "serial_source_mismatch"
                return "reversal_conflict"

        outcomes = await asyncio.wait_for(
            asyncio.gather(reactivate(), reverse_correction()),
            timeout=15,
        )
        assert set(outcomes) in (
            {"reactivated", "reversal_conflict"},
            {"reactivation_conflict", "reversed"},
        )

        async with AsyncSession(engine) as db:
            unit = await db.get(InventoryUnit, unit_id)
            assert unit is not None and unit.state == InventoryUnitState.STORED
            assert unit.current_location_id in {
                scenario.location_one_id,
                scenario.location_two_id,
            }
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_journal_sequence_is_canonical_when_wall_clock_moves_backward(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.modules.inventory.service as inventory_service

    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            scenario = await _create_scenario(db)

        real_datetime = datetime

        class ReverseClock:
            calls = 0

            @classmethod
            def now(
                cls,
                tz: object | None = None,
            ) -> datetime:
                values = (
                    real_datetime(2026, 9, 2, 12, 0, 0, tzinfo=UTC),
                    real_datetime(2026, 9, 2, 11, 0, 0, tzinfo=UTC),
                )
                if cls.calls >= len(values):
                    raise AssertionError(
                        "inventory movement clock was read more often than expected"
                    )
                value = values[cls.calls]
                cls.calls += 1
                return value

        monkeypatch.setattr(inventory_service, "datetime", ReverseClock)

        async with AsyncSession(engine, expire_on_commit=False) as db:
            receipt_id = await _create_and_commit(
                db,
                MovementCreate(
                    movement_type=MovementType.RECEIPT,
                    destination_location_id=scenario.location_one_id,
                    client_request_id=(
                        f"journal-seq-receipt-{scenario.marker}"
                    ),
                    lines=[
                        MovementLineCreate(
                            item_id=scenario.serial_item_id,
                            serial_number=f"JSEQ-{scenario.marker}",
                        )
                    ],
                ),
                scenario,
            )
            receipt_record = await get_movement_record(db, receipt_id)
            unit_id = receipt_record.lines[0].inventory_unit_id
            assert unit_id is not None

        async with AsyncSession(engine, expire_on_commit=False) as db:
            issue_id = await _create_and_commit(
                db,
                MovementCreate(
                    movement_type=MovementType.ISSUE,
                    source_location_id=scenario.location_one_id,
                    destination_holder_user_id=scenario.holder_one_id,
                    client_request_id=(
                        f"journal-seq-issue-{scenario.marker}"
                    ),
                    lines=[
                        MovementLineCreate(
                            inventory_unit_id=unit_id,
                        )
                    ],
                ),
                scenario,
            )

        assert ReverseClock.calls == 2

        async with AsyncSession(engine) as db:
            receipt = await db.get(Movement, receipt_id)
            issue = await db.get(Movement, issue_id)
            unit = await db.get(InventoryUnit, unit_id)

            assert receipt is not None
            assert issue is not None
            assert unit is not None

            # Wall clock deliberately moved backwards.
            assert receipt.occurred_at > issue.occurred_at

            # Database journal order still reflects accepted state transitions.
            assert receipt.journal_seq < issue.journal_seq

            history = await inventory_service.list_movements(
                db,
                movement_type=None,
                item_id=None,
                inventory_unit_id=unit_id,
                limit=10,
                offset=0,
            )
            assert [record.movement.id for record in history.items] == [
                issue_id,
                receipt_id,
            ]

            canonical_latest = await db.scalar(
                text(
                    "SELECT m.id "
                    "FROM movements AS m "
                    "JOIN movement_lines AS ml ON ml.movement_id = m.id "
                    "WHERE ml.inventory_unit_id = :unit_id "
                    "ORDER BY m.journal_seq DESC "
                    "LIMIT 1"
                ),
                {"unit_id": unit_id},
            )
            assert canonical_latest == issue_id

            assert unit.state == InventoryUnitState.ISSUED
            assert unit.current_location_id is None
            assert unit.current_holder_user_id == scenario.holder_one_id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_movement_line_cardinality_is_sealed_at_commit() -> None:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            scenario = await _create_scenario(db)

            quantity_receipt_id = await _create_and_commit(
                db,
                MovementCreate(
                    movement_type=MovementType.RECEIPT,
                    destination_location_id=scenario.location_one_id,
                    client_request_id=f"sealed-q-receipt-{scenario.marker}",
                    lines=[
                        MovementLineCreate(
                            item_id=scenario.quantity_item_id,
                            quantity=1,
                        )
                    ],
                ),
                scenario,
            )

            serial_receipt_id = await _create_and_commit(
                db,
                MovementCreate(
                    movement_type=MovementType.RECEIPT,
                    destination_location_id=scenario.location_one_id,
                    client_request_id=f"sealed-s-receipt-{scenario.marker}",
                    lines=[
                        MovementLineCreate(
                            item_id=scenario.serial_item_id,
                            serial_number=f"SEALED-{scenario.marker}",
                        )
                    ],
                ),
                scenario,
            )

        # A later INSERT must not be able to rewrite the semantic contents
        # of an already committed movement.
        async with AsyncSession(engine, expire_on_commit=False) as db:
            serial_record = await get_movement_record(db, serial_receipt_id)
            serial_line = serial_record.lines[0]

            late_line = MovementLine(
                movement_id=quantity_receipt_id,
                line_no=2,
                item_id=serial_line.item_id,
                item_accounting_mode=serial_line.item_accounting_mode,
                inventory_unit_id=serial_line.inventory_unit_id,
                quantity=None,
                item_name_snapshot=serial_line.item_name_snapshot,
                manufacturer_name_snapshot=serial_line.manufacturer_name_snapshot,
                model_snapshot=serial_line.model_snapshot,
                manufacturer_part_number_snapshot=(
                    serial_line.manufacturer_part_number_snapshot
                ),
                serial_number_snapshot=serial_line.serial_number_snapshot,
                wwn_snapshot=serial_line.wwn_snapshot,
            )
            db.add(late_line)

            # Deferred constraint intentionally permits normal header->lines
            # construction inside one transaction and rejects only at commit.
            await db.flush()

            with pytest.raises(IntegrityError):
                await db.commit()
            await db.rollback()

        async with AsyncSession(engine) as db:
            persisted_line_count = await db.scalar(
                select(func.count())
                .select_from(MovementLine)
                .where(MovementLine.movement_id == quantity_receipt_id)
            )
            assert persisted_line_count == 1

            original = await db.get(Movement, quantity_receipt_id)
            assert original is not None
            assert original.line_count == 1

        # A raw/buggy writer also cannot commit a header without the lines
        # declared by that immutable header.
        orphan_id = uuid.uuid4()
        async with AsyncSession(engine, expire_on_commit=False) as db:
            original = await db.get(Movement, quantity_receipt_id)
            assert original is not None

            orphan = Movement(
                id=orphan_id,
                line_count=1,
                movement_type=MovementType.RECEIPT,
                actor_user_id=scenario.actor_id,
                destination_location_id=scenario.location_one_id,
                client_request_id=f"sealed-orphan-{scenario.marker}",
                request_fingerprint="0" * 64,
                actor_display_name_snapshot="Warehouse Admin (@admin)",
                destination_location_code_snapshot=(
                    original.destination_location_code_snapshot
                ),
                destination_location_name_snapshot=(
                    original.destination_location_name_snapshot
                ),
            )
            db.add(orphan)
            await db.flush()

            with pytest.raises(IntegrityError):
                await db.commit()
            await db.rollback()

        async with AsyncSession(engine) as db:
            assert await db.get(Movement, orphan_id) is None
    finally:
        await engine.dispose()

@pytest.mark.asyncio
async def test_movement_line_accounting_shape_rejects_null_required_values() -> None:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            scenario = await _create_scenario(db)

            quantity_receipt_id = await _create_and_commit(
                db,
                MovementCreate(
                    movement_type=MovementType.RECEIPT,
                    destination_location_id=scenario.location_one_id,
                    client_request_id=f"null-shape-quantity-{scenario.marker}",
                    lines=[
                        MovementLineCreate(
                            item_id=scenario.quantity_item_id,
                            quantity=1,
                        )
                    ],
                ),
                scenario,
            )

            serial_receipt_id = await _create_and_commit(
                db,
                MovementCreate(
                    movement_type=MovementType.RECEIPT,
                    destination_location_id=scenario.location_one_id,
                    client_request_id=f"null-shape-serial-{scenario.marker}",
                    lines=[
                        MovementLineCreate(
                            item_id=scenario.serial_item_id,
                            serial_number=f"NULL-SHAPE-{scenario.marker}",
                        )
                    ],
                ),
                scenario,
            )

            serial_receipt = await get_movement_record(db, serial_receipt_id)
            serial_unit_id = serial_receipt.lines[0].inventory_unit_id
            assert serial_unit_id is not None

        async with AsyncSession(engine) as db:
            with pytest.raises(IntegrityError):
                await db.execute(
                    insert(MovementLine).values(
                        id=uuid.uuid4(),
                        movement_id=quantity_receipt_id,
                        line_no=2,
                        item_id=scenario.quantity_item_id,
                        item_accounting_mode=AccountingMode.QUANTITY,
                        inventory_unit_id=None,
                        quantity=None,
                        item_name_snapshot="Malformed quantity line",
                        serial_number_snapshot=None,
                        wwn_snapshot=None,
                    )
                )
                await db.flush()
            await db.rollback()

        async with AsyncSession(engine) as db:
            with pytest.raises(IntegrityError):
                await db.execute(
                    insert(MovementLine).values(
                        id=uuid.uuid4(),
                        movement_id=quantity_receipt_id,
                        line_no=2,
                        item_id=scenario.serial_item_id,
                        item_accounting_mode=AccountingMode.SERIAL,
                        inventory_unit_id=serial_unit_id,
                        quantity=None,
                        item_name_snapshot="Malformed serial line",
                        serial_number_snapshot=None,
                        wwn_snapshot=None,
                    )
                )
                await db.flush()
            await db.rollback()
    finally:
        await engine.dispose()

@pytest.mark.asyncio
async def test_correction_racing_original_reversal_has_no_lock_order_deadlock() -> None:
    engine = create_async_engine(
        DATABASE_URL,
        pool_pre_ping=True,
    )

    try:
        async with AsyncSession(
            engine,
            expire_on_commit=False,
        ) as db:
            scenario = await _create_scenario(db)

            receipt_id = await _create_and_commit(
                db,
                MovementCreate(
                    movement_type=MovementType.RECEIPT,
                    destination_location_id=(
                        scenario.location_one_id
                    ),
                    client_request_id=(
                        "correction-reversal-race-receipt-"
                        f"{scenario.marker}"
                    ),
                    lines=[
                        MovementLineCreate(
                            item_id=(
                                scenario.quantity_item_id
                            ),
                            quantity=1,
                        )
                    ],
                ),
                scenario,
            )

        start_gate = asyncio.Event()
        correction_ready = asyncio.Event()
        reversal_ready = asyncio.Event()

        async def run_correction() -> str:
            correction_ready.set()
            await start_gate.wait()

            try:
                async with (
                    AsyncSession(
                        engine,
                        expire_on_commit=False,
                    ) as db,
                    db.begin(),
                ):
                    await create_movement(
                        db,
                        MovementCreate(
                            movement_type=(
                                MovementType.CORRECTION
                            ),
                            source_location_id=(
                                scenario.location_one_id
                            ),
                            original_movement_id=receipt_id,
                            client_request_id=(
                                "correction-reversal-race-"
                                "correction-"
                                f"{scenario.marker}"
                            ),
                            lines=[
                                MovementLineCreate(
                                    item_id=(
                                        scenario
                                        .quantity_item_id
                                    ),
                                    quantity=1,
                                )
                            ],
                        ),
                        actor_user_id=scenario.actor_id,
                        actor_display_name=(
                            "Warehouse Admin (@admin)"
                        ),
                    )

                return "corrected"

            except InventoryConflictError as error:
                assert error.code == "insufficient_stock"
                return "correction_conflict"

        async def run_reversal() -> str:
            reversal_ready.set()
            await start_gate.wait()

            try:
                async with (
                    AsyncSession(
                        engine,
                        expire_on_commit=False,
                    ) as db,
                    db.begin(),
                ):
                    reversal = await reverse_movement(
                        db,
                        receipt_id,
                        MovementReversalCreate(
                            client_request_id=(
                                "correction-reversal-race-"
                                "reversal-"
                                f"{scenario.marker}"
                            )
                        ),
                        actor_user_id=scenario.actor_id,
                        actor_display_name=(
                            "Warehouse Admin (@admin)"
                        ),
                    )

                    assert (
                        reversal.record.movement.movement_type
                        == MovementType.REVERSAL
                    )

                return "reversed"

            except InventoryConflictError as error:
                assert error.code == "insufficient_stock"
                return "reversal_conflict"

        correction_task = asyncio.create_task(
            run_correction()
        )
        reversal_task = asyncio.create_task(
            run_reversal()
        )

        await asyncio.wait_for(
            asyncio.gather(
                correction_ready.wait(),
                reversal_ready.wait(),
            ),
            timeout=2,
        )

        start_gate.set()

        outcomes = await asyncio.wait_for(
            asyncio.gather(
                correction_task,
                reversal_task,
            ),
            timeout=10,
        )

        assert set(outcomes) in (
            {
                "corrected",
                "reversal_conflict",
            },
            {
                "correction_conflict",
                "reversed",
            },
        )

        async with AsyncSession(engine) as db:
            assert (
                await _quantity_at(
                    db,
                    scenario.quantity_item_id,
                    location_id=(
                        scenario.location_one_id
                    ),
                )
                == 0
            )

            correction_count = await db.scalar(
                select(func.count())
                .select_from(Movement)
                .where(
                    Movement.movement_type
                    == MovementType.CORRECTION,
                    Movement.original_movement_id
                    == receipt_id,
                )
            )

            reversal_count = await db.scalar(
                select(func.count())
                .select_from(Movement)
                .where(
                    Movement.movement_type
                    == MovementType.REVERSAL,
                    Movement.original_movement_id
                    == receipt_id,
                )
            )

            assert correction_count is not None
            assert reversal_count is not None

            assert (
                correction_count
                + reversal_count
                == 1
            )

    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_warehouse_history_rejects_truncate() -> None:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    try:
        async with AsyncSession(engine) as db:
            trigger_names = set(
                (
                    await db.scalars(
                        text(
                            """
                            SELECT tgname
                            FROM pg_trigger
                            WHERE NOT tgisinternal
                              AND tgrelid IN (
                                  'movements'::regclass,
                                  'movement_lines'::regclass
                              )
                            """
                        )
                    )
                ).all()
            )

            assert {
                "trg_movements_append_only_truncate",
                "trg_movement_lines_append_only_truncate",
            } <= trigger_names

            with pytest.raises(DBAPIError) as exc_info:
                await db.execute(
                    text("TRUNCATE TABLE movements, movement_lines")
                )

            sqlstate = (
                getattr(exc_info.value.orig, "sqlstate", None)
                or getattr(exc_info.value.orig, "pgcode", None)
            )
            assert sqlstate == "55000"

            await db.rollback()
    finally:
        await engine.dispose()
@pytest.mark.asyncio
async def test_serial_reconciliation_detects_identity_drift() -> None:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            scenario = await _create_scenario(db)

            serial_number = f"RECON-{scenario.marker}"
            wwn = f"WWN-{scenario.marker}"

            receipt_id = await _create_and_commit(
                db,
                MovementCreate(
                    movement_type=MovementType.RECEIPT,
                    destination_location_id=scenario.location_one_id,
                    client_request_id=f"reconciliation-identity-{scenario.marker}",
                    lines=[
                        MovementLineCreate(
                            item_id=scenario.serial_item_id,
                            serial_number=serial_number,
                            wwn=wwn,
                        )
                    ],
                ),
                scenario,
            )

            receipt = await get_movement_record(db, receipt_id)
            unit_id = receipt.lines[0].inventory_unit_id
            assert unit_id is not None

        tampered_serial = f"TAMPERED-{scenario.marker}"
        tampered_wwn = f"TAMPERED-WWN-{scenario.marker}"

        async with AsyncSession(engine, expire_on_commit=False) as db:
            unit = await db.get(InventoryUnit, unit_id)
            assert unit is not None

            # Keep projection state and position completely valid.
            # Corrupt only the mutable identity projection.
            unit.serial_number = tampered_serial
            unit.normalized_serial_number = tampered_serial.casefold()
            unit.wwn = tampered_wwn
            unit.normalized_wwn = tampered_wwn.casefold()

            await db.commit()

        reconciliation_path = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "reconcile_inventory_projections.sql"
        )
        reconciliation_sql = reconciliation_path.read_text()

        serial_marker = "WITH latest_serial_line AS ("
        assert serial_marker in reconciliation_sql

        serial_reconciliation_sql = (
            serial_marker
            + reconciliation_sql.split(serial_marker, 1)[1]
        )

        async with AsyncSession(engine) as db:
            result = await db.execute(text(serial_reconciliation_sql))
            rows = result.mappings().all()

        matching = [
            row
            for row in rows
            if row["inventory_unit_id"] == unit_id
        ]

        assert len(matching) == 1
        drift = matching[0]

        assert drift["journal_state"] == InventoryUnitState.STORED.value
        assert drift["projection_state"] == InventoryUnitState.STORED.value
        assert drift["journal_location_id"] == scenario.location_one_id
        assert drift["projection_location_id"] == scenario.location_one_id

        assert drift["journal_serial_number"] == serial_number
        assert drift["projection_serial_number"] == tampered_serial
        assert drift["journal_wwn"] == wwn
        assert drift["projection_wwn"] == tampered_wwn
    finally:
        await engine.dispose()
