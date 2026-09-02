from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
)

from app.core.config import Settings
from app.modules.identity.enums import (
    AccessRequestStatus,
    UserAccessStatus,
)
from app.modules.identity.models import (
    AccessRequest,
    TelegramIdentity,
    User,
)
from app.modules.notifications.models import (
    NotificationOutbox,
)
from app.modules.notifications.service import (
    notification_dedupe_key,
)
from app.modules.telegram_bot.models import (
    AccessDecisionCallback,
)
from app.modules.telegram_bot.service import (
    enqueue_access_request_admin_notification,
)

DATABASE_URL = os.environ["DATABASE_URL"]

POSTGRES_INTEGRATION_ENABLED = (
    os.getenv("RUN_POSTGRES_INTEGRATION") == "1"
)

pytestmark = pytest.mark.skipif(
    not POSTGRES_INTEGRATION_ENABLED,
    reason=(
        "set RUN_POSTGRES_INTEGRATION=1 against "
        "a migrated PostgreSQL test DB"
    ),
)

SETTINGS = Settings(
    database_url=DATABASE_URL,
    admin_telegram_user_id=700000099,
)


@pytest.mark.asyncio
async def test_dead_access_admin_notification_is_requeued() -> None:
    engine = create_async_engine(
        DATABASE_URL,
        pool_pre_ping=True,
    )

    user_id = uuid.uuid4()
    request_id = uuid.uuid4()

    dedupe_key = notification_dedupe_key(
        "access-request",
        request_id,
        "admin",
    )

    try:
        async with AsyncSession(
            engine,
            expire_on_commit=False,
        ) as db:
            user = User(
                id=user_id,
                access_status=(
                    UserAccessStatus.PENDING
                ),
            )

            identity = TelegramIdentity(
                user=user,
                user_id=user_id,
                telegram_user_id=700000098,
                username="recovery_test",
                first_name="Recovery",
            )

            access_request = AccessRequest(
                id=request_id,
                user=user,
                user_id=user_id,
                status=AccessRequestStatus.PENDING,
            )

            db.add_all(
                [
                    user,
                    identity,
                    access_request,
                ]
            )

            await db.flush()

            await (
                enqueue_access_request_admin_notification(
                    db,
                    access_request=access_request,
                    identity=identity,
                    settings=SETTINGS,
                )
            )

            await db.commit()

        async with AsyncSession(
            engine,
            expire_on_commit=False,
        ) as db:
            row = await db.scalar(
                select(NotificationOutbox).where(
                    NotificationOutbox.dedupe_key
                    == dedupe_key
                )
            )

            assert row is not None

            original_outbox_id = row.id

            original_tokens = set(
                (
                    await db.scalars(
                        select(
                            AccessDecisionCallback.token
                        ).where(
                            AccessDecisionCallback
                            .access_request_id
                            == request_id
                        )
                    )
                ).all()
            )

            assert len(original_tokens) == 2

            row.status = "DEAD"
            row.attempts = 8
            row.last_error = "TelegramGatewayError"
            row.claimed_at = None
            row.claim_token = None

            await db.commit()

        async with AsyncSession(
            engine,
            expire_on_commit=False,
        ) as db:
            saved_request = await db.get(
                AccessRequest,
                request_id,
            )

            saved_identity = await db.scalar(
                select(TelegramIdentity).where(
                    TelegramIdentity.user_id
                    == user_id
                )
            )

            assert saved_request is not None
            assert saved_identity is not None

            await (
                enqueue_access_request_admin_notification(
                    db,
                    access_request=saved_request,
                    identity=saved_identity,
                    settings=SETTINGS,
                )
            )

            await db.commit()

        async with AsyncSession(engine) as db:
            row = await db.scalar(
                select(NotificationOutbox).where(
                    NotificationOutbox.dedupe_key
                    == dedupe_key
                )
            )

            assert row is not None
            assert row.id == original_outbox_id
            assert row.status == "PENDING"
            assert row.attempts == 0
            assert row.claimed_at is None
            assert row.claim_token is None
            assert row.last_error is None

            outbox_count = await db.scalar(
                select(func.count())
                .select_from(NotificationOutbox)
                .where(
                    NotificationOutbox.dedupe_key
                    == dedupe_key
                )
            )

            callback_tokens = set(
                (
                    await db.scalars(
                        select(
                            AccessDecisionCallback.token
                        ).where(
                            AccessDecisionCallback
                            .access_request_id
                            == request_id
                        )
                    )
                ).all()
            )

            assert outbox_count == 1
            assert callback_tokens == original_tokens

            await db.execute(
                delete(NotificationOutbox).where(
                    NotificationOutbox.dedupe_key
                    == dedupe_key
                )
            )

            await db.execute(
                delete(
                    AccessDecisionCallback
                ).where(
                    AccessDecisionCallback
                    .access_request_id
                    == request_id
                )
            )

            await db.execute(
                delete(AccessRequest).where(
                    AccessRequest.id
                    == request_id
                )
            )

            await db.execute(
                delete(TelegramIdentity).where(
                    TelegramIdentity.user_id
                    == user_id
                )
            )

            await db.execute(
                delete(User).where(
                    User.id == user_id
                )
            )

            await db.commit()

    finally:
        await engine.dispose()
