from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.db.errors import (
    POSTGRES_UNIQUE_VIOLATION_SQLSTATE,
    RETRYABLE_POSTGRES_SQLSTATES,
    postgres_sqlstate,
)
from app.modules.auth.dependencies import Admin, Approved, DbSession
from app.modules.inventory.enums import (
    InventoryUnitState,
    LocationStatus,
    MovementType,
)
from app.modules.inventory.models import Location, MovementLine
from app.modules.inventory.schemas import (
    InventoryUnitListOut,
    InventoryUnitOut,
    LocationCreate,
    LocationListOut,
    LocationOut,
    LocationPositionOut,
    MovementCreate,
    MovementLineOut,
    MovementListOut,
    MovementOut,
    MovementReversalCreate,
    StockBalanceListOut,
    StockBalanceOut,
    UserPositionOut,
)
from app.modules.inventory.service import (
    InventoryConflictError,
    InventoryError,
    InventoryNotFoundError,
    InventoryUnitRecord,
    MovementRecord,
    StockBalanceRecord,
    create_location,
    create_movement,
    display_identity,
    get_inventory_unit_record,
    get_location,
    get_movement_record,
    list_inventory_units,
    list_locations,
    list_movements,
    list_stock_balances,
    reverse_movement,
    set_location_archived,
)

read_router = APIRouter(prefix="/api/inventory", tags=["inventory"])
admin_router = APIRouter(prefix="/api/admin/inventory", tags=["admin-inventory"])


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
    return LocationOut(
        id=location.id,
        code=location.code,
        name=location.name,
        description=location.description,
        status=location.status,
        archived_at=location.archived_at,
        created_at=location.created_at,
        updated_at=location.updated_at,
    )


def _movement_line_out(line: MovementLine) -> MovementLineOut:
    return MovementLineOut(
        id=line.id,
        line_no=line.line_no,
        item_id=line.item_id,
        accounting_mode=line.item_accounting_mode,
        inventory_unit_id=line.inventory_unit_id,
        quantity=line.quantity,
        item_name_snapshot=line.item_name_snapshot,
        manufacturer_name_snapshot=line.manufacturer_name_snapshot,
        model_snapshot=line.model_snapshot,
        manufacturer_part_number_snapshot=line.manufacturer_part_number_snapshot,
        serial_number_snapshot=line.serial_number_snapshot,
        wwn_snapshot=line.wwn_snapshot,
    )


def _movement_out(record: MovementRecord) -> MovementOut:
    movement = record.movement
    return MovementOut(
        id=movement.id,
        journal_seq=movement.journal_seq,
        movement_type=movement.movement_type,
        actor_user_id=movement.actor_user_id,
        actor_display_name_snapshot=movement.actor_display_name_snapshot,
        source_location_id=movement.source_location_id,
        source_location_code_snapshot=movement.source_location_code_snapshot,
        source_location_name_snapshot=movement.source_location_name_snapshot,
        destination_location_id=movement.destination_location_id,
        destination_location_code_snapshot=(movement.destination_location_code_snapshot),
        destination_location_name_snapshot=(movement.destination_location_name_snapshot),
        source_holder_user_id=movement.source_holder_user_id,
        source_holder_display_name_snapshot=(movement.source_holder_display_name_snapshot),
        destination_holder_user_id=movement.destination_holder_user_id,
        destination_holder_display_name_snapshot=(
            movement.destination_holder_display_name_snapshot
        ),
        original_movement_id=movement.original_movement_id,
        client_request_id=movement.client_request_id,
        purpose=movement.purpose,
        comment=movement.comment,
        occurred_at=movement.occurred_at,
        lines=[_movement_line_out(line) for line in record.lines],
    )


def _stock_balance_out(record: StockBalanceRecord) -> StockBalanceOut:
    balance = record.balance
    return StockBalanceOut(
        id=balance.id,
        item_id=balance.item_id,
        item_name=record.item.name,
        quantity=balance.quantity,
        location=(
            LocationPositionOut(
                location_id=record.location.id,
                code=record.location.code,
                name=record.location.name,
            )
            if record.location is not None
            else None
        ),
        holder=(
            UserPositionOut(
                user_id=balance.holder_user_id,
                display_name=record.holder_display_name,
            )
            if balance.holder_user_id is not None and record.holder_display_name is not None
            else None
        ),
        updated_at=balance.updated_at,
    )


def _inventory_unit_out(record: InventoryUnitRecord) -> InventoryUnitOut:
    unit = record.unit
    return InventoryUnitOut(
        id=unit.id,
        item_id=unit.item_id,
        item_name=record.item.name,
        serial_number=unit.serial_number,
        wwn=unit.wwn,
        comment=unit.comment,
        state=unit.state,
        location=(
            LocationPositionOut(
                location_id=record.location.id,
                code=record.location.code,
                name=record.location.name,
            )
            if record.location is not None
            else None
        ),
        holder=(
            UserPositionOut(
                user_id=unit.current_holder_user_id,
                display_name=record.holder_display_name,
            )
            if unit.current_holder_user_id is not None and record.holder_display_name is not None
            else None
        ),
        created_at=unit.created_at,
        updated_at=unit.updated_at,
    )


@read_router.get("/locations", response_model=LocationListOut)
async def get_locations(
    db: DbSession,
    _approved: Approved,
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
    _approved: Approved,
) -> LocationOut:
    try:
        return _location_out(await get_location(db, location_id))
    except InventoryError as error:
        _raise_inventory_error(error)


@read_router.get("/stock", response_model=StockBalanceListOut)
async def get_stock(
    db: DbSession,
    _approved: Approved,
    item_id: UUID | None = None,
    location_id: UUID | None = None,
    holder_user_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> StockBalanceListOut:
    page = await list_stock_balances(
        db,
        item_id=item_id,
        location_id=location_id,
        holder_user_id=holder_user_id,
        limit=limit,
        offset=offset,
    )
    return StockBalanceListOut(
        items=[_stock_balance_out(item) for item in page.items],
        total=page.total,
        limit=limit,
        offset=offset,
    )


@read_router.get("/units", response_model=InventoryUnitListOut)
async def get_inventory_units(
    db: DbSession,
    _approved: Approved,
    item_id: UUID | None = None,
    unit_state: Annotated[InventoryUnitState | None, Query(alias="state")] = None,
    location_id: UUID | None = None,
    holder_user_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> InventoryUnitListOut:
    page = await list_inventory_units(
        db,
        item_id=item_id,
        state=unit_state,
        location_id=location_id,
        holder_user_id=holder_user_id,
        limit=limit,
        offset=offset,
    )
    return InventoryUnitListOut(
        items=[_inventory_unit_out(item) for item in page.items],
        total=page.total,
        limit=limit,
        offset=offset,
    )


@read_router.get("/units/{unit_id}", response_model=InventoryUnitOut)
async def get_inventory_unit(
    unit_id: UUID,
    db: DbSession,
    _approved: Approved,
) -> InventoryUnitOut:
    try:
        return _inventory_unit_out(await get_inventory_unit_record(db, unit_id))
    except InventoryError as error:
        _raise_inventory_error(error)


@read_router.get("/movements", response_model=MovementListOut)
async def get_movements(
    db: DbSession,
    _approved: Approved,
    movement_type: MovementType | None = None,
    item_id: UUID | None = None,
    inventory_unit_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MovementListOut:
    page = await list_movements(
        db,
        movement_type=movement_type,
        item_id=item_id,
        inventory_unit_id=inventory_unit_id,
        limit=limit,
        offset=offset,
    )
    return MovementListOut(
        items=[_movement_out(item) for item in page.items],
        total=page.total,
        limit=limit,
        offset=offset,
    )


@read_router.get("/movements/{movement_id}", response_model=MovementOut)
async def get_movement(
    movement_id: UUID,
    db: DbSession,
    _approved: Approved,
) -> MovementOut:
    try:
        return _movement_out(await get_movement_record(db, movement_id))
    except InventoryError as error:
        _raise_inventory_error(error)


@admin_router.post(
    "/locations",
    response_model=LocationOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_location(
    payload: LocationCreate,
    db: DbSession,
    _admin: Admin,
) -> LocationOut:
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
    db: DbSession,
    _admin: Admin,
) -> LocationOut:
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
    db: DbSession,
    _admin: Admin,
) -> LocationOut:
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


@admin_router.post(
    "/movements",
    response_model=MovementOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_movement(
    payload: MovementCreate,
    db: DbSession,
    admin: Admin,
) -> MovementOut:
    try:
        result = await create_movement(
            db,
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


@admin_router.post(
    "/movements/{movement_id}/reversal",
    response_model=MovementOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_movement_reversal(
    movement_id: UUID,
    payload: MovementReversalCreate,
    db: DbSession,
    admin: Admin,
) -> MovementOut:
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
