import uuid
from typing import Any

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.catalog.models import Item
from app.modules.catalog.service import create_item
from app.modules.identity.enums import UserRole
from app.modules.inventory.models import Movement, StockBalance
from app.modules.inventory.schemas import (
    LocationCreate,
    MovementCreate,
    MovementLineCreate,
    MovementReversalCreate,
)
from app.modules.inventory.service import (
    InventoryConflictError,
    create_location,
    create_movement,
    reverse_movement,
)
from app.modules.procurement.enums import (
    ProcurementEventType,
    ProcurementLineType,
    ProcurementStatus,
)
from app.modules.procurement.models import (
    ProcurementEvent,
    ProcurementRequest,
    ProcurementRevision,
    ProcurementRevisionLine,
)
from app.modules.procurement.schemas import (
    CorrectionRequest,
    DiscrepancyCreate,
    ExistingItemLineCreate,
    ExpectedStateMutation,
    ProcurementAcceptanceCreate,
    ProcurementRequestCreate,
    ProposedItemCreateAndBind,
    ProposedItemLineCreate,
    RevisionCreate,
)
from app.modules.procurement.service import (
    ProcurementConflictError,
    complete_acceptance,
    create_and_bind_line,
    create_request,
    manager_accept,
    report_discrepancy,
    return_for_correction,
    submit_revision,
    transfer_to_acceptance,
)
from tests.warehouse_helpers import actor, cable_payload

pytestmark = pytest.mark.asyncio


def settings() -> Settings:
    return Settings(app_env="test")


def existing_line(
    item_id: uuid.UUID,
    quantity: int,
) -> ExistingItemLineCreate:
    return ExistingItemLineCreate(
        line_type=ProcurementLineType.EXISTING_ITEM,
        item_id=item_id,
        quantity=quantity,
    )


def request_payload(
    manager_id: uuid.UUID,
    item_id: uuid.UUID,
    *,
    key: str,
    quantity: int = 2,
) -> ProcurementRequestCreate:
    return ProcurementRequestCreate(
        assigned_manager_user_id=manager_id,
        general_comment="Synthetic procurement",
        client_request_id=key,
        lines=[existing_line(item_id, quantity)],
    )


def expected(
    record: Any,
    key: str,
) -> ExpectedStateMutation:
    return ExpectedStateMutation(
        expected_state_version=record.request.state_version,
        expected_revision_id=record.request.current_revision_id,
        client_request_id=key,
    )


async def seed_procurement(
    db: AsyncSession,
    *,
    quantity: int = 2,
) -> tuple[Any, ...]:
    initiator, _ = await actor(db, UserRole.ADMIN)
    manager, _ = await actor(db, UserRole.MANAGER)
    senior, _ = await actor(db, UserRole.SENIOR_ENGINEER)

    item_id = await create_item(
        db,
        cable_payload(),
    )

    location = await create_location(
        db,
        LocationCreate(
            code=uuid.uuid4().hex,
            name="Procurement receiving",
            location_type="WAREHOUSE",
        ),
    )

    record = await create_request(
        db,
        request_payload(
            manager.id,
            item_id,
            key=uuid.uuid4().hex,
            quantity=quantity,
        ),
        actor_user_id=initiator.id,
        settings=settings(),
    )

    return initiator, manager, senior, item_id, location, record


async def move_to_acceptance(
    db: AsyncSession,
    record: Any,
    *,
    manager_id: uuid.UUID,
) -> Any:
    record = await manager_accept(
        db,
        record.request.id,
        expected(record, uuid.uuid4().hex),
        actor_user_id=manager_id,
    )

    record = await transfer_to_acceptance(
        db,
        record.request.id,
        expected(record, uuid.uuid4().hex),
        actor_user_id=manager_id,
        settings=settings(),
    )

    assert record.request.status == ProcurementStatus.AWAITING_ACCEPTANCE

    return record


async def completed_procurement(db: AsyncSession) -> tuple[Any, ...]:
    initiator, manager, senior, item_id, location, record = await seed_procurement(db)
    record = await move_to_acceptance(db, record, manager_id=manager.id)
    record = await complete_acceptance(
        db,
        record.request.id,
        ProcurementAcceptanceCreate(
            expected_state_version=record.request.state_version,
            expected_revision_id=record.request.current_revision_id,
            client_request_id=uuid.uuid4().hex,
            receiving_location_id=location.id,
        ),
        actor_user_id=senior.id,
        settings=settings(),
    )
    return initiator, manager, senior, item_id, location, record


async def test_completed_procurement_receipt_rejects_generic_reversal_and_correction(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    _initiator, _manager, senior, item_id, location, record = await completed_procurement(db)
    movement_id = record.request.final_movement_id
    assert movement_id is not None
    movement_count = await db.scalar(select(func.count(Movement.id)))
    stock_before = await db.scalar(
        select(StockBalance.quantity).where(
            StockBalance.item_id == item_id,
            StockBalance.location_id == location.id,
        )
    )

    with pytest.raises(InventoryConflictError) as reversal_error:
        await reverse_movement(
            db,
            movement_id,
            MovementReversalCreate(client_request_id="protected-reversal"),
            actor_user_id=senior.id,
            actor_display_name="Synthetic actor",
        )
    assert reversal_error.value.code == "procurement_movement_protected"

    with pytest.raises(InventoryConflictError) as correction_error:
        await create_movement(
            db,
            MovementCreate(
                movement_type="CORRECTION",
                source_location_id=location.id,
                original_movement_id=movement_id,
                client_request_id="protected-correction",
                lines=[MovementLineCreate(item_id=item_id, quantity=1)],
            ),
            actor_user_id=senior.id,
            actor_display_name="Synthetic actor",
        )
    assert correction_error.value.code == "procurement_movement_protected"
    assert await db.scalar(select(func.count(Movement.id))) == movement_count
    assert (
        await db.scalar(
            select(StockBalance.quantity).where(
                StockBalance.item_id == item_id,
                StockBalance.location_id == location.id,
            )
        )
        == stock_before
    )
    await db.refresh(record.request)
    assert record.request.status == ProcurementStatus.COMPLETED
    assert record.request.final_movement_id == movement_id


@pytest.mark.parametrize("movement_type", ["CORRECTION", "REVERSAL"])
async def test_procurement_receipt_db_trigger_rejects_direct_adjustment(
    warehouse_db: AsyncSession,
    movement_type: str,
) -> None:
    db = warehouse_db
    (
        _initiator,
        _manager,
        _senior,
        _item_id,
        _location,
        record,
    ) = await completed_procurement(db)

    movement_id = record.request.final_movement_id
    assert movement_id is not None

    movement_count = await db.scalar(select(func.count(Movement.id)))

    with pytest.raises(DBAPIError) as error:
        async with db.begin_nested():
            await db.execute(
                text(
                    """
                    INSERT INTO movements (
                        id,
                        line_count,
                        movement_type,
                        actor_user_id,
                        custody_user_id,
                        source_location_id,
                        destination_location_id,
                        original_movement_id,
                        client_request_id,
                        request_fingerprint,
                        actor_display_name_snapshot,
                        source_location_code_snapshot,
                        source_location_name_snapshot,
                        destination_location_code_snapshot,
                        destination_location_name_snapshot
                    )
                    SELECT
                        gen_random_uuid(),
                        line_count,
                        :movement_type,
                        actor_user_id,
                        NULL,
                        source_location_id,
                        destination_location_id,
                        id,
                        :client_request_id,
                        repeat('f', 64),
                        actor_display_name_snapshot,
                        source_location_code_snapshot,
                        source_location_name_snapshot,
                        destination_location_code_snapshot,
                        destination_location_name_snapshot
                    FROM movements
                    WHERE id = :movement_id
                    """
                ),
                {
                    "movement_type": movement_type,
                    "client_request_id": (f"direct-db-protected-{movement_type.lower()}"),
                    "movement_id": movement_id,
                },
            )

    assert getattr(error.value.orig, "sqlstate", None) == "23514"
    assert "procurement movement is protected" in str(error.value.orig)
    assert await db.scalar(select(func.count(Movement.id))) == movement_count


async def test_d4_downgrade_refuses_completed_procurement(
    migration_database: str,
) -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    from tests.migration_helpers import alembic

    alembic(migration_database, "upgrade", "head")
    engine = create_async_engine(migration_database)

    try:
        async with (
            AsyncSession(
                engine,
                expire_on_commit=False,
            ) as db,
            db.begin(),
        ):
            (
                _initiator,
                _manager,
                _senior,
                _item_id,
                _location,
                record,
            ) = await completed_procurement(db)
            assert record.request.final_movement_id is not None
    finally:
        await engine.dispose()

    output = alembic(
        migration_database,
        "downgrade",
        "c3d4e5f6a7b8",
        success=False,
    )
    assert (
        "procurement receipt protection downgrade refused: completed procurement exists"
    ) in output

    engine = create_async_engine(migration_database)
    try:
        async with engine.connect() as connection:
            assert (
                await connection.scalar(text("SELECT version_num FROM alembic_version"))
                == "d4e5f6a7b8c9"
            )
            assert (
                await connection.scalar(
                    text(
                        "SELECT count(*) "
                        "FROM procurement_requests "
                        "WHERE final_movement_id IS NOT NULL"
                    )
                )
                == 1
            )
    finally:
        await engine.dispose()


async def test_create_and_bind_proposed_item_is_atomic_and_idempotent(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    initiator, _ = await actor(db, UserRole.ADMIN)
    manager, _ = await actor(db, UserRole.MANAGER)
    senior, _ = await actor(db, UserRole.SENIOR_ENGINEER)
    proposed = cable_payload()
    record = await create_request(
        db,
        ProcurementRequestCreate(
            assigned_manager_user_id=manager.id,
            client_request_id=uuid.uuid4().hex,
            lines=[
                ProposedItemLineCreate(
                    line_type=ProcurementLineType.PROPOSED_ITEM,
                    category_key=proposed.category_key,
                    manufacturer_id=proposed.manufacturer_id,
                    name=proposed.name,
                    model=proposed.model,
                    attributes=proposed.attributes,
                    quantity=2,
                )
            ],
        ),
        actor_user_id=initiator.id,
        settings=settings(),
    )
    line_id = record.current_revision.lines[0].id
    payload = ProposedItemCreateAndBind(
        expected_state_version=record.request.state_version,
        expected_revision_id=record.request.current_revision_id,
        client_request_id=" create-and-bind ",
        line_id=line_id,
        item=proposed,
    )
    item_count = await db.scalar(select(func.count()).select_from(Item))
    saved = await create_and_bind_line(db, record.request.id, payload, actor_user_id=senior.id)
    saved_binding = saved.current_revision.lines[0].binding
    assert saved_binding is not None
    bound_id = saved_binding.item_id
    assert await db.scalar(select(func.count()).select_from(Item)) == (item_count or 0) + 1

    replay = await create_and_bind_line(db, record.request.id, payload, actor_user_id=senior.id)
    replay_binding = replay.current_revision.lines[0].binding
    assert replay_binding is not None
    assert replay_binding.item_id == bound_id
    assert await db.scalar(select(func.count()).select_from(Item)) == (item_count or 0) + 1

    conflict = ProposedItemCreateAndBind(
        expected_state_version=replay.request.state_version,
        expected_revision_id=replay.request.current_revision_id,
        client_request_id="second-create-and-bind",
        line_id=line_id,
        item=cable_payload(),
    )
    with pytest.raises(ProcurementConflictError) as error:
        await create_and_bind_line(db, record.request.id, conflict, actor_user_id=senior.id)
    assert error.value.code == "line_already_bound"
    assert await db.scalar(select(func.count()).select_from(Item)) == (item_count or 0) + 1


async def test_request_creation_is_idempotent(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    initiator, _ = await actor(db, UserRole.ADMIN)
    manager, _ = await actor(db, UserRole.MANAGER)
    item_id = await create_item(db, cable_payload())

    payload = request_payload(
        manager.id,
        item_id,
        key="create-idempotent",
        quantity=2,
    )

    first = await create_request(
        db,
        payload,
        actor_user_id=initiator.id,
        settings=settings(),
    )

    second = await create_request(
        db,
        payload,
        actor_user_id=initiator.id,
        settings=settings(),
    )

    assert first.request.id == second.request.id

    assert await db.scalar(select(func.count(ProcurementRequest.id))) == 1

    assert await db.scalar(select(func.count(ProcurementRevision.id))) == 1

    assert await db.scalar(select(func.count(ProcurementEvent.id))) == 1

    conflict = request_payload(
        manager.id,
        item_id,
        key="create-idempotent",
        quantity=3,
    )

    with pytest.raises(
        ProcurementConflictError,
    ) as exc_info:
        await create_request(
            db,
            conflict,
            actor_user_id=initiator.id,
            settings=settings(),
        )

    assert exc_info.value.code == "idempotency_payload_conflict"


async def test_revision_history_is_immutable(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db

    (
        initiator,
        manager,
        _senior,
        item_id,
        _location,
        record,
    ) = await seed_procurement(db)

    original_revision_id = record.request.current_revision_id

    record = await return_for_correction(
        db,
        record.request.id,
        CorrectionRequest(
            expected_state_version=(record.request.state_version),
            expected_revision_id=(record.request.current_revision_id),
            client_request_id="correction-1",
            comment="Please revise quantity",
        ),
        actor_user_id=manager.id,
        settings=settings(),
    )

    assert record.request.status == ProcurementStatus.AGREEMENT_REVISION_REQUIRED

    record = await submit_revision(
        db,
        record.request.id,
        RevisionCreate(
            expected_state_version=(record.request.state_version),
            expected_revision_id=(record.request.current_revision_id),
            client_request_id="revision-2",
            general_comment="Revised quantity",
            lines=[
                existing_line(
                    item_id,
                    3,
                )
            ],
        ),
        actor_user_id=initiator.id,
        settings=settings(),
    )

    assert record.request.status == ProcurementStatus.AGREEMENT_PENDING_MANAGER

    assert record.request.current_revision_id != original_revision_id

    rows = (
        await db.execute(
            select(
                ProcurementRevision.revision_number,
                ProcurementRevisionLine.quantity,
            )
            .join(
                ProcurementRevisionLine,
                ProcurementRevisionLine.revision_id == ProcurementRevision.id,
            )
            .where(ProcurementRevision.request_id == record.request.id)
            .order_by(ProcurementRevision.revision_number)
        )
    ).all()

    assert [tuple(row) for row in rows] == [(1, 2), (2, 3)]

    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(
                update(ProcurementRevisionLine)
                .where(ProcurementRevisionLine.revision_id == original_revision_id)
                .values(quantity=99)
            )

    rows_after = (
        await db.execute(
            select(
                ProcurementRevision.revision_number,
                ProcurementRevisionLine.quantity,
            )
            .join(
                ProcurementRevisionLine,
                ProcurementRevisionLine.revision_id == ProcurementRevision.id,
            )
            .where(ProcurementRevision.request_id == record.request.id)
            .order_by(ProcurementRevision.revision_number)
        )
    ).all()

    assert [tuple(row) for row in rows_after] == [(1, 2), (2, 3)]


async def test_discrepancy_does_not_change_stock_and_can_return_to_correction(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db

    (
        _initiator,
        manager,
        senior,
        _item_id,
        _location,
        record,
    ) = await seed_procurement(db)

    record = await move_to_acceptance(
        db,
        record,
        manager_id=manager.id,
    )

    movement_count_before = await db.scalar(select(func.count(Movement.id))) or 0

    stock_before = [
        tuple(row)
        for row in (
            await db.execute(
                select(
                    StockBalance.id,
                    StockBalance.item_id,
                    StockBalance.location_id,
                    StockBalance.quantity,
                    StockBalance.created_at,
                    StockBalance.updated_at,
                ).order_by(StockBalance.id)
            )
        ).all()
    ]

    discrepancy = DiscrepancyCreate(
        expected_state_version=(record.request.state_version),
        expected_revision_id=(record.request.current_revision_id),
        client_request_id="discrepancy-1",
        comment="Received quantity differs",
    )

    record = await report_discrepancy(
        db,
        record.request.id,
        discrepancy,
        comment=discrepancy.comment,
        actor_user_id=senior.id,
        settings=settings(),
    )

    assert record.request.status == ProcurementStatus.AWAITING_ACCEPTANCE

    assert await db.scalar(select(func.count(Movement.id))) == movement_count_before

    stock_after = [
        tuple(row)
        for row in (
            await db.execute(
                select(
                    StockBalance.id,
                    StockBalance.item_id,
                    StockBalance.location_id,
                    StockBalance.quantity,
                    StockBalance.created_at,
                    StockBalance.updated_at,
                ).order_by(StockBalance.id)
            )
        ).all()
    ]

    assert stock_after == stock_before

    record = await return_for_correction(
        db,
        record.request.id,
        CorrectionRequest(
            expected_state_version=(record.request.state_version),
            expected_revision_id=(record.request.current_revision_id),
            client_request_id="correction-after-discrepancy",
            comment="Official composition must be revised",
        ),
        actor_user_id=manager.id,
        settings=settings(),
    )

    assert record.request.status == ProcurementStatus.AGREEMENT_REVISION_REQUIRED


async def test_final_acceptance_creates_exactly_one_receipt_and_is_replay_safe(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db

    (
        _initiator,
        manager,
        senior,
        item_id,
        location,
        record,
    ) = await seed_procurement(
        db,
        quantity=4,
    )

    record = await move_to_acceptance(
        db,
        record,
        manager_id=manager.id,
    )

    awaiting_version = record.request.state_version

    acceptance = ProcurementAcceptanceCreate(
        expected_state_version=(record.request.state_version),
        expected_revision_id=(record.request.current_revision_id),
        client_request_id="accept-once",
        receiving_location_id=location.id,
    )

    movement_count_before = await db.scalar(select(func.count(Movement.id))) or 0

    completed = await complete_acceptance(
        db,
        record.request.id,
        acceptance,
        actor_user_id=senior.id,
        settings=settings(),
    )

    assert completed.request.status == ProcurementStatus.COMPLETED

    assert completed.request.final_movement_id is not None

    assert await db.scalar(select(func.count(Movement.id))) == movement_count_before + 1

    assert (
        await db.scalar(
            select(StockBalance.quantity).where(
                StockBalance.item_id == item_id,
                StockBalance.location_id == location.id,
            )
        )
        == 4
    )

    replay = await complete_acceptance(
        db,
        record.request.id,
        acceptance,
        actor_user_id=senior.id,
        settings=settings(),
    )

    assert replay.request.final_movement_id == completed.request.final_movement_id

    assert await db.scalar(select(func.count(Movement.id))) == movement_count_before + 1

    assert (
        await db.scalar(
            select(func.count(ProcurementEvent.id)).where(
                ProcurementEvent.request_id == record.request.id,
                ProcurementEvent.event_type == ProcurementEventType.COMPLETED,
            )
        )
        == 1
    )

    stale = ProcurementAcceptanceCreate(
        expected_state_version=awaiting_version,
        expected_revision_id=(acceptance.expected_revision_id),
        client_request_id="accept-stale-new-key",
        receiving_location_id=location.id,
    )

    with pytest.raises(
        ProcurementConflictError,
    ) as exc_info:
        await complete_acceptance(
            db,
            record.request.id,
            stale,
            actor_user_id=senior.id,
            settings=settings(),
        )

    assert exc_info.value.code == "stale_state"

    assert await db.scalar(select(func.count(Movement.id))) == movement_count_before + 1


async def test_concurrent_acceptance_and_assignment_are_serialized(
    migration_database: str,
) -> None:
    import asyncio

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.modules.procurement.schemas import AssignmentMutation
    from app.modules.procurement.service import take_ownership
    from tests.migration_helpers import alembic

    alembic(migration_database, "upgrade", "head")
    engine = create_async_engine(migration_database)

    async with (
        AsyncSession(
            engine,
            expire_on_commit=False,
        ) as db,
        db.begin(),
    ):
        (
            _initiator,
            acceptance_manager,
            senior,
            acceptance_item_id,
            acceptance_location,
            acceptance_record,
        ) = await seed_procurement(db, quantity=4)

        acceptance_record = await move_to_acceptance(
            db,
            acceptance_record,
            manager_id=acceptance_manager.id,
        )

        acceptance_request_id = acceptance_record.request.id
        acceptance_version = acceptance_record.request.state_version
        acceptance_revision_id = acceptance_record.request.current_revision_id
        acceptance_actor_id = senior.id
        acceptance_location_id = acceptance_location.id

        (
            _initiator2,
            assigned_manager,
            _senior2,
            _item2,
            _location2,
            assignment_record,
        ) = await seed_procurement(db)

        taker_a, _ = await actor(db, UserRole.MANAGER)
        taker_b, _ = await actor(db, UserRole.MANAGER)

        assignment_request_id = assignment_record.request.id
        assignment_version = assignment_record.request.state_version
        assignment_revision_id = assignment_record.request.current_revision_id
        original_manager_id = assigned_manager.id
        taker_a_id = taker_a.id
        taker_b_id = taker_b.id

    async def accept_once(key: str) -> str:
        async with AsyncSession(
            engine,
            expire_on_commit=False,
        ) as db:
            try:
                async with db.begin():
                    await complete_acceptance(
                        db,
                        acceptance_request_id,
                        ProcurementAcceptanceCreate(
                            expected_state_version=acceptance_version,
                            expected_revision_id=acceptance_revision_id,
                            client_request_id=key,
                            receiving_location_id=acceptance_location_id,
                        ),
                        actor_user_id=acceptance_actor_id,
                        settings=settings(),
                    )
            except ProcurementConflictError as error:
                return error.code
        return "ok"

    acceptance_results = await asyncio.gather(
        accept_once("concurrent-accept-a"),
        accept_once("concurrent-accept-b"),
    )

    assert sorted(acceptance_results) == ["ok", "stale_state"]

    async def take_once(
        actor_id: uuid.UUID,
        key: str,
    ) -> str:
        async with AsyncSession(
            engine,
            expire_on_commit=False,
        ) as db:
            try:
                async with db.begin():
                    await take_ownership(
                        db,
                        assignment_request_id,
                        AssignmentMutation(
                            expected_state_version=assignment_version,
                            expected_revision_id=assignment_revision_id,
                            client_request_id=key,
                            expected_assigned_manager_user_id=original_manager_id,
                        ),
                        actor_user_id=actor_id,
                        settings=settings(),
                    )
            except ProcurementConflictError as error:
                return error.code
        return "ok"

    assignment_results = await asyncio.gather(
        take_once(taker_a_id, "concurrent-take-a"),
        take_once(taker_b_id, "concurrent-take-b"),
    )

    assert sorted(assignment_results) == ["ok", "stale_state"]

    async with AsyncSession(
        engine,
        expire_on_commit=False,
    ) as db:
        acceptance_request = await db.get(
            ProcurementRequest,
            acceptance_request_id,
        )
        assignment_request = await db.get(
            ProcurementRequest,
            assignment_request_id,
        )

        assert acceptance_request is not None
        assert acceptance_request.status == ProcurementStatus.COMPLETED
        assert acceptance_request.final_movement_id is not None

        assert assignment_request is not None
        assert assignment_request.assigned_manager_user_id in {
            taker_a_id,
            taker_b_id,
        }

        assert await db.scalar(select(func.count(Movement.id))) == 1

        assert (
            await db.scalar(
                select(StockBalance.quantity).where(
                    StockBalance.item_id == acceptance_item_id,
                    StockBalance.location_id == acceptance_location_id,
                )
            )
            == 4
        )

        assert (
            await db.scalar(
                select(func.count(ProcurementEvent.id)).where(
                    ProcurementEvent.request_id == acceptance_request_id,
                    ProcurementEvent.event_type == ProcurementEventType.COMPLETED,
                )
            )
            == 1
        )

        assert (
            await db.scalar(
                select(func.count(ProcurementEvent.id)).where(
                    ProcurementEvent.request_id == assignment_request_id,
                    ProcurementEvent.event_type == ProcurementEventType.ASSIGNMENT_TAKEN,
                )
            )
            == 1
        )

    await engine.dispose()


async def test_final_acceptance_rolls_back_warehouse_and_procurement_on_late_failure(
    migration_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    import app.modules.procurement.service as procurement_service
    from tests.migration_helpers import alembic

    alembic(migration_database, "upgrade", "head")
    engine = create_async_engine(migration_database)

    async with (
        AsyncSession(
            engine,
            expire_on_commit=False,
        ) as db,
        db.begin(),
    ):
        (
            _initiator,
            manager,
            senior,
            item_id,
            location,
            record,
        ) = await seed_procurement(
            db,
            quantity=5,
        )

        record = await move_to_acceptance(
            db,
            record,
            manager_id=manager.id,
        )

        request_id = record.request.id
        expected_state_version = record.request.state_version
        expected_revision_id = record.request.current_revision_id
        actor_user_id = senior.id
        location_id = location.id

    async def fail_notifications(*args: object, **kwargs: object) -> None:
        raise RuntimeError("synthetic late acceptance failure")

    monkeypatch.setattr(
        procurement_service,
        "enqueue_procurement_notifications",
        fail_notifications,
    )

    async with AsyncSession(
        engine,
        expire_on_commit=False,
    ) as db:
        with pytest.raises(
            RuntimeError,
            match="synthetic late acceptance failure",
        ):
            async with db.begin():
                await complete_acceptance(
                    db,
                    request_id,
                    ProcurementAcceptanceCreate(
                        expected_state_version=expected_state_version,
                        expected_revision_id=expected_revision_id,
                        client_request_id="rollback-acceptance",
                        receiving_location_id=location_id,
                    ),
                    actor_user_id=actor_user_id,
                    settings=settings(),
                )

    async with AsyncSession(
        engine,
        expire_on_commit=False,
    ) as db:
        request = await db.get(
            ProcurementRequest,
            request_id,
        )

        assert request is not None
        assert request.status == ProcurementStatus.AWAITING_ACCEPTANCE
        assert request.final_movement_id is None
        assert request.completed_at is None

        assert await db.scalar(select(func.count(Movement.id))) == 0

        assert (
            await db.scalar(
                select(func.count(StockBalance.id)).where(
                    StockBalance.item_id == item_id,
                    StockBalance.location_id == location_id,
                )
            )
            == 0
        )

        assert (
            await db.scalar(
                select(func.count(ProcurementEvent.id)).where(
                    ProcurementEvent.request_id == request_id,
                    ProcurementEvent.event_type == ProcurementEventType.COMPLETED,
                )
            )
            == 0
        )

    await engine.dispose()
