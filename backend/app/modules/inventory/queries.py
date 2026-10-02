from __future__ import annotations

import uuid
from datetime import datetime
from typing import cast

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.modules.catalog.models import Item
from app.modules.inventory.domain import (
    InventoryNotFoundError,
    LocationPage,
    MovementCursorPage,
    MovementFeedSnapshot,
    MovementPage,
    MovementRecord,
    StockBalancePage,
    StockBalanceRecord,
)
from app.modules.inventory.enums import (
    LocationStatus,
    MovementType,
)
from app.modules.inventory.models import (
    Location,
    Movement,
    MovementLine,
    StockBalance,
)


async def list_stock_balances(
    db: AsyncSession,
    *,
    item_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
    limit: int = 100,
    offset: int = 0,
) -> StockBalancePage:
    filters = []
    if item_id:
        filters.append(StockBalance.item_id == item_id)
    if location_id:
        filters.append(StockBalance.location_id == location_id)
    total = await db.scalar(select(func.count()).select_from(StockBalance).where(*filters))
    rows = (
        await db.execute(
            select(StockBalance, Item, Location)
            .join(Item, Item.id == StockBalance.item_id)
            .join(Location, Location.id == StockBalance.location_id)
            .where(*filters)
            .order_by(Item.normalized_name, Location.normalized_code, StockBalance.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return StockBalancePage([StockBalanceRecord(*row) for row in rows], int(total or 0))


async def _movement_filters(
    db: AsyncSession,
    *,
    movement_type: MovementType | None = None,
    item_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
    category_key: str | None = None,
    long_range: bool = False,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[ColumnElement[bool]]:
    from app.modules.catalog.query import equipment_scope

    filters: list[ColumnElement[bool]] = []

    if movement_type:
        filters.append(Movement.movement_type == movement_type)

    if actor_user_id:
        filters.append(Movement.actor_user_id == actor_user_id)

    if location_id:
        filters.append(
            or_(
                Movement.source_location_id == location_id,
                Movement.destination_location_id == location_id,
            )
        )

    if since:
        filters.append(Movement.occurred_at >= since)

    if until:
        filters.append(Movement.occurred_at < until)

    if item_id or category_key or long_range:
        item_query = select(Item.id).where(
            *await equipment_scope(
                db,
                category_key,
                long_range,
            )
        )

        if item_id:
            item_query = item_query.where(Item.id == item_id)

        filters.append(
            Movement.id.in_(
                select(MovementLine.movement_id).where(
                    MovementLine.item_id.in_(item_query)
                )
            )
        )

    return filters


async def list_movements(
    db: AsyncSession,
    *,
    movement_type: MovementType | None = None,
    item_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
    category_key: str | None = None,
    long_range: bool = False,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> MovementPage:
    filters = await _movement_filters(
        db,
        movement_type=movement_type,
        item_id=item_id,
        actor_user_id=actor_user_id,
        location_id=location_id,
        category_key=category_key,
        long_range=long_range,
        since=since,
        until=until,
    )

    total = await db.scalar(
        select(func.count())
        .select_from(Movement)
        .where(*filters)
    )

    movements = (
        await db.scalars(
            select(Movement)
            .where(*filters)
            .options(selectinload(Movement.lines))
            .order_by(Movement.journal_seq.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()

    return MovementPage(
        [
            MovementRecord(row, list(row.lines))
            for row in movements
        ],
        int(total or 0),
    )


async def list_movements_cursor(
    db: AsyncSession,
    *,
    movement_type: MovementType | None = None,
    item_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
    category_key: str | None = None,
    long_range: bool = False,
    since: datetime | None = None,
    until: datetime | None = None,
    before_journal_seq: int | None = None,
    database_snapshot: str | None = None,
    limit: int = 50,
) -> MovementCursorPage:
    filters = await _movement_filters(
        db,
        movement_type=movement_type,
        item_id=item_id,
        actor_user_id=actor_user_id,
        location_id=location_id,
        category_key=category_key,
        long_range=long_range,
        since=since,
        until=until,
    )

    if database_snapshot is not None:
        filters.append(
            cast(
                ColumnElement[bool],
                text(
                    "("
                    "pg_visible_in_snapshot("
                    "movements.xmin::text::xid8, "
                    "CAST(CAST(:movement_feed_snapshot AS text) "
                    "AS pg_snapshot)"
                    ") OR "
                    "pg_xact_status("
                    "movements.xmin::text::xid8"
                    ") = 'in progress'"
                    ")"
                ).bindparams(
                    movement_feed_snapshot=(
                        database_snapshot
                    )
                ),
            )
        )

    if before_journal_seq is not None:
        filters.append(
            Movement.journal_seq < before_journal_seq
        )

    movements = list(
        (
            await db.scalars(
                select(Movement)
                .where(*filters)
                .options(selectinload(Movement.lines))
                .order_by(Movement.journal_seq.desc())
                .limit(limit + 1)
            )
        ).all()
    )

    has_more = len(movements) > limit
    visible = movements[:limit]

    next_before_journal_seq = (
        visible[-1].journal_seq
        if has_more and visible
        else None
    )

    return MovementCursorPage(
        items=[
            MovementRecord(row, list(row.lines))
            for row in visible
        ],
        next_before_journal_seq=next_before_journal_seq,
    )


async def acquire_movement_feed_snapshot(
    db: AsyncSession,
) -> MovementFeedSnapshot:
    row = (
        await db.execute(
            text(
                "SELECT "
                "clock_timestamp() AS snapshot_at, "
                "pg_current_snapshot()::text "
                "AS database_snapshot"
            )
        )
    ).one()

    snapshot_at = row.snapshot_at
    database_snapshot = row.database_snapshot

    if not isinstance(snapshot_at, datetime):
        raise RuntimeError(
            "database did not return a movement "
            "feed snapshot timestamp"
        )

    if (
        not isinstance(database_snapshot, str)
        or not database_snapshot
    ):
        raise RuntimeError(
            "database did not return a movement "
            "feed MVCC snapshot"
        )

    return MovementFeedSnapshot(
        snapshot_at=snapshot_at,
        database_snapshot=database_snapshot,
    )


async def list_locations(
    db: AsyncSession,
    *,
    status: LocationStatus | None,
    limit: int,
    offset: int,
) -> LocationPage:
    filters = [Location.status == status] if status is not None else []
    total = await db.scalar(select(func.count()).select_from(Location).where(*filters))
    rows = await db.scalars(
        select(Location)
        .where(*filters)
        .order_by(Location.normalized_code, Location.id)
        .limit(limit)
        .offset(offset)
    )
    return LocationPage(items=list(rows.all()), total=total or 0)


async def get_location(db: AsyncSession, location_id: uuid.UUID) -> Location:
    location = await db.get(Location, location_id)
    if location is None:
        raise InventoryNotFoundError("location not found", code="location_not_found")
    return location


async def get_movement_record(
    db: AsyncSession,
    movement_id: uuid.UUID,
) -> MovementRecord:
    movement = await db.scalar(
        select(Movement).where(Movement.id == movement_id).options(selectinload(Movement.lines))
    )
    if movement is None:
        raise InventoryNotFoundError(
            "movement not found",
            code="movement_not_found",
        )
    return MovementRecord(movement=movement, lines=list(movement.lines))
