from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from internal_middleware.context import request_id_var

from app.clients.gateway_client import GatewayClient


def test_gateway_client_is_singleton(gateway_client):
    client = GatewayClient()
    assert gateway_client is client


def test_get_headers(gateway_client):

    with (
        patch.object(gateway_client, "service_id", "service-id"),
        patch.object(gateway_client, "service_token", "service-token"),
    ):
        headers = gateway_client._get_headers(
            user_context="user-context",
            request_id="request-id",
        )

    assert headers["X-Service-ID"] == "service-id"
    assert headers["X-Service-Token"] == "service-token"
    assert headers["X-User-Context"] == "user-context"
    assert headers["X-Request-ID"] == "request-id"


@pytest.mark.asyncio
async def test_create_profile(gateway_client, monkeypatch, request_id):
    user = MagicMock()
    user_context = "user-context"

    async def fake_request(method, url, headers=None, json=None, **kwargs):
        assert method == "POST"
        assert url.endswith("/api/internal/profile/create")
        assert headers["X-User-Context"] == user_context

        request = httpx.Request(method, str(url))
        return httpx.Response(201, request=request)

    monkeypatch.setattr(gateway_client.client, "request", fake_request)
    monkeypatch.setattr(
        gateway_client,
        "_create_user_context",
        AsyncMock(return_value=user_context),
    )

    await gateway_client.create_profile(user=user)


@pytest.mark.asyncio
async def test_restore_profile(gateway_client, monkeypatch, request_id):
    user = MagicMock()
    user_context = "user-context"

    create_context_mock = AsyncMock(return_value=user_context)
    request_mock = AsyncMock(return_value=MagicMock(status_code=204))

    monkeypatch.setattr(gateway_client, "_create_user_context", create_context_mock)
    monkeypatch.setattr(gateway_client, "request", request_mock)

    await gateway_client.restore_profile(user)

    create_context_mock.assert_awaited_once_with(user)
    request_mock.assert_awaited_once_with(
        method="POST",
        path="/api/internal/profile/me/restore",
        user_context=user_context,
        request_id=request_id_var.get(),
        json={},
    )


@pytest.mark.asyncio
async def test_delete_profile_permanently(gateway_client, monkeypatch, request_id):
    user = MagicMock()
    user_context = "user-context"

    create_context_mock = AsyncMock(return_value=user_context)
    request_mock = AsyncMock()

    monkeypatch.setattr(gateway_client, "_create_user_context", create_context_mock)
    monkeypatch.setattr(gateway_client, "request", request_mock)

    await gateway_client.delete_profile_permanently(user)

    create_context_mock.assert_awaited_once_with(user)
    request_mock.assert_awaited_once_with(
        method="DELETE",
        path="/api/internal/profile/me/permanent",
        user_context=user_context,
        request_id=request_id_var.get(),
        json={},
    )


@pytest.mark.asyncio
async def test_create_user_context(gateway_client):
    user = MagicMock()
    strategy = MagicMock()
    strategy.write_token = AsyncMock(return_value="user-context")

    module_globals = GatewayClient._create_user_context.__globals__

    with patch.dict(
        module_globals,
        {"get_strategy": MagicMock(return_value=strategy)},
    ) as patched_globals:
        get_strategy_mock = patched_globals["get_strategy"]
        result = await gateway_client._create_user_context(user)

    get_strategy_mock.assert_called_once_with()
    strategy.write_token.assert_awaited_once_with(user)
    assert result == "user-context"
