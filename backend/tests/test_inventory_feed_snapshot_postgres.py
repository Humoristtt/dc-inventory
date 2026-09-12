import inspect

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
)

from app.modules.inventory.service import (
    _create_movement,
    acquire_movement_feed_snapshot,
    list_movements_cursor,
)


def test_feed_snapshot_source_has_no_global_journal_lock() -> None:
    acquire_source = inspect.getsource(
        acquire_movement_feed_snapshot
    )
    movement_source = inspect.getsource(_create_movement)
    cursor_source = inspect.getsource(
        list_movements_cursor
    )

    assert "pg_advisory" not in acquire_source
    assert "_lock_journal_mutation" not in movement_source
    assert "pg_current_snapshot" in acquire_source
    assert "pg_visible_in_snapshot" in cursor_source
    assert "pg_xact_status" in cursor_source


@pytest.mark.asyncio
async def test_snapshot_excludes_transaction_committed_after_boundary(
    migration_database: str,
) -> None:
    engine = create_async_engine(migration_database)

    async with engine.begin() as setup:
        await setup.execute(
            text(
                "CREATE TABLE feed_snapshot_probe "
                "(id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY)"
            )
        )

    writer = await engine.connect()
    writer_transaction = await writer.begin()

    try:
        await writer.execute(
            text(
                "INSERT INTO feed_snapshot_probe "
                "DEFAULT VALUES"
            )
        )

        async with AsyncSession(
            engine,
            expire_on_commit=False,
        ) as reader:
            snapshot = (
                await acquire_movement_feed_snapshot(reader)
            )

            await writer_transaction.commit()

            old_visible = await reader.scalar(
                text(
                    "SELECT count(*) "
                    "FROM feed_snapshot_probe "
                    "WHERE pg_visible_in_snapshot("
                    "xmin::text::xid8, "
                    "CAST(CAST(:snapshot AS text) AS pg_snapshot)"
                    ")"
                ),
                {
                    "snapshot":
                    snapshot.database_snapshot
                },
            )

            assert old_visible == 0

            fresh = (
                await acquire_movement_feed_snapshot(reader)
            )

            fresh_visible = await reader.scalar(
                text(
                    "SELECT count(*) "
                    "FROM feed_snapshot_probe "
                    "WHERE pg_visible_in_snapshot("
                    "xmin::text::xid8, "
                    "CAST(CAST(:snapshot AS text) AS pg_snapshot)"
                    ")"
                ),
                {
                    "snapshot":
                    fresh.database_snapshot
                },
            )

            assert fresh_visible == 1
    finally:
        if writer_transaction.is_active:
            await writer_transaction.rollback()
        await writer.close()
        await engine.dispose()
