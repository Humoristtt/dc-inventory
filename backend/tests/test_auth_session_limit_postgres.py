from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)

from app.modules.auth.models import AuthSession
from app.modules.auth.service import (
    MAX_ACTIVE_SESSIONS_PER_USER,
    issue_auth_session,
)
from app.modules.identity.enums import (
    UserAccessStatus,
    UserRole,
)
from app.modules.identity.models import User

DATABASE_URL = os.environ["DATABASE_URL"]
POSTGRES_INTEGRATION_ENABLED = (
    os.getenv("RUN_POSTGRES_INTEGRATION") == "1"
)

pytestmark = pytest.mark.skipif(
    not POSTGRES_INTEGRATION_ENABLED,
    reason=(
        "set RUN_POSTGRES_INTEGRATION=1 "
        "against a migrated PostgreSQL test DB"
    ),
)


async def _create_user(
    engine: AsyncEngine,
) -> uuid.UUID:
    user_id = uuid.uuid4()

    async with AsyncSession(
        engine,
        expire_on_commit=False,
    ) as db:
        db.add(
            User(
                id=user_id,
                role=UserRole.ENGINEER,
                access_status=(
                    UserAccessStatus.APPROVED
                ),
                approved_at=datetime.now(UTC),
            )
        )
        await db.commit()

    return user_id


async def _cleanup_user(
    engine: AsyncEngine,
    user_id: uuid.UUID,
) -> None:
    async with AsyncSession(engine) as db:
        await db.execute(
            delete(AuthSession).where(
                AuthSession.user_id == user_id
            )
        )
        await db.execute(
            delete(User).where(
                User.id == user_id
            )
        )
        await db.commit()


@pytest.mark.asyncio
async def test_session_limit_revokes_oldest_active_only() -> None:
    engine = create_async_engine(
        DATABASE_URL,
        pool_pre_ping=True,
    )
    user_id = await _create_user(engine)

    base = datetime.now(UTC) - timedelta(
        minutes=5
    )

    try:
        async with AsyncSession(
            engine,
            expire_on_commit=False,
        ) as db:
            user = await db.get(User, user_id)
            assert user is not None

            issued_ids: list[uuid.UUID] = []

            for offset in range(
                MAX_ACTIVE_SESSIONS_PER_USER
            ):
                issued = await issue_auth_session(
                    db,
                    user,
                    ttl_seconds=3600,
                    now=base
                    + timedelta(seconds=offset),
                )
                issued_ids.append(
                    issued.session.id
                )

            expired_id = uuid.uuid4()

            db.add(
                AuthSession(
                    id=expired_id,
                    user_id=user_id,
                    token_hash=os.urandom(32),
                    created_at=(
                        base - timedelta(hours=2)
                    ),
                    expires_at=(
                        base - timedelta(hours=1)
                    ),
                )
            )

            await db.commit()

        issue_time = base + timedelta(
            seconds=20
        )

        async with AsyncSession(
            engine,
            expire_on_commit=False,
        ) as db:
            user = await db.get(User, user_id)
            assert user is not None

            newest = await issue_auth_session(
                db,
                user,
                ttl_seconds=3600,
                now=issue_time,
            )

            newest_id = newest.session.id
            await db.commit()

        async with AsyncSession(engine) as db:
            active_rows = (
                await db.scalars(
                    select(AuthSession)
                    .where(
                        AuthSession.user_id
                        == user_id,
                        AuthSession.revoked_at.is_(
                            None
                        ),
                        AuthSession.expires_at
                        > issue_time,
                    )
                    .order_by(
                        AuthSession.created_at,
                        AuthSession.id,
                    )
                )
            ).all()

            assert len(active_rows) == (
                MAX_ACTIVE_SESSIONS_PER_USER
            )

            active_ids = {
                row.id for row in active_rows
            }

            assert issued_ids[0] not in active_ids
            assert newest_id in active_ids

            oldest = await db.get(
                AuthSession,
                issued_ids[0],
            )
            expired = await db.get(
                AuthSession,
                expired_id,
            )

            assert oldest is not None
            assert oldest.revoked_at == issue_time

            assert expired is not None
            assert expired.revoked_at is None
    finally:
        await _cleanup_user(
            engine,
            user_id,
        )
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_session_issuance_stays_bounded() -> None:
    engine = create_async_engine(
        DATABASE_URL,
        pool_pre_ping=True,
    )
    user_id = await _create_user(engine)

    base = datetime.now(UTC) - timedelta(
        minutes=5
    )

    try:
        async with AsyncSession(
            engine,
            expire_on_commit=False,
        ) as db:
            user = await db.get(User, user_id)
            assert user is not None

            original_ids: list[uuid.UUID] = []

            for offset in range(
                MAX_ACTIVE_SESSIONS_PER_USER - 1
            ):
                issued = await issue_auth_session(
                    db,
                    user,
                    ttl_seconds=3600,
                    now=base
                    + timedelta(seconds=offset),
                )
                original_ids.append(
                    issued.session.id
                )

            await db.commit()

        async def issue_one(
            issue_time: datetime,
        ) -> uuid.UUID:
            async with AsyncSession(
                engine,
                expire_on_commit=False,
            ) as db:
                user = await db.get(
                    User,
                    user_id,
                )
                assert user is not None

                issued = await issue_auth_session(
                    db,
                    user,
                    ttl_seconds=3600,
                    now=issue_time,
                )

                await db.commit()
                return issued.session.id

        first_id, second_id = await asyncio.gather(
            issue_one(
                base + timedelta(seconds=20)
            ),
            issue_one(
                base + timedelta(seconds=21)
            ),
        )

        check_time = base + timedelta(
            seconds=22
        )

        async with AsyncSession(engine) as db:
            active_ids = set(
                (
                    await db.scalars(
                        select(AuthSession.id).where(
                            AuthSession.user_id
                            == user_id,
                            AuthSession.revoked_at.is_(
                                None
                            ),
                            AuthSession.expires_at
                            > check_time,
                        )
                    )
                ).all()
            )

            active_count = await db.scalar(
                select(
                    func.count(AuthSession.id)
                ).where(
                    AuthSession.user_id
                    == user_id,
                    AuthSession.revoked_at.is_(
                        None
                    ),
                    AuthSession.expires_at
                    > check_time,
                )
            )

            assert active_count == (
                MAX_ACTIVE_SESSIONS_PER_USER
            )

            assert first_id in active_ids
            assert second_id in active_ids

            assert (
                original_ids[0]
                not in active_ids
            )
    finally:
        await _cleanup_user(
            engine,
            user_id,
        )
        await engine.dispose()
