from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine


class DatabaseUnavailableError(RuntimeError):
    """База данных недоступна для обслуживания запросов."""


async def ensure_database_ready(engine: AsyncEngine) -> None:
    try:
        async with engine.connect() as connection:
            await connection.execute(
                text(
                    "SELECT u.role, u.access_status, s.expires_at, i.identity_signature, "
                    "m.journal_seq, m.custody_user_id, ml.quantity, b.quantity, "
                    "c.user_id, c.item_id, c.quantity, "
                    "ua.actor_user_id, ua.target_user_id, "
                    "ua.before_access_status, ua.after_access_status, ua.occurred_at, "
                    "ur.actor_user_id, ur.target_user_id, "
                    "ur.before_role, ur.after_role, ur.occurred_at, "
                    "pr.state_version, pr.current_revision_id, "
                    "pe.event_type, eo.status "
                    "FROM public.users u, public.auth_sessions s, public.items i, "
                    "public.movements m, public.movement_lines ml, public.stock_balances b, "
                    "public.user_item_custody_balances c, "
                    "public.user_access_events ua, public.user_role_events ur, "
                    "public.procurement_requests pr, public.procurement_events pe, "
                    "public.email_outbox eo "
                    "WHERE false"
                )
            )
    except (SQLAlchemyError, OSError, TimeoutError) as exc:
        raise DatabaseUnavailableError from exc
