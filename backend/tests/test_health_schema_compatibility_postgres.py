import pytest
from sqlalchemy import text
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
        "f8b9c0d1e2f3",
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


@pytest.mark.parametrize(
    ("break_sql", "restore_sql"),
    [
        (
            "ALTER TABLE public.items DISABLE TRIGGER trg_items_validate_identity",
            "ALTER TABLE public.items ENABLE TRIGGER trg_items_validate_identity",
        ),
        (
            "ALTER TABLE public.procurement_revision_lines "
            "DISABLE TRIGGER trg_procurement_revision_lines_append_only",
            "ALTER TABLE public.procurement_revision_lines "
            "ENABLE TRIGGER trg_procurement_revision_lines_append_only",
        ),
        (
            "ALTER FUNCTION public.catalog_decimal_identity(numeric) "
            "RENAME TO catalog_decimal_identity_readiness_disabled",
            "ALTER FUNCTION public.catalog_decimal_identity_readiness_disabled(numeric) "
            "RENAME TO catalog_decimal_identity",
        ),
    ],
)
async def test_readiness_rejects_disabled_triggers_or_missing_function(
    migration_database: str,
    break_sql: str,
    restore_sql: str,
) -> None:
    alembic(migration_database, "upgrade", "head")
    engine = create_async_engine(migration_database)
    try:
        async with engine.begin() as connection:
            await connection.execute(text(break_sql))
        try:
            with pytest.raises(DatabaseUnavailableError):
                await ensure_database_ready(engine)
        finally:
            async with engine.begin() as connection:
                await connection.execute(text(restore_sql))
        await ensure_database_ready(engine)
    finally:
        await engine.dispose()
