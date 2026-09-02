from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Settings, get_settings
from app.db.engine import create_engine
from app.maintenance.technical_retention import (
    RetentionCounts,
    run_technical_retention_once,
)


async def run_maintenance_once(
    engine: AsyncEngine,
    settings: Settings,
) -> RetentionCounts:
    async with (
        AsyncSession(engine, expire_on_commit=False) as db,
        db.begin(),
    ):
        return await run_technical_retention_once(db, settings)


async def run_worker() -> None:
    settings = get_settings()
    engine = create_engine(settings)

    try:
        while True:
            counts = await run_maintenance_once(
                engine,
                settings,
            )
            print(
                "technical retention:"
                f" auth_sessions={counts.auth_sessions}"
                f" telegram_updates={counts.telegram_updates}"
                f" notification_outbox={counts.notification_outbox}"
                " access_decision_callbacks="
                f"{counts.access_decision_callbacks}"
                f" total={counts.total}",
                flush=True,
            )
            await asyncio.sleep(
                settings.maintenance_worker_poll_seconds
            )
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
