import time

from .config import settings
from .redis_backend import get_redis


async def acquire_lock(key: str, ttl_s: int = 30) -> bool:
    try:
        r = await get_redis()
    except Exception:
        # Fail-open if Redis is unavailable
        return True
    namespaced = f"{settings.namespace}:lock:{key}"
    # Redis SET with NX and EX returns True if the key was set
    return bool(await r.set(namespaced, str(time.time()), nx=True, ex=ttl_s))


async def release_lock(key: str) -> None:
    try:
        r = await get_redis()
    except Exception:
        return
    await r.delete(f"{settings.namespace}:lock:{key}")
