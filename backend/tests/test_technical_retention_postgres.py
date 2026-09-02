from __future__ import annotations

import hashlib
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import Settings
from app.maintenance.technical_retention import (
    TECHNICAL_RETENTION_ADVISORY_LOCK_KEY,
    run_technical_retention_once,
)
from app.modules.auth.models import AuthSession
from app.modules.identity.enums import (
    AccessRequestStatus,
    UserAccessStatus,
    UserRole,
)
from app.modules.identity.models import AccessRequest, User
from app.modules.notifications.models import NotificationOutbox
from app.modules.telegram_bot.models import (
    AccessDecisionCallback,
    TelegramUpdate,
)

DATABASE_URL = os.environ["DATABASE_URL"]
POSTGRES_INTEGRATION_ENABLED = (
    os.getenv("RUN_POSTGRES_INTEGRATION") == "1"
)

pytestmark = pytest.mark.skipif(
    not POSTGRES_INTEGRATION_ENABLED,
    reason=(
        "set RUN_POSTGRES_INTEGRATION=1 against a migrated "
        "PostgreSQL test DB"
    ),
)


def token_hash(label: str) -> bytes:
    return hashlib.sha256(label.encode()).digest()


@pytest.mark.asyncio
async def test_retention_deletes_only_old_terminal_technical_rows() -> None:
    engine = create_async_engine(
        DATABASE_URL,
        pool_pre_ping=True,
    )

    now = datetime(2026, 9, 2, 9, 0, tzinfo=UTC)
    old = datetime(2025, 1, 1, 9, 0, tzinfo=UTC)
    recent = now - timedelta(days=1)
    future = now + timedelta(days=30)

    admin_id = uuid.uuid4()
    terminal_user_id = uuid.uuid4()
    pending_user_id = uuid.uuid4()

    terminal_request_id = uuid.uuid4()
    pending_request_id = uuid.uuid4()
    recent_request_id = uuid.uuid4()

    old_session_id = uuid.uuid4()
    revoked_session_id = uuid.uuid4()
    live_session_id = uuid.uuid4()

    old_sent_id = uuid.uuid4()
    old_dead_id = uuid.uuid4()
    pending_outbox_id = uuid.uuid4()
    recent_sent_id = uuid.uuid4()

    old_update_id = 8_100_000_001
    recent_update_id = 8_100_000_002
    unprocessed_update_id = 8_100_000_003

    old_callback_token = "old_callback_token_123456"
    pending_callback_token = "pending_callback_token_123"
    recent_callback_token = "recent_callback_token_1234"

    settings = Settings(
        database_url=DATABASE_URL,
        maintenance_retention_batch_size=100,
        auth_session_retention_days=7,
        telegram_update_retention_days=30,
        notification_outbox_retention_days=90,
        access_callback_retention_days=30,
    )

    try:
        async with AsyncSession(
            engine,
            expire_on_commit=False,
        ) as db:
            admin = User(
                id=admin_id,
                role=UserRole.ADMIN,
                access_status=UserAccessStatus.APPROVED,
                approved_at=old,
            )
            terminal_user = User(
                id=terminal_user_id,
                access_status=UserAccessStatus.APPROVED,
            )
            pending_user = User(
                id=pending_user_id,
                access_status=UserAccessStatus.PENDING,
            )

            terminal_request = AccessRequest(
                id=terminal_request_id,
                user_id=terminal_user_id,
                status=AccessRequestStatus.APPROVED,
                requested_at=old - timedelta(days=1),
                decided_at=old,
                decided_by_user_id=admin_id,
            )
            pending_request = AccessRequest(
                id=pending_request_id,
                user_id=pending_user_id,
                status=AccessRequestStatus.PENDING,
                requested_at=old,
            )
            recent_request = AccessRequest(
                id=recent_request_id,
                user_id=terminal_user_id,
                status=AccessRequestStatus.REJECTED,
                requested_at=recent - timedelta(hours=1),
                decided_at=recent,
                decided_by_user_id=admin_id,
            )

            # Explicit flush phases are intentional. These test rows
            # use scalar foreign-key ids rather than ORM relationships,
            # so fixture ordering must not depend on ORM unit-of-work
            # mapper ordering.
            db.add_all(
                [
                    admin,
                    terminal_user,
                    pending_user,
                ]
            )
            await db.flush()

            db.add_all(
                [
                    terminal_request,
                    pending_request,
                    recent_request,
                ]
            )
            await db.flush()

            db.add_all(
                [
                    AuthSession(
                        id=old_session_id,
                        user_id=terminal_user_id,
                        token_hash=token_hash("old-session"),
                        created_at=old - timedelta(days=1),
                        last_seen_at=old,
                        expires_at=old,
                    ),
                    AuthSession(
                        id=revoked_session_id,
                        user_id=terminal_user_id,
                        token_hash=token_hash("revoked-session"),
                        created_at=old - timedelta(days=1),
                        last_seen_at=old,
                        expires_at=future,
                        revoked_at=old,
                    ),
                    AuthSession(
                        id=live_session_id,
                        user_id=terminal_user_id,
                        token_hash=token_hash("live-session"),
                        created_at=recent,
                        last_seen_at=recent,
                        expires_at=future,
                    ),
                    TelegramUpdate(
                        update_id=old_update_id,
                        received_at=old,
                        processed_at=old,
                    ),
                    TelegramUpdate(
                        update_id=recent_update_id,
                        received_at=recent,
                        processed_at=recent,
                    ),
                    TelegramUpdate(
                        update_id=unprocessed_update_id,
                        received_at=old,
                        processed_at=None,
                    ),
                    NotificationOutbox(
                        id=old_sent_id,
                        method="sendMessage",
                        payload={},
                        dedupe_key="retention-old-sent",
                        status="SENT",
                        attempts=1,
                        available_at=old,
                        sent_at=old,
                        created_at=old,
                        updated_at=old,
                    ),
                    NotificationOutbox(
                        id=old_dead_id,
                        method="sendMessage",
                        payload={},
                        dedupe_key="retention-old-dead",
                        status="DEAD",
                        attempts=8,
                        available_at=old,
                        created_at=old,
                        updated_at=old,
                    ),
                    NotificationOutbox(
                        id=pending_outbox_id,
                        method="sendMessage",
                        payload={},
                        dedupe_key="retention-pending",
                        status="PENDING",
                        attempts=0,
                        available_at=old,
                        created_at=old,
                        updated_at=old,
                    ),
                    NotificationOutbox(
                        id=recent_sent_id,
                        method="sendMessage",
                        payload={},
                        dedupe_key="retention-recent-sent",
                        status="SENT",
                        attempts=1,
                        available_at=recent,
                        sent_at=recent,
                        created_at=recent,
                        updated_at=recent,
                    ),
                ]
            )
            await db.flush()

            db.add_all(
                [
                    AccessDecisionCallback(
                        token=old_callback_token,
                        access_request_id=terminal_request_id,
                        action="APPROVE",
                        created_at=old,
                    ),
                    AccessDecisionCallback(
                        token=pending_callback_token,
                        access_request_id=pending_request_id,
                        action="APPROVE",
                        created_at=old,
                    ),
                    AccessDecisionCallback(
                        token=recent_callback_token,
                        access_request_id=recent_request_id,
                        action="APPROVE",
                        created_at=recent,
                    ),
                ]
            )
            await db.commit()

        async with AsyncSession(
            engine,
            expire_on_commit=False,
        ) as db:
            async with db.begin():
                counts = await run_technical_retention_once(
                    db,
                    settings,
                    now=now,
                )

            assert counts.auth_sessions >= 2
            assert counts.telegram_updates >= 1
            assert counts.notification_outbox >= 2
            assert counts.access_decision_callbacks >= 1

        async with AsyncSession(engine) as db:
            assert (
                await db.get(AuthSession, old_session_id)
                is None
            )
            assert (
                await db.get(AuthSession, revoked_session_id)
                is None
            )
            assert (
                await db.get(AuthSession, live_session_id)
                is not None
            )

            assert (
                await db.get(TelegramUpdate, old_update_id)
                is None
            )
            assert (
                await db.get(TelegramUpdate, recent_update_id)
                is not None
            )
            assert (
                await db.get(
                    TelegramUpdate,
                    unprocessed_update_id,
                )
                is not None
            )

            assert (
                await db.get(NotificationOutbox, old_sent_id)
                is None
            )
            assert (
                await db.get(NotificationOutbox, old_dead_id)
                is None
            )
            assert (
                await db.get(
                    NotificationOutbox,
                    pending_outbox_id,
                )
                is not None
            )
            assert (
                await db.get(NotificationOutbox, recent_sent_id)
                is not None
            )

            assert (
                await db.get(
                    AccessDecisionCallback,
                    old_callback_token,
                )
                is None
            )
            assert (
                await db.get(
                    AccessDecisionCallback,
                    pending_callback_token,
                )
                is not None
            )
            assert (
                await db.get(
                    AccessDecisionCallback,
                    recent_callback_token,
                )
                is not None
            )

    finally:
        async with AsyncSession(engine) as db:
            await db.execute(
                delete(AccessDecisionCallback).where(
                    AccessDecisionCallback.access_request_id.in_(
                        [
                            terminal_request_id,
                            pending_request_id,
                            recent_request_id,
                        ]
                    )
                )
            )
            await db.execute(
                delete(AuthSession).where(
                    AuthSession.user_id.in_(
                        [
                            terminal_user_id,
                            pending_user_id,
                        ]
                    )
                )
            )
            await db.execute(
                delete(NotificationOutbox).where(
                    NotificationOutbox.id.in_(
                        [
                            old_sent_id,
                            old_dead_id,
                            pending_outbox_id,
                            recent_sent_id,
                        ]
                    )
                )
            )
            await db.execute(
                delete(TelegramUpdate).where(
                    TelegramUpdate.update_id.in_(
                        [
                            old_update_id,
                            recent_update_id,
                            unprocessed_update_id,
                        ]
                    )
                )
            )
            await db.execute(
                delete(AccessRequest).where(
                    AccessRequest.id.in_(
                        [
                            terminal_request_id,
                            pending_request_id,
                            recent_request_id,
                        ]
                    )
                )
            )
            await db.execute(
                delete(User).where(
                    User.id.in_(
                        [
                            terminal_user_id,
                            pending_user_id,
                            admin_id,
                        ]
                    )
                )
            )
            await db.commit()

        await engine.dispose()


@pytest.mark.asyncio
async def test_retention_batch_size_is_a_hard_limit() -> None:
    engine = create_async_engine(
        DATABASE_URL,
        pool_pre_ping=True,
    )

    now = datetime(2026, 9, 2, 10, 0, tzinfo=UTC)
    ancient = datetime(2000, 1, 1, tzinfo=UTC)
    update_ids = [
        8_200_000_001,
        8_200_000_002,
        8_200_000_003,
    ]

    settings = Settings(
        database_url=DATABASE_URL,
        maintenance_retention_batch_size=2,
        telegram_update_retention_days=30,
    )

    try:
        async with AsyncSession(engine) as db:
            db.add_all(
                [
                    TelegramUpdate(
                        update_id=update_id,
                        received_at=ancient,
                        processed_at=ancient,
                    )
                    for update_id in update_ids
                ]
            )
            await db.commit()

        async with AsyncSession(engine) as db:
            async with db.begin():
                counts = await run_technical_retention_once(
                    db,
                    settings,
                    now=now,
                )

            assert counts.telegram_updates == 2

        async with AsyncSession(engine) as db:
            remaining = list(
                (
                    await db.scalars(
                        select(TelegramUpdate.update_id).where(
                            TelegramUpdate.update_id.in_(
                                update_ids
                            )
                        )
                    )
                ).all()
            )

            assert len(remaining) == 1

    finally:
        async with AsyncSession(engine) as db:
            await db.execute(
                delete(TelegramUpdate).where(
                    TelegramUpdate.update_id.in_(update_ids)
                )
            )
            await db.commit()

        await engine.dispose()


@pytest.mark.asyncio
async def test_retention_is_singleton_per_database_transaction() -> None:
    engine = create_async_engine(
        DATABASE_URL,
        pool_pre_ping=True,
    )

    settings = Settings(
        database_url=DATABASE_URL,
        maintenance_retention_batch_size=100,
    )

    try:
        async with (
            AsyncSession(engine) as lock_db,
            AsyncSession(engine) as runner_db,
            lock_db.begin(),
        ):
            acquired = await lock_db.scalar(
                text(
                    "SELECT "
                    "pg_try_advisory_xact_lock(:lock_key)"
                ),
                {
                    "lock_key": (
                        TECHNICAL_RETENTION_ADVISORY_LOCK_KEY
                    )
                },
            )

            assert acquired is True

            async with runner_db.begin():
                counts = (
                    await run_technical_retention_once(
                        runner_db,
                        settings,
                    )
                )

            assert counts.total == 0

    finally:
        await engine.dispose()
