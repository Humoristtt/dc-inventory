"""PostgreSQL regressions for journal-controlled warehouse projections."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.modules.identity.enums import UserRole
from app.modules.inventory.models import StockBalance, UserItemCustodyBalance
from tests.migration_helpers import alembic
from tests.warehouse_helpers import move, scenario

pytestmark = pytest.mark.asyncio

PREVIOUS_HEAD = "c1d2e3f4a5b6"
CURRENT_HEAD = "d2e3f4a5b6c7"


async def _reconciliation_rows(db: AsyncSession) -> list[object]:
    sql = (
        Path(__file__).parents[1]
        / "scripts"
        / "reconcile_inventory_projections.sql"
    ).read_text()
    return list((await db.execute(text(sql))).all())


async def test_d2_service_keeps_stock_and_custody_equal_to_journal(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    state = await scenario(db, UserRole.ENGINEER)

    receipt = await move(
        db,
        state,
        "RECEIPT",
        10,
        destination=state[2],
        key="d2-receipt",
    )
    issue = await move(
        db,
        state,
        "ISSUE",
        4,
        source=state[2],
        custody_user_id=state[0],
        key="d2-issue",
    )

    assert (
        await db.scalar(
            select(StockBalance.quantity).where(
                StockBalance.item_id == state[1],
                StockBalance.location_id == state[2],
            )
        )
        == 6
    )
    assert (
        await db.scalar(
            select(UserItemCustodyBalance.quantity).where(
                UserItemCustodyBalance.user_id == state[0],
                UserItemCustodyBalance.item_id == state[1],
            )
        )
        == 4
    )

    # The DB writer is idempotent because it derives projections from the
    # immutable journal instead of re-applying a caller-provided delta.
    for movement_id in (
        receipt.record.movement.id,
        issue.record.movement.id,
        issue.record.movement.id,
    ):
        await db.execute(
            text(
                "SELECT refresh_warehouse_projection("
                "CAST(:movement_id AS uuid), CAST(:item_id AS uuid)"
                ")"
            ),
            {
                "movement_id": str(movement_id),
                "item_id": str(state[1]),
            },
        )

    assert not await _reconciliation_rows(db)


async def test_d2_upgrade_refuses_existing_projection_drift(
    migration_database: str,
) -> None:
    url = migration_database
    alembic(url, "upgrade", CURRENT_HEAD)

    engine = create_async_engine(url)

    async with AsyncSession(engine, expire_on_commit=False) as db:
        async with db.begin():
            state = await scenario(db)
            await move(
                db,
                state,
                "RECEIPT",
                5,
                destination=state[2],
                key="d2-preflight-receipt",
            )
            item_id = state[1]
            location_id = state[2]

    alembic(url, "downgrade", PREVIOUS_HEAD)

    async with engine.begin() as db:
        await db.execute(
            update(StockBalance)
            .where(
                StockBalance.item_id == item_id,
                StockBalance.location_id == location_id,
            )
            .values(quantity=6)
        )

    output = alembic(
        url,
        "upgrade",
        CURRENT_HEAD,
        success=False,
    )
    assert "warehouse projection drift exists" in output

    async with engine.connect() as db:
        assert (
            await db.scalar(text("SELECT version_num FROM alembic_version"))
            == PREVIOUS_HEAD
        )
        assert (
            await db.scalar(
                select(StockBalance.quantity).where(
                    StockBalance.item_id == item_id,
                    StockBalance.location_id == location_id,
                )
            )
            == 6
        )

    await engine.dispose()
