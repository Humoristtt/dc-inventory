"""PostgreSQL regressions for CP-18 invariant closure c1d2e3f4a5b6."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.catalog.models import Category, CategoryAttribute, ItemAttributeValue
from app.modules.catalog.service import create_item
from app.modules.identity.enums import UserAccessStatus, UserRole
from app.modules.identity.models import User
from app.modules.inventory.enums import MovementType
from app.modules.inventory.models import Location
from app.modules.inventory.schemas import LocationCreate, MovementCreate, MovementLineCreate
from app.modules.inventory.service import create_location, create_movement
from app.modules.procurement.enums import ProcurementLineType, ProcurementStatus
from app.modules.procurement.models import ProcurementRequest
from app.modules.procurement.schemas import ExistingItemLineCreate, ProcurementRequestCreate
from app.modules.procurement.service import ProcurementRecord, create_request
from tests.warehouse_helpers import actor, cable_payload

pytestmark = pytest.mark.asyncio


async def _create_procurement(
    db: AsyncSession,
) -> tuple[User, User, uuid.UUID, Location, ProcurementRecord]:
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
            code=f"C1-{uuid.uuid4().hex}",
            name="CP18 invariant receiving",
            location_type="WAREHOUSE",
        ),
    )
    record = await create_request(
        db,
        ProcurementRequestCreate(
            assigned_manager_user_id=manager.id,
            client_request_id=f"c1-create-{uuid.uuid4().hex}",
            lines=[
                ExistingItemLineCreate(
                    line_type=ProcurementLineType.EXISTING_ITEM,
                    item_id=item_id,
                    quantity=2,
                )
            ],
        ),
        actor_user_id=initiator.id,
        settings=Settings(app_env="test"),
    )
    return senior, manager, item_id, location, record


async def test_completed_procurement_binding_cannot_be_unlinked(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    senior, _manager, item_id, location, record = await _create_procurement(db)

    receipt = await create_movement(
        db,
        MovementCreate(
            movement_type=MovementType.RECEIPT,
            destination_location_id=location.id,
            client_request_id=f"c1-receipt-{uuid.uuid4().hex}",
            lines=[
                MovementLineCreate(
                    item_id=item_id,
                    quantity=2,
                )
            ],
        ),
        actor_user_id=senior.id,
        actor_display_name="CP18 senior",
    )

    await db.execute(
        update(ProcurementRequest)
        .where(ProcurementRequest.id == record.request.id)
        .values(
            status=ProcurementStatus.COMPLETED,
            final_movement_id=receipt.record.movement.id,
            completed_at=datetime.now(UTC),
        )
    )
    await db.flush()
    await db.commit()

    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(
                update(ProcurementRequest)
                .where(ProcurementRequest.id == record.request.id)
                .values(
                    status=ProcurementStatus.PURCHASING,
                    final_movement_id=None,
                    completed_at=None,
                )
            )
            await db.flush()


async def test_procurement_event_rejects_invalid_status_value(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    senior, _manager, _item_id, _location, record = await _create_procurement(db)

    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(
                text(
                    """
                    INSERT INTO procurement_events (
                        id,
                        request_id,
                        event_type,
                        actor_user_id,
                        actor_display_name_snapshot,
                        client_request_id,
                        request_fingerprint,
                        from_status,
                        to_status
                    )
                    VALUES (
                        CAST(:id AS uuid),
                        CAST(:request_id AS uuid),
                        'LINE_BOUND',
                        CAST(:actor_user_id AS uuid),
                        'CP18 senior',
                        :client_request_id,
                        :fingerprint,
                        'INVALID_STATE',
                        'AWAITING_ACCEPTANCE'
                    )
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "request_id": str(record.request.id),
                    "actor_user_id": str(senior.id),
                    "client_request_id": f"c1-event-{uuid.uuid4().hex}",
                    "fingerprint": "a" * 64,
                },
            )


async def test_procurement_event_revision_must_belong_to_request(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    senior_a, _manager_a, _item_a, _location_a, request_a = await _create_procurement(db)
    _senior_b, _manager_b, _item_b, _location_b, request_b = await _create_procurement(db)

    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(
                text(
                    """
                    INSERT INTO procurement_events (
                        id,
                        request_id,
                        event_type,
                        actor_user_id,
                        actor_display_name_snapshot,
                        client_request_id,
                        request_fingerprint,
                        revision_id
                    )
                    VALUES (
                        CAST(:id AS uuid),
                        CAST(:request_id AS uuid),
                        'LINE_BOUND',
                        CAST(:actor_user_id AS uuid),
                        'CP18 senior',
                        :client_request_id,
                        :fingerprint,
                        CAST(:revision_id AS uuid)
                    )
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "request_id": str(request_a.request.id),
                    "actor_user_id": str(senior_a.id),
                    "client_request_id": f"c1-cross-revision-{uuid.uuid4().hex}",
                    "fingerprint": "b" * 64,
                    "revision_id": str(request_b.request.current_revision_id),
                },
            )


async def test_item_attribute_value_must_match_declared_data_type(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    item_id = await create_item(db, cable_payload())

    value_id = await db.scalar(
        select(ItemAttributeValue.id)
        .join(
            CategoryAttribute,
            CategoryAttribute.id == ItemAttributeValue.category_attribute_id,
        )
        .join(
            Category,
            Category.id == CategoryAttribute.category_id,
        )
        .where(
            ItemAttributeValue.item_id == item_id,
            Category.key == "optical_patch_cord",
            CategoryAttribute.key == "length_m",
            CategoryAttribute.data_type == "DECIMAL",
        )
    )
    assert value_id is not None

    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(
                text(
                    """
                    UPDATE item_attribute_values
                    SET decimal_value = NULL,
                        integer_value = 5
                    WHERE id = CAST(:value_id AS uuid)
                    """
                ),
                {"value_id": str(value_id)},
            )


async def test_item_attribute_enum_value_must_be_allowed(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    item_id = await create_item(db, cable_payload())
    category_id = await db.scalar(
        select(Category.id).where(
            Category.key == "optical_patch_cord"
        )
    )
    assert category_id is not None

    attribute_id = uuid.uuid4()
    await db.execute(
        text(
            """
            INSERT INTO category_attributes (
                id,
                category_id,
                key,
                label,
                data_type,
                required,
                allowed_values
            )
            VALUES (
                CAST(:id AS uuid),
                CAST(:category_id AS uuid),
                :key,
                :label,
                'ENUM',
                false,
                CAST(:allowed_values AS jsonb)
            )
            """
        ),
        {
            "id": str(attribute_id),
            "category_id": str(category_id),
            "key": f"cp18_enum_{uuid.uuid4().hex}",
            "label": "CP18 enum",
            "allowed_values": '["A", "B"]',
        },
    )
    await db.flush()

    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(
                text(
                    """
                    INSERT INTO item_attribute_values (
                        id,
                        item_id,
                        category_attribute_id,
                        category_id,
                        enum_value
                    )
                    VALUES (
                        CAST(:id AS uuid),
                        CAST(:item_id AS uuid),
                        CAST(:attribute_id AS uuid),
                        CAST(:category_id AS uuid),
                        'C'
                    )
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "item_id": str(item_id),
                    "attribute_id": str(attribute_id),
                    "category_id": str(category_id),
                },
            )


async def test_category_attribute_type_change_rejects_existing_values(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    item_id = await create_item(db, cable_payload())

    attribute_id = await db.scalar(
        select(CategoryAttribute.id)
        .join(
            Category,
            Category.id == CategoryAttribute.category_id,
        )
        .where(
            Category.key == "optical_patch_cord",
            CategoryAttribute.key == "connector_a",
        )
    )
    assert attribute_id is not None

    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(
                text(
                    """
                    UPDATE category_attributes
                    SET data_type = 'ENUM',
                        allowed_values = '["OTHER"]'::jsonb
                    WHERE id = CAST(:attribute_id AS uuid)
                    """
                ),
                {"attribute_id": str(attribute_id)},
            )
            await db.execute(
                text("SET CONSTRAINTS ALL IMMEDIATE")
            )
