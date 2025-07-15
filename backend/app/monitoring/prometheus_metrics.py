"""
Prometheus metrics module for InstaInstru.

This module provides Prometheus-compatible metrics by leveraging existing
@measure_operation performance data. It follows Prometheus naming conventions
and best practices for metric types.
"""

from collections import defaultdict
from typing import Dict, Optional

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, Histogram, generate_latest

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
    "instainstru_errors_total", "Total number of errors", ["service", "operation", "error_type"], registry=REGISTRY
)

# Storage for tracking active operations
active_operations: Dict[str, int] = defaultdict(int)


class PrometheusMetrics:
    """Manages Prometheus metrics collection and exposure."""

    @staticmethod
    def record_http_request(method: str, endpoint: str, duration: float, status_code: int) -> None:
        """Record HTTP request metrics."""
        labels = {"method": method, "endpoint": endpoint, "status_code": str(status_code)}

        http_request_duration_seconds.labels(**labels).observe(duration)
        http_requests_total.labels(**labels).inc()

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
        service: str, operation: str, duration: float, status: str = "success", error_type: Optional[str] = None
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
        service_operation_duration_seconds.labels(service=service, operation=operation).observe(duration)

        # Record count
        service_operations_total.labels(service=service, operation=operation, status=status).inc()

        # Record error if applicable
        if status == "error" and error_type:
            errors_total.labels(service=service, operation=operation, error_type=error_type).inc()

    @staticmethod
    def get_metrics() -> bytes:
        """
        Generate Prometheus metrics in exposition format.

        Returns:
            Metrics data in Prometheus text format
        """
        return generate_latest(REGISTRY)

    @staticmethod
    def get_content_type() -> str:
        """Get the content type for Prometheus metrics."""
        return CONTENT_TYPE_LATEST


# Singleton instance
prometheus_metrics = PrometheusMetrics()
