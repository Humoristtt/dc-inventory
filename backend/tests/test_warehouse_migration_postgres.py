"""Historical schema references here intentionally test migration safety."""

import json
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from tests.migration_helpers import alembic

HEAD = "f8a9b0c1d2e3"
CURRENT_HEAD = "b2c3d4e5f6a7"
PREVIOUS = "a2b3c4d5e6f7"
pytestmark = pytest.mark.asyncio


async def _seed_user_item_location(db: AsyncConnection) -> tuple[str, str, str]:
    user_id = str(await db.scalar(text(
        "INSERT INTO users (id, role, access_status) "
        "VALUES (gen_random_uuid(), 'USER', 'APPROVED') RETURNING id"
    )))
    item_id = str(await db.scalar(text(
        "INSERT INTO items "
        "(id, category_id, name, normalized_name, status, identity_signature) "
        "SELECT gen_random_uuid(), id, 'test', 'test', 'ACTIVE', repeat('a', 64) "
        "FROM categories WHERE key = 'optical_patch_cord' RETURNING id"
    )))
    location_id = str(await db.scalar(text(
        "INSERT INTO locations (id, code, normalized_code, name, location_type) "
        "VALUES (gen_random_uuid(), 'test', 'test', 'test', 'WAREHOUSE') RETURNING id"
    )))
    return user_id, item_id, location_id


async def _seed_issue_history(
    db: AsyncConnection,
    *,
    with_custody: bool = False,
) -> tuple[str, str, str, str]:
    user_id, item_id, location_id = await _seed_user_item_location(db)
    custody_column = ", custody_user_id" if with_custody else ""
    custody_value = ", :user_id" if with_custody else ""
    movement_id = str(await db.scalar(text(
        "INSERT INTO movements "
        "(id, movement_type, line_count, actor_user_id, actor_display_name_snapshot, "
        "source_location_id, source_location_code_snapshot, source_location_name_snapshot, "
        f"client_request_id, request_fingerprint{custody_column}) "
        "VALUES (gen_random_uuid(), 'ISSUE', 1, :user_id, 'test', :location_id, "
        f"'test', 'test', 'test', repeat('b', 64){custody_value}) RETURNING id"
    ), {"user_id": user_id, "location_id": location_id}))
    await db.execute(text(
        "INSERT INTO movement_lines "
        "(id, movement_id, line_no, item_id, quantity, item_name_snapshot) "
        "VALUES (gen_random_uuid(), :movement_id, 1, :item_id, 1, 'test')"
    ), {"movement_id": movement_id, "item_id": item_id})
    return user_id, item_id, location_id, movement_id


async def test_custody_migration_clean_upgrade_and_empty_downgrade(
    migration_database: str,
) -> None:
    url = migration_database
    alembic(url, "upgrade", "e7f8a9b0c1d2")
    engine = create_async_engine(url)
    async with engine.connect() as db:
        assert await db.scalar(text("SELECT to_regclass('user_item_custody_balances')")) is None
    alembic(url, "upgrade", HEAD)
    async with engine.connect() as db:
        assert await db.scalar(text("SELECT version_num FROM alembic_version")) == HEAD
        assert await db.scalar(text("SELECT to_regclass('user_item_custody_balances')"))
        assert await db.scalar(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'movements' AND column_name = 'custody_user_id'"
        )) == 1
    alembic(url, "downgrade", "e7f8a9b0c1d2")
    async with engine.connect() as db:
        assert await db.scalar(text("SELECT version_num FROM alembic_version")) == "e7f8a9b0c1d2"
        assert await db.scalar(text("SELECT to_regclass('user_item_custody_balances')")) is None
    await engine.dispose()


async def test_custody_upgrade_refuses_ambiguous_issue_return_history(
    migration_database: str,
) -> None:
    url = migration_database
    alembic(url, "upgrade", "e7f8a9b0c1d2")
    engine = create_async_engine(url)
    async with engine.begin() as db:
        await _seed_issue_history(db)
    output = alembic(url, "upgrade", HEAD, success=False)
    assert "existing ISSUE/RETURN history" in output
    async with engine.connect() as db:
        assert await db.scalar(text("SELECT version_num FROM alembic_version")) == "e7f8a9b0c1d2"
        assert await db.scalar(text("SELECT count(*) FROM movements")) == 1
    await engine.dispose()


@pytest.mark.parametrize("domain", ["history", "projection"])
async def test_custody_downgrade_refuses_data(
    migration_database: str,
    domain: str,
) -> None:
    url = migration_database
    alembic(url, "upgrade", HEAD)
    engine = create_async_engine(url)
    async with engine.begin() as db:
        if domain == "history":
            await _seed_issue_history(db, with_custody=True)
        else:
            user_id, item_id, _location_id = await _seed_user_item_location(db)
            await db.execute(
                text(
                    "INSERT INTO user_item_custody_balances "
                    "(id, user_id, item_id, quantity) "
                    "VALUES (gen_random_uuid(), :user_id, :item_id, 1)"
                ),
                {"user_id": user_id, "item_id": item_id},
            )
    output = alembic(url, "downgrade", "e7f8a9b0c1d2", success=False)
    assert "custody history or projection exists" in output
    async with engine.connect() as db:
        assert await db.scalar(text("SELECT version_num FROM alembic_version")) == HEAD
    await engine.dispose()


async def test_baseline_head_empty_downgrade_and_metadata(migration_database: str) -> None:
    url = migration_database
    alembic(url, "upgrade", "48c2f07f01a0")
    alembic(url, "upgrade", "head")
    engine = create_async_engine(url)
    async with engine.connect() as db:
        assert (await db.scalar(text("SHOW server_version"))).startswith("18")
        assert (
            await db.scalar(text("SELECT version_num FROM alembic_version"))
            == CURRENT_HEAD
        )
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
        assert (
            await db.scalar(
                text(
                    "SELECT count(*) FROM categories "
                    "WHERE parent_id IS NOT NULL "
                    "AND is_system = true "
                    "AND description IS NOT NULL "
                    "AND btrim(description) <> ''"
                )
            )
            == 11
        )
    await engine.dispose()
    assert "No new upgrade operations detected" in alembic(url, "check")
    alembic(url, "downgrade", PREVIOUS)
    alembic(url, "upgrade", CURRENT_HEAD)
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


async def test_access_audit_downgrade_refuses_history(
    migration_database: str,
) -> None:
    url = migration_database
    alembic(url, "upgrade", HEAD)

    engine = create_async_engine(url)

    async with engine.begin() as db:
        user_id = await db.scalar(
            text(
                """
                INSERT INTO users (
                    id,
                    role,
                    access_status
                )
                VALUES (
                    gen_random_uuid(),
                    'ADMIN',
                    'APPROVED'
                )
                RETURNING id
                """
            )
        )
        assert user_id is not None

        await db.execute(
            text(
                """
                INSERT INTO user_access_events (
                    id,
                    actor_user_id,
                    target_user_id,
                    before_access_status,
                    after_access_status
                )
                VALUES (
                    gen_random_uuid(),
                    :user_id,
                    :user_id,
                    'APPROVED',
                    'BLOCKED'
                )
                """
            ),
            {"user_id": user_id},
        )

    output = alembic(
        url,
        "downgrade",
        "d6e7f8a9b0c1",
        success=False,
    )

    assert "user access audit downgrade refused" in output

    async with engine.connect() as db:
        assert (
            await db.scalar(
                text("SELECT version_num FROM alembic_version")
            )
            == HEAD
        )
        assert (
            await db.scalar(
                text("SELECT count(*) FROM user_access_events")
            )
            == 1
        )

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
