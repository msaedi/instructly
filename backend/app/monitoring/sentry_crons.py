from __future__ import annotations

from typing import Any, Callable, TypeVar

try:  # pragma: no cover - optional dependency in some test environments
    from sentry_sdk.crons import monitor as _monitor
except Exception:  # pragma: no cover
    _monitor = None

_DEFAULT_MONITOR_LIMITS: dict[str, int] = {
    "checkin_margin": 10,  # minutes
    "max_runtime": 30,  # minutes
    "failure_issue_threshold": 2,
    "recovery_threshold": 1,
}

CRITICAL_BEAT_MONITOR_CONFIGS: dict[str, dict[str, Any]] = {
    "apply-data-retention-policies": {
        "schedule": {"type": "crontab", "value": "0 2 * * *"},
        "timezone": "US/Eastern",
        **_DEFAULT_MONITOR_LIMITS,
    },
    "calculate-search-metrics": {
        "schedule": {"type": "crontab", "value": "0 * * * *"},
        "timezone": "US/Eastern",
        **_DEFAULT_MONITOR_LIMITS,
    },
    "learn-location-aliases": {
        "schedule": {"type": "crontab", "value": "10 3 * * *"},
        "timezone": "US/Eastern",
        **_DEFAULT_MONITOR_LIMITS,
    },
    "resolve-undisputed-no-shows": {
        "schedule": {"type": "crontab", "value": "0 * * * *"},
        "timezone": "US/Eastern",
        **_DEFAULT_MONITOR_LIMITS,
    },
}

CRITICAL_BEAT_MONITOR_SLUGS: tuple[str, ...] = tuple(CRITICAL_BEAT_MONITOR_CONFIGS.keys())
CRITICAL_BEAT_MONITOR_EXCLUDES: tuple[str, ...] = tuple(
    f"^{slug}$" for slug in CRITICAL_BEAT_MONITOR_SLUGS
)

F = TypeVar("F", bound=Callable[..., Any])


def monitor_if_configured(slug: str) -> Callable[[F], F]:
    monitor_config = CRITICAL_BEAT_MONITOR_CONFIGS.get(slug)
    if _monitor is None or monitor_config is None:

        def decorator(func: F) -> F:
            return func

        return decorator
    return _monitor(monitor_slug=slug, monitor_config=monitor_config)
