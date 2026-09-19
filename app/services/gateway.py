import httpx

from app.services.users import get_strategy
from config import settings


class GatewayClient:
    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def create_profile(self, user) -> None:
        await self._post(
            "/api/profile/create/",
            user_context=await self._create_user_context(user),
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

    async def _post(self, path: str, user_context: str) -> None:
        response = await self._client.post(
            path,
            headers=self._get_headers(user_context),
        )
        response.raise_for_status()
