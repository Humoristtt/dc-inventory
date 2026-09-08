from __future__ import annotations

import json

import httpx

_RESPONSE_LIMIT_BYTES = 1_048_576
_USER_AGENT = "dc-inventory-telegram-worker/1.0"


class TelegramGatewayError(RuntimeError):
    """Безопасная ошибка доставки без утечки gateway secret/token."""


class TelegramGatewayClient:
    def __init__(
        self,
        *,
        base_url: str,
        secret: str,
        timeout_seconds: int = 10,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.secret = secret
        self.timeout_seconds = timeout_seconds
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            timeout = float(self.timeout_seconds)
            self._client = httpx.AsyncClient(
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": _USER_AGENT,
                    "X-DC-Inventory-Gateway-Secret": self.secret,
                },
                timeout=httpx.Timeout(
                    connect=timeout,
                    read=timeout,
                    write=timeout,
                    pool=timeout,
                ),
                limits=httpx.Limits(
                    max_connections=10,
                    max_keepalive_connections=10,
                    keepalive_expiry=30.0,
                ),
                follow_redirects=False,
                transport=self._transport,
            )
        return self._client

    async def send(
        self,
        method: str,
        payload: dict[str, object],
    ) -> object:
        body = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

        try:
            async with self._get_client().stream(
                "POST",
                f"{self.base_url}/telegram/{method}",
                content=body,
            ) as response:
                response.raise_for_status()

                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(raw) + len(chunk) > _RESPONSE_LIMIT_BYTES:
                        raise TelegramGatewayError(
                            "gateway response is too large"
                        )
                    raw.extend(chunk)

        except httpx.HTTPStatusError as exc:
            raise TelegramGatewayError(
                f"gateway returned HTTP {exc.response.status_code}"
            ) from exc
        except httpx.RequestError as exc:
            raise TelegramGatewayError(
                "gateway request failed"
            ) from exc

        try:
            result: object = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise TelegramGatewayError(
                "gateway returned invalid JSON"
            ) from exc

        if not isinstance(result, dict) or result.get("ok") is not True:
            raise TelegramGatewayError(
                "Telegram Bot API call failed"
            )

        return result.get("result")

    async def aclose(self) -> None:
        client = self._client
        self._client = None
        if client is not None:
            await client.aclose()
