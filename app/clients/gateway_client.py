import logging
from typing import Any

from initial_client import InitialClient

from app.services.jwt import get_strategy
from config import settings

logger = logging.getLogger(__name__)


class GatewayClient(InitialClient):
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

    async def create_profile(
        self, user, request_id: str, json: dict[str, Any] | None=None
    ) -> None:
        user_context = await self._create_user_context(user)

        await self.request(
            method="POST",
            path="/api/profile/create",
            user_context=user_context,
            request_id=request_id,
            json={} if json is None else json,
        )

    async def _create_user_context(self, user) -> str:
        strategy = get_strategy()
        return await strategy.write_token(user)
