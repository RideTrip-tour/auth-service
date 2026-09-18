import httpx

from config import settings


class GatewayClient:
    async def create_profile(self, user_context: str) -> None:
        async with httpx.AsyncClient(
            base_url=settings.gateway_url,
        ) as client:
            response = await client.post(
                "/api/profile/",
                headers={
                    "X-Service-ID": settings.service_id,
                    "X-Service-Token": settings.service_token,
                    "X-User-Context": user_context,
                },
            )
        response.raise_for_status()


gateway_cleint = GatewayClient()
