from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.schema_contract import critical_trigger_contract_sql

ROOT = Path(__file__).resolve().parents[2]


class DatabaseUnavailableError(RuntimeError):
    """База данных недоступна для обслуживания запросов."""


@lru_cache
def source_migration_head() -> str:
    config = Config(
        str(ROOT / "alembic.ini")
    )
    config.set_main_option(
        "script_location",
        str(ROOT / "migrations"),
    )

    heads = (
        ScriptDirectory
        .from_config(config)
        .get_heads()
    )

    if len(heads) != 1:
        raise RuntimeError(
            "expected exactly one "
            f"Alembic head, got {heads!r}"
        )

    return heads[0]


async def ensure_database_ready(
    engine: AsyncEngine,
) -> None:
    try:
        expected_head = source_migration_head()

        async with engine.connect() as connection:
            database_head = await connection.scalar(
                text(
                    "SELECT version_num "
                    "FROM public.alembic_version"
                )
            )

            if database_head != expected_head:
                raise DatabaseUnavailableError(
                    "database migration "
                    "head mismatch"
                )

            await connection.execute(
                text(
                    "SELECT u.role, u.access_status, s.expires_at, "
                    "i.identity_signature, "
                    "m.journal_seq, m.custody_user_id, ml.quantity, "
                    "b.quantity, "
                    "c.user_id, c.item_id, c.quantity, "
                    "ua.actor_user_id, ua.target_user_id, "
                    "ua.before_access_status, "
                    "ua.after_access_status, ua.occurred_at, "
                    "ur.actor_user_id, ur.target_user_id, "
                    "ur.before_role, ur.after_role, ur.occurred_at, "
                    "pr.state_version, pr.current_revision_id, "
                    "prl.expected_identity_signature, "
                    "pe.event_type, eo.status "
                    "FROM public.users u, public.auth_sessions s, "
                    "public.items i, "
                    "public.movements m, public.movement_lines ml, "
                    "public.stock_balances b, "
                    "public.user_item_custody_balances c, "
                    "public.user_access_events ua, "
                    "public.user_role_events ur, "
                    "public.procurement_requests pr, "
                    "public.procurement_revision_lines prl, "
                    "public.procurement_events pe, "
                    "public.email_outbox eo "
                    "WHERE false"
                )
            )

            contract_broken = (
                await connection.scalar(
                    text(
                        critical_trigger_contract_sql()
                    )
                )
            )

            if contract_broken is True:
                raise DatabaseUnavailableError(
                    "critical database "
                    "trigger contract mismatch"
                )

    except DatabaseUnavailableError:
        raise

    except (
        SQLAlchemyError,
        OSError,
        TimeoutError,
        RuntimeError,
    ) as exc:
        raise DatabaseUnavailableError from exc
