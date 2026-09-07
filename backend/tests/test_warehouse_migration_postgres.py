"""Historical schema references here intentionally test migration safety."""

import json
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.migration_helpers import alembic

HEAD = "b3c4d5e6f7a8"
PREVIOUS = "a2b3c4d5e6f7"
pytestmark = pytest.mark.asyncio


async def test_baseline_head_empty_downgrade_and_metadata(migration_database: str) -> None:
    url = migration_database
    alembic(url, "upgrade", "48c2f07f01a0")
    alembic(url, "upgrade", "head")
    engine = create_async_engine(url)
    async with engine.connect() as db:
        assert (await db.scalar(text("SHOW server_version"))).startswith("18")
        assert await db.scalar(text("SELECT version_num FROM alembic_version")) == HEAD
        assert await db.scalar(text("SELECT to_regclass('inventory_units')")) is None
        columns = (
            (
                await db.execute(
                    text(
                        (
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_schema='public'"
                        )
                    )
                )
            )
            .scalars()
            .all()
        )
        assert not {
            "serial_number",
            "wwn",
            "accounting_mode",
            "holder_user_id",
            "source_holder_user_id",
            "destination_holder_user_id",
            "datasheet_url",
        }.intersection(columns)
        assert await db.scalar(text("SELECT count(*) FROM categories")) == 18
    await engine.dispose()
    assert "No new upgrade operations detected" in alembic(url, "check")
    alembic(url, "downgrade", PREVIOUS)
    alembic(url, "upgrade", HEAD)
    assert "No new upgrade operations detected" in alembic(url, "check")


@pytest.mark.parametrize(
    "seed,reason",
    [
        (
            (
                "INSERT INTO locations (id,code,normalized_code,name) "
                "VALUES (gen_random_uuid(),'test','test','test')"
            ),
            "locations contains data",
        ),
        (
            (
                "INSERT INTO items "
                "(id,category_id,name,normalized_name,accounting_mode,status) "
                "SELECT gen_random_uuid(),id,'test','test','QUANTITY','ACTIVE' "
                "FROM categories WHERE key='sfp'"
            ),
            "items contains data",
        ),
        (
            (
                "INSERT INTO items "
                "(id,category_id,name,normalized_name,accounting_mode,status) "
                "SELECT gen_random_uuid(),id,'test','test','SERIAL','ACTIVE' "
                "FROM categories WHERE key='nic'"
            ),
            "serial catalog",
        ),
        (
            (
                "INSERT INTO categories "
                "(id,key,display_name,default_accounting_mode,is_system) "
                "VALUES (gen_random_uuid(),'custom','Custom','QUANTITY',false)"
            ),
            "custom categories",
        ),
    ],
)
async def test_upgrade_refuses_populated_legacy_domain(
    migration_database: str,
    seed: str,
    reason: str,
) -> None:
    url = migration_database
    alembic(url, "upgrade", PREVIOUS)
    engine = create_async_engine(url)
    async with engine.begin() as db:
        await db.execute(text(seed))
    output = alembic(url, "upgrade", HEAD, success=False)
    assert reason in output
    async with engine.connect() as db:
        assert await db.scalar(text("SELECT version_num FROM alembic_version")) == PREVIOUS
        assert await db.scalar(text("SELECT to_regclass('inventory_units')")) is not None
    await engine.dispose()


@pytest.mark.parametrize("domain", ["location", "item", "journal"])
async def test_downgrade_refuses_populated_v2_without_losing_data(
    migration_database: str,
    domain: str,
) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.catalog.service import create_item
    from app.modules.inventory.schemas import LocationCreate
    from app.modules.inventory.service import create_location
    from tests.warehouse_helpers import actor, cable_payload, move, scenario

    url = migration_database
    alembic(url, "upgrade", HEAD)
    engine = create_async_engine(url)
    async with AsyncSession(engine, expire_on_commit=False) as db:
        if domain == "item":
            await create_item(db, cable_payload())
        elif domain == "location":
            await actor(db)
            await create_location(
                db, LocationCreate(code="test", name="test", location_type="WAREHOUSE")
            )
        else:
            s = await scenario(db)
            await move(db, s, "RECEIPT", 3, destination=s[2])
        await db.commit()
        before = [
            await db.scalar(text(f"SELECT count(*) FROM {table}"))
            for table in ("items", "locations", "movements", "movement_lines", "stock_balances")
        ]
    assert "downgrade refused" in alembic(url, "downgrade", PREVIOUS, success=False)
    async with engine.connect() as db:
        after = [
            await db.scalar(text(f"SELECT count(*) FROM {table}"))
            for table in ("items", "locations", "movements", "movement_lines", "stock_balances")
        ]
        assert before == after
        assert await db.scalar(text("SELECT version_num FROM alembic_version")) == HEAD
    await engine.dispose()


async def test_frozen_configuration_matches_current_product_contract() -> None:
    from dataclasses import asdict

    from app.modules.catalog.configuration import FAMILIES, LEAVES

    path = Path(__file__).parents[1] / "migrations/data/b3c4d5e6f7a8_configuration.json"
    frozen = json.loads(path.read_text())
    assert frozen["families"] == {k: list(v) for k, v in FAMILIES.items()}
    assert frozen["leaves"] == {
        k: [v[0], v[1], [asdict(a) for a in v[2]]] for k, v in LEAVES.items()
    }
