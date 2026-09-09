from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine


class DatabaseUnavailableError(RuntimeError):
    """База данных недоступна для обслуживания запросов."""


async def ensure_database_ready(engine: AsyncEngine) -> None:
    try:
        async with engine.connect() as connection:
            await connection.execute(text(
                "SELECT u.access_status, s.expires_at, i.identity_signature, "
                "m.journal_seq, ml.quantity, b.quantity, "
                    "ua.actor_user_id, ua.target_user_id, "
                    "ua.before_access_status, ua.after_access_status, ua.occurred_at "
                "FROM public.users u, public.auth_sessions s, public.items i, "
                "public.movements m, public.movement_lines ml, public.stock_balances b, "
                    "public.user_access_events ua "
                "WHERE false"
            ))
    except (SQLAlchemyError, OSError, TimeoutError) as exc:
        raise DatabaseUnavailableError from exc
