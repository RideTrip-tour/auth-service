import logging
from collections.abc import Iterable
from typing import Any

import httpx
from fastapi import status
from internal_client import InternalClient
from internal_middleware.context import request_id_var

from app.services.jwt import get_strategy
from config import settings

logger = logging.getLogger(__name__)


class GatewayClient(InternalClient):
    def __init__(self):
        super().__init__(
            base_url=settings.gateway_url,
            service_id=settings.service_id,
            service_token=settings.service_token,
            gateway_name=settings.gateway_name,
            access_token_expire_sec=settings.access_token_expire_sec,
            jwt_secret=settings.jwt_secret,
            timeout=10.0,
        )

    async def _send_profile_request(
        self,
        user,
        path: str,
        method: str = "POST",
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        user_context = await self._create_user_context(user)
        request_id = request_id_var.get()
        if request_id is None:
            raise ValueError("Request ID is required")

        response = await self.request(
            method=method,
            path=path,
            user_context=user_context,
            request_id=request_id,
            json={} if json is None else json,
        )
        response.raise_for_status()
        return response

    def _ensure_status(self, response: httpx.Response, expected: Iterable[int]) -> None:
        if response.status_code not in expected:
            expected_str = ", ".join(str(code) for code in expected)
            raise httpx.HTTPStatusError(
                f"Expected {expected_str}, got {response.status_code}",
                request=response.request,
                response=response,
            )

    async def create_profile(self, user, json: dict[str, Any] | None = None) -> None:
        response = await self._send_profile_request(
            user=user,
            path="/api/internal/profile/create",
            json=json,
        )
        self._ensure_status(
            response=response,
            expected={
                status.HTTP_201_CREATED,
            },
        )

    async def restore_profile(self, user, json: dict[str, Any] | None = None) -> None:
        response = await self._send_profile_request(
            user=user,
            path="/api/internal/profile/me/restore",
            json=json,
        )
        self._ensure_status(
            response=response,
            expected={
                status.HTTP_204_NO_CONTENT,
            },
        )

    async def delete_profile_permanently(self, user) -> None:
        response = await self._send_profile_request(
            user,
            path="/api/internal/profile/me/permanent",
            method="DELETE",
        )
        self._ensure_status(
            response=response,
            expected={
                status.HTTP_204_NO_CONTENT,
            },
        )

    async def _create_user_context(self, user) -> str:
        strategy = get_strategy()
        return await strategy.write_token(user)
