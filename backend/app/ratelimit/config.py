from dataclasses import dataclass
import json
import logging
import os
from typing import Any, Dict, Optional, cast

from .metrics import rl_active_overrides, rl_config_reload_total

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RateLimitSettings:
    enabled: bool = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
    # Default: true in non-prod, false in prod unless explicitly set via env
    shadow: bool = (
        os.getenv("RATE_LIMIT_SHADOW") is not None
        and os.getenv("RATE_LIMIT_SHADOW", "true").lower() == "true"
        or (
            os.getenv("RATE_LIMIT_SHADOW") is None
            and os.getenv("SITE_MODE", "").strip().lower() not in {"prod", "production", "live"}
        )
    )
    # Rate limiting/idempotency Redis (can be isolated from general caching Redis).
    # Note: the global ASGI middleware in `app.middleware.rate_limiter_asgi` uses CacheService
    # (REDIS_URL / `settings.redis_url`). Set RATE_LIMIT_REDIS_URL only when you intentionally
    # want isolation for the new `app.ratelimit.*` dependency-based limiter/idempotency/locks.
    redis_url: str = os.getenv("RATE_LIMIT_REDIS_URL", "redis://localhost:6379/0")
    namespace: str = os.getenv("RATE_LIMIT_NAMESPACE", "instainstru")
    default_policy: str = os.getenv("RATE_LIMIT_DEFAULT_POLICY", "read")


settings: RateLimitSettings = RateLimitSettings()

# bucket policies (will be extended in PR-2)
BUCKETS: Dict[str, Dict[str, Any]] = {
    "auth_bootstrap": dict(rate_per_min=100, burst=20, window_s=60),
    "read": dict(rate_per_min=60, burst=10, window_s=60),
    # Messaging uses the "write" bucket; relax to 30/min with a burst of 5 to prevent 429s during normal chat use
    "write": dict(rate_per_min=30, burst=10, window_s=60),
    # Conversation-scoped messaging limit (per user+conversation)
    "conv_msg": dict(rate_per_min=60, burst=10, window_s=60),
    "financial": dict(rate_per_min=5, burst=0, window_s=60),
}

# Per-bucket shadow overrides (default inherits global). Financial enforcement in PR-3.
BUCKET_SHADOW_OVERRIDES: dict[str, bool] = {
    # If RATE_LIMIT_SHADOW_FINANCIAL is not explicitly true, default to enforcement (shadow false) for PR-3
    "financial": os.getenv("RATE_LIMIT_SHADOW_FINANCIAL", "").lower() == "true",
    # PR-4: enable enforcement for write by default; allow shadow via env
    "write": os.getenv("RATE_LIMIT_SHADOW_WRITE", "").lower() == "true",
    "conv_msg": os.getenv("RATE_LIMIT_SHADOW_CONV_MSG", "").lower() == "true",
    # Additional per-bucket toggles for PR-7
    "read": os.getenv("RATE_LIMIT_SHADOW_READ", "").lower() == "true",
    "auth_bootstrap": os.getenv("RATE_LIMIT_SHADOW_AUTH", "").lower() == "true",
}


def is_shadow_mode(bucket: str) -> bool:
    """Return effective shadow flag for a bucket, honoring overrides."""
    override = BUCKET_SHADOW_OVERRIDES.get(bucket)
    return settings.shadow if override is None else bool(override)


# Route policy overrides: map of routePattern -> {rate_per_min, burst, window_s, shadow}
_POLICY_OVERRIDES: Dict[str, Dict[str, Any]] = {}


def _load_overrides_from_env() -> Dict[str, Dict[str, Any]]:
    raw = os.getenv("RATE_LIMIT_POLICY_OVERRIDES_JSON", "").strip()
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return {
                str(k): cast(Dict[str, Any], dict(v)) for k, v in obj.items() if isinstance(v, dict)
            }
    except Exception:
        return {}
    return {}


async def _load_overrides_from_redis_async() -> Dict[str, Dict[str, Any]]:
    """Best-effort load of policy overrides from Redis (async)."""
    try:
        from .redis_backend import get_redis

        # Lazy import to avoid circular dependency
        r = await get_redis()
        key = f"{settings.namespace}:rl:overrides"
        val = await r.get(key)
        if not val:
            return {}
        obj = json.loads(val)
        if isinstance(obj, dict):
            return {
                str(k): cast(Dict[str, Any], dict(v)) for k, v in obj.items() if isinstance(v, dict)
            }
    except Exception:
        return {}
    return {}


def reload_config(cache_ttl_s: int = 30) -> Dict[str, Any]:
    """Reload runtime config from env and Redis overrides.

    Returns merged view for debugging/introspection.
    """
    global BUCKET_SHADOW_OVERRIDES, _POLICY_OVERRIDES, settings

    # Recreate settings to resample env flags
    settings = RateLimitSettings()

    # Rebuild bucket shadow overrides from env
    BUCKET_SHADOW_OVERRIDES = {
        "financial": os.getenv("RATE_LIMIT_SHADOW_FINANCIAL", "").lower() == "true",
        "write": os.getenv("RATE_LIMIT_SHADOW_WRITE", "").lower() == "true",
        "conv_msg": os.getenv("RATE_LIMIT_SHADOW_CONV_MSG", "").lower() == "true",
        "read": os.getenv("RATE_LIMIT_SHADOW_READ", "").lower() == "true",
        "auth_bootstrap": os.getenv("RATE_LIMIT_SHADOW_AUTH", "").lower() == "true",
    }

    env_overrides = _load_overrides_from_env()
    # Redis-backed overrides require async Redis access; keep this function sync and env-only.
    # If you need Redis overrides, call `await reload_config_async()`.
    _POLICY_OVERRIDES = env_overrides

    info: Dict[str, Any] = {
        "enabled": settings.enabled,
        "shadow": settings.shadow,
        "bucket_shadows": BUCKET_SHADOW_OVERRIDES,
        "policy_overrides_count": len(_POLICY_OVERRIDES),
    }

    # Emit PR-8 metrics: count reloads and gauge active overrides
    try:
        rl_config_reload_total.inc()
        rl_active_overrides.set(len(_POLICY_OVERRIDES))
    except Exception:
        logger.debug("Non-fatal error ignored", exc_info=True)
    return info


async def reload_config_async(cache_ttl_s: int = 30) -> Dict[str, Any]:
    """Async version of reload_config that includes Redis-backed overrides."""
    global BUCKET_SHADOW_OVERRIDES, _POLICY_OVERRIDES, settings

    settings = RateLimitSettings()

    BUCKET_SHADOW_OVERRIDES = {
        "financial": os.getenv("RATE_LIMIT_SHADOW_FINANCIAL", "").lower() == "true",
        "write": os.getenv("RATE_LIMIT_SHADOW_WRITE", "").lower() == "true",
        "conv_msg": os.getenv("RATE_LIMIT_SHADOW_CONV_MSG", "").lower() == "true",
        "read": os.getenv("RATE_LIMIT_SHADOW_READ", "").lower() == "true",
        "auth_bootstrap": os.getenv("RATE_LIMIT_SHADOW_AUTH", "").lower() == "true",
    }

    env_overrides = _load_overrides_from_env()
    redis_overrides = await _load_overrides_from_redis_async()
    _POLICY_OVERRIDES = {**env_overrides, **redis_overrides}

    info: Dict[str, Any] = {
        "enabled": settings.enabled,
        "shadow": settings.shadow,
        "bucket_shadows": BUCKET_SHADOW_OVERRIDES,
        "policy_overrides_count": len(_POLICY_OVERRIDES),
    }

    try:
        rl_config_reload_total.inc()
        rl_active_overrides.set(len(_POLICY_OVERRIDES))
    except Exception:
        logger.debug("Non-fatal error ignored", exc_info=True)
    return info


def get_effective_policy(
    route: Optional[str], method: Optional[str], bucket: str
) -> Dict[str, Any]:
    """Return merged policy for a route/method based on bucket + overrides.

    Simple prefix pattern match for overrides.
    """
    base: Dict[str, Any] = dict(BUCKETS.get(bucket, {}))
    base["bucket"] = bucket
    base["shadow"] = is_shadow_mode(bucket)
    if not route:
        return base
    for pattern, override in _POLICY_OVERRIDES.items():
        try:
            if str(route).startswith(pattern):
                merged = {**base}
                if "rate" in override:
                    merged["rate_per_min"] = int(override["rate"])  # tolerate shorthand
                if "burst" in override:
                    merged["burst"] = int(override["burst"])
                if "window" in override:
                    merged["window_s"] = int(override["window"])  # tolerate shorthand
                if "shadow" in override:
                    merged["shadow"] = bool(override["shadow"])
                return merged
        except Exception:
            logger.debug("Non-fatal error ignored", exc_info=True)
            continue
    return base
