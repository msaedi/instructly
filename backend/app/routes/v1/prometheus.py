"""
Prometheus metrics endpoint for monitoring infrastructure.

This is a PUBLIC endpoint (no authentication required) following
standard Prometheus practices. It exposes metrics collected from
the @measure_operation decorators throughout the application.
"""

import os
import re
from time import monotonic
from typing import Optional, Tuple

from fastapi import APIRouter, Request, Response
from prometheus_client import Counter

from app.core.config import settings
from app.monitoring.prometheus_metrics import REGISTRY, prometheus_metrics

router = APIRouter()


_BASE_CACHE_TTL_SECONDS = 1.0
_metrics_cache: Optional[Tuple[float, bytes]] = None
_scrape_counter = Counter(
    "instainstru_prometheus_scrapes_total",
    "Total number of Prometheus metrics scrapes",
    registry=REGISTRY,
)
SCRAPE_COUNT = 0


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

    now = monotonic()
    cache_allowed = _cache_enabled()

    if not cache_allowed or force_refresh or _metrics_cache is None:
        payload = prometheus_metrics.get_metrics()
        if cache_allowed:
            _metrics_cache = (now, payload)
        return payload

    cached_ts, cached_payload = _metrics_cache
    ttl = (
        5.0
        if os.getenv("PROMETHEUS_CACHE_IN_TESTS", "0").lower() in {"1", "true", "yes"}
        else _BASE_CACHE_TTL_SECONDS
    )

    if now - cached_ts < ttl:
        return cached_payload

    payload = prometheus_metrics.get_metrics()
    _metrics_cache = (now, payload)
    return payload


def _refresh_scrape_counter_line(payload: bytes) -> bytes:
    """Update the scrape counter line so it reflects the latest increment."""
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return payload

    replacement = f"instainstru_prometheus_scrapes_total {SCRAPE_COUNT}"

    updated_text, count = re.subn(
        r"instainstru_prometheus_scrapes_total\s+[0-9eE\+\-\.]+", replacement, text, count=1
    )
    if count == 0:
        return payload
    return updated_text.encode("utf-8")


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


@router.get("/prometheus", include_in_schema=False, response_class=Response, response_model=None)
async def get_prometheus_metrics(request: Request) -> Response:
    """
    Expose Prometheus metrics for scraping.

    This endpoint is intentionally PUBLIC (no authentication) as per
    Prometheus best practices. The metrics exposed are performance
    metrics only and do not contain sensitive business data.

    Returns:
        Response with Prometheus exposition format (text/plain)
    """
    global SCRAPE_COUNT
    refresh_flag = request.query_params.get("refresh", "").lower() in {"1", "true", "yes"}

    metrics_data = _get_cached_metrics_payload(force_refresh=refresh_flag)

    SCRAPE_COUNT += 1
    _scrape_counter.inc()
    response_body = _refresh_scrape_counter_line(metrics_data)
    content_type = prometheus_metrics.get_content_type()

    return Response(
        content=response_body,
        media_type=content_type,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )
