from typing import Annotated

from fastapi import Depends, Request

from app.services.cache import CacheManager


def get_cache_manager(request: Request):
    return CacheManager(request.app.state.redis)


CacheManagerDep = Annotated[CacheManager, Depends(get_cache_manager)]
