"""Fail-closed one-shot bootstrap for the first real production inventory load."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.bootstrap.inventory_workbook import Validation, import_inventory, read_workbook
from app.core.config import get_settings
from app.modules.catalog.models import Item, Manufacturer
from app.modules.inventory.enums import LocationType, MovementType
from app.modules.inventory.models import Location, Movement, MovementLine, StockBalance
from app.modules.inventory.schemas import LocationCreate
from app.modules.inventory.service import create_location

CONFIRMATION = "BOOTSTRAP_REAL_INVENTORY_ONCE"
BOOTSTRAP_LOCK_KEY = 80901620260907

RECONCILIATION_SQL = (
    Path(__file__).parents[2] / "scripts" / "reconcile_inventory_projections.sql"
).read_text()


def source_sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def assert_production_runtime(
    *,
    app_env: str,
    database_url: str,
    gate_enabled: bool,
) -> None:
    url = make_url(database_url)

    if app_env != "production":
        raise ValueError("production bootstrap requires APP_ENV=production")

    if url.drivername != "postgresql+asyncpg" or url.host != "postgres":
        raise ValueError(
            "production bootstrap requires the production Docker PostgreSQL boundary"
        )

    if gate_enabled:
        raise ValueError(
            "REAL_INVENTORY_MUTATIONS_ENABLED must remain false during bootstrap"
        )


def assert_validation_contract(
    validation: Validation,
    *,
    expected_rows: int,
    expected_items: int,
    expected_quantity: int,
) -> None:
    if validation.errors:
        raise ValueError(
            "workbook validation failed: " + "; ".join(validation.errors)
        )

    if validation.raw_rows != expected_rows:
        raise ValueError(
            f"unexpected workbook row count: "
            f"{validation.raw_rows} != {expected_rows}"
        )

    if len(validation.items) != expected_items:
        raise ValueError(
            f"unexpected normalized item count: "
            f"{len(validation.items)} != {expected_items}"
        )

    if validation.source_quantity != expected_quantity:
        raise ValueError(
            f"unexpected source quantity: "
            f"{validation.source_quantity} != {expected_quantity}"
        )


async def warehouse_counts(db: AsyncSession) -> dict[str, int]:
    models = {
        "items": Item,
        "manufacturers": Manufacturer,
        "locations": Location,
        "movements": Movement,
        "movement_lines": MovementLine,
        "stock_balances": StockBalance,
    }

    result: dict[str, int] = {}

    for name, model in models.items():
        value = await db.scalar(select(func.count()).select_from(model))
        result[name] = int(value or 0)

    return result


async def bootstrap_transaction(
    db: AsyncSession,
    validation: Validation,
    *,
    location_code: str,
    location_name: str,
    location_type: LocationType,
    actor_user_id: UUID,
    expected_items: int,
    expected_quantity: int,
) -> dict[str, object]:
    await db.execute(select(func.pg_advisory_xact_lock(BOOTSTRAP_LOCK_KEY)))

    before = await warehouse_counts(db)

    if any(before.values()):
        raise ValueError(
            f"BOOTSTRAP_ALREADY_POPULATED: production warehouse is not empty: {before}"
        )

    location = await create_location(
        db,
        LocationCreate(
            code=location_code,
            name=location_name,
            location_type=location_type,
        ),
    )

    movement_id = await import_inventory(
        db,
        validation,
        target=str(location.id),
        actor_user_id=actor_user_id,
    )

    after = await warehouse_counts(db)

    expected_after = {
        "locations": 1,
        "items": expected_items,
        "movements": 1,
        "movement_lines": expected_items,
        "stock_balances": expected_items,
    }

    for name, expected in expected_after.items():
        if after[name] != expected:
            raise ValueError(
                f"post-bootstrap count mismatch for {name}: "
                f"{after[name]} != {expected}"
            )

    stock_total = int(
        await db.scalar(select(func.coalesce(func.sum(StockBalance.quantity), 0)))
        or 0
    )
    line_total = int(
        await db.scalar(select(func.coalesce(func.sum(MovementLine.quantity), 0)))
        or 0
    )

    if stock_total != expected_quantity:
        raise ValueError(
            f"post-bootstrap stock quantity mismatch: "
            f"{stock_total} != {expected_quantity}"
        )

    if line_total != expected_quantity:
        raise ValueError(
            f"post-bootstrap movement quantity mismatch: "
            f"{line_total} != {expected_quantity}"
        )

    movement = await db.get(Movement, movement_id)

    if movement is None:
        raise ValueError("bootstrap receipt movement disappeared")

    if movement.movement_type != MovementType.RECEIPT:
        raise ValueError("bootstrap movement is not RECEIPT")

    if movement.destination_location_id != location.id:
        raise ValueError("bootstrap receipt destination mismatch")

    if movement.line_count != expected_items:
        raise ValueError(
            f"bootstrap movement line_count mismatch: "
            f"{movement.line_count} != {expected_items}"
        )

    drift = (await db.execute(text(RECONCILIATION_SQL))).all()

    if drift:
        raise ValueError(
            f"post-bootstrap projection reconciliation failed: {len(drift)} drift rows"
        )

    return {
        "location_id": str(location.id),
        "location_code": location.code,
        "receipt_movement_id": str(movement_id),
        "counts": after,
        "stock_quantity": stock_total,
        "movement_quantity": line_total,
        "projection_drift_rows": 0,
    }


async def run_production_bootstrap(args: argparse.Namespace) -> dict[str, object]:
    settings = get_settings()

    assert_production_runtime(
        app_env=settings.app_env,
        database_url=settings.database_url,
        gate_enabled=settings.real_inventory_mutations_enabled,
    )

    if args.confirm != CONFIRMATION:
        raise ValueError(
            f"explicit confirmation required: --confirm {CONFIRMATION}"
        )

    source: Path = args.source

    expected_sha256 = str(args.expected_sha256).strip().lower()

    if len(expected_sha256) != 64 or any(
        char not in "0123456789abcdef" for char in expected_sha256
    ):
        raise ValueError("expected SHA-256 must be 64 lowercase hexadecimal characters")

    actual_sha256 = source_sha256(source)

    if not hmac.compare_digest(actual_sha256, expected_sha256):
        raise ValueError(
            f"source SHA-256 mismatch: {actual_sha256} != {expected_sha256}"
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
        async with AsyncSession(engine, expire_on_commit=False) as db, db.begin():
            result = await bootstrap_transaction(
                db,
                validation,
                location_code=str(args.location_code),
                location_name=str(args.location_name),
                location_type=LocationType(str(args.location_type)),
                actor_user_id=UUID(str(args.actor)),
                expected_items=int(args.expected_items),
                expected_quantity=int(args.expected_quantity),
            )
    finally:
        await engine.dispose()

    return {
        "state": "success",
        "source_sha256": actual_sha256,
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

    parser.add_argument("--location-code", required=True)
    parser.add_argument("--location-name", required=True)
    parser.add_argument(
        "--location-type",
        choices=[item.value for item in LocationType],
        required=True,
    )
    parser.add_argument("--actor", required=True)

    parser.add_argument("--confirm", required=True)

    args = parser.parse_args()

    result = asyncio.run(run_production_bootstrap(args))

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
