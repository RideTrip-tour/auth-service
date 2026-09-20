import httpx

from app.services.jwt import get_strategy
from config import settings


class GatewayClient:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "client"):
            self.client = httpx.AsyncClient(
                base_url=settings.gateway_url,
                timeout=10.0,
            )

    async def create_profile(self, user) -> None:
        user_context = await self._create_user_context(user)

        await self._request(
            method="POST",
            path="/api/profile/create/",
            user_context=user_context,
        )

    async def _create_user_context(self, user) -> str:
        strategy = get_strategy()
        return await strategy.write_token(user)

    def _get_headers(self, user_context: str) -> dict[str, str]:
        return {
            "X-Service-ID": settings.service_id,
            "X-Service-Token": settings.service_token,
            "X-User-Context": user_context,
        }

    async def _request(
        self,
        method: str,
        path: str,
        user_context: str,
    ) -> None:
        response = await self.client.request(
            method,
            path,
            headers=self._get_headers(user_context),
        )
        response.raise_for_status()

    async def close(self) -> None:
        await self.client.aclose()
