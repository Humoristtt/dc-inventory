from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Settings, get_settings
from app.db.engine import create_engine
from app.modules.notifications.gateway import TelegramGatewayClient
from app.modules.notifications.service import (
    ClaimedNotification,
    claim_notification_batch,
    mark_notification_failed,
    mark_notification_sent,
)

logger = logging.getLogger(__name__)


def configured_gateway_client(settings: Settings) -> TelegramGatewayClient:
    gateway_url = settings.telegram_gateway_url_value
    gateway_secret = settings.telegram_gateway_secret_value
    if gateway_url is None or gateway_secret is None:
        raise RuntimeError("Telegram gateway is not configured")

    return TelegramGatewayClient(
        base_url=gateway_url,
        secret=gateway_secret,
        timeout_seconds=settings.telegram_gateway_timeout_seconds,
    )


async def _finalize_success(
    engine: AsyncEngine,
    claim: ClaimedNotification,
) -> None:
    async with AsyncSession(engine, expire_on_commit=False) as db, db.begin():
        await mark_notification_sent(db, claim)


async def _finalize_failure(
    engine: AsyncEngine,
    claim: ClaimedNotification,
    *,
    error: str,
    max_attempts: int,
) -> None:
    async with AsyncSession(engine, expire_on_commit=False) as db, db.begin():
        await mark_notification_failed(
            db,
            claim,
            error=error,
            max_attempts=max_attempts,
        )


async def run_worker_once(
    engine: AsyncEngine,
    client: TelegramGatewayClient,
    settings: Settings,
) -> int:
    async with AsyncSession(engine, expire_on_commit=False) as db, db.begin():
        claims = await claim_notification_batch(
            db,
            batch_size=settings.notification_worker_batch_size,
            claim_ttl_seconds=settings.notification_worker_claim_ttl_seconds,
            max_attempts=settings.notification_worker_max_attempts,
        )

    for claim in claims:
        try:
            await client.send(claim.method, claim.payload)
        except Exception as exc:
            logger.warning(
                "Telegram outbox delivery failed id=%s attempt=%s",
                claim.id,
                claim.attempts,
            )
            await _finalize_failure(
                engine,
                claim,
                error=type(exc).__name__,
                max_attempts=settings.notification_worker_max_attempts,
            )
        else:
            await _finalize_success(engine, claim)

    return len(claims)


async def run_worker() -> None:
    settings = get_settings()
    client = configured_gateway_client(settings)
    engine = create_engine(settings)

    try:
        while True:
            try:
                processed = await run_worker_once(engine, client, settings)
            except Exception:
                logger.exception("Notification worker iteration failed")
                processed = 0

            if processed == 0:
                await asyncio.sleep(settings.notification_worker_poll_seconds)
    finally:
        await engine.dispose()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
