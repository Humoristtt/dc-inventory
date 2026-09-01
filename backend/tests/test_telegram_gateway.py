from __future__ import annotations

import urllib.request

from app.modules.notifications.gateway import TelegramGatewayClient


class _Response:
    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        return b'{"ok":true}'


def test_gateway_client_sets_service_user_agent(monkeypatch) -> None:
    captured: dict[str, str | None] = {}

    def fake_urlopen(
        request: urllib.request.Request,
        *,
        timeout: int,
    ) -> _Response:
        assert timeout == 10
        captured["user_agent"] = request.get_header("User-agent")
        return _Response()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    client = TelegramGatewayClient(
        base_url="https://gateway.example",
        secret="test-secret",
    )

    client._send_sync(
        "sendMessage",
        {
            "chat_id": 1,
            "text": "test",
        },
    )

    assert captured["user_agent"] == "dc-inventory-telegram-worker/1.0"
