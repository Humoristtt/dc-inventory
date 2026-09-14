from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.catalog.models import Item
from app.modules.catalog.schemas import ItemPatch
from app.modules.catalog.service import create_item, update_item
from app.modules.identity.enums import (
    AccessRequestStatus,
    UserAccessStatus,
    UserRole,
)
from app.modules.identity.models import (
    AccessRequest,
    TelegramIdentity,
)
from app.modules.inventory.enums import MovementType
from app.modules.inventory.models import Movement
from app.modules.inventory.schemas import (
    LocationCreate,
    MovementCreate,
    MovementLineCreate,
)
from app.modules.inventory.service import (
    create_location,
    create_movement,
)
from app.modules.procurement.enums import (
    ProcurementLineType,
    ProcurementStatus,
)
from app.modules.procurement.models import (
    ProcurementRequest,
    ProcurementRevisionLine,
)
from app.modules.procurement.schemas import (
    ExistingItemLineCreate,
    ExpectedStateMutation,
    LineBindingCreate,
    ProcurementAcceptanceCreate,
    ProcurementRequestCreate,
    ProposedItemCreateAndBind,
    ProposedItemLineCreate,
)
from app.modules.procurement.service import (
    ProcurementConflictError,
    bind_line,
    complete_acceptance,
    create_and_bind_line,
    create_request,
    manager_accept,
    transfer_to_acceptance,
)
from app.modules.telegram_bot.service import (
    TelegramAccessManagerAuthorizationError,
    access_callback_data,
    apply_access_decision,
    create_access_decision_callbacks,
)
from tests.warehouse_helpers import actor, cable_payload

pytestmark = pytest.mark.asyncio


def settings() -> Settings:
    return Settings(app_env="test")


def expected(record: object, key: str) -> ExpectedStateMutation:
    request = record.request  # type: ignore[attr-defined]
    return ExpectedStateMutation(
        expected_state_version=request.state_version,
        expected_revision_id=request.current_revision_id,
        client_request_id=key,
    )


async def create_existing_procurement(
    db: AsyncSession,
    *,
    quantity: int = 2,
) -> tuple[object, object, object, uuid.UUID, object, object]:
    initiator, _ = await actor(
        db,
        UserRole.ADMIN,
        UserAccessStatus.APPROVED,
    )
    manager, _ = await actor(
        db,
        UserRole.MANAGER,
        UserAccessStatus.APPROVED,
    )
    senior, _ = await actor(
        db,
        UserRole.SENIOR_ENGINEER,
        UserAccessStatus.APPROVED,
    )

    item_id = await create_item(db, cable_payload())

    location = await create_location(
        db,
        LocationCreate(
            code=f"CP01-{uuid.uuid4().hex}",
            name="CP01 receiving",
            location_type="WAREHOUSE",
        ),
    )

    record = await create_request(
        db,
        ProcurementRequestCreate(
            assigned_manager_user_id=manager.id,
            client_request_id=f"cp01-create-{uuid.uuid4().hex}",
            lines=[
                ExistingItemLineCreate(
                    line_type=ProcurementLineType.EXISTING_ITEM,
                    item_id=item_id,
                    quantity=quantity,
                )
            ],
        ),
        actor_user_id=initiator.id,
        settings=settings(),
    )

    return (
        initiator,
        manager,
        senior,
        item_id,
        location,
        record,
    )


async def create_proposed_procurement(
    db: AsyncSession,
) -> tuple[object, object, object, object, object]:
    initiator, _ = await actor(
        db,
        UserRole.ADMIN,
        UserAccessStatus.APPROVED,
    )
    manager, _ = await actor(
        db,
        UserRole.MANAGER,
        UserAccessStatus.APPROVED,
    )
    senior, _ = await actor(
        db,
        UserRole.SENIOR_ENGINEER,
        UserAccessStatus.APPROVED,
    )

    approved_item = cable_payload()

    record = await create_request(
        db,
        ProcurementRequestCreate(
            assigned_manager_user_id=manager.id,
            client_request_id=f"cp01-proposed-{uuid.uuid4().hex}",
            lines=[
                ProposedItemLineCreate(
                    line_type=ProcurementLineType.PROPOSED_ITEM,
                    category_key=approved_item.category_key,
                    manufacturer_id=approved_item.manufacturer_id,
                    name=approved_item.name,
                    model=approved_item.model,
                    attributes=approved_item.attributes,
                    quantity=2,
                )
            ],
        ),
        actor_user_id=initiator.id,
        settings=settings(),
    )

    return initiator, manager, senior, approved_item, record


async def move_to_acceptance(
    db: AsyncSession,
    record: object,
    *,
    manager_id: uuid.UUID,
) -> object:
    record = await manager_accept(
        db,
        record.request.id,  # type: ignore[attr-defined]
        expected(
            record,
            f"cp01-manager-accept-{uuid.uuid4().hex}",
        ),
        actor_user_id=manager_id,
    )

    record = await transfer_to_acceptance(
        db,
        record.request.id,  # type: ignore[attr-defined]
        expected(
            record,
            f"cp01-transfer-{uuid.uuid4().hex}",
        ),
        actor_user_id=manager_id,
        settings=settings(),
    )

    assert (
        record.request.status  # type: ignore[attr-defined]
        == ProcurementStatus.AWAITING_ACCEPTANCE
    )

    return record


async def test_cp01_admin_cannot_approve_pending_admin_via_telegram(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db

    admin, _ = await actor(
        db,
        UserRole.ADMIN,
        UserAccessStatus.APPROVED,
    )
    target, _ = await actor(
        db,
        UserRole.ADMIN,
        UserAccessStatus.PENDING,
    )

    admin_identity = await db.scalar(
        select(TelegramIdentity).where(TelegramIdentity.user_id == admin.id)
    )
    assert admin_identity is not None

    access_request = AccessRequest(
        user_id=target.id,
        status=AccessRequestStatus.PENDING,
    )
    db.add(access_request)
    await db.flush()

    approve, _reject = await create_access_decision_callbacks(
        db,
        access_request.id,
    )

    with pytest.raises(TelegramAccessManagerAuthorizationError):
        await apply_access_decision(
            db,
            callback_data=access_callback_data(approve.token),
            callback_query_id=f"cp01-{uuid.uuid4().hex}",
            actor_telegram_user_id=(admin_identity.telegram_user_id),
            message_chat_id=None,
            message_id=None,
            settings=settings(),
        )

    await db.refresh(target)
    assert target.access_status == UserAccessStatus.PENDING


async def test_cp01_proposed_line_rejects_mismatched_existing_item_binding(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db

    (
        _initiator,
        _manager,
        senior,
        approved_item,
        record,
    ) = await create_proposed_procurement(db)

    wrong_item = approved_item.model_copy(update={"model": "CP01-WRONG-MODEL"})
    wrong_item_id = await create_item(db, wrong_item)

    line = record.current_revision.lines[0]

    with pytest.raises(ProcurementConflictError):
        await bind_line(
            db,
            record.request.id,
            LineBindingCreate(
                expected_state_version=(record.request.state_version),
                expected_revision_id=(record.request.current_revision_id),
                client_request_id=(f"cp01-bind-{uuid.uuid4().hex}"),
                item_id=wrong_item_id,
                line_id=line.id,
            ),
            actor_user_id=senior.id,
        )


async def test_cp01_create_and_bind_rejects_payload_mismatching_approved_snapshot(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db

    (
        _initiator,
        _manager,
        senior,
        approved_item,
        record,
    ) = await create_proposed_procurement(db)

    wrong_item = approved_item.model_copy(update={"model": "CP01-CREATE-WRONG-MODEL"})

    line = record.current_revision.lines[0]

    item_count_before = int(await db.scalar(select(func.count()).select_from(Item)) or 0)

    with pytest.raises(ProcurementConflictError):
        await create_and_bind_line(
            db,
            record.request.id,
            ProposedItemCreateAndBind(
                expected_state_version=(record.request.state_version),
                expected_revision_id=(record.request.current_revision_id),
                client_request_id=(f"cp01-create-bind-{uuid.uuid4().hex}"),
                line_id=line.id,
                item=wrong_item,
            ),
            actor_user_id=senior.id,
        )

    assert int(await db.scalar(select(func.count()).select_from(Item)) or 0) == item_count_before


async def test_cp01_existing_item_identity_change_blocks_final_acceptance(
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
    ) = await create_existing_procurement(db)

    record = await move_to_acceptance(
        db,
        record,
        manager_id=manager.id,
    )

    await update_item(
        db,
        item_id,
        ItemPatch(model="CP01-MUTATED-AFTER-APPROVAL"),
        fields_set={"model"},
    )

    movement_count_before = int(await db.scalar(select(func.count(Movement.id))) or 0)

    with pytest.raises(ProcurementConflictError):
        await complete_acceptance(
            db,
            record.request.id,
            ProcurementAcceptanceCreate(
                expected_state_version=(record.request.state_version),
                expected_revision_id=(record.request.current_revision_id),
                client_request_id=(f"cp01-accept-{uuid.uuid4().hex}"),
                receiving_location_id=location.id,
            ),
            actor_user_id=senior.id,
            settings=settings(),
        )

    assert int(await db.scalar(select(func.count(Movement.id))) or 0) == movement_count_before


async def test_cp01_committed_revision_rejects_late_line_insert(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db

    (
        _initiator,
        _manager,
        _senior,
        item_id,
        _location,
        record,
    ) = await create_existing_procurement(db)

    original_line = record.current_revision.lines[0]
    revision_id = record.request.current_revision_id

    # This closes the normal service operation. A revision that is already
    # published/current must no longer accept extra lines afterwards.
    await db.commit()

    late_line = ProcurementRevisionLine(
        id=uuid.uuid4(),
        revision_id=revision_id,
        line_no=2,
        line_type=ProcurementLineType.EXISTING_ITEM,
        catalog_item_id=item_id,
        display_snapshot=dict(original_line.display_snapshot),
        quantity=1,
    )

    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            db.add(late_line)
            await db.flush()


async def test_cp01_adjusted_movement_cannot_later_become_final_procurement_receipt(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db

    (
        _initiator,
        _manager,
        senior,
        item_id,
        location,
        record,
    ) = await create_existing_procurement(
        db,
        quantity=2,
    )

    receipt = await create_movement(
        db,
        MovementCreate(
            movement_type=MovementType.RECEIPT,
            destination_location_id=location.id,
            client_request_id=(f"cp01-independent-receipt-{uuid.uuid4().hex}"),
            lines=[
                MovementLineCreate(
                    item_id=item_id,
                    quantity=2,
                )
            ],
        ),
        actor_user_id=senior.id,
        actor_display_name="CP01 senior",
    )

    receipt_id = receipt.record.movement.id

    correction = await create_movement(
        db,
        MovementCreate(
            movement_type=MovementType.CORRECTION,
            source_location_id=location.id,
            original_movement_id=receipt_id,
            client_request_id=(f"cp01-prebind-correction-{uuid.uuid4().hex}"),
            lines=[
                MovementLineCreate(
                    item_id=item_id,
                    quantity=1,
                )
            ],
        ),
        actor_user_id=senior.id,
        actor_display_name="CP01 senior",
    )

    assert correction.record.movement.original_movement_id == receipt_id

    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(
                update(ProcurementRequest)
                .where(ProcurementRequest.id == record.request.id)
                .values(
                    status=ProcurementStatus.COMPLETED,
                    final_movement_id=receipt_id,
                    completed_at=datetime.now(UTC),
                )
            )
            await db.flush()
