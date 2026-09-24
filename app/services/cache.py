import redis.asyncio as redis


class CacheManager:
    def __init__(self, redis: redis.Redis):
        self.redis = redis

    async def acquire_cooldown(
        self,
        key: str,
        ttl: int = 60,
    ) -> bool:
        return bool(
            await self.redis.set(
                key,
                "1",
                ex=ttl,
                nx=True,
            )
        )
