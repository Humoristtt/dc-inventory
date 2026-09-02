from pathlib import Path

from app.core.config import Settings
from app.db.migration_settings import migration_server_settings

DATABASE_URL = (
    "postgresql+asyncpg://dc_inventory:test@postgres:5432/"
    "dc_inventory"
)


def test_migration_server_settings_defaults() -> None:
    settings = Settings(database_url=DATABASE_URL)

    assert migration_server_settings(settings) == {
        "application_name": "dc-inventory-migrations",
        "timezone": "UTC",
        "statement_timeout": "300000",
        "lock_timeout": "5000",
    }


def test_migration_server_settings_use_dedicated_values() -> None:
    settings = Settings(
        database_url=DATABASE_URL,
        database_statement_timeout_seconds=17,
        database_lock_timeout_seconds=3,
        migration_statement_timeout_seconds=600,
        migration_lock_timeout_seconds=11,
    )

    values = migration_server_settings(settings)

    assert values["statement_timeout"] == "600000"
    assert values["lock_timeout"] == "11000"


def test_alembic_env_uses_canonical_migration_server_settings() -> None:
    source = Path("migrations/env.py").read_text()

    assert (
        '"server_settings": migration_server_settings(settings)'
        in source
    )
