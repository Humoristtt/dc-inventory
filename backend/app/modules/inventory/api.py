import calendar
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, NoReturn
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.config import Settings
from app.core.safety import require_real_inventory_mutations_enabled
from app.db.errors import (
    POSTGRES_CHECK_VIOLATION_SQLSTATE,
    POSTGRES_UNIQUE_VIOLATION_SQLSTATE,
    RETRYABLE_POSTGRES_SQLSTATES,
    postgres_error_message,
    postgres_sqlstate,
)
from app.modules.auth.dependencies import (
    DbSession,
    InventoryAdmin,
    InventoryOperate,
    InventoryRead,
    MovementRead,
)
from app.modules.catalog.api import _raise_catalog_error
from app.modules.catalog.models import Item
from app.modules.catalog.service import CatalogError
from app.modules.identity.policy import CUSTODY_ROLES, Capability, has_capability
from app.modules.inventory.enums import (
    LocationStatus,
    MovementType,
)
from app.modules.inventory.models import Location, Movement, StockBalance
from app.modules.inventory.schemas import (
    InventoryCurrentSummaryOut,
    LocationCreate,
    LocationListOut,
    LocationOut,
    LocationPatch,
    LocationPositionOut,
    MovementCreate,
    MovementCursorListOut,
    MovementListOut,
    MovementOut,
    MovementReversalCreate,
    StockBalanceListOut,
    StockBalanceOut,
)
from app.modules.inventory.service import (
    InventoryConflictError,
    InventoryError,
    InventoryNotFoundError,
    MovementRecord,
    StockBalanceRecord,
    acquire_movement_feed_snapshot,
    create_location,
    create_movement,
    display_identity,
    get_location,
    get_movement_record,
    list_locations,
    list_movements,
    list_movements_cursor,
    list_stock_balances,
    reverse_movement,
    set_location_archived,
    update_location,
)
from app.modules.notifications.service import (
    enqueue_telegram_call,
    notification_dedupe_key,
)

read_router = APIRouter(prefix="/api/inventory", tags=["inventory"])
admin_router = APIRouter(prefix="/api/admin/inventory", tags=["admin-inventory"])


_CUSTODY_TRIGGER_CONFLICT_CODES = {
    "custody is only valid for issue, return, or reversal":
        "custody_movement_type_invalid",
    "user issue/return custody must match movement actor":
        "custody_actor_mismatch",
    "admin issue/return must not carry custody":
        "custody_admin_invalid",
    "correction of custody movement is forbidden":
        "custody_correction_forbidden",
    "reversal original movement not found":
        "reversal_original_not_found",
    "reversal custody must match original movement":
        "reversal_custody_mismatch",
    "custody reversal requires issue or return original":
        "reversal_custody_original_invalid",
}


async def _enqueue_issue_admin_notification(
    db: DbSession,
    *,
    record: MovementRecord,
    settings: Settings,
) -> None:
    admin_id = settings.admin_telegram_user_id
    if admin_id is None:
        return

    movement = record.movement
    if movement.movement_type != MovementType.ISSUE:
        return

    lines = []
    for line in record.lines:
        title = line.item_name_snapshot
        if line.manufacturer_name_snapshot:
            title = f"{line.manufacturer_name_snapshot} {title}"
        if line.model_snapshot:
            title = f"{title} ({line.model_snapshot})"
        lines.append(f"• {title} — {line.quantity} шт.")

    location = (
        movement.source_location_name_snapshot
        or movement.source_location_code_snapshot
        or "не указано"
    )

    await enqueue_telegram_call(
        db,
        method="sendMessage",
        payload={
            "chat_id": admin_id,
            "text": (
                "📦 Выдача оборудования\n\n"
                f"Сотрудник: {movement.actor_display_name_snapshot}\n"
                f"Откуда: {location}\n\n" + "\n".join(lines)
            ),
        },
        dedupe_key=notification_dedupe_key(
            "inventory-issue",
            movement.id,
            "admin",
        ),
    )


def _raise_inventory_error(error: InventoryError) -> NoReturn:
    if isinstance(error, InventoryNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(error, InventoryConflictError):
        status_code = status.HTTP_409_CONFLICT
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    raise HTTPException(
        status_code=status_code,
        detail={"code": error.code, "message": str(error)},
    ) from error


def _raise_integrity_conflict(error: IntegrityError) -> NoReturn:
    sqlstate = postgres_sqlstate(error)

    if sqlstate in RETRYABLE_POSTGRES_SQLSTATES:
        _raise_retryable_db_conflict(error)

    if sqlstate == POSTGRES_CHECK_VIOLATION_SQLSTATE:
        trigger_message = postgres_error_message(error)
        trigger_code = (
            _CUSTODY_TRIGGER_CONFLICT_CODES.get(trigger_message)
            if trigger_message is not None
            else None
        )

        if trigger_code is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": trigger_code,
                    "message": (
                        "inventory custody constraint "
                        "rejected the operation"
                    ),
                },
            ) from error

    if sqlstate != POSTGRES_UNIQUE_VIOLATION_SQLSTATE:
        raise error

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "inventory_conflict",
            "message": "inventory operation conflicts with current state",
        },
    ) from error


def _raise_retryable_db_conflict(error: DBAPIError) -> NoReturn:
    if postgres_sqlstate(error) not in RETRYABLE_POSTGRES_SQLSTATES:
        raise error
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "inventory_concurrency_conflict",
            "message": "inventory operation conflicted with concurrent activity; retry",
        },
    ) from error


def _location_out(location: Location) -> LocationOut:
    return LocationOut.model_validate(location)


def _movement_out(record: MovementRecord) -> MovementOut:
    return MovementOut.model_validate(
        {
            **{
                key: getattr(record.movement, key)
                for key in MovementOut.model_fields
                if key != "lines"
            },
            "lines": record.lines,
        }
    )


def _stock_balance_out(record: StockBalanceRecord) -> StockBalanceOut:
    return StockBalanceOut(
        id=record.balance.id,
        item_id=record.item.id,
        item_name=record.item.name,
        quantity=record.balance.quantity,
        updated_at=record.balance.updated_at,
        location=LocationPositionOut(
            location_id=record.location.id, code=record.location.code, name=record.location.name
        ),
    )


@read_router.get("/locations", response_model=LocationListOut)
async def get_locations(
    db: DbSession,
    _approved: InventoryRead,
    location_status: Annotated[LocationStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> LocationListOut:
    page = await list_locations(
        db,
        status=location_status,
        limit=limit,
        offset=offset,
    )
    return LocationListOut(
        items=[_location_out(item) for item in page.items],
        total=page.total,
        limit=limit,
        offset=offset,
    )


@read_router.get("/locations/{location_id}", response_model=LocationOut)
async def get_location_detail(
    location_id: UUID,
    db: DbSession,
    _approved: InventoryRead,
) -> LocationOut:
    try:
        return _location_out(await get_location(db, location_id))
    except InventoryError as error:
        _raise_inventory_error(error)


@read_router.get("/items/{item_id}/summary", response_model=InventoryCurrentSummaryOut)
async def get_item_inventory_summary(
    item_id: UUID, db: DbSession, _approved: InventoryRead
) -> InventoryCurrentSummaryOut:
    if await db.get(Item, item_id) is None:
        raise HTTPException(status_code=404, detail="item not found")
    # Item detail includes the complete location breakdown, without a silent page cap.
    rows = (
        await db.execute(
            select(StockBalance, Item, Location)
            .join(Item, Item.id == StockBalance.item_id)
            .join(Location, Location.id == StockBalance.location_id)
            .where(StockBalance.item_id == item_id)
            .order_by(Location.normalized_code)
        )
    ).all()
    balances = [_stock_balance_out(StockBalanceRecord(*row)) for row in rows]
    return InventoryCurrentSummaryOut(
        total_count=sum(x.quantity for x in balances), locations=balances
    )


@read_router.get("/stock", response_model=StockBalanceListOut)
async def get_stock(
    db: DbSession,
    _approved: InventoryRead,
    item_id: UUID | None = None,
    location_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> StockBalanceListOut:
    page = await list_stock_balances(
        db, item_id=item_id, location_id=location_id, limit=limit, offset=offset
    )
    return StockBalanceListOut(
        items=[_stock_balance_out(x) for x in page.items],
        total=page.total,
        limit=limit,
        offset=offset,
    )


@read_router.get("/movement-actors")
async def get_movement_actors(db: DbSession, approved: MovementRead) -> list[dict[str, str]]:
    query = (
        select(Movement.actor_user_id, Movement.actor_display_name_snapshot)
        .distinct(Movement.actor_user_id)
        .order_by(Movement.actor_user_id, Movement.journal_seq.desc())
    )
    if not has_capability(approved.user.role, Capability.MOVEMENT_READ_ALL):
        query = query.where(Movement.actor_user_id == approved.user.id)
    rows = (await db.execute(query)).all()
    return [
        {"id": str(key), "name": value}
        for key, value in sorted(rows, key=lambda row: (row[1], str(row[0])))
    ]


@read_router.get("/movements", response_model=MovementListOut, deprecated=True)
async def get_movements(
    db: DbSession,
    approved: MovementRead,
    movement_type: MovementType | None = None,
    item_id: UUID | None = None,
    actor_user_id: UUID | None = None,
    category: str | None = None,
    long_range: bool = False,
    location_id: UUID | None = None,
    period: Literal["7d", "30d", "3m", "year", "all"] = "3m",
    since: datetime | None = None,
    until: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MovementListOut:
    # Existing journal policy restricted employee-wide history to ADMIN.
    # Users can now see their own immutable actions; no cross-user disclosure.
    if not has_capability(approved.user.role, Capability.MOVEMENT_READ_ALL):
        if actor_user_id is not None and actor_user_id != approved.user.id:
            raise HTTPException(status_code=403, detail="all movement history capability required")
        actor_user_id = approved.user.id
    if since is None and period != "all":
        now = datetime.now(UTC)
        if period in {"7d", "30d"}:
            since = now - timedelta(days=7 if period == "7d" else 30)
        else:
            months = 3 if period == "3m" else 12
            month_index = now.year * 12 + now.month - 1 - months
            year, month = divmod(month_index, 12)
            since = now.replace(
                year=year,
                month=month + 1,
                day=min(now.day, calendar.monthrange(year, month + 1)[1]),
            )
    if any(x is not None and x.tzinfo is None for x in (since, until)):
        raise HTTPException(status_code=422, detail="timestamps require timezone")
    if since and until and since >= until:
        raise HTTPException(status_code=422, detail="invalid period")
    try:
        page = await list_movements(
            db,
            movement_type=movement_type,
            item_id=item_id,
            actor_user_id=actor_user_id,
            category_key=category,
            long_range=long_range,
            location_id=location_id,
            since=since,
            until=until,
            limit=limit,
            offset=offset,
        )
    except CatalogError as error:
        _raise_catalog_error(error)
    return MovementListOut(
        items=[_movement_out(x) for x in page.items], total=page.total, limit=limit, offset=offset
    )


@read_router.get(
    "/movements/feed",
    response_model=MovementCursorListOut,
)
async def get_movement_feed(
    db: DbSession,
    approved: MovementRead,
    movement_type: MovementType | None = None,
    actor_user_id: UUID | None = None,
    category: str | None = None,
    long_range: bool = False,
    location_id: UUID | None = None,
    period: Literal["7d", "30d", "3m", "year", "all"] = "3m",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    before_journal_seq: Annotated[int | None, Query(ge=1)] = None,
    snapshot_at: datetime | None = None,
) -> MovementCursorListOut:
    if not has_capability(approved.user.role, Capability.MOVEMENT_READ_ALL):
        if (
            actor_user_id is not None
            and actor_user_id != approved.user.id
        ):
            raise HTTPException(
                status_code=403,
                detail="all movement history capability required",
            )
        actor_user_id = approved.user.id

    if snapshot_at is None:
        snapshot_at = await acquire_movement_feed_snapshot(db)

    if snapshot_at.tzinfo is None or snapshot_at.year < 2:
        raise HTTPException(status_code=422, detail="snapshot requires timezone and year >= 2")
    since: datetime | None = None

    if period != "all":
        now = snapshot_at

        if period in {"7d", "30d"}:
            since = now - timedelta(
                days=7 if period == "7d" else 30
            )
        else:
            months = 3 if period == "3m" else 12
            month_index = (
                now.year * 12
                + now.month
                - 1
                - months
            )
            year, month = divmod(month_index, 12)

            since = now.replace(
                year=year,
                month=month + 1,
                day=min(
                    now.day,
                    calendar.monthrange(
                        year,
                        month + 1,
                    )[1],
                ),
            )

    try:
        page = await list_movements_cursor(
            db,
            movement_type=movement_type,
            actor_user_id=actor_user_id,
            category_key=category,
            long_range=long_range,
            location_id=location_id,
            since=since,
            until=snapshot_at,
            before_journal_seq=before_journal_seq,
            limit=limit,
        )
    except CatalogError as error:
        _raise_catalog_error(error)

    return MovementCursorListOut(
        items=[
            _movement_out(record)
            for record in page.items
        ],
        limit=limit,
        snapshot_at=snapshot_at,
        next_before_journal_seq=(
            page.next_before_journal_seq
        ),
    )


@read_router.get("/movements/{movement_id}", response_model=MovementOut)
async def get_movement(movement_id: UUID, db: DbSession, approved: MovementRead) -> MovementOut:
    try:
        record = await get_movement_record(db, movement_id)
        if (
            not has_capability(
                approved.user.role,
                Capability.MOVEMENT_READ_ALL,
            )
            and record.movement.actor_user_id != approved.user.id
        ):
            raise HTTPException(status_code=403, detail="all movement history capability required")
        return _movement_out(record)
    except InventoryError as error:
        _raise_inventory_error(error)


@admin_router.patch("/locations/{location_id}", response_model=LocationOut)
async def patch_location(
    location_id: UUID,
    payload: LocationPatch,
    request: Request,
    db: DbSession,
    _admin: InventoryAdmin,
) -> LocationOut:
    require_real_inventory_mutations_enabled(request)
    try:
        location = await update_location(db, location_id, payload)
        await db.commit()
        return _location_out(location)
    except InventoryError as error:
        await db.rollback()
        _raise_inventory_error(error)
    except DBAPIError as error:
        await db.rollback()
        _raise_retryable_db_conflict(error)


@admin_router.post(
    "/locations",
    response_model=LocationOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_location(
    payload: LocationCreate,
    request: Request,
    db: DbSession,
    _admin: InventoryAdmin,
) -> LocationOut:
    require_real_inventory_mutations_enabled(request)
    try:
        location = await create_location(db, payload)
        await db.commit()
    except InventoryError as error:
        await db.rollback()
        _raise_inventory_error(error)
    except IntegrityError as error:
        await db.rollback()
        _raise_integrity_conflict(error)
    except DBAPIError as error:
        await db.rollback()
        _raise_retryable_db_conflict(error)
    return _location_out(location)


@admin_router.post("/locations/{location_id}/archive", response_model=LocationOut)
async def archive_location(
    location_id: UUID,
    request: Request,
    db: DbSession,
    _admin: InventoryAdmin,
) -> LocationOut:
    require_real_inventory_mutations_enabled(request)
    try:
        location = await set_location_archived(db, location_id, archived=True)
        await db.commit()
    except InventoryError as error:
        await db.rollback()
        _raise_inventory_error(error)
    except DBAPIError as error:
        await db.rollback()
        _raise_retryable_db_conflict(error)
    return _location_out(location)


@admin_router.post("/locations/{location_id}/unarchive", response_model=LocationOut)
async def unarchive_location(
    location_id: UUID,
    request: Request,
    db: DbSession,
    _admin: InventoryAdmin,
) -> LocationOut:
    require_real_inventory_mutations_enabled(request)
    try:
        location = await set_location_archived(db, location_id, archived=False)
        await db.commit()
    except InventoryError as error:
        await db.rollback()
        _raise_inventory_error(error)
    except DBAPIError as error:
        await db.rollback()
        _raise_retryable_db_conflict(error)
    return _location_out(location)


@read_router.post(
    "/movements",
    response_model=MovementOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_movement(
    payload: MovementCreate,
    request: Request,
    db: DbSession,
    approved: InventoryOperate,
) -> MovementOut:
    if (
        not has_capability(approved.user.role, Capability.INVENTORY_ADMIN)
        and payload.movement_type not in {
            MovementType.RECEIPT,
            MovementType.ISSUE,
            MovementType.RETURN,
            MovementType.TRANSFER,
        }
    ):
        raise HTTPException(status_code=403, detail="inventory admin capability required")
    require_real_inventory_mutations_enabled(request)
    try:
        result = await create_movement(
            db,
            payload,
            actor_user_id=approved.user.id,
            actor_display_name=display_identity(approved.identity),
            custody_user_id=(
                approved.user.id
                if approved.user.role in CUSTODY_ROLES
                and payload.movement_type in {MovementType.ISSUE, MovementType.RETURN}
                else None
            ),
        )
        await _enqueue_issue_admin_notification(
            db,
            record=result.record,
            settings=request.app.state.settings,
        )
        await db.commit()
    except InventoryError as error:
        await db.rollback()
        _raise_inventory_error(error)
    except IntegrityError as error:
        await db.rollback()
        _raise_integrity_conflict(error)
    except DBAPIError as error:
        await db.rollback()
        _raise_retryable_db_conflict(error)
    return _movement_out(result.record)


@admin_router.post(
    "/movements/{movement_id}/reversal",
    response_model=MovementOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_movement_reversal(
    movement_id: UUID,
    payload: MovementReversalCreate,
    request: Request,
    db: DbSession,
    admin: InventoryAdmin,
) -> MovementOut:
    require_real_inventory_mutations_enabled(request)
    try:
        result = await reverse_movement(
            db,
            movement_id,
            payload,
            actor_user_id=admin.user.id,
            actor_display_name=display_identity(admin.identity),
        )
        await db.commit()
    except InventoryError as error:
        await db.rollback()
        _raise_inventory_error(error)
    except IntegrityError as error:
        await db.rollback()
        _raise_integrity_conflict(error)
    except DBAPIError as error:
        await db.rollback()
        _raise_retryable_db_conflict(error)
    return _movement_out(result.record)
