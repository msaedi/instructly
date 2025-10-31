"""
Prometheus metrics endpoint for monitoring infrastructure.

This is a PUBLIC endpoint (no authentication required) following
standard Prometheus practices. It exposes metrics collected from
the @measure_operation decorators throughout the application.
"""

import os
from time import monotonic
from typing import Optional, Tuple

from fastapi import APIRouter, Request, Response
from prometheus_client import Counter

from ..core.config import settings
from ..monitoring.prometheus_metrics import REGISTRY, prometheus_metrics

router = APIRouter()


_METRICS_CACHE_TTL_SECONDS = 1.0
_metrics_cache: Optional[Tuple[float, bytes]] = None
_scrape_counter = Counter(
    "instainstru_prometheus_scrapes_total",
    "Total number of Prometheus metrics scrapes",
    registry=REGISTRY,
)


def _cache_enabled() -> bool:
    if os.getenv("PROMETHEUS_DISABLE_CACHE", "0").lower() in {"1", "true", "yes"}:
        return False
    env = (settings.environment or "").strip().lower()
    if env == "test":
        return os.getenv("PROMETHEUS_CACHE_IN_TESTS", "1").lower() in {"1", "true", "yes"}
    return True


def _get_cached_metrics_payload(*, force_refresh: bool = False) -> bytes:
    """Return cached metrics payload with fresh-if-recent bypass for rapid scrapes."""

    global _metrics_cache

    if not _cache_enabled():
        return prometheus_metrics.get_metrics()

    now = monotonic()

    if not force_refresh and _metrics_cache is not None:
        cached_ts, cached_payload = _metrics_cache
        elapsed = now - cached_ts

        if elapsed < _METRICS_CACHE_TTL_SECONDS:
            return cached_payload

    payload = prometheus_metrics.get_metrics()
    _metrics_cache = (now, payload)
    return payload


def warm_prometheus_metrics_response_cache() -> None:
    """Populate the metrics response cache so the first scrape is warm."""

    global _metrics_cache

    if not _cache_enabled():
        try:
            prometheus_metrics.get_metrics()
        except Exception:
            return
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
async def get_prometheus_metrics(request: Request) -> Response:
    """
    Expose Prometheus metrics for scraping.

    This endpoint is intentionally PUBLIC (no authentication) as per
    Prometheus best practices. The metrics exposed are performance
    metrics only and do not contain sensitive business data.

    Returns:
        Response with Prometheus exposition format (text/plain)
    """
    refresh_flag = request.query_params.get("refresh", "").lower() in {"1", "true", "yes"}
    _scrape_counter.inc()
    if _cache_enabled():
        global _metrics_cache
        _metrics_cache = None
    metrics_data = _get_cached_metrics_payload(force_refresh=refresh_flag)
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
