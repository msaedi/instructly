"""
Prometheus metrics middleware for HTTP request tracking.

This middleware integrates with the prometheus_metrics module to
track HTTP request metrics including duration, status codes, and
in-progress requests.
"""

import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from ..core.constants import SSE_PATH_PREFIX
from ..monitoring.prometheus_metrics import prometheus_metrics


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Middleware to collect Prometheus metrics for HTTP requests."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process the request and collect metrics.

        Args:
            request: The incoming request
            call_next: The next middleware/handler

        Returns:
            The response from the handler
        """
        # Skip metrics collection for the metrics endpoint itself and SSE endpoints
        # SSE endpoints need direct passthrough to avoid interference with streaming
        if request.url.path == "/metrics/prometheus" or request.url.path.startswith(SSE_PATH_PREFIX):
            return await call_next(request)

        method = request.method
        raw_path = request.url.path
        # Normalize endpoint label to reduce cardinality (strip numeric IDs)
        # Example: /api/bookings/123 -> /api/bookings/:id
        path = "/".join(":id" if segment.isdigit() else segment for segment in raw_path.split("/"))

        # Track request start
        prometheus_metrics.track_http_request_start(method, path)

        # Time the request
        start_time = time.time()

        try:
            response = await call_next(request)
            duration = time.time() - start_time

            # Record metrics
            prometheus_metrics.record_http_request(
                method=method, endpoint=path, duration=duration, status_code=response.status_code
            )

            return response

        finally:
            # Always track request end
            prometheus_metrics.track_http_request_end(method, path)
