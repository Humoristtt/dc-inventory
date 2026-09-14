from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
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
from app.modules.telegram_bot.service import (
    InvalidAccessCallbackError,
    access_callback_data,
    apply_access_decision,
    create_access_decision_callbacks,
)
from tests.warehouse_helpers import actor

pytestmark = pytest.mark.asyncio


def settings() -> Settings:
    return Settings(app_env="test")


async def _telegram_user_id(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> int:
    telegram_user_id = await db.scalar(
        select(TelegramIdentity.telegram_user_id).where(TelegramIdentity.user_id == user_id)
    )
    assert telegram_user_id is not None
    return telegram_user_id


async def test_cp03_owner_can_approve_pending_admin_via_telegram(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    now = datetime(2026, 9, 15, 1, 0, tzinfo=UTC)

    owner, _ = await actor(
        db,
        UserRole.OWNER,
        UserAccessStatus.APPROVED,
    )
    target, _ = await actor(
        db,
        UserRole.ADMIN,
        UserAccessStatus.PENDING,
    )

    request = AccessRequest(
        user_id=target.id,
        status=AccessRequestStatus.PENDING,
    )
    db.add(request)
    await db.flush()

    approve, _reject = await create_access_decision_callbacks(
        db,
        request.id,
    )

    result = await apply_access_decision(
        db,
        callback_data=access_callback_data(approve.token),
        callback_query_id=f"cp03-owner-{uuid.uuid4().hex}",
        actor_telegram_user_id=await _telegram_user_id(
            db,
            owner.id,
        ),
        message_chat_id=None,
        message_id=None,
        settings=settings(),
        now=now,
    )

    assert result.changed is True
    assert result.status == AccessRequestStatus.APPROVED

    await db.flush()
    await db.refresh(request)
    await db.refresh(target)

    assert request.status == AccessRequestStatus.APPROVED
    assert request.decided_by_user_id == owner.id
    assert target.access_status == UserAccessStatus.APPROVED
    assert target.approved_by_user_id == owner.id

    events = list(
        (
            await db.scalars(
                select(UserAccessEvent).where(UserAccessEvent.target_user_id == target.id)
            )
        ).all()
    )

    assert len(events) == 1
    assert events[0].actor_user_id == owner.id
    assert events[0].before_access_status == UserAccessStatus.PENDING
    assert events[0].after_access_status == UserAccessStatus.APPROVED


async def test_cp03_expired_privileged_callback_is_rejected_without_mutation(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    now = datetime(2026, 9, 15, 1, 0, tzinfo=UTC)

    admin, _ = await actor(
        db,
        UserRole.ADMIN,
        UserAccessStatus.APPROVED,
    )
    target, _ = await actor(
        db,
        UserRole.ENGINEER,
        UserAccessStatus.PENDING,
    )

    request = AccessRequest(
        user_id=target.id,
        status=AccessRequestStatus.PENDING,
    )
    db.add(request)
    await db.flush()

    approve, _reject = await create_access_decision_callbacks(
        db,
        request.id,
    )

    # Deliberately far older than any reasonable privileged-action TTL.
    # CP-03 will define the exact policy in implementation.
    approve.created_at = now - timedelta(days=2)
    await db.flush()

    with pytest.raises(
        InvalidAccessCallbackError,
        match="expired",
    ):
        await apply_access_decision(
            db,
            callback_data=access_callback_data(approve.token),
            callback_query_id=f"cp03-expired-{uuid.uuid4().hex}",
            actor_telegram_user_id=await _telegram_user_id(
                db,
                admin.id,
            ),
            message_chat_id=None,
            message_id=None,
            settings=settings(),
            now=now,
        )

    await db.refresh(request)
    await db.refresh(target)

    assert request.status == AccessRequestStatus.PENDING
    assert request.decided_at is None
    assert request.decided_by_user_id is None

    assert target.access_status == UserAccessStatus.PENDING
    assert target.approved_at is None
    assert target.approved_by_user_id is None

    event_count = await db.scalar(
        select(func.count(UserAccessEvent.id)).where(UserAccessEvent.target_user_id == target.id)
    )

    assert int(event_count or 0) == 0
