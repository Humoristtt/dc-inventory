from __future__ import annotations

import asyncio
import uuid
from contextlib import suppress
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
)

from app.core.config import Settings
from app.modules.catalog.enums import ItemStatus
from app.modules.catalog.models import Item
from app.modules.catalog.service import (
    create_item,
    load_attributes_for_items,
    set_item_archived,
)
from app.modules.identity.admin_service import (
    AdminUserError,
    update_user_role,
)
from app.modules.identity.enums import (
    UserAccessStatus,
    UserRole,
)
from app.modules.identity.models import User
from app.modules.identity.policy import (
    Capability,
    has_capability,
)
from app.modules.notifications.models import NotificationOutbox
from app.modules.notifications.service import (
    notification_dedupe_key,
)
from app.modules.procurement import service as procurement_service
from app.modules.procurement.enums import (
    ProcurementLineType,
    ProcurementStatus,
)
from app.modules.procurement.models import ProcurementRequest
from app.modules.procurement.notifications import (
    enqueue_procurement_notifications,
)
from app.modules.procurement.schemas import (
    CorrectionRequest,
    ExistingItemLineCreate,
    ProcurementRequestCreate,
)
from app.modules.procurement.service import (
    ProcurementRecord,
    create_request,
    return_for_correction,
)
from tests.warehouse_helpers import actor, cable_payload

pytestmark = pytest.mark.asyncio


def settings() -> Settings:
    return Settings(app_env="test")


async def create_existing_request(
    db: AsyncSession,
    *,
    initiator_role: UserRole = UserRole.ADMIN,
) -> tuple[User, User, uuid.UUID, ProcurementRecord]:
    initiator, _ = await actor(
        db,
        initiator_role,
        UserAccessStatus.APPROVED,
    )
    manager, _ = await actor(
        db,
        UserRole.MANAGER,
        UserAccessStatus.APPROVED,
    )
    item_id = await create_item(
        db,
        cable_payload(),
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
                    quantity=1,
                )
            ],
        ),
        actor_user_id=initiator.id,
        settings=settings(),
    )

    return initiator, manager, item_id, record


async def test_cp01_procurement_notification_requires_current_read_capability(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db

    _initiator, _manager, _item_id, record = await create_existing_request(db)

    engineer, _ = await actor(
        db,
        UserRole.ENGINEER,
        UserAccessStatus.APPROVED,
    )

    assert not has_capability(
        engineer.role,
        Capability.PROCUREMENT_READ,
    )

    event_id = uuid.uuid4()
    dedupe_key = notification_dedupe_key(
        "procurement",
        event_id,
        engineer.id,
        "telegram",
    )

    await enqueue_procurement_notifications(
        db,
        settings=settings(),
        request_id=record.request.id,
        request_number=record.request.request_number,
        event_id=event_id,
        action="CP01 capability regression",
        lines=record.current_revision.lines,
        recipient_user_ids={engineer.id},
    )

    leaked = await db.scalar(
        select(NotificationOutbox).where(NotificationOutbox.dedupe_key == dedupe_key)
    )

    assert leaked is None


async def test_cp01_revision_required_initiator_cannot_be_left_without_create_capability(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db

    owner, _ = await actor(
        db,
        UserRole.OWNER,
        UserAccessStatus.APPROVED,
    )

    initiator, manager, _item_id, record = await create_existing_request(
        db,
        initiator_role=UserRole.ADMIN,
    )

    record = await return_for_correction(
        db,
        record.request.id,
        CorrectionRequest(
            expected_state_version=record.request.state_version,
            expected_revision_id=record.request.current_revision_id,
            client_request_id=(f"cp01-correction-{uuid.uuid4().hex}"),
            comment="CP01 revision required",
        ),
        actor_user_id=manager.id,
        settings=settings(),
    )

    assert record.request.status == ProcurementStatus.AGREEMENT_REVISION_REQUIRED

    with suppress(AdminUserError):
        await update_user_role(
            db,
            actor_user_id=owner.id,
            target_user_id=initiator.id,
            role=UserRole.ENGINEER,
            recovery_telegram_user_id=None,
        )

    request = await db.get(
        ProcurementRequest,
        record.request.id,
    )
    assert request is not None

    effective_initiator = await db.get(
        User,
        request.initiator_user_id,
    )
    assert effective_initiator is not None

    assert effective_initiator.access_status == UserAccessStatus.APPROVED
    assert has_capability(
        effective_initiator.role,
        Capability.PROCUREMENT_CREATE,
    )


async def test_cp01_archive_and_procurement_snapshot_are_serialized(
    migration_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.migration_helpers import alembic

    alembic(
        migration_database,
        "upgrade",
        "head",
    )

    engine = create_async_engine(
        migration_database,
        pool_pre_ping=True,
    )

    try:
        async with AsyncSession(
            engine,
            expire_on_commit=False,
        ) as setup_db:
            async with setup_db.begin():
                initiator, _ = await actor(
                    setup_db,
                    UserRole.ADMIN,
                    UserAccessStatus.APPROVED,
                )
                manager, _ = await actor(
                    setup_db,
                    UserRole.MANAGER,
                    UserAccessStatus.APPROVED,
                )
                item_id = await create_item(
                    setup_db,
                    cable_payload(),
                )

            initiator_id = initiator.id
            manager_id = manager.id

        snapshot_loaded = asyncio.Event()
        allow_creation_to_continue = asyncio.Event()

        original_load_attributes_for_items = load_attributes_for_items

        async def paused_load_attributes_for_items(
            db: AsyncSession,
            candidate_item_ids: list[uuid.UUID],
        ) -> dict[uuid.UUID, dict[str, str | int | Decimal | bool]]:
            attributes = await original_load_attributes_for_items(
                db,
                candidate_item_ids,
            )

            if item_id in candidate_item_ids:
                snapshot_loaded.set()
                await allow_creation_to_continue.wait()

            return attributes

        monkeypatch.setattr(
            procurement_service,
            "load_attributes_for_items",
            paused_load_attributes_for_items,
        )

        async def create_procurement() -> uuid.UUID:
            async with AsyncSession(
                engine,
                expire_on_commit=False,
            ) as create_db:
                async with create_db.begin():
                    created = await create_request(
                        create_db,
                        ProcurementRequestCreate(
                            assigned_manager_user_id=manager_id,
                            client_request_id=(f"cp01-race-{uuid.uuid4().hex}"),
                            lines=[
                                ExistingItemLineCreate(
                                    line_type=(ProcurementLineType.EXISTING_ITEM),
                                    item_id=item_id,
                                    quantity=1,
                                )
                            ],
                        ),
                        actor_user_id=initiator_id,
                        settings=settings(),
                    )

                return created.request.id

        async def archive_item() -> None:
            async with (
                AsyncSession(
                    engine,
                    expire_on_commit=False,
                ) as archive_db,
                archive_db.begin(),
            ):
                await set_item_archived(
                    archive_db,
                    item_id,
                    archived=True,
                )

        create_task = asyncio.create_task(create_procurement())

        await asyncio.wait_for(
            snapshot_loaded.wait(),
            timeout=5,
        )

        archive_task = asyncio.create_task(archive_item())

        # A correct snapshot path must hold a row-level serialization
        # lock here. The archive transaction therefore cannot commit
        # while request creation is paused on the same Item.
        await asyncio.sleep(0.25)

        archive_completed_before_creation = archive_task.done()

        allow_creation_to_continue.set()

        await create_task
        await archive_task

        assert not archive_completed_before_creation

        async with AsyncSession(engine) as verify_db:
            item = await verify_db.get(
                Item,
                item_id,
            )
            assert item is not None
            assert item.status == ItemStatus.ARCHIVED

    finally:
        await engine.dispose()
