import hashlib
import json

from app.ratelimit.config import settings
from app.ratelimit.redis_backend import get_redis


def idem_key(raw: str) -> str:
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return f"{settings.namespace}:idem:{digest}"


def get_cached(raw_key: str):
    r = get_redis()
    val = r.get(idem_key(raw_key))
    return json.loads(val) if val else None


def set_cached(raw_key: str, payload: dict, ttl_s: int = 86400):
    r = get_redis()
    r.setex(idem_key(raw_key), ttl_s, json.dumps(payload))
