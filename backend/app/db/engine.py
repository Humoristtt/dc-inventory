from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import get_settings


def create_engine() -> AsyncEngine:
    settings = get_settings()

    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args={
            "timeout": settings.database_connect_timeout_seconds,
        },
    )
