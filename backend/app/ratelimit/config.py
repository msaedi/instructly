import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitSettings:
    enabled: bool = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
    shadow: bool = os.getenv("RATE_LIMIT_SHADOW", "true").lower() == "true"
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
}


def is_shadow_mode(bucket: str) -> bool:
    """Return effective shadow flag for a bucket, honoring overrides."""
    override = BUCKET_SHADOW_OVERRIDES.get(bucket)
    return settings.shadow if override is None else bool(override)
