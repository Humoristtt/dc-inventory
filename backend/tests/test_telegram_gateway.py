from __future__ import annotations

import httpx
import pytest

from app.modules.notifications.gateway import (
    TelegramGatewayClient,
    TelegramGatewayError,
)


@pytest.mark.asyncio
async def test_gateway_client_reuses_async_pool_and_preserves_contract() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": {"message_id": len(requests)},
            },
        )

    client = TelegramGatewayClient(
        base_url="https://gateway.example/",
        secret="test-secret",
        timeout_seconds=10,
        transport=httpx.MockTransport(handler),
    )

    try:
        first = await client.send(
            "sendMessage",
            {"chat_id": 1, "text": "Привет"},
        )
        pooled_client = client._client
        second = await client.send(
            "deleteMessage",
            {"chat_id": 1, "message_id": 1},
        )

        assert first == {"message_id": 1}
        assert second == {"message_id": 2}

        assert pooled_client is not None
        assert client._client is pooled_client

        assert [request.url.path for request in requests] == [
            "/telegram/sendMessage",
            "/telegram/deleteMessage",
        ]
        for request in requests:
            assert (
                request.headers["User-Agent"]
                == "dc-inventory-telegram-worker/1.0"
            )
            assert (
                request.headers["X-DC-Inventory-Gateway-Secret"]
                == "test-secret"
            )
            assert request.headers["Content-Type"] == "application/json"
    finally:
        await client.aclose()

    assert pooled_client.is_closed
    assert client._client is None


@pytest.mark.asyncio
async def test_gateway_client_maps_http_error_without_response_body() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            503,
            text="do-not-expose-upstream-body",
        )

    client = TelegramGatewayClient(
        base_url="https://gateway.example",
        secret="test-secret",
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(
            TelegramGatewayError,
            match=r"^gateway returned HTTP 503$",
        ):
            await client.send(
                "sendMessage",
                {"chat_id": 1, "text": "test"},
            )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_gateway_client_maps_transport_error_safely() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(
            "do-not-expose-network-detail",
            request=request,
        )

    client = TelegramGatewayClient(
        base_url="https://gateway.example",
        secret="test-secret",
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(
            TelegramGatewayError,
            match=r"^gateway request failed$",
        ):
            await client.send(
                "sendMessage",
                {"chat_id": 1, "text": "test"},
            )
    finally:
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [
        b"not-json",
        b'{"ok":false}',
    ],
)
async def test_gateway_client_rejects_invalid_gateway_result(
    content: bytes,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, content=content)

    client = TelegramGatewayClient(
        base_url="https://gateway.example",
        secret="test-secret",
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(TelegramGatewayError):
            await client.send(
                "sendMessage",
                {"chat_id": 1, "text": "test"},
            )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_gateway_client_rejects_oversized_response() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            content=b"x" * (1_048_576 + 1),
        )

    client = TelegramGatewayClient(
        base_url="https://gateway.example",
        secret="test-secret",
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(
            TelegramGatewayError,
            match=r"^gateway response is too large$",
        ):
            await client.send(
                "sendMessage",
                {"chat_id": 1, "text": "test"},
            )
    finally:
        await client.aclose()
