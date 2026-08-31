from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import Settings, get_settings


def create_engine(settings: Settings | None = None) -> AsyncEngine:
    runtime_settings = settings or get_settings()

    return create_async_engine(
        runtime_settings.database_url,
        pool_pre_ping=True,
        pool_size=runtime_settings.database_pool_size,
        max_overflow=runtime_settings.database_max_overflow,
        pool_timeout=runtime_settings.database_pool_timeout_seconds,
        connect_args={
            "timeout": runtime_settings.database_connect_timeout_seconds,
            "server_settings": {
                "application_name": "dc-inventory",
                "timezone": "UTC",
                "statement_timeout": str(
                    runtime_settings.database_statement_timeout_seconds * 1000
                ),
                "lock_timeout": str(runtime_settings.database_lock_timeout_seconds * 1000),
            },
        },
    )
