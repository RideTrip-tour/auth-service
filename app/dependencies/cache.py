from fastapi import Request

from app.services.cache import CacheManager


def get_cache_manager(request: Request):
    return CacheManager(request.app.state.redis)
