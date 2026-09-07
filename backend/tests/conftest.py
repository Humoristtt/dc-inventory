import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://dc_inventory:test-only@127.0.0.1:5432/dc_inventory",
)

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


@pytest_asyncio.fixture
async def warehouse_db():
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("requires migrated disposable PostgreSQL")
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.connect() as connection:
        transaction = await connection.begin()
        async with AsyncSession(connection, expire_on_commit=False,
                                join_transaction_mode="create_savepoint") as db:
            yield db
        await transaction.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def migration_database():
    """Create and remove only our uniquely named disposable database."""
    import uuid
    from sqlalchemy import text
    from sqlalchemy.engine import make_url
    if not any(os.getenv(flag) == "1" for flag in
               ("RUN_POSTGRES_INTEGRATION", "RUN_SFP_DOWNGRADE_POSTGRES")):
        pytest.skip("requires disposable PostgreSQL migration gate")
    base_url = make_url(os.environ["DATABASE_URL"])
    name = "warehouse_test_" + uuid.uuid4().hex
    admin = create_async_engine(base_url, isolation_level="AUTOCOMMIT")
    async with admin.connect() as connection:
        await connection.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield base_url.set(database=name).render_as_string(hide_password=False)
    finally:
        async with admin.connect() as connection:
            await connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        await admin.dispose()
