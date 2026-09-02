import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.maintenance.technical_retention import (
    TECHNICAL_RETENTION_TARGETS,
)

DATABASE_URL = (
    "postgresql+asyncpg://dc_inventory:test@postgres:5432/"
    "dc_inventory"
)


def test_technical_retention_targets_are_explicit_and_non_warehouse() -> None:
    assert frozenset(
        {
            "auth_sessions",
            "telegram_updates",
            "notification_outbox",
            "access_decision_callbacks",
        }
    ) == TECHNICAL_RETENTION_TARGETS

    assert "movements" not in TECHNICAL_RETENTION_TARGETS
    assert "movement_lines" not in TECHNICAL_RETENTION_TARGETS
    assert "stock_balances" not in TECHNICAL_RETENTION_TARGETS
    assert "inventory_units" not in TECHNICAL_RETENTION_TARGETS


def test_retention_defaults_are_bounded() -> None:
    settings = Settings(database_url=DATABASE_URL)

    assert settings.maintenance_worker_poll_seconds == 3600
    assert settings.maintenance_retention_batch_size == 1000
    assert settings.auth_session_retention_days == 7
    assert settings.telegram_update_retention_days == 30
    assert settings.notification_outbox_retention_days == 90
    assert settings.access_callback_retention_days == 30


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("maintenance_worker_poll_seconds", 59),
        ("maintenance_retention_batch_size", 0),
        ("maintenance_retention_batch_size", 5001),
        ("auth_session_retention_days", 0),
        ("telegram_update_retention_days", 0),
        ("notification_outbox_retention_days", 0),
        ("access_callback_retention_days", 0),
    ],
)
def test_invalid_retention_settings_are_rejected(
    field: str,
    value: int,
) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(
            {
                "database_url": DATABASE_URL,
                field: value,
            }
        )
