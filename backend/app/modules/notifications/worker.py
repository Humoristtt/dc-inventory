from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from urllib.parse import urlsplit

from sqlalchemy import select
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
from app.modules.telegram_bot.models import (
    START_WELCOME_DEDUPE_PREFIX,
    TelegramChatState,
)

logger = logging.getLogger(__name__)


def validate_notification_worker_config(settings: Settings) -> None:
    validate_notification_worker_lease(settings)

    gateway_url = settings.telegram_gateway_url_value
    gateway_secret = settings.telegram_gateway_secret_value

    if gateway_url is None or gateway_secret is None:
        raise RuntimeError("Telegram gateway is not configured")

    raw_gateway_url = settings.telegram_gateway_url
    if (
        raw_gateway_url is None
        or raw_gateway_url != raw_gateway_url.strip()
    ):
        raise RuntimeError(
            "TELEGRAM_GATEWAY_URL must not contain surrounding whitespace"
        )

    try:
        parsed = urlsplit(gateway_url)
        _ = parsed.port
    except ValueError as error:
        raise RuntimeError(
            "TELEGRAM_GATEWAY_URL must be a valid absolute URL"
        ) from error

    if (
        parsed.scheme.lower() not in {"http", "https"}
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError(
            "TELEGRAM_GATEWAY_URL must be a valid absolute URL"
        )

    if (
        settings.app_env == "production"
        and parsed.scheme.lower() != "https"
    ):
        raise RuntimeError(
            "TELEGRAM_GATEWAY_URL must use HTTPS in production"
        )


def configured_gateway_client(settings: Settings) -> TelegramGatewayClient:
    validate_notification_worker_config(settings)

    gateway_url = settings.telegram_gateway_url_value
    gateway_secret = settings.telegram_gateway_secret_value

    assert gateway_url is not None
    assert gateway_secret is not None

    return TelegramGatewayClient(
        base_url=gateway_url,
        secret=gateway_secret,
        timeout_seconds=settings.telegram_gateway_timeout_seconds,
    )


def validate_notification_worker_lease(settings: Settings) -> None:
    minimum_ttl_seconds = (
        settings.telegram_gateway_timeout_seconds * 2 + 5
    )

    if (
        settings.notification_worker_claim_ttl_seconds
        < minimum_ttl_seconds
    ):
        raise RuntimeError(
            "NOTIFICATION_WORKER_CLAIM_TTL_SECONDS must be at least "
            f"{minimum_ttl_seconds} seconds for the configured "
            "TELEGRAM_GATEWAY_TIMEOUT_SECONDS"
        )


def _start_welcome_context(
    claim: ClaimedNotification,
) -> tuple[int, int] | None:
    if not claim.dedupe_key.startswith(START_WELCOME_DEDUPE_PREFIX):
        return None

    suffix = claim.dedupe_key[len(START_WELCOME_DEDUPE_PREFIX) :]
    update_raw, separator, chat_raw = suffix.partition(":")
    if not separator:
        return None

    try:
        update_id = int(update_raw)
        chat_id = int(chat_raw)
    except ValueError:
        return None

    if update_id < 0:
        return None
    return update_id, chat_id


def _telegram_message_id(result: object) -> int | None:
    if not isinstance(result, dict):
        return None
    message_id = result.get("message_id")
    if (
        isinstance(message_id, bool)
        or not isinstance(message_id, int)
        or message_id <= 0
    ):
        return None
    return message_id


async def _is_current_start(
    engine: AsyncEngine,
    *,
    chat_id: int,
    update_id: int,
) -> bool:
    async with AsyncSession(engine, expire_on_commit=False) as db:
        latest = await db.scalar(
            select(TelegramChatState.latest_start_update_id).where(
                TelegramChatState.chat_id == chat_id
            )
        )
    return latest == update_id


async def _record_welcome_if_current_in_session(
    db: AsyncSession,
    *,
    chat_id: int,
    update_id: int,
    message_id: int,
) -> bool:
    state = await db.scalar(
        select(TelegramChatState)
        .where(TelegramChatState.chat_id == chat_id)
        .with_for_update()
    )
    if state is None or state.latest_start_update_id != update_id:
        return False

    current_time = datetime.now(UTC)
    state.last_welcome_message_id = message_id
    state.last_welcome_sent_at = current_time
    state.updated_at = current_time
    await db.flush()
    return True


async def _record_welcome_if_current(
    engine: AsyncEngine,
    *,
    chat_id: int,
    update_id: int,
    message_id: int,
) -> bool:
    async with AsyncSession(engine, expire_on_commit=False) as db, db.begin():
        return await _record_welcome_if_current_in_session(
            db,
            chat_id=chat_id,
            update_id=update_id,
            message_id=message_id,
        )


async def _finalize_start_welcome_success(
    engine: AsyncEngine,
    claim: ClaimedNotification,
    *,
    chat_id: int,
    update_id: int,
    message_id: int,
) -> bool:
    async with AsyncSession(engine, expire_on_commit=False) as db, db.begin():
        is_current = await _record_welcome_if_current_in_session(
            db,
            chat_id=chat_id,
            update_id=update_id,
            message_id=message_id,
        )
        await mark_notification_sent(db, claim)
        return is_current


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


async def _best_effort_start_reaction(
    client: TelegramGatewayClient,
    *,
    chat_id: int,
    message_id: int,
) -> None:
    try:
        await client.send(
            "setMessageReaction",
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "reaction": [{"type": "emoji", "emoji": "⚡"}],
                "is_big": True,
            },
        )
    except Exception as exc:
        logger.warning(
            "Start welcome reaction failed chat_id=%s message_id=%s error=%s",
            chat_id,
            message_id,
            type(exc).__name__,
        )


async def _best_effort_delete_superseded_welcome(
    client: TelegramGatewayClient,
    *,
    chat_id: int,
    message_id: int,
) -> None:
    try:
        await client.send(
            "deleteMessage",
            {
                "chat_id": chat_id,
                "message_id": message_id,
            },
        )
    except Exception as exc:
        logger.warning(
            "Superseded start welcome cleanup failed "
            "chat_id=%s message_id=%s error=%s",
            chat_id,
            message_id,
            type(exc).__name__,
        )


async def run_worker_once(
    engine: AsyncEngine,
    client: TelegramGatewayClient,
    settings: Settings,
) -> int:
    validate_notification_worker_lease(settings)

    processed = 0

    for _ in range(settings.notification_worker_batch_size):
        async with (
            AsyncSession(engine, expire_on_commit=False) as db,
            db.begin(),
        ):
            claims = await claim_notification_batch(
                db,
                batch_size=1,
                claim_ttl_seconds=(
                    settings.notification_worker_claim_ttl_seconds
                ),
                max_attempts=settings.notification_worker_max_attempts,
            )

        if not claims:
            break

        claim = claims[0]
        start_context = _start_welcome_context(claim)

        if start_context is not None:
            start_update_id, start_chat_id = start_context
            if not await _is_current_start(
                engine,
                chat_id=start_chat_id,
                update_id=start_update_id,
            ):
                await _finalize_success(engine, claim)
                processed += 1
                continue

        try:
            result = await client.send(claim.method, claim.payload)
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
            if start_context is None:
                await _finalize_success(engine, claim)
            else:
                start_update_id, start_chat_id = start_context
                message_id = _telegram_message_id(result)
                if message_id is None:
                    logger.warning(
                        "Start welcome Telegram result has no message_id "
                        "chat_id=%s update_id=%s",
                        start_chat_id,
                        start_update_id,
                    )
                    await _finalize_success(engine, claim)
                else:
                    is_current = await _finalize_start_welcome_success(
                        engine,
                        claim,
                        chat_id=start_chat_id,
                        update_id=start_update_id,
                        message_id=message_id,
                    )
                    if is_current:
                        await _best_effort_start_reaction(
                            client,
                            chat_id=start_chat_id,
                            message_id=message_id,
                        )
                    else:
                        await _best_effort_delete_superseded_welcome(
                            client,
                            chat_id=start_chat_id,
                            message_id=message_id,
                        )

        processed += 1

    return processed


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
