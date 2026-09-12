import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.health import DatabaseUnavailableError, ensure_database_ready
from tests.migration_helpers import alembic

pytestmark = pytest.mark.asyncio


async def assert_database_unready(database_url: str) -> None:
    engine = create_async_engine(database_url)

    try:
        with pytest.raises(DatabaseUnavailableError):
            await ensure_database_ready(engine)
    finally:
        await engine.dispose()


async def test_readiness_rejects_pre_rbac_and_pre_procurement_schemas_and_accepts_head(
    migration_database: str,
) -> None:
    alembic(
        migration_database,
        "upgrade",
        "f8a9b0c1d2e3",
    )

    await assert_database_unready(migration_database)

    alembic(
        migration_database,
        "upgrade",
        "b2c3d4e5f6a7",
    )

    await assert_database_unready(migration_database)

    alembic(
        migration_database,
        "upgrade",
        "head",
    )

    engine = create_async_engine(migration_database)

    try:
        await ensure_database_ready(engine)
    finally:
        await engine.dispose()
