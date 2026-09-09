from __future__ import annotations

import datetime as datetime_module
import hashlib
import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.modules.catalog.enums import ItemStatus
from app.modules.catalog.models import Item, Manufacturer
from app.modules.catalog.normalization import identity_text
from app.modules.identity.enums import UserAccessStatus, UserRole
from app.modules.identity.models import TelegramIdentity, User
from app.modules.inventory.enums import LocationStatus, MovementType
from app.modules.inventory.models import (
    Location,
    Movement,
    MovementLine,
    StockBalance,
    UserItemCustodyBalance,
)
from app.modules.inventory.schemas import (
    LocationCreate,
    LocationPatch,
    MovementCreate,
    MovementLineCreate,
    MovementReversalCreate,
)


async def create_location(db: AsyncSession, payload: LocationCreate) -> Location:
    code = normalize_inline_text(payload.code, field="code", max_length=64)
    normalized_code = identity_text(code)
    if len(normalized_code) > 64:
        raise InventoryValidationError("normalized location code exceeds 64 characters")
    location = Location(
        code=code,
        normalized_code=normalized_code,
        name=normalize_inline_text(payload.name, field="name", max_length=255),
        location_type=payload.location_type,
        address=normalize_optional_text(payload.address),
        status=LocationStatus.ACTIVE,
    )
    db.add(location)
    await db.flush()
    return location


async def update_location(
    db: AsyncSession, location_id: uuid.UUID, payload: LocationPatch
) -> Location:
    location = await db.scalar(select(Location).where(Location.id == location_id).with_for_update())
    if location is None:
        raise InventoryNotFoundError("location not found")
    location.name = normalize_inline_text(payload.name, field="name", max_length=255)
    location.location_type = payload.location_type
    location.address = normalize_optional_text(payload.address)
    await db.flush()
    return location


async def set_location_archived(
    db: AsyncSession, location_id: uuid.UUID, *, archived: bool, now: datetime | None = None
) -> Location:
    location = await db.scalar(select(Location).where(Location.id == location_id).with_for_update())
    if location is None:
        raise InventoryNotFoundError("location not found")
    if archived and await db.scalar(
        select(StockBalance.id).where(StockBalance.location_id == location_id).limit(1)
    ):
        raise InventoryConflictError(
            "location with stock cannot be archived", code="location_not_empty"
        )
    location.status = LocationStatus.ARCHIVED if archived else LocationStatus.ACTIVE
    location.archived_at = (now or datetime.now(UTC)) if archived else None
    await db.flush()
    return location


def validate_positions(payload: MovementCreate) -> None:
    source, destination = payload.source_location_id, payload.destination_location_id
    if source is not None and source == destination:
        raise InventoryValidationError("source and destination must differ", code="same_location")
    shape = (source is not None, destination is not None)
    allowed = {
        MovementType.RECEIPT: {(False, True)},
        MovementType.RETURN: {(False, True)},
        MovementType.ISSUE: {(True, False)},
        MovementType.WRITE_OFF: {(True, False)},
        MovementType.TRANSFER: {(True, True)},
        MovementType.CORRECTION: {(True, False), (False, True), (True, True)},
        MovementType.REVERSAL: {(True, False), (False, True), (True, True)},
    }
    if shape not in allowed[payload.movement_type]:
        raise InventoryValidationError(
            "invalid movement locations", code="movement_positions_invalid"
        )
    linked = payload.movement_type in {MovementType.CORRECTION, MovementType.REVERSAL}
    if linked != (payload.original_movement_id is not None):
        raise InventoryValidationError("invalid original movement relationship")


async def create_movement(
    db: AsyncSession,
    payload: MovementCreate,
    *,
    actor_user_id: uuid.UUID,
    actor_display_name: str,
    custody_user_id: uuid.UUID | None = None,
) -> MovementResult:
    if payload.movement_type == MovementType.REVERSAL:
        raise InventoryValidationError("use the reversal endpoint")
    return await _create_movement(
        db,
        payload,
        actor_user_id=actor_user_id,
        actor_display_name=actor_display_name,
        custody_user_id=custody_user_id,
    )


async def _movement_timestamp(
    db: AsyncSession,
) -> datetime:
    value = await db.scalar(
        select(func.clock_timestamp())
    )
    if not isinstance(
        value,
        datetime_module.datetime,
    ):
        raise RuntimeError(
            "database did not return a movement timestamp"
        )
    return value


async def _create_movement(
    db: AsyncSession,
    payload: MovementCreate,
    *,
    actor_user_id: uuid.UUID,
    actor_display_name: str,
    custody_user_id: uuid.UUID | None = None,
) -> MovementResult:
    """Caller owns transaction.

    Lock order: request, custody user, original, locations, items, stock, custody.

    Locking every involved item also serializes creation of previously absent
    stock and custody rows. Both projections and the sealed movement commit or
    roll back together.
    """
    if payload.movement_type != MovementType.REVERSAL:
        if custody_user_id is not None and payload.movement_type not in {
            MovementType.ISSUE,
            MovementType.RETURN,
        }:
            raise InventoryValidationError(
                "custody is only valid for issue or return",
                code="custody_movement_type_invalid",
            )
        if custody_user_id is not None and custody_user_id != actor_user_id:
            raise InventoryValidationError(
                "custody user must match movement actor",
                code="custody_actor_mismatch",
            )
    request_id = normalize_inline_text(
        payload.client_request_id, field="client_request_id", max_length=128
    )
    canonical = payload.model_dump(mode="json")
    canonical["client_request_id"] = request_id
    canonical["custody_user_id"] = str(custody_user_id) if custody_user_id else None
    canonical["lines"] = sorted(canonical["lines"], key=lambda line: line["item_id"])
    fingerprint = _fingerprint(canonical)
    await _lock_idempotency_key(db, actor_user_id, request_id)
    existing = await _existing_idempotent_result(
        db,
        actor_user_id=actor_user_id,
        client_request_id=request_id,
        request_fingerprint=fingerprint,
    )
    if existing:
        return existing

    # Every transaction capable of appending to the immutable journal holds a
    # shared barrier lock until commit/rollback. A first-page feed snapshot
    # takes the matching exclusive lock, which drains already-running journal
    # writers before fixing its timestamp.
    await _lock_journal_mutation(db)

    movement_occurred_at = await _movement_timestamp(db)

    custody_user: User | None = None

    if custody_user_id is not None:
        # Serialize custody-changing warehouse operations with administrative
        # APPROVED -> BLOCKED transitions. update_user_access() locks the same
        # users row before it checks whether blocking is allowed.
        custody_user = await db.scalar(
            select(User)
            .where(User.id == custody_user_id)
            .with_for_update()
        )

        if custody_user is None:
            raise InventoryNotFoundError(
                "custody user not found",
                code="custody_user_not_found",
            )

        if (
            payload.movement_type != MovementType.REVERSAL
            and (
                custody_user.role != UserRole.USER
                or custody_user.access_status
                != UserAccessStatus.APPROVED
            )
        ):
            raise InventoryConflictError(
                "custody user is not an approved user",
                code="custody_user_not_approved",
            )

    validate_positions(payload)
    original: MovementRecord | None = None
    if payload.original_movement_id:
        await _lock_original_movement_context(db, payload.original_movement_id)
        original = await get_movement_record(db, payload.original_movement_id)
        if original.movement.movement_type == MovementType.REVERSAL:
            raise InventoryValidationError("invalid correction/reversal target")
        if (
            payload.movement_type == MovementType.CORRECTION
            and original.movement.custody_user_id is not None
        ):
            raise InventoryValidationError(
                "correction of a custody movement is forbidden",
                code="custody_correction_forbidden",
            )
        if (
            payload.movement_type == MovementType.REVERSAL
            and custody_user_id != original.movement.custody_user_id
        ):
            raise InventoryValidationError(
                "reversal custody must match original movement",
                code="reversal_custody_mismatch",
            )
        if payload.movement_type == MovementType.REVERSAL and await db.scalar(
            select(Movement.id).where(
                Movement.original_movement_id == payload.original_movement_id,
                Movement.movement_type == MovementType.REVERSAL,
            )
        ):
            raise InventoryConflictError(
                "movement already reversed", code="movement_already_reversed"
            )

        # Reversing a RETURN recreates employee custody. It must therefore
        # obey the same approved-user boundary as a normal ISSUE.
        #
        # A reversal that reduces custody is not rejected here: that remains
        # available as an administrative repair path.
        if (
            payload.movement_type == MovementType.REVERSAL
            and custody_user_id is not None
            and _custody_delta(payload.movement_type, original) > 0
            and (
                custody_user is None
                or custody_user.role != UserRole.USER
                or custody_user.access_status
                != UserAccessStatus.APPROVED
            )
        ):
            raise InventoryConflictError(
                "custody user is not an approved user",
                code="custody_user_not_approved",
            )

    location_ids = {x for x in (payload.source_location_id, payload.destination_location_id) if x}
    locations = {
        x.id: x
        for x in (
            await db.scalars(
                select(Location)
                .where(Location.id.in_(location_ids))
                .order_by(Location.id)
                .with_for_update()
            )
        ).all()
    }
    if set(locations) != location_ids:
        raise InventoryNotFoundError("location not found")
    if any(x.status != LocationStatus.ACTIVE for x in locations.values()):
        raise InventoryConflictError("archived location cannot be used", code="location_archived")
    item_ids = {line.item_id for line in payload.lines}
    if len(item_ids) != len(payload.lines):
        raise InventoryValidationError("each item must occur once per movement")
    items = {
        x.id: x
        for x in (
            await db.scalars(
                select(Item).where(Item.id.in_(item_ids)).order_by(Item.id).with_for_update()
            )
        ).all()
    }
    if set(items) != item_ids:
        raise InventoryNotFoundError("item not found")
    if payload.movement_type in {MovementType.RECEIPT, MovementType.ISSUE} and any(
        x.status != ItemStatus.ACTIVE for x in items.values()
    ):
        raise InventoryConflictError("archived item cannot be received or issued")
    if original and payload.movement_type == MovementType.CORRECTION:
        original_locations = {
            original.movement.source_location_id,
            original.movement.destination_location_id,
        } - {None}
        if not location_ids.intersection(original_locations) or not item_ids.issubset(
            {line.item_id for line in original.lines}
        ):
            raise InventoryValidationError("correction must concern an original item and location")
    manufacturers = {
        x.id: x.name
        for x in (
            await db.scalars(
                select(Manufacturer).where(
                    Manufacturer.id.in_(
                        {x.manufacturer_id for x in items.values() if x.manufacturer_id}
                    )
                )
            )
        ).all()
    }
    source = locations.get(payload.source_location_id) if payload.source_location_id else None
    destination = (
        locations.get(payload.destination_location_id) if payload.destination_location_id else None
    )
    # The request is bounded to 500 items and two locations. Item locks above
    # serialize missing-row creation as well as existing-row updates. Lock all
    # balances in one deterministic statement before applying any deltas.
    balances = {
        (balance.item_id, balance.location_id): balance
        for balance in (
            await db.scalars(
                select(StockBalance)
                .where(
                    StockBalance.item_id.in_(item_ids),
                    StockBalance.location_id.in_(location_ids),
                )
                .order_by(StockBalance.item_id, StockBalance.location_id)
                .with_for_update()
            )
        ).all()
    }
    custody_balances: dict[uuid.UUID, UserItemCustodyBalance] = {}
    if custody_user_id is not None:
        custody_balances = {
            balance.item_id: balance
            for balance in (
                await db.scalars(
                    select(UserItemCustodyBalance)
                    .where(
                        UserItemCustodyBalance.user_id == custody_user_id,
                        UserItemCustodyBalance.item_id.in_(item_ids),
                    )
                    .order_by(UserItemCustodyBalance.item_id)
                    .with_for_update()
                )
            ).all()
        }
    movement = Movement(
        id=uuid.uuid4(),
        movement_type=payload.movement_type,
        line_count=len(payload.lines),
        actor_user_id=actor_user_id,
        custody_user_id=custody_user_id,
        actor_display_name_snapshot=normalize_inline_text(
            actor_display_name, field="actor", max_length=579
        ),
        source_location_id=payload.source_location_id,
        destination_location_id=payload.destination_location_id,
        source_location_code_snapshot=source.code if source else None,
        source_location_name_snapshot=source.name if source else None,
        destination_location_code_snapshot=destination.code if destination else None,
        destination_location_name_snapshot=destination.name if destination else None,
        original_movement_id=payload.original_movement_id,
        client_request_id=request_id,
        request_fingerprint=fingerprint,
        occurred_at=movement_occurred_at,
    )
    db.add(movement)
    await db.flush()
    movement_lines = []
    for number, line in enumerate(sorted(payload.lines, key=lambda x: x.item_id), 1):
        if line.quantity <= 0:
            raise InventoryValidationError("quantity must be positive")
        for location_id, delta in (
            (payload.source_location_id, -line.quantity),
            (payload.destination_location_id, line.quantity),
        ):
            if location_id is None:
                continue
            balance = balances.get((line.item_id, location_id))
            quantity = (balance.quantity if balance else 0) + delta
            if quantity < 0:
                raise InventoryConflictError("insufficient stock", code="insufficient_stock")
            if quantity > 2**53 - 1:
                raise InventoryConflictError(
                    "quantity exceeds supported range", code="quantity_overflow"
                )
            if balance is not None:
                if quantity == 0:
                    await db.delete(balance)
                else:
                    balance.quantity = quantity
            elif quantity:
                db.add(
                    StockBalance(item_id=line.item_id, location_id=location_id, quantity=quantity)
                )
        custody_delta = _custody_delta(payload.movement_type, original) * line.quantity
        if custody_user_id is not None and custody_delta:
            custody_balance = custody_balances.get(line.item_id)
            custody_quantity = (
                custody_balance.quantity if custody_balance is not None else 0
            ) + custody_delta
            if custody_quantity < 0:
                raise InventoryConflictError(
                    "insufficient user custody",
                    code="insufficient_custody",
                )
            if custody_quantity > 2**53 - 1:
                raise InventoryConflictError(
                    "quantity exceeds supported range",
                    code="quantity_overflow",
                )
            if custody_balance is not None:
                if custody_quantity == 0:
                    await db.delete(custody_balance)
                else:
                    custody_balance.quantity = custody_quantity
            elif custody_quantity:
                new_custody_balance = UserItemCustodyBalance(
                    user_id=custody_user_id,
                    item_id=line.item_id,
                    quantity=custody_quantity,
                )
                db.add(new_custody_balance)
                custody_balances[line.item_id] = new_custody_balance
        item = items[line.item_id]
        movement_lines.append(
            MovementLine(
                movement_id=movement.id,
                line_no=number,
                item_id=item.id,
                quantity=line.quantity,
                item_name_snapshot=item.name,
                model_snapshot=item.model,
                manufacturer_name_snapshot=manufacturers.get(item.manufacturer_id)
                if item.manufacturer_id
                else None,
            )
        )
    db.add_all(movement_lines)
    await db.flush()
    return MovementResult(MovementRecord(movement, movement_lines), replayed=False)


async def reverse_movement(
    db: AsyncSession,
    original_movement_id: uuid.UUID,
    payload: MovementReversalCreate,
    *,
    actor_user_id: uuid.UUID,
    actor_display_name: str,
) -> MovementResult:
    original = await get_movement_record(db, original_movement_id)
    return await _create_movement(
        db,
        MovementCreate(
            movement_type=MovementType.REVERSAL,
            original_movement_id=original_movement_id,
            client_request_id=payload.client_request_id,
            source_location_id=original.movement.destination_location_id,
            destination_location_id=original.movement.source_location_id,
            lines=[
                MovementLineCreate(item_id=x.item_id, quantity=x.quantity) for x in original.lines
            ],
        ),
        actor_user_id=actor_user_id,
        actor_display_name=actor_display_name,
        custody_user_id=original.movement.custody_user_id,
    )


def _custody_delta(
    movement_type: MovementType,
    original: MovementRecord | None,
) -> int:
    if movement_type == MovementType.ISSUE:
        return 1
    if movement_type == MovementType.RETURN:
        return -1
    if movement_type != MovementType.REVERSAL or original is None:
        return 0
    if original.movement.movement_type == MovementType.ISSUE:
        return -1
    if original.movement.movement_type == MovementType.RETURN:
        return 1
    return 0


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


class InventoryError(RuntimeError):
    code = "inventory_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class InventoryValidationError(InventoryError):
    code = "inventory_validation_error"


class InventoryNotFoundError(InventoryError):
    code = "inventory_not_found"


class InventoryConflictError(InventoryError):
    code = "inventory_conflict"


@dataclass(frozen=True, slots=True)
class LocationPage:
    items: list[Location]
    total: int


@dataclass(frozen=True, slots=True)
class StockBalanceRecord:
    balance: StockBalance
    item: Item
    location: Location


@dataclass(frozen=True, slots=True)
class StockBalancePage:
    items: list[StockBalanceRecord]
    total: int


@dataclass(frozen=True, slots=True)
class MovementRecord:
    movement: Movement
    lines: list[MovementLine]


@dataclass(frozen=True, slots=True)
class MovementPage:
    items: list[MovementRecord]
    total: int


@dataclass(frozen=True, slots=True)
class MovementCursorPage:
    items: list[MovementRecord]
    next_before_journal_seq: int | None


@dataclass(frozen=True, slots=True)
class MovementResult:
    record: MovementRecord
    replayed: bool


def normalize_inline_text(value: str, *, field: str, max_length: int) -> str:
    normalized = " ".join(value.split())
    if not normalized:
        raise InventoryValidationError(
            f"{field} must not be blank",
            code=f"{field}_required",
        )
    if len(normalized) > max_length:
        raise InventoryValidationError(
            f"{field} exceeds {max_length} characters",
            code=f"{field}_too_long",
        )
    return normalized


def normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def display_identity(identity: TelegramIdentity) -> str:
    full_name = " ".join(value for value in (identity.first_name, identity.last_name) if value)
    if identity.username:
        return f"{full_name} (@{identity.username})"
    return full_name


def _fingerprint(payload: Mapping[str, object]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _advisory_lock_key(namespace: str, *parts: object) -> int:
    value = "|".join([namespace, *(str(part) for part in parts)])
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


_JOURNAL_SNAPSHOT_LOCK_KEY = _advisory_lock_key(
    "warehouse-journal-snapshot"
)


async def _lock_journal_mutation(
    db: AsyncSession,
) -> None:
    await db.execute(
        select(
            func.pg_advisory_xact_lock_shared(
                _JOURNAL_SNAPSHOT_LOCK_KEY
            )
        )
    )


async def acquire_movement_feed_snapshot(
    db: AsyncSession,
) -> datetime:
    """Create a commit-stable journal timestamp boundary.

    The exclusive transaction-scoped advisory lock waits for every movement
    transaction that already holds the shared journal lock. New journal
    writers cannot cross the boundary until this read transaction finishes.
    clock_timestamp() is intentional: transaction_timestamp()/now() could
    predate the wait itself.
    """
    await db.execute(
        select(
            func.pg_advisory_xact_lock(
                _JOURNAL_SNAPSHOT_LOCK_KEY
            )
        )
    )

    snapshot = await db.scalar(
        select(func.clock_timestamp())
    )

    if not isinstance(snapshot, datetime):
        raise RuntimeError(
            "database did not return a movement feed snapshot timestamp"
        )

    return snapshot


async def _lock_idempotency_key(
    db: AsyncSession,
    actor_user_id: uuid.UUID,
    client_request_id: str,
) -> None:
    await db.execute(
        select(
            func.pg_advisory_xact_lock(
                _advisory_lock_key(
                    "warehouse-idempotency",
                    actor_user_id,
                    client_request_id,
                )
            )
        )
    )


async def _lock_original_movement_context(
    db: AsyncSession,
    movement_id: uuid.UUID,
) -> None:
    await db.execute(
        select(
            func.pg_advisory_xact_lock(
                _advisory_lock_key(
                    "warehouse-original-movement",
                    movement_id,
                )
            )
        )
    )


async def _existing_idempotent_result(
    db: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    client_request_id: str,
    request_fingerprint: str,
) -> MovementResult | None:
    movement = await db.scalar(
        select(Movement)
        .where(
            Movement.actor_user_id == actor_user_id,
            Movement.client_request_id == client_request_id,
        )
        .options(selectinload(Movement.lines))
    )
    if movement is None:
        return None
    if movement.request_fingerprint != request_fingerprint:
        raise InventoryConflictError(
            "idempotency key was already used with a different payload",
            code="idempotency_payload_conflict",
        )
    return MovementResult(
        record=MovementRecord(movement=movement, lines=list(movement.lines)),
        replayed=True,
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
