from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
)

from app.modules.identity.enums import (
    UserAccessStatus,
    UserRole,
)
from app.modules.identity.locking import (
    acquire_identity_management_shared_barrier,
    lock_identity_actor_and_target,
)
from app.modules.identity.models import User
from app.modules.identity.policy import (
    IDENTITY_MANAGEMENT_LOCK_KEY,
)

pytestmark = pytest.mark.asyncio


async def test_shared_barrier_does_not_serialize_ordinary_operations() -> None:
    engine = create_async_engine(
        os.environ["DATABASE_URL"]
    )

    first = AsyncSession(
        engine,
        expire_on_commit=False,
    )
    second = AsyncSession(
        engine,
        expire_on_commit=False,
    )
    exclusive_probe = AsyncSession(
        engine,
        expire_on_commit=False,
    )

    try:
        await first.begin()
        await second.begin()
        await exclusive_probe.begin()

        await acquire_identity_management_shared_barrier(
            first
        )

        await asyncio.wait_for(
            acquire_identity_management_shared_barrier(
                second
            ),
            timeout=1.0,
        )

        acquired_exclusive = (
            await exclusive_probe.scalar(
                select(
                    func.pg_try_advisory_xact_lock(
                        IDENTITY_MANAGEMENT_LOCK_KEY
                    )
                )
            )
        )

        assert acquired_exclusive is False
    finally:
        await first.rollback()
        await second.rollback()
        await exclusive_probe.rollback()
        await first.close()
        await second.close()
        await exclusive_probe.close()
        await engine.dispose()


async def test_same_actor_can_lock_distinct_targets_in_parallel() -> None:
    engine = create_async_engine(
        os.environ["DATABASE_URL"]
    )

    actor_id = uuid.uuid4()
    first_target_id = uuid.uuid4()
    second_target_id = uuid.uuid4()
    now = datetime.now(UTC)

    async with AsyncSession(
        engine,
        expire_on_commit=False,
    ) as setup:
        setup.add_all(
            [
                User(
                    id=actor_id,
                    role=UserRole.ADMIN,
                    access_status=(
                        UserAccessStatus.APPROVED
                    ),
                    approved_at=now,
                ),
                User(
                    id=first_target_id,
                    role=UserRole.ENGINEER,
                    access_status=(
                        UserAccessStatus.APPROVED
                    ),
                    approved_at=now,
                ),
                User(
                    id=second_target_id,
                    role=UserRole.ENGINEER,
                    access_status=(
                        UserAccessStatus.APPROVED
                    ),
                    approved_at=now,
                ),
            ]
        )
        await setup.commit()

    first = AsyncSession(
        engine,
        expire_on_commit=False,
    )
    second = AsyncSession(
        engine,
        expire_on_commit=False,
    )

    try:
        await first.begin()
        await second.begin()

        await acquire_identity_management_shared_barrier(
            first
        )
        first_actor, first_target = (
            await lock_identity_actor_and_target(
                first,
                actor_user_id=actor_id,
                target_user_id=first_target_id,
            )
        )

        assert first_actor is not None
        assert first_target is not None

        async def acquire_second() -> None:
            await acquire_identity_management_shared_barrier(
                second
            )
            second_actor, second_target = (
                await lock_identity_actor_and_target(
                    second,
                    actor_user_id=actor_id,
                    target_user_id=second_target_id,
                )
            )
            assert second_actor is not None
            assert second_target is not None

        await asyncio.wait_for(
            acquire_second(),
            timeout=1.0,
        )
    finally:
        await first.rollback()
        await second.rollback()
        await first.close()
        await second.close()

        async with AsyncSession(
            engine,
            expire_on_commit=False,
        ) as cleanup:
            await cleanup.execute(
                delete(User).where(
                    User.id.in_(
                        {
                            actor_id,
                            first_target_id,
                            second_target_id,
                        }
                    )
                )
            )
            await cleanup.commit()

        await engine.dispose()
