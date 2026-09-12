from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import cast

import pytest
from sqlalchemy import Table, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.admin_service import (
    list_admin_users,
)
from app.modules.identity.enums import (
    UserAccessStatus,
    UserRole,
)
from app.modules.identity.models import (
    TelegramIdentity,
    User,
)

pytestmark = pytest.mark.asyncio

SEARCH_INDEXES = {
    "ix_telegram_identities_username_trgm",
    "ix_telegram_identities_first_name_trgm",
    "ix_telegram_identities_last_name_trgm",
}


async def _create_user(
    db: AsyncSession,
    *,
    telegram_user_id: int,
    username: str | None,
    first_name: str,
    last_name: str | None,
) -> User:
    user = User(
        id=uuid.uuid4(),
        role=UserRole.ENGINEER,
        access_status=(
            UserAccessStatus.APPROVED
        ),
        approved_at=datetime.now(UTC),
    )

    db.add_all(
        [
            user,
            TelegramIdentity(
                user=user,
                user_id=user.id,
                telegram_user_id=(
                    telegram_user_id
                ),
                username=username,
                first_name=first_name,
                last_name=last_name,
            ),
        ]
    )

    await db.flush()
    return user


async def test_admin_user_search_semantics(
    warehouse_db: AsyncSession,
) -> None:
    marker = uuid.uuid4().hex[:12]

    telegram_user_id = (
        1_000_000_000
        + uuid.uuid4().int
        % 8_000_000_000
    )

    target = await _create_user(
        warehouse_db,
        telegram_user_id=telegram_user_id,
        username=f"a21needle{marker}",
        first_name=f"Alpha {marker}",
        last_name=f"Omega {marker}",
    )

    literal_wildcard = await _create_user(
        warehouse_db,
        telegram_user_id=(
            telegram_user_id + 1
        ),
        username=f"literal%{marker}",
        first_name="Literal",
        last_name="Wildcard",
    )

    decoy = await _create_user(
        warehouse_db,
        telegram_user_id=(
            telegram_user_id + 2
        ),
        username=f"unrelated{marker}",
        first_name="Unrelated",
        last_name="Person",
    )

    by_username = await list_admin_users(
        warehouse_db,
        query=f"needle{marker}",
        limit=20,
    )

    assert {
        user.id
        for user in by_username.items
    } == {target.id}

    by_first_name = await list_admin_users(
        warehouse_db,
        query=f"alpha {marker}",
        limit=20,
    )

    assert target.id in {
        user.id
        for user in by_first_name.items
    }

    by_last_name = await list_admin_users(
        warehouse_db,
        query=f"OMEGA {marker}",
        limit=20,
    )

    assert target.id in {
        user.id
        for user in by_last_name.items
    }

    by_exact_id = await list_admin_users(
        warehouse_db,
        query=str(telegram_user_id),
        limit=20,
    )

    assert target.id in {
        user.id
        for user in by_exact_id.items
    }

    by_partial_id = await list_admin_users(
        warehouse_db,
        query=str(telegram_user_id)[-5:],
        limit=20,
    )

    assert target.id not in {
        user.id
        for user in by_partial_id.items
    }

    by_literal_percent = (
        await list_admin_users(
            warehouse_db,
            query="%",
            limit=20,
        )
    )

    literal_ids = {
        user.id
        for user in by_literal_percent.items
    }

    assert literal_wildcard.id in literal_ids
    assert target.id not in literal_ids
    assert decoy.id not in literal_ids


async def test_admin_user_search_indexes_are_usable(
    warehouse_db: AsyncSession,
) -> None:
    database_indexes = set(
        (
            await warehouse_db.scalars(
                text(
                    """
                    SELECT indexname
                    FROM pg_indexes
                    WHERE schemaname = current_schema()
                      AND tablename = 'telegram_identities'
                    """
                )
            )
        ).all()
    )

    assert database_indexes >= SEARCH_INDEXES

    model_table = cast(
        Table,
        TelegramIdentity.__table__,
    )
    model_indexes = {
        index.name
        for index in model_table.indexes
    }

    assert model_indexes >= SEARCH_INDEXES

    marker = uuid.uuid4().hex

    await _create_user(
        warehouse_db,
        telegram_user_id=(
            1_000_000_000
            + uuid.uuid4().int
            % 8_000_000_000
        ),
        username=f"a21plan{marker}",
        first_name="Plan",
        last_name="Check",
    )

    await warehouse_db.execute(
        text(
            "SET LOCAL enable_seqscan = off"
        )
    )

    plan = "\n".join(
        (
            await warehouse_db.scalars(
                text(
                    """
                    EXPLAIN (COSTS OFF)
                    SELECT id
                    FROM telegram_identities
                    WHERE username ILIKE :pattern
                    """
                ),
                {
                    "pattern": f"%{marker}%",
                },
            )
        ).all()
    )

    assert (
        "ix_telegram_identities_username_trgm"
        in plan
    )
