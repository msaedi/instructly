import hashlib
import json
from typing import Any, Dict

from app.ratelimit.config import settings
from app.ratelimit.redis_backend import get_redis


def idem_key(raw: str) -> str:
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return f"{settings.namespace}:idem:{digest}"


async def get_cached(raw_key: str) -> Any:
    try:
        redis_client = await get_redis()
        value = await redis_client.get(idem_key(raw_key))
        return json.loads(value) if value else None
    except Exception:
        return None


async def set_cached(raw_key: str, payload: Dict[str, Any], ttl_s: int = 86400) -> None:
    try:
        redis_client = await get_redis()
        await redis_client.setex(idem_key(raw_key), ttl_s, json.dumps(payload))
    except Exception:
        return
