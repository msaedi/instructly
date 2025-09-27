import time

from redis import Redis

from .config import settings
from .redis_backend import get_redis


def acquire_lock(key: str, ttl_s: int = 30) -> bool:
    r: Redis = get_redis()
    namespaced = f"{settings.namespace}:lock:{key}"
    # Redis SET with NX and EX returns True if the key was set
    return r.set(namespaced, str(time.time()), nx=True, ex=ttl_s) is True


def release_lock(key: str) -> None:
    r: Redis = get_redis()
    r.delete(f"{settings.namespace}:lock:{key}")
