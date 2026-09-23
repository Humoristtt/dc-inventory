"""Fail-closed incremental production receipt from a validated inventory workbook.

The initial production bootstrap remains one-shot. This command is the explicit
path for adding a later, separately inventoried workbook to an existing
warehouse without reopening the generic inventory mutation API.
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
    expected_items: int,
    expected_quantity: int,
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
        or movement.line_count != expected_items
    ):
        raise ValueError(
            "existing workbook receipt conflicts with the requested import"
        )

    quantity = int(
        await db.scalar(
            select(func.coalesce(func.sum(MovementLine.quantity), 0)).where(
                MovementLine.movement_id == movement.id
            )
        )
        or 0
    )
    if quantity != expected_quantity:
        raise ValueError(
            "existing workbook receipt quantity conflicts with the source"
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
        expected_items=len(validation.items),
        expected_quantity=validation.source_quantity,
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
            "receipt_quantity": validation.source_quantity,
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
    lines: list[MovementLineCreate] = []

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

        lines.append(
            MovementLineCreate(
                item_id=catalog_item.id,
                quantity=equipment.quantity,
            )
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

    movement_result = await create_movement(
        db,
        MovementCreate(
            movement_type=MovementType.RECEIPT,
            destination_location_id=location.id,
            client_request_id=client_request_id(source_hash),
            lines=lines,
        ),
        actor_user_id=actor_user_id,
        actor_display_name=(
            "Администратор · импорт "
            + Path(source_name).name
        ),
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

    if stock_after - stock_before != validation.source_quantity:
        raise ValueError(
            "post-import stock delta does not match workbook quantity"
        )

    movement = movement_result.record.movement
    movement_quantity = sum(
        line.quantity
        for line in movement_result.record.lines
    )
    if (
        movement.line_count != len(validation.items)
        or movement_quantity != validation.source_quantity
    ):
        raise ValueError(
            "post-import receipt does not match workbook totals"
        )

    drift = (await db.execute(text(RECONCILIATION_SQL))).all()
    if drift:
        raise ValueError(
            "post-import projection reconciliation failed: "
            f"{len(drift)} drift rows"
        )

    return {
        "state": "success",
        "replayed": movement_result.replayed,
        "location_id": str(location.id),
        "location_code": location.code,
        "receipt_movement_id": str(movement.id),
        "created_items": created_items,
        "reused_items": len(validation.items) - created_items,
        "created_manufacturers": created_manufacturers,
        "reused_manufacturers": (
            len(manufacturer_names) - created_manufacturers
        ),
        "stock_before": stock_before,
        "stock_after": stock_after,
        "receipt_quantity": movement_quantity,
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

    validation = read_workbook(source)
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
                    "receipt_quantity": validation.source_quantity,
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
        help="commit one idempotent receipt; default is dry-run",
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
