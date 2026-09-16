import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.catalog.service import create_item
from app.modules.identity.enums import UserRole
from app.modules.procurement.enums import (
    ProcurementLineType,
)
from app.modules.procurement.schemas import (
    ExistingItemLineCreate,
    ProcurementRequestCreate,
    ProposedItemLineCreate,
)
from app.modules.procurement.service import (
    _prepare_lines,
    create_request,
    list_requests,
)
from tests.warehouse_helpers import actor, cable_payload

pytestmark = pytest.mark.asyncio


@asynccontextmanager
async def captured_statements(
    db: AsyncSession,
) -> AsyncIterator[list[str]]:
    connection = await db.connection()
    target = connection.sync_connection
    statements: list[str] = []

    def before_cursor_execute(
        _conn: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        normalized = " ".join(statement.split())

        if normalized.upper().startswith(("SELECT ", "WITH ")):
            statements.append(normalized)

    event.listen(
        target,
        "before_cursor_execute",
        before_cursor_execute,
    )

    try:
        yield statements
    finally:
        event.remove(
            target,
            "before_cursor_execute",
            before_cursor_execute,
        )


async def test_procurement_list_summary_does_not_load_full_history(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db

    initiator, _ = await actor(
        db,
        UserRole.ADMIN,
    )

    manager, _ = await actor(
        db,
        UserRole.MANAGER,
    )

    initiator_id = initiator.id
    manager_id = manager.id

    item_id = await create_item(
        db,
        cable_payload(),
    )

    await create_request(
        db,
        ProcurementRequestCreate(
            assigned_manager_user_id=manager_id,
            general_comment="CP06 summary query",
            client_request_id=uuid.uuid4().hex,
            lines=[
                ExistingItemLineCreate(
                    line_type=(ProcurementLineType.EXISTING_ITEM),
                    item_id=item_id,
                    quantity=1,
                )
            ],
        ),
        actor_user_id=initiator_id,
        settings=Settings(app_env="test"),
    )

    await db.flush()
    db.expire_all()

    async with captured_statements(db) as statements:
        page = await list_requests(
            db,
            actor_user_id=manager_id,
            view="active",
            limit=30,
            offset=0,
        )

    assert page.total >= 1
    assert page.items

    lowered = [statement.lower() for statement in statements]

    forbidden_tables = (
        "procurement_events",
        "procurement_revision_lines",
        "procurement_line_catalog_bindings",
    )

    history_statements = [
        statement for statement in lowered if any(table in statement for table in forbidden_tables)
    ]

    assert not history_statements, (
        "CP06 summary list must not load full "
        "Procurement history; "
        f"history_sql={history_statements}"
    )

    assert len(statements) <= 4, (
        "CP06 Procurement summary query count "
        "must remain bounded; "
        f"queries={len(statements)} "
        f"sql={lowered}"
    )


def proposed_line() -> ProposedItemLineCreate:
    draft = cable_payload()

    return ProposedItemLineCreate(
        line_type=ProcurementLineType.PROPOSED_ITEM,
        category_key=draft.category_key,
        manufacturer_id=draft.manufacturer_id,
        name=draft.name,
        model=draft.model,
        attributes=draft.attributes,
        quantity=1,
    )


async def prepare_line_query_counts(
    db: AsyncSession,
    *,
    item_id: uuid.UUID,
    mode: str,
) -> dict[int, int]:
    counts: dict[int, int] = {}

    if mode == "existing":
        template = ExistingItemLineCreate(
            line_type=ProcurementLineType.EXISTING_ITEM,
            item_id=item_id,
            quantity=1,
        )
    else:
        template = proposed_line()

    for size in (
        1,
        100,
        500,
    ):
        db.expire_all()

        async with captured_statements(db) as statements:
            rows = await _prepare_lines(
                db,
                [template for _ in range(size)],
                uuid.uuid4(),
            )

        assert len(rows) == size

        counts[size] = len(statements)

    return counts


@pytest.mark.parametrize(
    "mode",
    [
        "existing",
        "proposed",
    ],
)
async def test_prepare_lines_query_count_is_bounded_by_metadata_not_line_count(
    warehouse_db: AsyncSession,
    mode: str,
) -> None:
    db = warehouse_db

    item_id = await create_item(
        db,
        cable_payload(),
    )

    counts = await prepare_line_query_counts(
        db,
        item_id=item_id,
        mode=mode,
    )

    baseline = counts[1]
    allowed = baseline + 6

    assert counts[100] <= allowed, (
        "CP06 prepare-lines query count must stay "
        "bounded as line count grows; "
        f"mode={mode} counts={counts} "
        f"allowed={allowed}"
    )

    assert counts[500] <= allowed, (
        "CP06 prepare-lines query count must stay "
        "bounded as line count grows; "
        f"mode={mode} counts={counts} "
        f"allowed={allowed}"
    )
