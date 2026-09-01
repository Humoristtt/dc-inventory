from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from dataclasses import dataclass


class TelegramGatewayError(RuntimeError):
    """Безопасная ошибка доставки без утечки gateway secret/token."""


@dataclass(frozen=True, slots=True)
class TelegramGatewayClient:
    base_url: str
    secret: str
    timeout_seconds: int = 10

    async def send(
        self,
        method: str,
        payload: dict[str, object],
    ) -> None:
        await asyncio.to_thread(self._send_sync, method, payload)

    def _send_sync(
        self,
        method: str,
        payload: dict[str, object],
    ) -> None:
        body = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/telegram/{method}",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "User-Agent": "dc-inventory-telegram-worker/1.0",
                "X-DC-Inventory-Gateway-Secret": self.secret,
            },
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_seconds,
            ) as response:
                raw = response.read(1_048_576)
        except urllib.error.HTTPError as exc:
            raise TelegramGatewayError(
                f"gateway returned HTTP {exc.code}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise TelegramGatewayError("gateway request failed") from exc

        try:
            result = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise TelegramGatewayError("gateway returned invalid JSON") from exc

        if not isinstance(result, dict) or result.get("ok") is not True:
            raise TelegramGatewayError("Telegram Bot API call failed")
