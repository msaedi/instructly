import hashlib
import json
from typing import Any, Dict

from redis import Redis

from app.ratelimit.config import settings
from app.ratelimit.redis_backend import get_redis


def idem_key(raw: str) -> str:
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return f"{settings.namespace}:idem:{digest}"


def get_cached(raw_key: str) -> Any:
    redis_client: Redis = get_redis()
    value = redis_client.get(idem_key(raw_key))
    return json.loads(value) if value else None


def set_cached(raw_key: str, payload: Dict[str, Any], ttl_s: int = 86400) -> None:
    redis_client: Redis = get_redis()
    redis_client.setex(idem_key(raw_key), ttl_s, json.dumps(payload))
