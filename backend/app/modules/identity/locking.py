from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import User
from app.modules.identity.policy import IDENTITY_MANAGEMENT_LOCK_KEY


async def acquire_identity_management_shared_barrier(
    db: AsyncSession,
) -> None:
    await db.execute(
        select(
            func.pg_advisory_xact_lock_shared(
                IDENTITY_MANAGEMENT_LOCK_KEY
            )
        )
    )


async def acquire_identity_management_exclusive_barrier(
    db: AsyncSession,
) -> None:
    await db.execute(
        select(
            func.pg_advisory_xact_lock(
                IDENTITY_MANAGEMENT_LOCK_KEY
            )
        )
    )


async def lock_identity_actor_and_target(
    db: AsyncSession,
    *,
    actor_user_id: UUID,
    target_user_id: UUID,
) -> tuple[User | None, User | None]:
    locked: dict[UUID, User | None] = {}

    for user_id in sorted(
        {
            actor_user_id,
            target_user_id,
        },
        key=str,
    ):
        statement = select(User).where(
            User.id == user_id
        )

        if user_id == target_user_id:
            statement = statement.with_for_update()
        else:
            statement = statement.with_for_update(
                read=True
            )

        locked[user_id] = await db.scalar(
            statement
        )

    return (
        locked.get(actor_user_id),
        locked.get(target_user_id),
    )
