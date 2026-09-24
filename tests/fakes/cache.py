class FakeCacheManager:
    def __init__(self):
        self._cache: dict[str, object] = {}

    async def acquire_cooldown(self, key: str, ttl: int = 60) -> bool:
        if key in self._cache:
            return False

        self._cache[key] = "1"
        return True

    def set(self, key: str, value: object = "1") -> None:
        self._cache[key] = value
