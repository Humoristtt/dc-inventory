"""Проверка обновления непустой БД с d4: OWNER и Telegram identity сохраняются."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.migration_helpers import alembic

pytestmark = pytest.mark.asyncio


async def test_f6_upgrade_preserves_existing_owner_and_telegram_identity(
    migration_database: str,
) -> None:
    alembic(migration_database, "upgrade", "d4e5f6a7b8c9")
    owner_id = uuid.uuid4()
    identity_id = uuid.uuid4()
    engine = create_async_engine(migration_database)

    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO users (id, role, access_status) "
                    "VALUES (:id, 'OWNER', 'APPROVED')"
                ),
                {"id": owner_id},
            )
            await connection.execute(
                text(
                    "UPDATE users SET approved_by_user_id = :id "
                    "WHERE id = :id"
                ),
                {"id": owner_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO telegram_identities "
                    "(id, user_id, telegram_user_id, first_name) "
                    "VALUES (:identity_id, :owner_id, :telegram_id, 'Owner')"
                ),
                {
                    "identity_id": identity_id,
                    "owner_id": owner_id,
                    "telegram_id": 100001,
                },
            )
    finally:
        await engine.dispose()

    alembic(migration_database, "upgrade", "f6a7b8c9d0e1")
    engine = create_async_engine(migration_database)

    try:
        async with engine.connect() as connection:
            assert await connection.scalar(
                text("SELECT version_num FROM alembic_version")
            ) == "f6a7b8c9d0e1"
            assert await connection.scalar(
                text(
                    "SELECT count(*) FROM users "
                    "WHERE id = :id AND role = 'OWNER' "
                    "AND access_status = 'APPROVED' "
                    "AND approved_by_user_id = id"
                ),
                {"id": owner_id},
            ) == 1
            assert await connection.scalar(
                text(
                    "SELECT count(*) FROM telegram_identities "
                    "WHERE id = :identity_id AND user_id = :owner_id "
                    "AND telegram_user_id = 100001"
                ),
                {"identity_id": identity_id, "owner_id": owner_id},
            ) == 1
            assert await connection.scalar(
                text(
                    "SELECT count(*) FROM pg_trigger "
                    "WHERE tgname IN ('trg_users_require_access_audit', "
                    "'trg_users_require_role_audit') "
                    "AND tgenabled = 'O'"
                )
            ) == 2
            assert await connection.scalar(
                text(
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE table_schema = 'public' "
                    "AND table_name IN ('user_access_events', 'user_role_events') "
                    "AND column_name = 'db_transaction_id'"
                )
            ) == 2
    finally:
        await engine.dispose()
