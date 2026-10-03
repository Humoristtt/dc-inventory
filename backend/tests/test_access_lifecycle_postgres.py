import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.access.service import create_or_get_access_request
from app.modules.auth.service import reconcile_recovery_owner
from app.modules.identity.admin_service import (
    decide_pending_access_request,
)
from app.modules.identity.enums import (
    AccessRequestStatus,
    UserAccessStatus,
    UserRole,
)
from app.modules.identity.models import (
    AccessRequest,
    TelegramIdentity,
    UserAccessEvent,
)
from tests.warehouse_helpers import actor

pytestmark = pytest.mark.asyncio


async def test_rejected_user_rerequest_is_audited(
    warehouse_db: AsyncSession,
) -> None:
    user, _ = await actor(
        warehouse_db,
        UserRole.ENGINEER,
        UserAccessStatus.REJECTED,
    )

    result = await create_or_get_access_request(
        warehouse_db,
        user.id,
    )

    assert result.access_status == UserAccessStatus.PENDING
    assert result.request.status == AccessRequestStatus.PENDING

    events = list(
        (
            await warehouse_db.scalars(
                select(UserAccessEvent)
                .where(
                    UserAccessEvent.target_user_id == user.id
                )
            )
        ).all()
    )

    assert len(events) == 1
    assert events[0].actor_user_id == user.id
    assert (
        events[0].before_access_status
        == UserAccessStatus.REJECTED
    )
    assert (
        events[0].after_access_status
        == UserAccessStatus.PENDING
    )


async def test_admin_pending_decision_is_audited(
    warehouse_db: AsyncSession,
) -> None:
    admin, _ = await actor(
        warehouse_db,
        UserRole.ADMIN,
        UserAccessStatus.APPROVED,
    )
    pending, _ = await actor(
        warehouse_db,
        UserRole.ENGINEER,
        UserAccessStatus.PENDING,
    )

    access_request = AccessRequest(
        user_id=pending.id,
        status=AccessRequestStatus.PENDING,
    )
    warehouse_db.add(access_request)
    await warehouse_db.flush()

    _, decided_request, event = (
        await decide_pending_access_request(
            warehouse_db,
            actor_user_id=admin.id,
            target_user_id=pending.id,
            decision=AccessRequestStatus.APPROVED,
            recovery_telegram_user_id=None,
        )
    )

    assert decided_request.status == AccessRequestStatus.APPROVED
    assert pending.access_status == UserAccessStatus.APPROVED
    assert pending.approved_by_user_id == admin.id
    assert event.actor_user_id == admin.id
    assert event.target_user_id == pending.id
    assert (
        event.before_access_status
        == UserAccessStatus.PENDING
    )
    assert (
        event.after_access_status
        == UserAccessStatus.APPROVED
    )


async def test_recovery_owner_access_repair_is_audited(
    warehouse_db: AsyncSession,
) -> None:
    user, _ = await actor(
        warehouse_db,
        UserRole.ADMIN,
        UserAccessStatus.BLOCKED,
    )

    identity = await warehouse_db.scalar(
        select(TelegramIdentity).where(
            TelegramIdentity.user_id == user.id
        )
    )
    assert identity is not None

    changed = await reconcile_recovery_owner(
        warehouse_db,
        user=user,
        identity=identity,
        settings=Settings(
            app_env="test",
            admin_telegram_user_id=identity.telegram_user_id,
        ),
    )

    assert changed
    assert user.role == UserRole.OWNER
    assert user.access_status == UserAccessStatus.APPROVED

    event = await warehouse_db.scalar(
        select(UserAccessEvent).where(
            UserAccessEvent.target_user_id == user.id,
            UserAccessEvent.before_access_status
            == UserAccessStatus.BLOCKED,
            UserAccessEvent.after_access_status
            == UserAccessStatus.APPROVED,
        )
    )

    assert event is not None
    assert event.actor_user_id == user.id
