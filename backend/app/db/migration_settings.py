from __future__ import annotations

from app.core.config import Settings


def migration_server_settings(settings: Settings) -> dict[str, str]:
    return {
        "application_name": "dc-inventory-migrations",
        "timezone": "UTC",
        "statement_timeout": str(
            settings.migration_statement_timeout_seconds * 1000
        ),
        "lock_timeout": str(
            settings.migration_lock_timeout_seconds * 1000
        ),
    }
