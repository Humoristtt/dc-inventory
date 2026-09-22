"""Регрессии для PostgreSQL-инвариантов миграции e5f6a7b8c9d0."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.catalog.service import create_item
from app.modules.identity.enums import UserAccessStatus, UserRole
from app.modules.identity.models import User
from app.modules.inventory.enums import MovementType
from app.modules.inventory.models import Location
from app.modules.inventory.schemas import LocationCreate, MovementCreate, MovementLineCreate
from app.modules.inventory.service import create_location, create_movement
from app.modules.procurement.enums import ProcurementLineType, ProcurementStatus
from app.modules.procurement.models import ProcurementRequest, ProcurementRevisionLine
from app.modules.procurement.schemas import ExistingItemLineCreate, ProcurementRequestCreate
from app.modules.procurement.service import ProcurementRecord, create_request
from tests.warehouse_helpers import actor, cable_payload

pytestmark = pytest.mark.asyncio


async def _create_procurement(
    db: AsyncSession,
) -> tuple[User, uuid.UUID, Location, ProcurementRecord]:
    initiator, _ = await actor(db, UserRole.ADMIN, UserAccessStatus.APPROVED)
    manager, _ = await actor(db, UserRole.MANAGER, UserAccessStatus.APPROVED)
    senior, _ = await actor(db, UserRole.SENIOR_ENGINEER, UserAccessStatus.APPROVED)
    item_id = await create_item(db, cable_payload())
    location = await create_location(
        db,
        LocationCreate(
            code=f"E5-{uuid.uuid4().hex}",
            name="E5 test receiving",
            location_type="WAREHOUSE",
        ),
    )
    record = await create_request(
        db,
        ProcurementRequestCreate(
            assigned_manager_user_id=manager.id,
            client_request_id=f"e5-create-{uuid.uuid4().hex}",
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
    return senior, item_id, location, record


async def test_e5_published_revision_rejects_late_line_insert(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    _senior, item_id, _location, record = await _create_procurement(db)
    original = record.current_revision.lines[0]
    revision_id = record.request.current_revision_id

    # Фиксируем публикацию: проверяем именно следующую транзакцию.
    await db.commit()

    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            db.add(
                ProcurementRevisionLine(
                    id=uuid.uuid4(),
                    revision_id=revision_id,
                    line_no=2,
                    line_type=ProcurementLineType.EXISTING_ITEM,
                    catalog_item_id=item_id,
                    display_snapshot=dict(original.display_snapshot),
                    quantity=1,
                )
            )
            await db.flush()


async def test_e5_adjusted_receipt_cannot_be_bound_to_procurement(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    senior, item_id, location, record = await _create_procurement(db)

    receipt = await create_movement(
        db,
        MovementCreate(
            movement_type=MovementType.RECEIPT,
            destination_location_id=location.id,
            client_request_id=f"e5-receipt-{uuid.uuid4().hex}",
            lines=[MovementLineCreate(item_id=item_id, quantity=2)],
        ),
        actor_user_id=senior.id,
        actor_display_name="E5 senior",
    )
    receipt_id = receipt.record.movement.id

    adjustment = await create_movement(
        db,
        MovementCreate(
            movement_type=MovementType.CORRECTION,
            source_location_id=location.id,
            original_movement_id=receipt_id,
            client_request_id=f"e5-correction-{uuid.uuid4().hex}",
            lines=[MovementLineCreate(item_id=item_id, quantity=1)],
        ),
        actor_user_id=senior.id,
        actor_display_name="E5 senior",
    )
    assert adjustment.record.movement.original_movement_id == receipt_id

    # Имеющая коррекцию складская проводка не может стать финальным receipt.
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
