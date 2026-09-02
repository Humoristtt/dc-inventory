from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.modules.catalog.enums import AccountingMode, ItemStatus
from app.modules.catalog.models import Item, Manufacturer
from app.modules.identity.enums import UserAccessStatus
from app.modules.identity.models import TelegramIdentity, User
from app.modules.inventory.enums import (
    InventoryUnitState,
    LocationStatus,
    MovementType,
)
from app.modules.inventory.models import (
    InventoryUnit,
    Location,
    Movement,
    MovementLine,
    StockBalance,
)
from app.modules.inventory.schemas import (
    LocationCreate,
    MovementCreate,
    MovementLineCreate,
    MovementReversalCreate,
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


POSTGRES_BIGINT_MAX = 2**63 - 1
IDENTITY_DISPLAY_MAX_LENGTH = 579


@dataclass(frozen=True, slots=True)
class Position:
    location_id: uuid.UUID | None = None
    holder_user_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        if (self.location_id is None) == (self.holder_user_id is None):
            raise ValueError("position requires exactly one location or holder")


@dataclass(frozen=True, slots=True)
class LocationPage:
    items: list[Location]
    total: int


@dataclass(frozen=True, slots=True)
class StockBalanceRecord:
    balance: StockBalance
    item: Item
    location: Location | None
    holder_display_name: str | None


@dataclass(frozen=True, slots=True)
class StockBalancePage:
    items: list[StockBalanceRecord]
    total: int


@dataclass(frozen=True, slots=True)
class InventoryUnitRecord:
    unit: InventoryUnit
    item: Item
    location: Location | None
    holder_display_name: str | None


@dataclass(frozen=True, slots=True)
class InventoryUnitPage:
    items: list[InventoryUnitRecord]
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
class MovementResult:
    record: MovementRecord
    replayed: bool


@dataclass(slots=True)
class PreparedLine:
    item: Item
    manufacturer_name: str | None
    quantity: int | None = None
    unit: InventoryUnit | None = None
    new_serial_number: str | None = None
    new_normalized_serial_number: str | None = None
    new_wwn: str | None = None
    new_normalized_wwn: str | None = None
    new_unit_comment: str | None = None


@dataclass(frozen=True, slots=True)
class ParsedSerialLine:
    item_id: uuid.UUID
    serial_number: str
    normalized_serial_number: str
    wwn: str | None
    normalized_wwn: str | None
    unit_comment: str | None


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


def normalize_optional_inline_text(
    value: str | None,
    *,
    field: str,
    max_length: int,
) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split())
    if not normalized:
        return None
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


def normalize_identity(value: str, *, field: str, max_length: int) -> str:
    normalized = normalize_inline_text(
        value,
        field=field,
        max_length=max_length,
    ).casefold()
    if len(normalized) > max_length:
        raise InventoryValidationError(
            f"{field} normalized value exceeds {max_length} characters",
            code=f"{field}_too_long",
        )
    return normalized


def normalize_optional_identity(
    value: str | None,
    *,
    field: str,
    max_length: int,
) -> tuple[str | None, str | None]:
    display_value = normalize_optional_inline_text(
        value,
        field=field,
        max_length=max_length,
    )
    if display_value is None:
        return None, None
    normalized = display_value.casefold()
    if len(normalized) > max_length:
        raise InventoryValidationError(
            f"{field} normalized value exceeds {max_length} characters",
            code=f"{field}_too_long",
        )
    return display_value, normalized


def display_identity(identity: TelegramIdentity) -> str:
    full_name = " ".join(value for value in (identity.first_name, identity.last_name) if value)
    if identity.username:
        return f"{full_name} (@{identity.username})"
    return full_name


def _position(
    location_id: uuid.UUID | None,
    holder_user_id: uuid.UUID | None,
) -> Position | None:
    if location_id is None and holder_user_id is None:
        return None
    if location_id is not None and holder_user_id is not None:
        raise InventoryValidationError(
            "a movement side cannot be both a location and a holder",
            code="position_ambiguous",
        )
    return Position(location_id=location_id, holder_user_id=holder_user_id)


def _positions_equal(left: Position | None, right: Position | None) -> bool:
    return left is not None and left == right


def _validate_operation_positions(
    movement_type: MovementType,
    source: Position | None,
    destination: Position | None,
) -> None:
    valid = False
    if movement_type == MovementType.RECEIPT:
        valid = source is None and destination is not None and destination.location_id is not None
    elif movement_type == MovementType.ISSUE:
        valid = (
            source is not None
            and source.location_id is not None
            and destination is not None
            and destination.holder_user_id is not None
        )
    elif movement_type == MovementType.RETURN:
        valid = (
            source is not None
            and source.holder_user_id is not None
            and destination is not None
            and destination.location_id is not None
        )
    elif movement_type == MovementType.TRANSFER:
        valid = (
            source is not None
            and source.location_id is not None
            and destination is not None
            and destination.location_id is not None
        )
    elif movement_type == MovementType.WRITE_OFF:
        valid = source is not None and destination is None
    elif movement_type in {MovementType.CORRECTION, MovementType.REVERSAL}:
        valid = source is not None or destination is not None

    if not valid or _positions_equal(source, destination):
        raise InventoryValidationError(
            f"invalid positions for {movement_type.value}",
            code="movement_positions_invalid",
        )


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


async def create_location(db: AsyncSession, payload: LocationCreate) -> Location:
    code = normalize_inline_text(payload.code, field="location_code", max_length=64)
    normalized_code = normalize_identity(
        code,
        field="location_code",
        max_length=64,
    )
    if (
        await db.scalar(select(Location.id).where(Location.normalized_code == normalized_code))
        is not None
    ):
        raise InventoryConflictError(
            "location code already exists",
            code="location_code_conflict",
        )
    location = Location(
        code=code,
        normalized_code=normalized_code,
        name=normalize_inline_text(payload.name, field="location_name", max_length=255),
        description=normalize_optional_text(payload.description),
        status=LocationStatus.ACTIVE,
    )
    db.add(location)
    await db.flush()
    return location


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


async def set_location_archived(
    db: AsyncSession,
    location_id: uuid.UUID,
    *,
    archived: bool,
    now: datetime | None = None,
) -> Location:
    location = await db.scalar(select(Location).where(Location.id == location_id).with_for_update())
    if location is None:
        raise InventoryNotFoundError("location not found", code="location_not_found")

    target = LocationStatus.ARCHIVED if archived else LocationStatus.ACTIVE
    if location.status == target:
        return location
    if archived:
        has_balance = await db.scalar(
            select(StockBalance.id).where(StockBalance.location_id == location.id).limit(1)
        )
        has_unit = await db.scalar(
            select(InventoryUnit.id)
            .where(InventoryUnit.current_location_id == location.id)
            .limit(1)
        )
        if has_balance is not None or has_unit is not None:
            raise InventoryConflictError(
                "location with current inventory cannot be archived",
                code="location_not_empty",
            )

    current_time = now or datetime.now(UTC)
    location.status = target
    location.archived_at = current_time if archived else None
    location.updated_at = current_time
    await db.flush()
    return location


async def _load_locations_for_operation(
    db: AsyncSession,
    source: Position | None,
    destination: Position | None,
    *,
    require_active_destination_only: bool,
) -> dict[uuid.UUID, Location]:
    location_ids = sorted(
        {
            position.location_id
            for position in (source, destination)
            if position is not None and position.location_id is not None
        },
        key=str,
    )
    if not location_ids:
        return {}
    rows = list(
        (
            await db.scalars(
                select(Location)
                .where(Location.id.in_(location_ids))
                .order_by(Location.id)
                .with_for_update()
            )
        ).all()
    )
    if len(rows) != len(location_ids):
        raise InventoryNotFoundError(
            "movement location not found",
            code="location_not_found",
        )
    required_active_ids = set(location_ids)
    if require_active_destination_only:
        required_active_ids = (
            {destination.location_id}
            if destination is not None and destination.location_id is not None
            else set()
        )
    if any(row.id in required_active_ids and row.status != LocationStatus.ACTIVE for row in rows):
        raise InventoryConflictError(
            "archived location cannot contain current inventory",
            code="location_archived",
        )
    return {row.id: row for row in rows}


async def _load_holders_for_operation(
    db: AsyncSession,
    source: Position | None,
    destination: Position | None,
    *,
    require_approved_destination: bool,
) -> dict[uuid.UUID, str]:
    holder_ids = sorted(
        {
            position.holder_user_id
            for position in (source, destination)
            if position is not None and position.holder_user_id is not None
        },
        key=str,
    )
    if not holder_ids:
        return {}
    users = list(
        (
            await db.scalars(
                select(User).where(User.id.in_(holder_ids)).order_by(User.id).with_for_update()
            )
        ).all()
    )
    if len(users) != len(holder_ids):
        raise InventoryNotFoundError("holder not found", code="holder_not_found")
    destination_holder_id = destination.holder_user_id if destination is not None else None
    if require_approved_destination and destination_holder_id is not None:
        destination_user = next(user for user in users if user.id == destination_holder_id)
        if destination_user.access_status != UserAccessStatus.APPROVED:
            raise InventoryConflictError(
                "destination holder is not approved",
                code="holder_not_approved",
            )

    identities = list(
        (
            await db.scalars(
                select(TelegramIdentity).where(TelegramIdentity.user_id.in_(holder_ids))
            )
        ).all()
    )
    if len(identities) != len(holder_ids):
        raise InventoryConflictError(
            "holder identity is unavailable",
            code="holder_identity_missing",
        )
    return {identity.user_id: display_identity(identity) for identity in identities}


async def _lock_units(
    db: AsyncSession,
    unit_ids: Sequence[uuid.UUID],
) -> dict[uuid.UUID, InventoryUnit]:
    if not unit_ids:
        return {}
    rows = list(
        (
            await db.scalars(
                select(InventoryUnit)
                .where(InventoryUnit.id.in_(unit_ids))
                .order_by(InventoryUnit.id)
                .with_for_update()
            )
        ).all()
    )
    if len(rows) != len(unit_ids):
        raise InventoryNotFoundError(
            "inventory unit not found",
            code="inventory_unit_not_found",
        )
    return {row.id: row for row in rows}


async def _lock_items(
    db: AsyncSession,
    item_ids: Sequence[uuid.UUID],
) -> dict[uuid.UUID, Item]:
    if not item_ids:
        return {}
    rows = list(
        (
            await db.scalars(
                select(Item).where(Item.id.in_(item_ids)).order_by(Item.id).with_for_update()
            )
        ).all()
    )
    if len(rows) != len(item_ids):
        raise InventoryNotFoundError("item not found", code="item_not_found")
    return {row.id: row for row in rows}


async def _manufacturer_names(
    db: AsyncSession,
    items: Sequence[Item],
) -> dict[uuid.UUID, str]:
    manufacturer_ids = {item.manufacturer_id for item in items if item.manufacturer_id is not None}
    if not manufacturer_ids:
        return {}
    rows = await db.scalars(select(Manufacturer).where(Manufacturer.id.in_(manufacturer_ids)))
    return {row.id: row.name for row in rows.all()}


async def _prepare_lines(
    db: AsyncSession,
    line_payloads: Sequence[MovementLineCreate],
    *,
    serial_creation: bool,
    movement_type: MovementType,
    source: Position | None,
    destination: Position | None,
) -> list[PreparedLine]:
    quantity_item_ids: set[uuid.UUID] = set()
    existing_unit_ids: set[uuid.UUID] = set()
    new_serial_keys: set[tuple[uuid.UUID, str]] = set()
    new_wwn_keys: set[str] = set()
    direct_item_ids: set[uuid.UUID] = set()
    parsed_serial_lines: dict[int, ParsedSerialLine] = {}

    for line_index, line in enumerate(line_payloads):
        if line.quantity is not None:
            if isinstance(line.quantity, bool) or not isinstance(line.quantity, int):
                raise InventoryValidationError(
                    "movement quantity must be an integer",
                    code="quantity_not_integer",
                )
            if line.quantity <= 0:
                raise InventoryValidationError(
                    "movement quantity must be positive",
                    code="quantity_not_positive",
                )
            if line.quantity > POSTGRES_BIGINT_MAX:
                raise InventoryValidationError(
                    "movement quantity exceeds PostgreSQL BIGINT",
                    code="quantity_too_large",
                )
            assert line.item_id is not None
            if line.item_id in quantity_item_ids:
                raise InventoryValidationError(
                    "quantity item may appear only once in a movement",
                    code="duplicate_quantity_line",
                )
            quantity_item_ids.add(line.item_id)
            direct_item_ids.add(line.item_id)
        elif line.inventory_unit_id is not None:
            if serial_creation:
                raise InventoryValidationError(
                    "receipt/correction from outside requires serial identity data",
                    code="serial_identity_required",
                )
            if line.inventory_unit_id in existing_unit_ids:
                raise InventoryValidationError(
                    "inventory unit may appear only once in a movement",
                    code="duplicate_serial_line",
                )
            existing_unit_ids.add(line.inventory_unit_id)
        else:
            if not serial_creation:
                raise InventoryValidationError(
                    "this operation requires an existing inventory unit",
                    code="inventory_unit_required",
                )
            assert line.item_id is not None and line.serial_number is not None
            serial_number = normalize_inline_text(
                line.serial_number,
                field="serial_number",
                max_length=255,
            )
            normalized_serial = normalize_identity(
                serial_number,
                field="serial_number",
                max_length=255,
            )
            key = (line.item_id, normalized_serial)
            if key in new_serial_keys:
                raise InventoryValidationError(
                    "serial identity may appear only once in a movement",
                    code="duplicate_serial_line",
                )
            new_serial_keys.add(key)
            direct_item_ids.add(line.item_id)
            wwn, normalized_wwn = normalize_optional_identity(
                line.wwn,
                field="wwn",
                max_length=255,
            )
            if normalized_wwn is not None:
                if normalized_wwn in new_wwn_keys:
                    raise InventoryValidationError(
                        "WWN identity may appear only once in a movement",
                        code="duplicate_wwn_line",
                    )
                new_wwn_keys.add(normalized_wwn)
            parsed_serial_lines[line_index] = ParsedSerialLine(
                item_id=line.item_id,
                serial_number=serial_number,
                normalized_serial_number=normalized_serial,
                wwn=wwn,
                normalized_wwn=normalized_wwn,
                unit_comment=normalize_optional_text(line.unit_comment),
            )

    identity_lock_keys = {
        _advisory_lock_key("warehouse-serial", item_id, normalized_serial)
        for item_id, normalized_serial in new_serial_keys
    }
    identity_lock_keys.update(
        _advisory_lock_key("warehouse-wwn", normalized_wwn) for normalized_wwn in new_wwn_keys
    )
    for lock_key in sorted(identity_lock_keys):
        await db.execute(select(func.pg_advisory_xact_lock(lock_key)))

    direct_unit_rows = (
        (
            await db.execute(
                select(InventoryUnit.id, InventoryUnit.item_id).where(
                    InventoryUnit.id.in_(existing_unit_ids)
                )
            )
        ).all()
        if existing_unit_ids
        else []
    )
    if len(direct_unit_rows) != len(existing_unit_ids):
        raise InventoryNotFoundError(
            "inventory unit not found",
            code="inventory_unit_not_found",
        )

    reusable_unit_ids: dict[tuple[uuid.UUID, str], uuid.UUID] = {}
    if new_serial_keys:
        reusable_rows = (
            await db.execute(
                select(
                    InventoryUnit.id,
                    InventoryUnit.item_id,
                    InventoryUnit.normalized_serial_number,
                ).where(
                    tuple_(
                        InventoryUnit.item_id,
                        InventoryUnit.normalized_serial_number,
                    ).in_(sorted(new_serial_keys, key=lambda value: (str(value[0]), value[1])))
                )
            )
        ).all()
        reusable_unit_ids = {
            (row.item_id, row.normalized_serial_number): row.id for row in reusable_rows
        }

    all_unit_ids = existing_unit_ids | set(reusable_unit_ids.values())
    units = await _lock_units(db, sorted(all_unit_ids, key=str))
    item_ids = sorted(
        direct_item_ids | {unit.item_id for unit in units.values()},
        key=str,
    )
    items = await _lock_items(db, item_ids)

    archived_items_allowed = movement_type in {
        MovementType.RETURN,
        MovementType.TRANSFER,
        MovementType.WRITE_OFF,
        MovementType.REVERSAL,
    } or (
        movement_type == MovementType.CORRECTION
        and source is not None
        and (destination is None or destination.location_id is not None)
    )
    if not archived_items_allowed and any(
        item.status != ItemStatus.ACTIVE for item in items.values()
    ):
        raise InventoryConflictError(
            "archived item cannot be received or issued",
            code="item_archived",
        )

    manufacturer_names = await _manufacturer_names(db, list(items.values()))

    for item_id in quantity_item_ids:
        if items[item_id].accounting_mode != AccountingMode.QUANTITY:
            raise InventoryValidationError(
                "quantity lines require a QUANTITY-accounted item",
                code="item_accounting_mode_mismatch",
            )
    for unit in units.values():
        if items[unit.item_id].accounting_mode != AccountingMode.SERIAL:
            raise InventoryValidationError(
                "inventory unit does not reference a SERIAL-accounted item",
                code="item_accounting_mode_mismatch",
            )

    reusable_units = {key: units[unit_id] for key, unit_id in reusable_unit_ids.items()}
    for existing_serial_unit in reusable_units.values():
        if existing_serial_unit.state != InventoryUnitState.VOIDED:
            raise InventoryConflictError(
                "serial identity already exists",
                code="serial_identity_conflict",
            )

    wwn_rows = (
        (
            await db.execute(
                select(InventoryUnit.id, InventoryUnit.normalized_wwn).where(
                    InventoryUnit.normalized_wwn.in_(new_wwn_keys)
                )
            )
        ).all()
        if new_wwn_keys
        else []
    )
    units_by_wwn = {row.normalized_wwn: row.id for row in wwn_rows}

    for parsed in parsed_serial_lines.values():
        reusable_unit = reusable_units.get((parsed.item_id, parsed.normalized_serial_number))
        if parsed.normalized_wwn is not None:
            conflicting_unit_id = units_by_wwn.get(parsed.normalized_wwn)
            if conflicting_unit_id is not None and (
                reusable_unit is None or conflicting_unit_id != reusable_unit.id
            ):
                raise InventoryConflictError(
                    "WWN identity already exists",
                    code="wwn_identity_conflict",
                )
        if (
            reusable_unit is not None
            and reusable_unit.normalized_wwn is not None
            and parsed.normalized_wwn is not None
            and reusable_unit.normalized_wwn != parsed.normalized_wwn
        ):
            raise InventoryConflictError(
                "reactivation cannot replace an existing WWN identity",
                code="wwn_replacement_conflict",
            )

    prepared: list[PreparedLine] = []
    for line_index, line in enumerate(line_payloads):
        if line.quantity is not None:
            assert line.item_id is not None
            item = items[line.item_id]
            prepared.append(
                PreparedLine(
                    item=item,
                    manufacturer_name=(
                        manufacturer_names.get(item.manufacturer_id)
                        if item.manufacturer_id is not None
                        else None
                    ),
                    quantity=line.quantity,
                )
            )
            continue
        if line.inventory_unit_id is not None:
            unit = units[line.inventory_unit_id]
            item = items[unit.item_id]
            prepared.append(
                PreparedLine(
                    item=item,
                    manufacturer_name=(
                        manufacturer_names.get(item.manufacturer_id)
                        if item.manufacturer_id is not None
                        else None
                    ),
                    unit=unit,
                )
            )
            continue

        parsed = parsed_serial_lines[line_index]
        item = items[parsed.item_id]
        if item.accounting_mode != AccountingMode.SERIAL:
            raise InventoryValidationError(
                "serial identity lines require a SERIAL-accounted item",
                code="item_accounting_mode_mismatch",
            )
        reusable_unit = reusable_units.get((item.id, parsed.normalized_serial_number))
        reactivation_wwn = parsed.wwn
        reactivation_normalized_wwn = parsed.normalized_wwn
        if (
            reusable_unit is not None
            and reusable_unit.normalized_wwn is not None
            and reactivation_normalized_wwn is None
        ):
            reactivation_wwn = reusable_unit.wwn
            reactivation_normalized_wwn = reusable_unit.normalized_wwn
        prepared.append(
            PreparedLine(
                item=item,
                manufacturer_name=(
                    manufacturer_names.get(item.manufacturer_id)
                    if item.manufacturer_id is not None
                    else None
                ),
                unit=reusable_unit,
                new_serial_number=parsed.serial_number,
                new_normalized_serial_number=parsed.normalized_serial_number,
                new_wwn=reactivation_wwn,
                new_normalized_wwn=reactivation_normalized_wwn,
                new_unit_comment=parsed.unit_comment,
            )
        )
    return prepared


def _balance_filter(
    position: Position,
) -> tuple[ColumnElement[bool], ColumnElement[bool]]:
    if position.location_id is not None:
        return (
            StockBalance.location_id == position.location_id,
            StockBalance.holder_user_id.is_(None),
        )
    return (
        StockBalance.location_id.is_(None),
        StockBalance.holder_user_id == position.holder_user_id,
    )


async def _subtract_quantity_balances(
    db: AsyncSession,
    source: Position,
    lines: Sequence[PreparedLine],
    *,
    now: datetime,
) -> None:
    quantity_lines = sorted(
        (line for line in lines if line.quantity is not None),
        key=lambda line: str(line.item.id),
    )
    if not quantity_lines:
        return
    item_ids = [line.item.id for line in quantity_lines]
    rows = list(
        (
            await db.scalars(
                select(StockBalance)
                .where(
                    StockBalance.item_id.in_(item_ids),
                    *_balance_filter(source),
                )
                .order_by(StockBalance.item_id)
                .with_for_update()
            )
        ).all()
    )
    balances = {row.item_id: row for row in rows}
    for line in quantity_lines:
        assert line.quantity is not None
        balance = balances.get(line.item.id)
        if balance is None or balance.quantity < line.quantity:
            raise InventoryConflictError(
                f"insufficient stock for item {line.item.id}",
                code="insufficient_stock",
            )
        if balance.quantity == line.quantity:
            await db.delete(balance)
        else:
            balance.quantity -= line.quantity
            balance.updated_at = now


async def _add_quantity_balance(
    db: AsyncSession,
    destination: Position,
    line: PreparedLine,
    *,
    now: datetime,
) -> None:
    assert line.quantity is not None
    values: dict[str, object] = {
        "id": uuid.uuid4(),
        "item_id": line.item.id,
        "item_accounting_mode": AccountingMode.QUANTITY.value,
        "quantity": line.quantity,
        "created_at": now,
        "updated_at": now,
    }
    if destination.location_id is not None:
        values["location_id"] = destination.location_id
        statement = pg_insert(StockBalance).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[StockBalance.item_id, StockBalance.location_id],
            index_where=StockBalance.holder_user_id.is_(None),
            set_={
                "quantity": StockBalance.quantity + statement.excluded.quantity,
                "updated_at": now,
            },
            where=(StockBalance.quantity <= POSTGRES_BIGINT_MAX - statement.excluded.quantity),
        )
    else:
        values["holder_user_id"] = destination.holder_user_id
        statement = pg_insert(StockBalance).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[StockBalance.item_id, StockBalance.holder_user_id],
            index_where=StockBalance.location_id.is_(None),
            set_={
                "quantity": StockBalance.quantity + statement.excluded.quantity,
                "updated_at": now,
            },
            where=(StockBalance.quantity <= POSTGRES_BIGINT_MAX - statement.excluded.quantity),
        )
    updated_balance_id = await db.scalar(statement.returning(StockBalance.id))
    if updated_balance_id is None:
        raise InventoryConflictError(
            "quantity balance would exceed PostgreSQL BIGINT",
            code="quantity_overflow",
        )


def _unit_matches_position(unit: InventoryUnit, position: Position) -> bool:
    if position.location_id is not None:
        return (
            unit.state == InventoryUnitState.STORED
            and unit.current_location_id == position.location_id
            and unit.current_holder_user_id is None
        )
    return (
        unit.state == InventoryUnitState.ISSUED
        and unit.current_location_id is None
        and unit.current_holder_user_id == position.holder_user_id
    )


def _place_unit(
    unit: InventoryUnit,
    destination: Position | None,
    *,
    movement_type: MovementType,
    now: datetime,
) -> None:
    if destination is None:
        unit.state = (
            InventoryUnitState.WRITTEN_OFF
            if movement_type == MovementType.WRITE_OFF
            else InventoryUnitState.VOIDED
        )
        unit.current_location_id = None
        unit.current_holder_user_id = None
    elif destination.location_id is not None:
        unit.state = InventoryUnitState.STORED
        unit.current_location_id = destination.location_id
        unit.current_holder_user_id = None
    else:
        unit.state = InventoryUnitState.ISSUED
        unit.current_location_id = None
        unit.current_holder_user_id = destination.holder_user_id
    unit.updated_at = now


async def _apply_projections(
    db: AsyncSession,
    lines: Sequence[PreparedLine],
    *,
    source: Position | None,
    destination: Position | None,
    movement_type: MovementType,
    reversal_absent_source_state: InventoryUnitState | None,
    now: datetime,
) -> None:
    if source is not None:
        await _subtract_quantity_balances(db, source, lines, now=now)
    for line in lines:
        if line.quantity is not None and destination is not None:
            await _add_quantity_balance(db, destination, line, now=now)

    for line in lines:
        if line.quantity is not None:
            continue
        unit = line.unit
        if line.new_serial_number is not None:
            if unit is None:
                unit = InventoryUnit(
                    item_id=line.item.id,
                    item_accounting_mode=AccountingMode.SERIAL,
                    serial_number=line.new_serial_number,
                    normalized_serial_number=line.new_normalized_serial_number,
                    wwn=line.new_wwn,
                    normalized_wwn=line.new_normalized_wwn,
                    comment=line.new_unit_comment,
                    state=InventoryUnitState.VOIDED,
                    created_at=now,
                    updated_at=now,
                )
                db.add(unit)
                line.unit = unit
            else:
                if unit.state != InventoryUnitState.VOIDED:
                    raise InventoryConflictError(
                        "serial identity is already active",
                        code="serial_identity_conflict",
                    )
                assert line.new_normalized_serial_number is not None
                unit.serial_number = line.new_serial_number
                unit.normalized_serial_number = line.new_normalized_serial_number
                unit.wwn = line.new_wwn
                unit.normalized_wwn = line.new_normalized_wwn
                unit.comment = line.new_unit_comment
        else:
            assert unit is not None
            if source is not None:
                if not _unit_matches_position(unit, source):
                    raise InventoryConflictError(
                        f"inventory unit {unit.id} is not at the movement source",
                        code="serial_source_mismatch",
                    )
            elif reversal_absent_source_state is not None:
                if unit.state != reversal_absent_source_state:
                    raise InventoryConflictError(
                        f"inventory unit {unit.id} is not in the reversible state",
                        code="serial_source_mismatch",
                    )
            else:
                raise InventoryValidationError(
                    "new serial identity is required for an external source",
                    code="serial_identity_required",
                )
        assert unit is not None
        _place_unit(
            unit,
            destination,
            movement_type=movement_type,
            now=now,
        )


def _movement_line(
    movement_id: uuid.UUID,
    prepared: PreparedLine,
    *,
    line_no: int,
) -> MovementLine:
    unit = prepared.unit
    return MovementLine(
        movement_id=movement_id,
        line_no=line_no,
        item_id=prepared.item.id,
        item_accounting_mode=prepared.item.accounting_mode,
        inventory_unit_id=unit.id if unit is not None else None,
        quantity=prepared.quantity,
        item_name_snapshot=prepared.item.name,
        manufacturer_name_snapshot=prepared.manufacturer_name,
        model_snapshot=prepared.item.model,
        manufacturer_part_number_snapshot=(prepared.item.manufacturer_part_number),
        serial_number_snapshot=unit.serial_number if unit is not None else None,
        wwn_snapshot=unit.wwn if unit is not None else None,
    )


def _movement_positions(movement: Movement) -> set[Position]:
    positions: set[Position] = set()
    for location_id, holder_user_id in (
        (movement.source_location_id, movement.source_holder_user_id),
        (movement.destination_location_id, movement.destination_holder_user_id),
    ):
        position = _position(location_id, holder_user_id)
        if position is not None:
            positions.add(position)
    return positions


def _validate_correction_relationship(
    original: Movement,
    prepared_lines: Sequence[PreparedLine],
    *,
    source: Position | None,
    destination: Position | None,
) -> None:
    correction_positions = {position for position in (source, destination) if position is not None}
    original_item_ids = {line.item_id for line in original.lines}
    if not correction_positions.intersection(_movement_positions(original)) or any(
        line.item.id not in original_item_ids for line in prepared_lines
    ):
        raise InventoryValidationError(
            "correction must concern an original item and position",
            code="correction_relationship_invalid",
        )


async def _execute_movement(
    db: AsyncSession,
    *,
    movement_type: MovementType,
    source: Position | None,
    destination: Position | None,
    original_movement_id: uuid.UUID | None,
    original_movement: Movement | None,
    client_request_id: str,
    request_fingerprint: str,
    purpose: str | None,
    comment: str | None,
    line_payloads: Sequence[MovementLineCreate],
    actor_user_id: uuid.UUID,
    actor_display_name: str,
    is_reversal: bool,
) -> MovementResult:
    existing = await _existing_idempotent_result(
        db,
        actor_user_id=actor_user_id,
        client_request_id=client_request_id,
        request_fingerprint=request_fingerprint,
    )
    if existing is not None:
        return existing

    _validate_operation_positions(movement_type, source, destination)
    locations = await _load_locations_for_operation(
        db,
        source,
        destination,
        require_active_destination_only=is_reversal,
    )
    holders = await _load_holders_for_operation(
        db,
        source,
        destination,
        require_approved_destination=not is_reversal,
    )
    serial_creation = source is None and not is_reversal
    prepared_lines = await _prepare_lines(
        db,
        line_payloads,
        serial_creation=serial_creation,
        movement_type=movement_type,
        source=source,
        destination=destination,
    )
    if movement_type == MovementType.CORRECTION:
        assert original_movement is not None
        _validate_correction_relationship(
            original_movement,
            prepared_lines,
            source=source,
            destination=destination,
        )
    reversal_absent_source_state = None
    if is_reversal and source is None:
        assert original_movement is not None
        reversal_absent_source_state = (
            InventoryUnitState.WRITTEN_OFF
            if original_movement.movement_type == MovementType.WRITE_OFF
            else InventoryUnitState.VOIDED
        )
    now = datetime.now(UTC)
    await _apply_projections(
        db,
        prepared_lines,
        source=source,
        destination=destination,
        movement_type=movement_type,
        reversal_absent_source_state=reversal_absent_source_state,
        now=now,
    )

    source_location = (
        locations[source.location_id]
        if source is not None and source.location_id is not None
        else None
    )
    destination_location = (
        locations[destination.location_id]
        if destination is not None and destination.location_id is not None
        else None
    )
    movement = Movement(
        movement_type=movement_type,
        line_count=len(prepared_lines),
        actor_user_id=actor_user_id,
        source_location_id=source.location_id if source is not None else None,
        destination_location_id=(destination.location_id if destination is not None else None),
        source_holder_user_id=(source.holder_user_id if source is not None else None),
        destination_holder_user_id=(
            destination.holder_user_id if destination is not None else None
        ),
        original_movement_id=original_movement_id,
        client_request_id=client_request_id,
        request_fingerprint=request_fingerprint,
        purpose=purpose,
        comment=comment,
        actor_display_name_snapshot=actor_display_name,
        source_holder_display_name_snapshot=(
            holders[source.holder_user_id]
            if source is not None and source.holder_user_id is not None
            else None
        ),
        destination_holder_display_name_snapshot=(
            holders[destination.holder_user_id]
            if destination is not None and destination.holder_user_id is not None
            else None
        ),
        source_location_code_snapshot=(
            source_location.code if source_location is not None else None
        ),
        source_location_name_snapshot=(
            source_location.name if source_location is not None else None
        ),
        destination_location_code_snapshot=(
            destination_location.code if destination_location is not None else None
        ),
        destination_location_name_snapshot=(
            destination_location.name if destination_location is not None else None
        ),
        occurred_at=now,
    )
    db.add(movement)
    await db.flush()
    movement_lines = [
        _movement_line(movement.id, prepared, line_no=line_no)
        for line_no, prepared in enumerate(prepared_lines, start=1)
    ]
    db.add_all(movement_lines)
    await db.flush()
    return MovementResult(
        record=MovementRecord(movement=movement, lines=movement_lines),
        replayed=False,
    )


async def create_movement(
    db: AsyncSession,
    payload: MovementCreate,
    *,
    actor_user_id: uuid.UUID,
    actor_display_name: str,
) -> MovementResult:
    if payload.movement_type == MovementType.REVERSAL:
        raise InventoryValidationError(
            "use the reversal endpoint for REVERSAL movements",
            code="reversal_endpoint_required",
        )
    if payload.movement_type == MovementType.CORRECTION:
        if payload.original_movement_id is None:
            raise InventoryValidationError(
                "CORRECTION requires original_movement_id",
                code="original_movement_required",
            )
    elif payload.original_movement_id is not None:
        raise InventoryValidationError(
            "original_movement_id is valid only for CORRECTION",
            code="original_movement_unexpected",
        )

    client_request_id = normalize_inline_text(
        payload.client_request_id,
        field="client_request_id",
        max_length=128,
    )
    fingerprint_payload = payload.model_dump(mode="json")
    fingerprint_payload["client_request_id"] = client_request_id
    request_fingerprint = _fingerprint(fingerprint_payload)
    await _lock_idempotency_key(db, actor_user_id, client_request_id)
    original: Movement | None = None
    if payload.movement_type == MovementType.CORRECTION:
        original = await db.scalar(
            select(Movement)
            .where(Movement.id == payload.original_movement_id)
            .options(selectinload(Movement.lines))
            .with_for_update(read=True, key_share=True)
        )
        if original is None:
            raise InventoryNotFoundError(
                "original movement not found",
                code="movement_not_found",
            )
        if original.movement_type == MovementType.REVERSAL:
            raise InventoryValidationError(
                "a REVERSAL cannot be the correction target",
                code="correction_target_invalid",
            )
    source = _position(payload.source_location_id, payload.source_holder_user_id)
    destination = _position(
        payload.destination_location_id,
        payload.destination_holder_user_id,
    )
    return await _execute_movement(
        db,
        movement_type=payload.movement_type,
        source=source,
        destination=destination,
        original_movement_id=payload.original_movement_id,
        original_movement=original,
        client_request_id=client_request_id,
        request_fingerprint=request_fingerprint,
        purpose=normalize_optional_inline_text(
            payload.purpose,
            field="purpose",
            max_length=255,
        ),
        comment=normalize_optional_text(payload.comment),
        line_payloads=payload.lines,
        actor_user_id=actor_user_id,
        actor_display_name=normalize_inline_text(
            actor_display_name,
            field="actor_display_name",
            max_length=IDENTITY_DISPLAY_MAX_LENGTH,
        ),
        is_reversal=False,
    )


async def reverse_movement(
    db: AsyncSession,
    original_movement_id: uuid.UUID,
    payload: MovementReversalCreate,
    *,
    actor_user_id: uuid.UUID,
    actor_display_name: str,
) -> MovementResult:
    client_request_id = normalize_inline_text(
        payload.client_request_id,
        field="client_request_id",
        max_length=128,
    )
    fingerprint_payload: dict[str, object] = payload.model_dump(mode="json")
    fingerprint_payload["client_request_id"] = client_request_id
    fingerprint_payload["original_movement_id"] = str(original_movement_id)
    fingerprint_payload["movement_type"] = MovementType.REVERSAL.value
    request_fingerprint = _fingerprint(fingerprint_payload)
    await _lock_idempotency_key(db, actor_user_id, client_request_id)
    existing = await _existing_idempotent_result(
        db,
        actor_user_id=actor_user_id,
        client_request_id=client_request_id,
        request_fingerprint=request_fingerprint,
    )
    if existing is not None:
        return existing

    original = await db.scalar(
        select(Movement)
        .where(Movement.id == original_movement_id)
        .options(selectinload(Movement.lines))
        .with_for_update()
    )
    if original is None:
        raise InventoryNotFoundError(
            "original movement not found",
            code="movement_not_found",
        )
    if original.movement_type == MovementType.REVERSAL:
        raise InventoryValidationError(
            "a REVERSAL cannot itself be reversed",
            code="reversal_target_invalid",
        )
    repeated = await db.scalar(
        select(Movement.id).where(
            Movement.movement_type == MovementType.REVERSAL,
            Movement.original_movement_id == original.id,
        )
    )
    if repeated is not None:
        raise InventoryConflictError(
            "movement was already reversed",
            code="movement_already_reversed",
        )

    line_payloads = [
        MovementLineCreate(
            item_id=line.item_id if line.quantity is not None else None,
            quantity=line.quantity,
            inventory_unit_id=line.inventory_unit_id,
        )
        for line in original.lines
    ]
    source = _position(
        original.destination_location_id,
        original.destination_holder_user_id,
    )
    destination = _position(
        original.source_location_id,
        original.source_holder_user_id,
    )
    return await _execute_movement(
        db,
        movement_type=MovementType.REVERSAL,
        source=source,
        destination=destination,
        original_movement_id=original.id,
        original_movement=original,
        client_request_id=client_request_id,
        request_fingerprint=request_fingerprint,
        purpose=normalize_optional_inline_text(
            payload.purpose,
            field="purpose",
            max_length=255,
        ),
        comment=normalize_optional_text(payload.comment),
        line_payloads=line_payloads,
        actor_user_id=actor_user_id,
        actor_display_name=normalize_inline_text(
            actor_display_name,
            field="actor_display_name",
            max_length=IDENTITY_DISPLAY_MAX_LENGTH,
        ),
        is_reversal=True,
    )


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


async def list_movements(
    db: AsyncSession,
    *,
    movement_type: MovementType | None,
    item_id: uuid.UUID | None,
    inventory_unit_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> MovementPage:
    filters = []
    if movement_type is not None:
        filters.append(Movement.movement_type == movement_type)
    if item_id is not None:
        filters.append(
            Movement.id.in_(select(MovementLine.movement_id).where(MovementLine.item_id == item_id))
        )
    if inventory_unit_id is not None:
        filters.append(
            Movement.id.in_(
                select(MovementLine.movement_id).where(
                    MovementLine.inventory_unit_id == inventory_unit_id
                )
            )
        )
    total = await db.scalar(select(func.count()).select_from(Movement).where(*filters))
    rows = list(
        (
            await db.scalars(
                select(Movement)
                .where(*filters)
                .options(selectinload(Movement.lines))
                .order_by(Movement.journal_seq.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )
    return MovementPage(
        items=[MovementRecord(movement=row, lines=list(row.lines)) for row in rows],
        total=total or 0,
    )


async def _holder_display_names(
    db: AsyncSession,
    holder_ids: set[uuid.UUID],
) -> dict[uuid.UUID, str]:
    if not holder_ids:
        return {}
    identities = await db.scalars(
        select(TelegramIdentity).where(TelegramIdentity.user_id.in_(holder_ids))
    )
    return {identity.user_id: display_identity(identity) for identity in identities.all()}


async def list_stock_balances(
    db: AsyncSession,
    *,
    item_id: uuid.UUID | None,
    location_id: uuid.UUID | None,
    holder_user_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> StockBalancePage:
    filters = []
    if item_id is not None:
        filters.append(StockBalance.item_id == item_id)
    if location_id is not None:
        filters.append(StockBalance.location_id == location_id)
    if holder_user_id is not None:
        filters.append(StockBalance.holder_user_id == holder_user_id)
    total = await db.scalar(select(func.count()).select_from(StockBalance).where(*filters))
    balances = list(
        (
            await db.scalars(
                select(StockBalance)
                .where(*filters)
                .order_by(StockBalance.item_id, StockBalance.id)
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )
    item_ids = {row.item_id for row in balances}
    location_ids = {row.location_id for row in balances if row.location_id is not None}
    holder_ids = {row.holder_user_id for row in balances if row.holder_user_id is not None}
    items = {
        row.id: row for row in (await db.scalars(select(Item).where(Item.id.in_(item_ids)))).all()
    }
    locations = {
        row.id: row
        for row in (await db.scalars(select(Location).where(Location.id.in_(location_ids)))).all()
    }
    holder_names = await _holder_display_names(db, holder_ids)
    return StockBalancePage(
        items=[
            StockBalanceRecord(
                balance=row,
                item=items[row.item_id],
                location=(locations[row.location_id] if row.location_id is not None else None),
                holder_display_name=(
                    holder_names[row.holder_user_id] if row.holder_user_id is not None else None
                ),
            )
            for row in balances
        ],
        total=total or 0,
    )


async def _unit_records(
    db: AsyncSession,
    units: Sequence[InventoryUnit],
) -> list[InventoryUnitRecord]:
    item_ids = {row.item_id for row in units}
    location_ids = {row.current_location_id for row in units if row.current_location_id is not None}
    holder_ids = {
        row.current_holder_user_id for row in units if row.current_holder_user_id is not None
    }
    items = {
        row.id: row for row in (await db.scalars(select(Item).where(Item.id.in_(item_ids)))).all()
    }
    locations = {
        row.id: row
        for row in (await db.scalars(select(Location).where(Location.id.in_(location_ids)))).all()
    }
    holder_names = await _holder_display_names(db, holder_ids)
    return [
        InventoryUnitRecord(
            unit=row,
            item=items[row.item_id],
            location=(
                locations[row.current_location_id] if row.current_location_id is not None else None
            ),
            holder_display_name=(
                holder_names[row.current_holder_user_id]
                if row.current_holder_user_id is not None
                else None
            ),
        )
        for row in units
    ]


async def get_inventory_unit_record(
    db: AsyncSession,
    unit_id: uuid.UUID,
) -> InventoryUnitRecord:
    unit = await db.get(InventoryUnit, unit_id)
    if unit is None:
        raise InventoryNotFoundError(
            "inventory unit not found",
            code="inventory_unit_not_found",
        )
    return (await _unit_records(db, [unit]))[0]


async def list_inventory_units(
    db: AsyncSession,
    *,
    item_id: uuid.UUID | None,
    state: InventoryUnitState | None,
    location_id: uuid.UUID | None,
    holder_user_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> InventoryUnitPage:
    filters = []
    if item_id is not None:
        filters.append(InventoryUnit.item_id == item_id)
    if state is not None:
        filters.append(InventoryUnit.state == state)
    if location_id is not None:
        filters.append(InventoryUnit.current_location_id == location_id)
    if holder_user_id is not None:
        filters.append(InventoryUnit.current_holder_user_id == holder_user_id)
    total = await db.scalar(select(func.count()).select_from(InventoryUnit).where(*filters))
    units = list(
        (
            await db.scalars(
                select(InventoryUnit)
                .where(*filters)
                .order_by(
                    InventoryUnit.item_id,
                    InventoryUnit.normalized_serial_number,
                    InventoryUnit.id,
                )
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )
    return InventoryUnitPage(
        items=await _unit_records(db, units),
        total=total or 0,
    )
