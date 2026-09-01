import asyncio
import os
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import Settings
from app.modules.identity.enums import AccessRequestStatus, UserAccessStatus, UserRole
from app.modules.identity.models import AccessRequest, TelegramIdentity, User
from app.modules.notifications.models import NotificationOutbox
from app.modules.notifications.service import (
    claim_notification_batch,
    enqueue_telegram_call,
    notification_dedupe_key,
)
from app.modules.telegram_bot.models import AccessDecisionCallback, TelegramUpdate
from app.modules.telegram_bot.service import (
    TelegramAdminAuthorizationError,
    access_callback_data,
    apply_access_decision,
    create_access_decision_callbacks,
    register_telegram_update,
)

DATABASE_URL = os.environ["DATABASE_URL"]
POSTGRES_INTEGRATION_ENABLED = os.getenv("RUN_POSTGRES_INTEGRATION") == "1"

pytestmark = pytest.mark.skipif(
    not POSTGRES_INTEGRATION_ENABLED,
    reason="set RUN_POSTGRES_INTEGRATION=1 against a migrated PostgreSQL test DB",
)

SETTINGS = Settings(
    database_url=DATABASE_URL,
    admin_telegram_user_id=700000001,
)


async def cleanup_users(db: AsyncSession, user_ids: list[uuid.UUID]) -> None:
    request_ids = list(
        (
            await db.scalars(
                select(AccessRequest.id).where(AccessRequest.user_id.in_(user_ids))
            )
        ).all()
    )
    if request_ids:
        await db.execute(
            delete(AccessDecisionCallback).where(
                AccessDecisionCallback.access_request_id.in_(request_ids)
            )
        )
        await db.execute(delete(AccessRequest).where(AccessRequest.id.in_(request_ids)))
    await db.execute(
        delete(TelegramIdentity).where(TelegramIdentity.user_id.in_(user_ids))
    )
    await db.execute(delete(User).where(User.id.in_(user_ids)))
    await db.commit()


@pytest.mark.asyncio
async def test_approve_callback_is_authorized_atomic_and_idempotent() -> None:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    admin_id = uuid.uuid4()
    target_id = uuid.uuid4()
    request_id = uuid.uuid4()
    now = datetime(2026, 9, 1, 3, 0, tzinfo=UTC)

    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            admin = User(
                id=admin_id,
                role=UserRole.ADMIN,
                access_status=UserAccessStatus.APPROVED,
                approved_at=now,
            )
            target = User(id=target_id, access_status=UserAccessStatus.PENDING)
            request = AccessRequest(
                id=request_id,
                user=target,
                user_id=target_id,
                status=AccessRequestStatus.PENDING,
            )
            db.add_all(
                [
                    admin,
                    target,
                    TelegramIdentity(
                        user=admin,
                        user_id=admin_id,
                        telegram_user_id=700000001,
                        first_name="Admin",
                    ),
                    TelegramIdentity(
                        user=target,
                        user_id=target_id,
                        telegram_user_id=700000002,
                        first_name="Target",
                    ),
                    request,
                ]
            )
            await db.flush()
            approve, _ = await create_access_decision_callbacks(db, request_id)
            callback_data = access_callback_data(approve.token)
            await db.commit()

            first = await apply_access_decision(
                db,
                callback_data=callback_data,
                callback_query_id="callback-1",
                actor_telegram_user_id=700000001,
                message_chat_id=700000001,
                message_id=55,
                settings=SETTINGS,
                now=now,
            )
            await db.commit()
            assert first.changed is True
            assert first.status == AccessRequestStatus.APPROVED

            repeated = await apply_access_decision(
                db,
                callback_data=callback_data,
                callback_query_id="callback-1",
                actor_telegram_user_id=700000001,
                message_chat_id=700000001,
                message_id=55,
                settings=SETTINGS,
                now=now,
            )
            await db.commit()
            assert repeated.changed is False

            await db.refresh(request)
            await db.refresh(target)
            assert request.decided_by_user_id == admin_id
            assert target.access_status == UserAccessStatus.APPROVED

            keys = [
                notification_dedupe_key(
                    "access-request", request_id, "user-decision"
                ),
                notification_dedupe_key(
                    "callback", "callback-1", "clear-buttons"
                ),
                notification_dedupe_key("callback", "callback-1", "answer"),
            ]
            count = await db.scalar(
                select(func.count())
                .select_from(NotificationOutbox)
                .where(NotificationOutbox.dedupe_key.in_(keys))
            )
            assert count == 3

        async with AsyncSession(engine) as db:
            await cleanup_users(db, [admin_id, target_id])
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_unapproved_admin_cannot_decide_access() -> None:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    admin_id = uuid.uuid4()
    target_id = uuid.uuid4()
    request_id = uuid.uuid4()

    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            admin = User(
                id=admin_id,
                role=UserRole.ADMIN,
                access_status=UserAccessStatus.PENDING,
            )
            target = User(id=target_id, access_status=UserAccessStatus.PENDING)
            request = AccessRequest(
                id=request_id,
                user=target,
                user_id=target_id,
                status=AccessRequestStatus.PENDING,
            )
            db.add_all(
                [
                    admin,
                    target,
                    TelegramIdentity(
                        user=admin,
                        user_id=admin_id,
                        telegram_user_id=700000011,
                        first_name="Admin",
                    ),
                    TelegramIdentity(
                        user=target,
                        user_id=target_id,
                        telegram_user_id=700000012,
                        first_name="Target",
                    ),
                    request,
                ]
            )
            await db.flush()
            approve, _ = await create_access_decision_callbacks(db, request_id)
            callback_data = access_callback_data(approve.token)
            await db.commit()

            with pytest.raises(TelegramAdminAuthorizationError):
                await apply_access_decision(
                    db,
                    callback_data=callback_data,
                    callback_query_id="callback-unauthorized",
                    actor_telegram_user_id=700000011,
                    message_chat_id=700000011,
                    message_id=1,
                    settings=SETTINGS,
                )
            await db.rollback()

            saved = await db.get(AccessRequest, request_id)
            assert saved is not None
            assert saved.status == AccessRequestStatus.PENDING

        async with AsyncSession(engine) as db:
            await cleanup_users(db, [admin_id, target_id])
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_telegram_update_dedupe_is_persistent() -> None:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    update_id = 2_147_000_001

    try:
        async with AsyncSession(engine) as db:
            assert await register_telegram_update(db, update_id) is True
            await db.commit()
            assert await register_telegram_update(db, update_id) is False
            await db.commit()
            await db.execute(
                delete(TelegramUpdate).where(TelegramUpdate.update_id == update_id)
            )
            await db.commit()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_skip_locked_claimers_do_not_claim_same_row() -> None:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    key_one = notification_dedupe_key("claim", uuid.uuid4())
    key_two = notification_dedupe_key("claim", uuid.uuid4())

    try:
        async with AsyncSession(engine) as db:
            await enqueue_telegram_call(
                db,
                method="sendMessage",
                payload={"chat_id": 1, "text": "one"},
                dedupe_key=key_one,
            )
            await enqueue_telegram_call(
                db,
                method="sendMessage",
                payload={"chat_id": 1, "text": "two"},
                dedupe_key=key_two,
            )
            await db.commit()

        barrier = asyncio.Barrier(2)

        async def claim_one() -> uuid.UUID:
            async with AsyncSession(engine) as db:
                await barrier.wait()
                async with db.begin():
                    claims = await claim_notification_batch(
                        db,
                        batch_size=1,
                        claim_ttl_seconds=60,
                        max_attempts=8,
                    )
                    assert len(claims) == 1
                    return claims[0].id

        first, second = await asyncio.gather(claim_one(), claim_one())
        assert first != second

        async with AsyncSession(engine) as db:
            await db.execute(
                delete(NotificationOutbox).where(
                    NotificationOutbox.dedupe_key.in_([key_one, key_two])
                )
            )
            await db.commit()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_pending_callback_cannot_override_blocked_user() -> None:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    admin_id = uuid.uuid4()
    target_id = uuid.uuid4()
    request_id = uuid.uuid4()

    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            admin = User(
                id=admin_id,
                role=UserRole.ADMIN,
                access_status=UserAccessStatus.APPROVED,
                approved_at=datetime.now(UTC),
            )
            target = User(
                id=target_id,
                access_status=UserAccessStatus.BLOCKED,
            )
            request = AccessRequest(
                id=request_id,
                user=target,
                user_id=target_id,
                status=AccessRequestStatus.PENDING,
            )
            db.add_all(
                [
                    admin,
                    target,
                    TelegramIdentity(
                        user=admin,
                        user_id=admin_id,
                        telegram_user_id=700000021,
                        first_name="Admin",
                    ),
                    TelegramIdentity(
                        user=target,
                        user_id=target_id,
                        telegram_user_id=700000022,
                        first_name="Blocked",
                    ),
                    request,
                ]
            )
            await db.flush()
            approve, _ = await create_access_decision_callbacks(db, request_id)
            callback_data = access_callback_data(approve.token)
            await db.commit()

            from app.modules.telegram_bot.service import InvalidAccessCallbackError

            with pytest.raises(InvalidAccessCallbackError):
                await apply_access_decision(
                    db,
                    callback_data=callback_data,
                    callback_query_id="callback-blocked",
                    actor_telegram_user_id=700000021,
                    message_chat_id=700000021,
                    message_id=1,
                    settings=SETTINGS,
                )
            await db.rollback()

            saved_request = await db.get(AccessRequest, request_id)
            saved_target = await db.get(User, target_id)
            assert saved_request is not None
            assert saved_target is not None
            assert saved_request.status == AccessRequestStatus.PENDING
            assert saved_target.access_status == UserAccessStatus.BLOCKED

        async with AsyncSession(engine) as db:
            await cleanup_users(db, [admin_id, target_id])
    finally:
        await engine.dispose()
