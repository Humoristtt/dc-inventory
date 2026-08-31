import pytest
from pydantic import ValidationError

from app.core.config import Settings

DATABASE_URL = "postgresql+asyncpg://dc_inventory:test@postgres:5432/dc_inventory"


def test_database_runtime_defaults() -> None:
    settings = Settings(database_url=DATABASE_URL)

    assert settings.database_connect_timeout_seconds == 5
    assert settings.database_pool_size == 5
    assert settings.database_max_overflow == 5
    assert settings.database_pool_timeout_seconds == 5
    assert settings.database_statement_timeout_seconds == 30
    assert settings.database_lock_timeout_seconds == 5


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("database_connect_timeout_seconds", 0),
        ("database_pool_size", 0),
        ("database_max_overflow", -1),
        ("database_pool_timeout_seconds", 0),
        ("database_statement_timeout_seconds", 0),
        ("database_lock_timeout_seconds", 0),
    ],
)
def test_invalid_database_runtime_settings_are_rejected(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"database_url": DATABASE_URL, field: value})
