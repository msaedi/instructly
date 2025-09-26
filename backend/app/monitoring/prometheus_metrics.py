"""
Prometheus metrics module for InstaInstru.

This module provides Prometheus-compatible metrics by leveraging existing
@measure_operation performance data. It follows Prometheus naming conventions
and best practices for metric types.
"""

from collections import defaultdict
import time
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

# Storage for tracking active operations
active_operations: Dict[str, int] = defaultdict(int)


class PrometheusMetrics:
    """Manages Prometheus metrics collection and exposure."""

    # Simple micro-cache to speed up repeated scrapes within a short window
    _cache_data: Optional[bytes] = None
    _cache_ts: float = 0.0
    _cache_ttl_seconds: float = 0.2  # 200ms micro-cache
    _dirty_since_last_scrape: bool = True

    @staticmethod
    def record_http_request(method: str, endpoint: str, duration: float, status_code: int) -> None:
        """Record HTTP request metrics."""
        labels = {"method": method, "endpoint": endpoint, "status_code": str(status_code)}

        http_request_duration_seconds.labels(**labels).observe(duration)
        http_requests_total.labels(**labels).inc()
        # Mark cache as dirty so next scrape doesn't serve stale data
        PrometheusMetrics._dirty_since_last_scrape = True

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
        PrometheusMetrics._dirty_since_last_scrape = True

    @staticmethod
    def get_metrics() -> bytes:
        """
        Generate Prometheus metrics in exposition format.

        Returns:
            Metrics data in Prometheus text format
        """
        now = time.perf_counter()
        # Serve cached payload if within TTL and nothing changed since last scrape
        if (
            PrometheusMetrics._cache_data is not None
            and (now - PrometheusMetrics._cache_ts) < PrometheusMetrics._cache_ttl_seconds
            and not PrometheusMetrics._dirty_since_last_scrape
        ):
            return PrometheusMetrics._cache_data

        data = cast(bytes, generate_latest(REGISTRY))
        PrometheusMetrics._cache_data = data
        PrometheusMetrics._cache_ts = now
        PrometheusMetrics._dirty_since_last_scrape = False
        return data

    @staticmethod
    def get_content_type() -> str:
        """Get the content type for Prometheus metrics."""
        return cast(str, CONTENT_TYPE_LATEST)

    # Domain helpers
    @staticmethod
    def inc_credits_applied(source: str = "authorization") -> None:
        """Increment credits applied counter."""
        credits_applied_total.labels(source=source).inc()
        PrometheusMetrics._dirty_since_last_scrape = True

    @staticmethod
    def inc_instant_payout_request(status: str) -> None:
        """Increment instant payout request counter with given status label."""
        instant_payout_requests_total.labels(status=status).inc()
        PrometheusMetrics._dirty_since_last_scrape = True

    @staticmethod
    def inc_beta_phase_header(phase: str) -> None:
        """Increment beta phase header distribution counter."""
        beta_phase_header_total.labels(phase=phase).inc()
        PrometheusMetrics._dirty_since_last_scrape = True

    @staticmethod
    def inc_preview_bypass(via: str) -> None:
        """Increment preview bypass counter by mechanism (session|header)."""
        preview_bypass_total.labels(via=via).inc()
        PrometheusMetrics._dirty_since_last_scrape = True


# Singleton instance
prometheus_metrics = PrometheusMetrics()

# Ensure histogram families have at least one labeled series so buckets appear in exposition even
# before any observations are recorded by the app/tests.
try:
    service_operation_duration_seconds.labels(service="bootstrap", operation="init").observe(0.0)
except Exception:
    pass
