from unittest.mock import AsyncMock

import pytest

from app.services.cache import CacheManager


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("redis_result", "expected"),
    [
        (True, True),
        (False, False),
        (None, False),
    ],
)
async def test_acquire_cooldown(redis_result, expected):
    redis = AsyncMock()
    redis.set.return_value = redis_result

    cache = CacheManager(redis)

    result = await cache.acquire_cooldown("test-key", ttl=30)

    assert result is expected
    redis.set.assert_awaited_once_with(
        "test-key",
        "1",
        ex=30,
        nx=True,
    )
