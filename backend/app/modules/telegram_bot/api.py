from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request, status

from app.core.config import Settings
from app.modules.auth.dependencies import DbSession
from app.modules.telegram_bot.service import (
    decode_update_json,
    mark_telegram_update_processed,
    process_telegram_update,
    register_telegram_update,
    verify_webhook_secret,
)

router = APIRouter(prefix="/api/telegram", tags=["telegram"])

MAX_TELEGRAM_UPDATE_BYTES = 1_048_576


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    db: DbSession,
    secret_token: str | None = Header(
        default=None,
        alias="X-Telegram-Bot-Api-Secret-Token",
    ),
) -> dict[str, bool]:
    settings: Settings = request.app.state.settings
    configured_secret = settings.telegram_webhook_secret_value
    if configured_secret is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram webhook is not configured",
        )

    if not verify_webhook_secret(secret_token, configured_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid Telegram webhook secret",
        )

    raw = await request.body()
    if len(raw) > MAX_TELEGRAM_UPDATE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Telegram update is too large",
        )

    try:
        payload = decode_update_json(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid Telegram update",
        ) from exc

    update_id = payload.get("update_id")
    if (
        isinstance(update_id, bool)
        or not isinstance(update_id, int)
        or update_id < 0
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid Telegram update_id",
        )

    async with db.begin():
        inserted = await register_telegram_update(db, update_id)
        if not inserted:
            return {"ok": True}

        await process_telegram_update(
            db,
            update_id=update_id,
            payload=payload,
            settings=settings,
        )
        await mark_telegram_update_processed(db, update_id)

    return {"ok": True}
