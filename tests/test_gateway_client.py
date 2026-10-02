from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.clients.gateway_client import GatewayClient


def test_gateway_client_is_singleton(gateway_client):
    client = GatewayClient()
    assert gateway_client is client


def test_get_headers(gateway_client):

    with (
        patch(
            "app.clients.gateway_client.settings.service_id",
            "service-id",
        ),
        patch(
            "app.clients.gateway_client.settings.service_token",
            "service-token",
        ),
    ):
        headers = gateway_client._get_headers("user-context")

    assert headers["X-Service-ID"] == "service-id"
    assert headers["X-Service-Token"] == "service-token"
    assert headers["X-User-Context"] == "user-context"


@pytest.mark.asyncio
async def test_create_profile(gateway_client, monkeypatch):
    user = MagicMock()
    user_context = "user-context"

    async def fake_request(method, path, headers, json):
        assert method == "POST"
        assert path == "/api/profile/create"
        assert headers["X-User-Context"] == "user-context"

        request = httpx.Request(method, f"http://test{path}")
        return httpx.Response(200, request=request)

    monkeypatch.setattr(gateway_client.client, "request", fake_request)
    monkeypatch.setattr(
        gateway_client,
        "_create_user_context",
        AsyncMock(return_value=user_context),
    )

    await gateway_client.create_profile(user)
