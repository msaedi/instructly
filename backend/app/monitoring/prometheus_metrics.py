"""
Prometheus metrics module for InstaInstru.

This module provides Prometheus-compatible metrics by leveraging existing
@measure_operation performance data. It follows Prometheus naming conventions
and best practices for metric types.
"""

from collections import defaultdict
import os
from threading import Lock
from time import monotonic
from typing import Dict, Optional, cast

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# Create a custom registry to avoid conflicts with default metrics
REGISTRY = CollectorRegistry()

# Define metrics following Prometheus naming conventions
http_request_duration_seconds = Histogram(
    "instainstru_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint", "status_code"],
    registry=REGISTRY,
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

http_requests_total = Counter(
    "instainstru_http_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "status_code"],
    registry=REGISTRY,
)

http_requests_in_progress = Gauge(
    "instainstru_http_requests_in_progress",
    "Number of HTTP requests currently being processed",
    ["method", "endpoint"],
    registry=REGISTRY,
)

service_operation_duration_seconds = Histogram(
    "instainstru_service_operation_duration_seconds",
    "Service operation duration in seconds",
    ["service", "operation"],
    registry=REGISTRY,
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)

service_operations_total = Counter(
    "instainstru_service_operations_total",
    "Total number of service operations",
    ["service", "operation", "status"],
    registry=REGISTRY,
)

errors_total = Counter(
    "instainstru_errors_total",
    "Total number of errors",
    ["service", "operation", "error_type"],
    registry=REGISTRY,
)

# Cache metrics for personal assets
profile_pic_url_cache_hits_total = Counter(
    "instainstru_profile_pic_url_cache_hits_total",
    "Total number of cache hits for profile picture URL generation",
    ["variant"],
    registry=REGISTRY,
)

profile_pic_url_cache_misses_total = Counter(
    "instainstru_profile_pic_url_cache_misses_total",
    "Total number of cache misses for profile picture URL generation",
    ["variant"],
    registry=REGISTRY,
)

# Domain-specific custom counters
credits_applied_total = Counter(
    "instainstru_credits_applied_total",
    "Total number of times credits were applied",
    ["source"],  # e.g., authorization, cancellation
    registry=REGISTRY,
)

instant_payout_requests_total = Counter(
    "instainstru_instant_payout_requests_total",
    "Count of instant payout requests",
    ["status"],  # success | error
    registry=REGISTRY,
)

# Beta program: distribution of x-beta-phase headers observed
beta_phase_header_total = Counter(
    "instainstru_beta_phase_header_total",
    "Count of responses by x-beta-phase header value",
    ["phase"],
    registry=REGISTRY,
)

# Preview bypass audit
preview_bypass_total = Counter(
    "instainstru_preview_bypass_total",
    "Count of preview bypass events (by mechanism)",
    ["via"],  # session | header
    registry=REGISTRY,
)

# Notification outbox instrumentation
notifications_outbox_total = Counter(
    "instainstru_notifications_outbox_total",
    "Total notification outbox events by terminal status",
    ["status", "event_type"],
    registry=REGISTRY,
)

notifications_outbox_attempt_total = Counter(
    "instainstru_notifications_outbox_attempt_total",
    "Number of notification outbox delivery attempts",
    ["event_type"],
    registry=REGISTRY,
)

notifications_dispatch_seconds = Histogram(
    "instainstru_notifications_dispatch_seconds",
    "Notification provider dispatch duration in seconds",
    ["event_type"],
    registry=REGISTRY,
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

# Storage for tracking active operations
active_operations: Dict[str, int] = defaultdict(int)


def _metrics_ttl_seconds() -> float:
    """Return cache TTL seconds based on SITE_MODE."""

    mode = (os.getenv("SITE_MODE") or "").strip().lower()
    if mode in {"ci", "test"}:
        return 2.0
    return 1.0


class PrometheusMetrics:
    """Manages Prometheus metrics collection and exposure."""

    _cache_lock: Lock = Lock()
    _cache_payload: Optional[bytes] = None
    _cache_ts: Optional[float] = None
    _cache_ttl_seconds: float = _metrics_ttl_seconds()

    @staticmethod
    def record_http_request(method: str, endpoint: str, duration: float, status_code: int) -> None:
        """Record HTTP request metrics."""
        labels = {"method": method, "endpoint": endpoint, "status_code": str(status_code)}

        http_request_duration_seconds.labels(**labels).observe(duration)
        http_requests_total.labels(**labels).inc()
        PrometheusMetrics._invalidate_cache()

    @staticmethod
    def track_http_request_start(method: str, endpoint: str) -> None:
        """Track the start of an HTTP request."""
        http_requests_in_progress.labels(method=method, endpoint=endpoint).inc()

    @staticmethod
    def track_http_request_end(method: str, endpoint: str) -> None:
        """Track the end of an HTTP request."""
        http_requests_in_progress.labels(method=method, endpoint=endpoint).dec()

    @staticmethod
    def record_service_operation(
        service: str,
        operation: str,
        duration: float,
        status: str = "success",
        error_type: Optional[str] = None,
    ) -> None:
        """
        Record service operation metrics from @measure_operation decorator.

        Args:
            service: Service name (e.g., 'BookingService')
            operation: Operation/method name (e.g., 'create_booking')
            duration: Operation duration in seconds
            status: Operation status ('success' or 'error')
            error_type: Type of error if status is 'error'
        """
        # Record duration
        service_operation_duration_seconds.labels(service=service, operation=operation).observe(
            duration
        )

        # Record count
        service_operations_total.labels(service=service, operation=operation, status=status).inc()

        # Record error if applicable
        if status == "error" and error_type:
            errors_total.labels(service=service, operation=operation, error_type=error_type).inc()
        PrometheusMetrics._invalidate_cache()

    @staticmethod
    def record_notification_attempt(event_type: str) -> None:
        """Increment attempt counter for notification outbox delivery."""
        notifications_outbox_attempt_total.labels(event_type=event_type).inc()
        PrometheusMetrics._invalidate_cache()

    @staticmethod
    def record_notification_outcome(event_type: str, status: str) -> None:
        """Record terminal outcome for notification outbox delivery."""
        notifications_outbox_total.labels(status=status, event_type=event_type).inc()
        PrometheusMetrics._invalidate_cache()

    @staticmethod
    def observe_notification_dispatch(event_type: str, duration: float) -> None:
        """Observe provider dispatch duration."""
        notifications_dispatch_seconds.labels(event_type=event_type).observe(max(duration, 0.0))
        PrometheusMetrics._invalidate_cache()

    @staticmethod
    def get_metrics() -> bytes:
        """
        Generate Prometheus metrics in exposition format.

        Returns:
            Metrics data in Prometheus text format
        """
        now = monotonic()
        payload = PrometheusMetrics._cache_payload
        ts = PrometheusMetrics._cache_ts
        ttl = PrometheusMetrics._cache_ttl_seconds

        if payload is not None and ts is not None and (now - ts) <= ttl:
            return payload

        with PrometheusMetrics._cache_lock:
            payload = PrometheusMetrics._cache_payload
            ts = PrometheusMetrics._cache_ts
            ttl = PrometheusMetrics._cache_ttl_seconds

            if payload is None or ts is None or (now - ts) > ttl:
                PrometheusMetrics._refresh_cache_locked()
                payload = PrometheusMetrics._cache_payload

        return cast(bytes, payload)

    @staticmethod
    def get_content_type() -> str:
        """Get the content type for Prometheus metrics."""
        return cast(str, CONTENT_TYPE_LATEST)

    @staticmethod
    def _refresh_cache_locked() -> None:
        """Refresh cached metrics payload. Caller must hold lock."""

        PrometheusMetrics._cache_payload = cast(bytes, generate_latest(REGISTRY))
        PrometheusMetrics._cache_ts = monotonic()
        PrometheusMetrics._cache_ttl_seconds = _metrics_ttl_seconds()

    @staticmethod
    def prewarm() -> None:
        """Populate the metrics cache so first request is warm."""

        with PrometheusMetrics._cache_lock:
            PrometheusMetrics._refresh_cache_locked()

    @staticmethod
    def _invalidate_cache() -> None:
        """Invalidate cached metrics so next scrape refreshes."""

        with PrometheusMetrics._cache_lock:
            PrometheusMetrics._cache_ts = None
            PrometheusMetrics._cache_payload = None

    # Domain helpers
    @staticmethod
    def inc_credits_applied(source: str = "authorization") -> None:
        """Increment credits applied counter."""
        credits_applied_total.labels(source=source).inc()
        PrometheusMetrics._invalidate_cache()

    @staticmethod
    def inc_instant_payout_request(status: str) -> None:
        """Increment instant payout request counter with given status label."""
        instant_payout_requests_total.labels(status=status).inc()
        PrometheusMetrics._invalidate_cache()

    @staticmethod
    def inc_beta_phase_header(phase: str) -> None:
        """Increment beta phase header distribution counter."""
        beta_phase_header_total.labels(phase=phase).inc()
        PrometheusMetrics._invalidate_cache()

    @staticmethod
    def inc_preview_bypass(via: str) -> None:
        """Increment preview bypass counter by mechanism (session|header)."""
        preview_bypass_total.labels(via=via).inc()
        PrometheusMetrics._invalidate_cache()


# Singleton instance
prometheus_metrics = PrometheusMetrics()

# Ensure histogram families have at least one labeled series so buckets appear in exposition even
# before any observations are recorded by the app/tests.
try:
    service_operation_duration_seconds.labels(service="bootstrap", operation="init").observe(0.0)
except Exception:
    pass
