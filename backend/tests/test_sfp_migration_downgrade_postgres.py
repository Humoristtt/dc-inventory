from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

HEAD_REVISION = "a2b3c4d5e6f7"
BASE_REVISION = "f1a2b3c4d5e6"
SFP_CATEGORY_ID = "10000000-0000-4000-8000-000000000001"
PROFILE_ATTRIBUTE_ID = "20000001-0000-4000-8000-000000000011"
REFUSAL_MESSAGE = "Refusing destructive downgrade of a2b3c4d5e6f7"

BACKEND_DIR = Path(__file__).parents[1]
ALEMBIC = Path(sys.executable).with_name("alembic")

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_SFP_DOWNGRADE_POSTGRES") != "1",
    reason="real PostgreSQL downgrade safety runs in the dedicated CI gate",
)


def _database_url() -> str:
    value = os.environ.get("DATABASE_URL")
    if not value:
        pytest.fail("DATABASE_URL is required for real downgrade integration")
    return value


def _alembic(
    *arguments: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    if not ALEMBIC.is_file():
        pytest.fail(f"Alembic executable not found: {ALEMBIC}")

    result = subprocess.run(
        [str(ALEMBIC), *arguments],
        cwd=BACKEND_DIR,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )

    if check and result.returncode != 0:
        pytest.fail(
            "Alembic command failed:\n"
            f"command={' '.join(arguments)}\n"
            f"stdout={result.stdout}\n"
            f"stderr={result.stderr}"
        )

    return result


def _current_revision() -> str:
    result = _alembic("current")
    return f"{result.stdout}\n{result.stderr}"


async def _insert_profile_fixture(
    *,
    item_id: str,
    value_id: str,
) -> None:
    engine = create_async_engine(_database_url())
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO items (
                        id,
                        category_id,
                        name,
                        normalized_name,
                        accounting_mode,
                        status
                    )
                    VALUES (
                        CAST(:item_id AS uuid),
                        CAST(:category_id AS uuid),
                        :name,
                        :normalized_name,
                        'QUANTITY',
                        'ACTIVE'
                    )
                    """
                ),
                {
                    "item_id": item_id,
                    "category_id": SFP_CATEGORY_ID,
                    "name": f"F35 downgrade guard {item_id}",
                    "normalized_name": f"f35 downgrade guard {item_id}",
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO item_attribute_values (
                        id,
                        item_id,
                        category_attribute_id,
                        category_id,
                        text_value
                    )
                    VALUES (
                        CAST(:value_id AS uuid),
                        CAST(:item_id AS uuid),
                        CAST(:attribute_id AS uuid),
                        CAST(:category_id AS uuid),
                        :text_value
                    )
                    """
                ),
                {
                    "value_id": value_id,
                    "item_id": item_id,
                    "attribute_id": PROFILE_ATTRIBUTE_ID,
                    "category_id": SFP_CATEGORY_ID,
                    "text_value": "F35 protected profile value",
                },
            )
    finally:
        await engine.dispose()


async def _assert_profile_fixture_preserved(
    *,
    item_id: str,
    value_id: str,
) -> None:
    engine = create_async_engine(_database_url())
    try:
        async with engine.connect() as connection:
            value_count = await connection.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM item_attribute_values
                    WHERE id = CAST(:value_id AS uuid)
                      AND item_id = CAST(:item_id AS uuid)
                      AND category_attribute_id = CAST(:attribute_id AS uuid)
                      AND text_value = :text_value
                    """
                ),
                {
                    "value_id": value_id,
                    "item_id": item_id,
                    "attribute_id": PROFILE_ATTRIBUTE_ID,
                    "text_value": "F35 protected profile value",
                },
            )
            attribute_count = await connection.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM category_attributes
                    WHERE id = CAST(:attribute_id AS uuid)
                    """
                ),
                {"attribute_id": PROFILE_ATTRIBUTE_ID},
            )

        assert value_count == 1
        assert attribute_count == 1
    finally:
        await engine.dispose()


async def _cleanup_profile_fixture(item_id: str) -> None:
    engine = create_async_engine(_database_url())
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    DELETE FROM items
                    WHERE id = CAST(:item_id AS uuid)
                    """
                ),
                {"item_id": item_id},
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_real_postgres_sfp_downgrade_cycle_and_destructive_guard() -> None:
    assert HEAD_REVISION in _current_revision()

    _alembic("downgrade", BASE_REVISION)
    assert BASE_REVISION in _current_revision()
    assert HEAD_REVISION not in _current_revision()

    _alembic("upgrade", "head")
    assert HEAD_REVISION in _current_revision()

    item_id = str(uuid.uuid4())
    value_id = str(uuid.uuid4())
    fixture_inserted = False

    try:
        await _insert_profile_fixture(
            item_id=item_id,
            value_id=value_id,
        )
        fixture_inserted = True

        blocked = _alembic(
            "downgrade",
            BASE_REVISION,
            check=False,
        )
        output = f"{blocked.stdout}\n{blocked.stderr}"

        assert blocked.returncode != 0
        assert REFUSAL_MESSAGE in output
        assert HEAD_REVISION in _current_revision()

        await _assert_profile_fixture_preserved(
            item_id=item_id,
            value_id=value_id,
        )
    finally:
        if HEAD_REVISION not in _current_revision():
            _alembic("upgrade", "head")

        if fixture_inserted:
            await _cleanup_profile_fixture(item_id)

    assert HEAD_REVISION in _current_revision()
