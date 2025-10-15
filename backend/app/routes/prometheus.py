"""
Prometheus metrics endpoint for monitoring infrastructure.

This is a PUBLIC endpoint (no authentication required) following
standard Prometheus practices. It exposes metrics collected from
the @measure_operation decorators throughout the application.
"""

from time import monotonic
from typing import Optional, Tuple

from fastapi import APIRouter, Response

from ..core.config import settings
from ..monitoring.prometheus_metrics import prometheus_metrics

router = APIRouter()


_METRICS_CACHE_TTL_SECONDS = 1.0
_METRICS_FORCE_REFRESH_WINDOW_SECONDS = 0.75
_metrics_cache: Optional[Tuple[float, bytes]] = None


def _cache_enabled() -> bool:
    env = (settings.environment or "").strip().lower()
    return env != "test"


def _get_cached_metrics_payload() -> bytes:
    """Return cached metrics payload with fresh-if-recent bypass for rapid scrapes."""

    global _metrics_cache

    if not _cache_enabled():
        return prometheus_metrics.get_metrics()

    now = monotonic()
    if _metrics_cache is not None:
        cached_ts, cached_payload = _metrics_cache
        elapsed = now - cached_ts

        if elapsed < _METRICS_FORCE_REFRESH_WINDOW_SECONDS:
            # Allow counters to advance when a second scrape follows immediately.
            return prometheus_metrics.get_metrics()

        if elapsed < _METRICS_CACHE_TTL_SECONDS:
            return cached_payload

    payload = prometheus_metrics.get_metrics()
    _metrics_cache = (now, payload)
    return payload


def warm_prometheus_metrics_response_cache() -> None:
    """Populate the metrics response cache so the first scrape is warm."""

    global _metrics_cache

    if not _cache_enabled():
        return

    try:
        payload = prometheus_metrics.get_metrics()
    except Exception:
        # Avoid failing startup if metrics generation raises (e.g., during tests)
        return

    _metrics_cache = (monotonic(), payload)


@router.get(
    "/metrics/prometheus", include_in_schema=False, response_class=Response, response_model=None
)
async def get_prometheus_metrics() -> Response:
    """
    Expose Prometheus metrics for scraping.

    This endpoint is intentionally PUBLIC (no authentication) as per
    Prometheus best practices. The metrics exposed are performance
    metrics only and do not contain sensitive business data.

    Returns:
        Response with Prometheus exposition format (text/plain)
    """
    metrics_data = _get_cached_metrics_payload()
    content_type = prometheus_metrics.get_content_type()

    return Response(
        content=metrics_data,
        media_type=content_type,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )
