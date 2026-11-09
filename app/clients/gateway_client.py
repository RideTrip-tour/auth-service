import logging
from typing import Any

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
    ) -> None:
        user_context = await self._create_user_context(user)

        await self.request(
            method=method,
            path=path,
            user_context=user_context,
            request_id=request_id_var.get(),
            json={} if json is None else json,
        )

    async def create_profile(self, user, json: dict[str, Any] | None = None) -> None:
        await self._send_profile_request(
            user=user,
            path="/api/internal/profile/create",
            json=json,
        )

    async def restore_profile(self, user, json: dict[str, Any] | None = None) -> None:
        await self._send_profile_request(
            user=user,
            path="/api/internal/profile/me/restore",
            json=json,
        )

    async def delete_profile_permanently(self, user) -> None:
        await self._send_profile_request(
            user,
            path="/api/internal/profile/me/permanent",
            method="DELETE",
        )

    async def _create_user_context(self, user) -> str:
        strategy = get_strategy()
        return await strategy.write_token(user)
