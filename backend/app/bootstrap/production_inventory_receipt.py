"""Fail-closed production stock snapshot reconciliation from inventory.xlsx.

The initial production bootstrap remains one-shot. A later workbook is treated
as an authoritative observed stock snapshot for the listed items at one
warehouse. Only positive deltas are received automatically; negative deltas are
blocked for explicit review instead of being silently written off.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy import String, cast, func, or_, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.bootstrap.inventory_workbook import Validation, read_workbook
from app.bootstrap.production_inventory import (
    RECONCILIATION_SQL,
    assert_production_runtime,
    assert_validation_contract,
    source_sha256,
)
from app.core.config import get_settings
from app.modules.catalog.enums import ItemStatus
from app.modules.catalog.models import Category, Item, Manufacturer
from app.modules.catalog.normalization import identity_text
from app.modules.catalog.schemas import ItemCreate, ManufacturerCreate
from app.modules.catalog.service import (
    CatalogError,
    create_item,
    create_manufacturer,
)
from app.modules.identity.enums import UserAccessStatus
from app.modules.identity.models import User
from app.modules.identity.policy import Capability, has_capability
from app.modules.inventory.enums import LocationStatus, MovementType
from app.modules.inventory.models import (
    Location,
    Movement,
    MovementLine,
    StockBalance,
)
from app.modules.inventory.schemas import MovementCreate, MovementLineCreate
from app.modules.inventory.service import InventoryError, create_movement

CONFIRMATION = "RECEIVE_REAL_INVENTORY_WORKBOOK"
IMPORT_LOCK_KEY = 80901620260923
REQUEST_PREFIX = "inventory-workbook-receipt:"


@dataclass(frozen=True, slots=True)
class ReceiptContext:
    location: Location
    actor: User


@dataclass(frozen=True, slots=True)
class ReceiptPlan:
    location_id: UUID
    location_code: str
    existing_movement_id: UUID | None
    existing_items: int
    new_items: int
    existing_manufacturers: int
    new_manufacturers: int
    current_quantity: int
    desired_quantity: int
    receipt_quantity: int
    negative_delta_items: int
    negative_delta_quantity: int
    zero_stock_items: int


def client_request_id(source_hash: str) -> str:
    value = source_hash.strip().lower()
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError("source SHA-256 must be 64 lowercase hexadecimal characters")
    request_id = REQUEST_PREFIX + value
    if len(request_id) > 128:
        raise RuntimeError("inventory workbook request id exceeds movement contract")
    return request_id


async def _context(
    db: AsyncSession,
    *,
    target: str,
    actor_user_id: UUID,
) -> ReceiptContext:
    location = await db.scalar(
        select(Location)
        .where(
            or_(
                Location.code == target,
                cast(Location.id, String) == target,
            )
        )
        .with_for_update()
    )
    if location is None or location.status != LocationStatus.ACTIVE:
        raise ValueError("explicit existing active target location required")

    actor = await db.scalar(
        select(User)
        .where(User.id == actor_user_id)
        .with_for_update()
    )
    if (
        actor is None
        or actor.access_status != UserAccessStatus.APPROVED
        or not has_capability(actor.role, Capability.INVENTORY_ADMIN)
    ):
        raise ValueError("existing approved inventory administrator required")

    return ReceiptContext(location=location, actor=actor)


async def _existing_import(
    db: AsyncSession,
    *,
    request_id: str,
    location_id: UUID,
) -> Movement | None:
    movements = list(
        (
            await db.scalars(
                select(Movement)
                .where(Movement.client_request_id == request_id)
                .order_by(Movement.id)
                .with_for_update()
            )
        ).all()
    )

    if len(movements) > 1:
        raise ValueError(
            "duplicate production workbook receipt idempotency records found"
        )
    if not movements:
        return None

    movement = movements[0]
    if (
        movement.movement_type != MovementType.RECEIPT
        or movement.destination_location_id != location_id
    ):
        raise ValueError(
            "existing workbook receipt conflicts with the requested import"
        )

    return movement


async def _plan(
    db: AsyncSession,
    validation: Validation,
    *,
    target: str,
    actor_user_id: UUID,
    source_hash: str,
) -> ReceiptPlan:
    await db.execute(select(func.pg_advisory_xact_lock(IMPORT_LOCK_KEY)))

    context = await _context(
        db,
        target=target,
        actor_user_id=actor_user_id,
    )
    request_id = client_request_id(source_hash)

    existing_movement = await _existing_import(
        db,
        request_id=request_id,
        location_id=context.location.id,
    )

    category_keys = sorted({item.category for item in validation.items})
    deployed_categories = set(
        (
            await db.scalars(
                select(Category.key).where(
                    Category.key.in_(category_keys),
                    Category.parent_id.is_not(None),
                )
            )
        ).all()
    )
    missing_categories = sorted(set(category_keys) - deployed_categories)
    if missing_categories:
        raise ValueError(
            "catalog categories are not deployed: "
            + ", ".join(missing_categories)
        )

    signatures = [item.signature for item in validation.items]
    existing_items = list(
        (
            await db.scalars(
                select(Item).where(
                    Item.identity_signature.in_(signatures)
                )
            )
        ).all()
    )
    archived = [
        item.identity_signature
        for item in existing_items
        if item.status != ItemStatus.ACTIVE
    ]
    if archived:
        raise ValueError(
            "workbook references archived catalog items: "
            + ", ".join(archived)
        )

    manufacturer_names = sorted(
        {
            identity_text(item.manufacturer)
            for item in validation.items
            if item.manufacturer
        }
    )
    existing_manufacturers = (
        list(
            (
                await db.scalars(
                    select(Manufacturer).where(
                        Manufacturer.normalized_name.in_(
                            manufacturer_names
                        )
                    )
                )
            ).all()
        )
        if manufacturer_names
        else []
    )

    items_by_signature = {
        item.identity_signature: item
        for item in existing_items
    }
    existing_ids = [
        item.id
        for item in existing_items
    ]
    balances = {
        balance.item_id: balance.quantity
        for balance in (
            (
                await db.scalars(
                    select(StockBalance).where(
                        StockBalance.location_id == context.location.id,
                        StockBalance.item_id.in_(existing_ids),
                    )
                )
            ).all()
            if existing_ids
            else []
        )
    }

    current_quantity = 0
    receipt_quantity = 0
    negative_delta_items = 0
    negative_delta_quantity = 0

    for equipment in validation.items:
        catalog_item = items_by_signature.get(
            equipment.signature
        )
        current = (
            balances.get(catalog_item.id, 0)
            if catalog_item is not None
            else 0
        )
        current_quantity += current
        delta = equipment.quantity - current

        if delta > 0:
            receipt_quantity += delta
        elif delta < 0:
            negative_delta_items += 1
            negative_delta_quantity += -delta

    return ReceiptPlan(
        location_id=context.location.id,
        location_code=context.location.code,
        existing_movement_id=(
            existing_movement.id
            if existing_movement is not None
            else None
        ),
        existing_items=len(existing_items),
        new_items=len(validation.items) - len(existing_items),
        existing_manufacturers=len(existing_manufacturers),
        new_manufacturers=(
            len(manufacturer_names) - len(existing_manufacturers)
        ),
        current_quantity=current_quantity,
        desired_quantity=validation.source_quantity,
        receipt_quantity=receipt_quantity,
        negative_delta_items=negative_delta_items,
        negative_delta_quantity=negative_delta_quantity,
        zero_stock_items=sum(
            1
            for item in validation.items
            if item.quantity == 0
        ),
    )


async def plan_inventory_receipt(
    db: AsyncSession,
    validation: Validation,
    *,
    target: str,
    actor_user_id: UUID,
    source_hash: str,
) -> ReceiptPlan:
    if validation.errors or not validation.items:
        raise ValueError("workbook validation failed")
    return await _plan(
        db,
        validation,
        target=target,
        actor_user_id=actor_user_id,
        source_hash=source_hash,
    )


async def apply_inventory_receipt(
    db: AsyncSession,
    validation: Validation,
    *,
    target: str,
    actor_user_id: UUID,
    source_hash: str,
    source_name: str,
) -> dict[str, object]:
    if validation.errors or not validation.items:
        raise ValueError("workbook validation failed")

    plan = await _plan(
        db,
        validation,
        target=target,
        actor_user_id=actor_user_id,
        source_hash=source_hash,
    )
    if plan.existing_movement_id is not None:
        return {
            "state": "already_applied",
            "replayed": True,
            "location_id": str(plan.location_id),
            "location_code": plan.location_code,
            "receipt_movement_id": str(plan.existing_movement_id),
            "created_items": 0,
            "reused_items": plan.existing_items,
            "created_manufacturers": 0,
            "reused_manufacturers": plan.existing_manufacturers,
            "desired_quantity": plan.desired_quantity,
            "receipt_quantity": int(
                await db.scalar(
                    select(
                        func.coalesce(
                            func.sum(MovementLine.quantity),
                            0,
                        )
                    ).where(
                        MovementLine.movement_id
                        == plan.existing_movement_id
                    )
                )
                or 0
            ),
            "zero_stock_items": plan.zero_stock_items,
            "projection_drift_rows": 0,
        }

    location = await db.get(Location, plan.location_id)
    if location is None:
        raise RuntimeError("locked target location disappeared")

    manufacturer_names = sorted(
        {
            identity_text(item.manufacturer)
            for item in validation.items
            if item.manufacturer
        }
    )
    manufacturers = {
        manufacturer.normalized_name: manufacturer
        for manufacturer in (
            (
                await db.scalars(
                    select(Manufacturer)
                    .where(
                        Manufacturer.normalized_name.in_(
                            manufacturer_names
                        )
                    )
                    .order_by(Manufacturer.normalized_name)
                    .with_for_update()
                )
            ).all()
            if manufacturer_names
            else []
        )
    }

    created_manufacturers = 0
    for equipment in validation.items:
        if not equipment.manufacturer:
            continue
        normalized = identity_text(equipment.manufacturer)
        if normalized in manufacturers:
            continue
        manufacturer = await create_manufacturer(
            db,
            ManufacturerCreate(name=equipment.manufacturer),
        )
        manufacturers[normalized] = manufacturer
        created_manufacturers += 1

    signatures = [item.signature for item in validation.items]
    items_by_signature = {
        item.identity_signature: item
        for item in (
            await db.scalars(
                select(Item)
                .where(Item.identity_signature.in_(signatures))
                .order_by(Item.identity_signature)
                .with_for_update()
            )
        ).all()
    }

    created_items = 0

    for equipment in validation.items:
        catalog_item = items_by_signature.get(equipment.signature)

        if catalog_item is None:
            manufacturer = (
                manufacturers[identity_text(equipment.manufacturer)]
                if equipment.manufacturer
                else None
            )
            item_id = await create_item(
                db,
                ItemCreate(
                    category_key=equipment.category,
                    manufacturer_id=(
                        manufacturer.id
                        if manufacturer is not None
                        else None
                    ),
                    name=equipment.name,
                    model=equipment.model,
                    attributes=equipment.attributes,
                ),
            )
            catalog_item = await db.get(Item, item_id)
            if catalog_item is None:
                raise RuntimeError("created catalog item disappeared")
            if catalog_item.identity_signature != equipment.signature:
                raise RuntimeError(
                    "created catalog item identity differs from workbook"
                )
            items_by_signature[equipment.signature] = catalog_item
            created_items += 1

        if catalog_item.status != ItemStatus.ACTIVE:
            raise ValueError("archived item cannot receive new stock")

    item_ids = [
        item.id
        for item in items_by_signature.values()
    ]
    balances = {
        balance.item_id: balance.quantity
        for balance in (
            await db.scalars(
                select(StockBalance)
                .where(
                    StockBalance.location_id == location.id,
                    StockBalance.item_id.in_(item_ids),
                )
                .order_by(StockBalance.item_id)
                .with_for_update()
            )
        ).all()
    }

    lines: list[MovementLineCreate] = []
    negative_deltas: list[str] = []

    for equipment in validation.items:
        catalog_item = items_by_signature[equipment.signature]
        current = balances.get(catalog_item.id, 0)
        delta = equipment.quantity - current

        if delta < 0:
            negative_deltas.append(
                f"{equipment.name}: current={current}, "
                f"snapshot={equipment.quantity}"
            )
        elif delta > 0:
            lines.append(
                MovementLineCreate(
                    item_id=catalog_item.id,
                    quantity=delta,
                )
            )

    if negative_deltas:
        details = "; ".join(negative_deltas[:20])
        raise ValueError(
            "snapshot would reduce existing stock; "
            "automatic write-off is forbidden: "
            + details
        )

    stock_before = int(
        await db.scalar(
            select(
                func.coalesce(
                    func.sum(StockBalance.quantity),
                    0,
                )
            ).where(
                StockBalance.location_id == location.id
            )
        )
        or 0
    )

    movement_result = (
        await create_movement(
            db,
            MovementCreate(
                movement_type=MovementType.RECEIPT,
                destination_location_id=location.id,
                client_request_id=client_request_id(source_hash),
                lines=lines,
            ),
            actor_user_id=actor_user_id,
            actor_display_name=(
                "Администратор · сверка "
                + Path(source_name).name
            ),
        )
        if lines
        else None
    )

    stock_after = int(
        await db.scalar(
            select(
                func.coalesce(
                    func.sum(StockBalance.quantity),
                    0,
                )
            ).where(
                StockBalance.location_id == location.id
            )
        )
        or 0
    )

    receipt_quantity = sum(
        line.quantity
        for line in lines
    )

    if stock_after - stock_before != receipt_quantity:
        raise ValueError(
            "post-import stock delta does not match planned receipt"
        )

    movement = (
        movement_result.record.movement
        if movement_result is not None
        else None
    )
    movement_quantity = (
        sum(
            line.quantity
            for line in movement_result.record.lines
        )
        if movement_result is not None
        else 0
    )
    if movement is not None and (
        movement.line_count != len(lines)
        or movement_quantity != receipt_quantity
    ):
        raise ValueError(
            "post-import receipt does not match planned delta"
        )

    drift = (await db.execute(text(RECONCILIATION_SQL))).all()
    if drift:
        raise ValueError(
            "post-import projection reconciliation failed: "
            f"{len(drift)} drift rows"
        )

    return {
        "state": "success",
        "replayed": (
            movement_result.replayed
            if movement_result is not None
            else False
        ),
        "location_id": str(location.id),
        "location_code": location.code,
        "receipt_movement_id": (
            str(movement.id)
            if movement is not None
            else None
        ),
        "created_items": created_items,
        "reused_items": len(validation.items) - created_items,
        "created_manufacturers": created_manufacturers,
        "reused_manufacturers": (
            len(manufacturer_names) - created_manufacturers
        ),
        "stock_before": stock_before,
        "stock_after": stock_after,
        "desired_quantity": validation.source_quantity,
        "receipt_quantity": movement_quantity,
        "zero_stock_items": sum(
            1
            for item in validation.items
            if item.quantity == 0
        ),
        "projection_drift_rows": 0,
    }


async def run(args: argparse.Namespace) -> dict[str, object]:
    settings = get_settings()
    assert_production_runtime(
        app_env=settings.app_env,
        database_url=settings.database_url,
        gate_enabled=settings.real_inventory_mutations_enabled,
    )

    url = make_url(settings.database_url)
    if url.host != "postgres":
        raise ValueError(
            "production inventory receipt requires Docker PostgreSQL"
        )

    source: Path = args.source
    actual_hash = source_sha256(source)
    expected_hash = str(args.expected_sha256).strip().lower()
    if actual_hash != expected_hash:
        raise ValueError(
            f"source SHA-256 mismatch: {actual_hash} != {expected_hash}"
        )

    validation = read_workbook(
        source,
        allow_zero_quantity=True,
    )
    assert_validation_contract(
        validation,
        expected_rows=int(args.expected_rows),
        expected_items=int(args.expected_items),
        expected_quantity=int(args.expected_quantity),
    )

    engine = create_async_engine(settings.database_url)
    try:
        async with AsyncSession(
            engine,
            expire_on_commit=False,
        ) as db, db.begin():
            if args.apply:
                if args.confirm != CONFIRMATION:
                    raise ValueError(
                        "explicit confirmation required: "
                        f"--confirm {CONFIRMATION}"
                    )
                result = await apply_inventory_receipt(
                    db,
                    validation,
                    target=str(args.location),
                    actor_user_id=UUID(str(args.actor)),
                    source_hash=actual_hash,
                    source_name=source.name,
                )
            else:
                plan = await plan_inventory_receipt(
                    db,
                    validation,
                    target=str(args.location),
                    actor_user_id=UUID(str(args.actor)),
                    source_hash=actual_hash,
                )
                result = {
                    "state": "dry_run",
                    "location_id": str(plan.location_id),
                    "location_code": plan.location_code,
                    "existing_movement_id": (
                        str(plan.existing_movement_id)
                        if plan.existing_movement_id is not None
                        else None
                    ),
                    "existing_items": plan.existing_items,
                    "new_items": plan.new_items,
                    "existing_manufacturers": (
                        plan.existing_manufacturers
                    ),
                    "new_manufacturers": plan.new_manufacturers,
                    "current_quantity": plan.current_quantity,
                    "desired_quantity": plan.desired_quantity,
                    "receipt_quantity": plan.receipt_quantity,
                    "negative_delta_items": (
                        plan.negative_delta_items
                    ),
                    "negative_delta_quantity": (
                        plan.negative_delta_quantity
                    ),
                    "zero_stock_items": plan.zero_stock_items,
                }
    finally:
        await engine.dispose()

    return {
        "source_sha256": actual_hash,
        "validation": validation.report(),
        **result,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--expected-rows", type=int, required=True)
    parser.add_argument("--expected-items", type=int, required=True)
    parser.add_argument("--expected-quantity", type=int, required=True)
    parser.add_argument(
        "--location",
        required=True,
        help="existing active warehouse location code or UUID",
    )
    parser.add_argument(
        "--actor",
        required=True,
        help="existing approved inventory administrator UUID",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "apply positive snapshot deltas as one idempotent receipt; "
            "default is dry-run"
        ),
    )
    parser.add_argument("--confirm")

    args = parser.parse_args()

    try:
        result = asyncio.run(run(args))
    except (ValueError, CatalogError, InventoryError) as error:
        print(
            json.dumps(
                {
                    "state": "error",
                    "error": str(error),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(1) from error

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
