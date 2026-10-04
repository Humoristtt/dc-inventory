import uuid
from collections.abc import Awaitable

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.inventory.domain import MovementCursorPage
from app.modules.inventory.enums import MovementType
from app.modules.inventory.queries import list_movements_cursor
from tests.sql_capture import capture_sql
from tests.warehouse_helpers import move, scenario

pytestmark = pytest.mark.asyncio


async def _captured_page(
    db: AsyncSession,
    operation: Awaitable[MovementCursorPage],
) -> tuple[MovementCursorPage, list[str]]:
    connection = await db.connection()

    with capture_sql(connection) as statements:
        page = await operation

    selects = [
        statement
        for statement in statements
        if statement.lstrip().upper().startswith("SELECT")
    ]
    assert 1 <= len(selects) <= 2

    normalized = "\n".join(selects).lower()
    assert "count(" not in normalized
    assert " offset " not in normalized

    return page, selects


async def test_movement_cursor_has_bounded_real_postgres_queries(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    warehouse = await scenario(db)

    for index in range(120):
        await move(
            db,
            warehouse,
            MovementType.RECEIPT,
            1,
            destination=warehouse[2],
            key=f"history-performance-{index}",
        )

    empty, _ = await _captured_page(
        db,
        list_movements_cursor(
            db,
            actor_user_id=uuid.uuid4(),
            limit=50,
        ),
    )
    assert empty.items == []
    assert empty.next_before_journal_seq is None

    single, _ = await _captured_page(
        db,
        list_movements_cursor(
            db,
            actor_user_id=warehouse[0],
            limit=1,
        ),
    )
    assert len(single.items) == 1
    assert single.next_before_journal_seq is not None

    seen: list[int] = []
    before: int | None = None

    for expected_size in (50, 50, 20):
        page, _ = await _captured_page(
            db,
            list_movements_cursor(
                db,
                actor_user_id=warehouse[0],
                before_journal_seq=before,
                limit=50,
            ),
        )

        assert len(page.items) == expected_size
        seen.extend(
            record.movement.journal_seq
            for record in page.items
        )
        before = page.next_before_journal_seq

    assert before is None
    assert len(seen) == 120
    assert len(set(seen)) == 120
    assert seen == sorted(seen, reverse=True)

    explain = await db.scalar(
        text(
            "EXPLAIN (FORMAT JSON) "
            "SELECT id FROM movements "
            "ORDER BY journal_seq DESC "
            "LIMIT 51"
        )
    )
    rendered_plan = str(explain)
    assert "Limit" in rendered_plan
    assert "Aggregate" not in rendered_plan
