from dataclasses import dataclass
import json
import os
from typing import Any, Dict, Optional


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
    redis_url: str = os.getenv("RATE_LIMIT_REDIS_URL", "redis://localhost:6379/0")
    namespace: str = os.getenv("RATE_LIMIT_NAMESPACE", "instainstru")
    default_policy: str = os.getenv("RATE_LIMIT_DEFAULT_POLICY", "read")


settings = RateLimitSettings()

# bucket policies (will be extended in PR-2)
BUCKETS = {
    "auth_bootstrap": dict(rate_per_min=100, burst=20, window_s=60),
    "read": dict(rate_per_min=60, burst=10, window_s=60),
    "write": dict(rate_per_min=20, burst=3, window_s=60),
    "financial": dict(rate_per_min=5, burst=0, window_s=60),
}

# Per-bucket shadow overrides (default inherits global). Financial enforcement in PR-3.
BUCKET_SHADOW_OVERRIDES: dict[str, bool] = {
    # If RATE_LIMIT_SHADOW_FINANCIAL is not explicitly true, default to enforcement (shadow false) for PR-3
    "financial": os.getenv("RATE_LIMIT_SHADOW_FINANCIAL", "").lower() == "true",
    # PR-4: enable enforcement for write by default; allow shadow via env
    "write": os.getenv("RATE_LIMIT_SHADOW_WRITE", "").lower() == "true",
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
            return {str(k): dict(v) for k, v in obj.items() if isinstance(v, dict)}
    except Exception:
        return {}
    return {}


def _load_overrides_from_redis() -> Dict[str, Dict[str, Any]]:
    try:
        # Lazy import to avoid circular dependency
        from .redis_backend import get_redis  # type: ignore

        r = get_redis()
        key = f"{settings.namespace}:rl:overrides"
        val = r.get(key)
        if not val:
            return {}
        obj = json.loads(val)
        if isinstance(obj, dict):
            return {str(k): dict(v) for k, v in obj.items() if isinstance(v, dict)}
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
        "read": os.getenv("RATE_LIMIT_SHADOW_READ", "").lower() == "true",
        "auth_bootstrap": os.getenv("RATE_LIMIT_SHADOW_AUTH", "").lower() == "true",
    }

    env_overrides = _load_overrides_from_env()
    redis_overrides = _load_overrides_from_redis()
    merged = {**env_overrides, **redis_overrides}
    _POLICY_OVERRIDES = merged

    info = {
        "enabled": settings.enabled,
        "shadow": settings.shadow,
        "bucket_shadows": BUCKET_SHADOW_OVERRIDES,
        "policy_overrides_count": len(_POLICY_OVERRIDES),
    }

    # Emit PR-8 metrics: count reloads and gauge active overrides
    try:
        from .metrics import rl_active_overrides, rl_config_reload_total  # type: ignore

        rl_config_reload_total.inc()
        rl_active_overrides.set(len(_POLICY_OVERRIDES))
    except Exception:
        pass

    return info


def get_effective_policy(
    route: Optional[str], method: Optional[str], bucket: str
) -> Dict[str, Any]:
    """Return merged policy for a route/method based on bucket + overrides.

    Simple prefix pattern match for overrides.
    """
    base = dict(BUCKETS.get(bucket, {}))
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
            continue
    return base
