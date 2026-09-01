import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import Settings
from app.modules.access.service import create_or_get_access_request
from app.modules.auth.models import AuthSession
from app.modules.auth.service import (
    hash_session_token,
    load_auth_context,
    upsert_telegram_identity,
)
from app.modules.auth.telegram import TelegramWebAppUser, ValidatedTelegramInitData
from app.modules.identity.enums import AccessRequestStatus, UserAccessStatus
from app.modules.identity.models import AccessRequest, TelegramIdentity, User

DATABASE_URL = os.environ["DATABASE_URL"]
POSTGRES_INTEGRATION_ENABLED = os.getenv("RUN_POSTGRES_INTEGRATION") == "1"

pytestmark = pytest.mark.skipif(
    not POSTGRES_INTEGRATION_ENABLED,
    reason="set RUN_POSTGRES_INTEGRATION=1 against a migrated PostgreSQL test DB",
)


@pytest.mark.asyncio
async def test_concurrent_access_request_creates_exactly_one_pending_row() -> None:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    user_id = uuid.uuid4()

    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            db.add(User(id=user_id, access_status=UserAccessStatus.PENDING))
            await db.commit()

        barrier = asyncio.Barrier(2)

        async def submit() -> tuple[bool, uuid.UUID]:
            async with AsyncSession(engine, expire_on_commit=False) as db:
                await barrier.wait()
                result = await create_or_get_access_request(db, user_id)
                request_id = result.request.id
                await db.commit()
                return result.created, request_id

        first, second = await asyncio.gather(submit(), submit())

        assert sorted([first[0], second[0]]) == [False, True]
        assert first[1] == second[1]

        async with AsyncSession(engine) as db:
            try:
                pending_result = await db.scalars(
                    select(AccessRequest).where(
                        AccessRequest.user_id == user_id,
                        AccessRequest.status == AccessRequestStatus.PENDING,
                    )
                )
                assert len(pending_result.all()) == 1
            finally:
                # Reuse the already-open DB connection for cleanup. On Docker
                # Desktop for macOS, opening an extra host-published connection
                # during teardown can briefly race the port-forward path.
                await db.execute(
                    delete(AccessRequest).where(AccessRequest.user_id == user_id)
                )
                await db.execute(delete(User).where(User.id == user_id))
                await db.commit()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_auth_session_query_rejects_revoked_and_expired_rows() -> None:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    user_id = uuid.uuid4()
    now = datetime(2026, 9, 1, 1, 0, tzinfo=UTC)

    valid_token = "valid-token"
    revoked_token = "revoked-token"
    expired_token = "expired-token"

    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            user = User(id=user_id, access_status=UserAccessStatus.APPROVED)
            identity = TelegramIdentity(
                id=uuid.uuid4(),
                user=user,
                user_id=user_id,
                telegram_user_id=900000000 + (user_id.int % 1_000_000),
                first_name="Integration",
            )
            db.add_all(
                [
                    user,
                    identity,
                    AuthSession(
                        id=uuid.uuid4(),
                        user=user,
                        user_id=user_id,
                        token_hash=hash_session_token(valid_token),
                        created_at=now - timedelta(minutes=10),
                        last_seen_at=now - timedelta(minutes=10),
                        expires_at=now + timedelta(hours=1),
                    ),
                    AuthSession(
                        id=uuid.uuid4(),
                        user=user,
                        user_id=user_id,
                        token_hash=hash_session_token(revoked_token),
                        created_at=now - timedelta(minutes=10),
                        last_seen_at=now - timedelta(minutes=10),
                        expires_at=now + timedelta(hours=1),
                        revoked_at=now - timedelta(minutes=1),
                    ),
                    AuthSession(
                        id=uuid.uuid4(),
                        user=user,
                        user_id=user_id,
                        token_hash=hash_session_token(expired_token),
                        created_at=now - timedelta(hours=2),
                        last_seen_at=now - timedelta(hours=2),
                        expires_at=now - timedelta(hours=1),
                    ),
                ]
            )
            await db.commit()

        async with AsyncSession(engine, expire_on_commit=False) as db:
            try:
                valid = await load_auth_context(db, valid_token, now=now)
                revoked = await load_auth_context(db, revoked_token, now=now)
                expired = await load_auth_context(db, expired_token, now=now)

                assert valid is not None
                assert valid.user.id == user_id
                assert revoked is None
                assert expired is None
            finally:
                await db.execute(
                    delete(AuthSession).where(AuthSession.user_id == user_id)
                )
                await db.execute(
                    delete(TelegramIdentity).where(TelegramIdentity.user_id == user_id)
                )
                await db.execute(delete(User).where(User.id == user_id))
                await db.commit()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_first_telegram_auth_creates_one_identity() -> None:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    telegram_user_id = 4_200_000_001
    now = datetime(2026, 9, 1, 2, 0, tzinfo=UTC)
    settings = Settings(database_url=DATABASE_URL)
    validated = ValidatedTelegramInitData(
        user=TelegramWebAppUser(
            id=telegram_user_id,
            first_name="Concurrent",
            username="concurrent-user",
            language_code="ru",
        ),
        auth_date=now,
        query_id="concurrent-query",
    )

    try:
        barrier = asyncio.Barrier(2)

        async def authenticate() -> tuple[uuid.UUID, uuid.UUID]:
            async with AsyncSession(engine, expire_on_commit=False) as db:
                await barrier.wait()
                async with db.begin():
                    user, identity = await upsert_telegram_identity(
                        db,
                        validated,
                        settings,
                        now=now,
                    )
                    return user.id, identity.id

        first, second = await asyncio.gather(authenticate(), authenticate())

        assert first == second

        async with AsyncSession(engine, expire_on_commit=False) as db:
            try:
                identities = (
                    await db.scalars(
                        select(TelegramIdentity).where(
                            TelegramIdentity.telegram_user_id == telegram_user_id
                        )
                    )
                ).all()

                assert len(identities) == 1
                assert identities[0].id == first[1]
                assert identities[0].user_id == first[0]
            finally:
                await db.execute(
                    delete(TelegramIdentity).where(
                        TelegramIdentity.telegram_user_id == telegram_user_id
                    )
                )
                await db.execute(delete(User).where(User.id == first[0]))
                await db.commit()
    finally:
        await engine.dispose()
