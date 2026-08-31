from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine


class DatabaseUnavailableError(RuntimeError):
    """База данных недоступна для обслуживания запросов."""


async def ensure_database_ready(engine: AsyncEngine) -> None:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError, TimeoutError) as exc:
        raise DatabaseUnavailableError from exc
