# backend/app/middleware/performance.py
"""
Performance monitoring middleware for production.

Integrates with the production monitor to track:
- Request performance
- Add correlation IDs
- Monitor slow endpoints
- Track database queries per request
"""

import time
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from ..monitoring.production_monitor import monitor


class PerformanceMiddleware(BaseHTTPMiddleware):
    """
    Middleware for comprehensive performance monitoring.

    Features:
    - Request ID and correlation ID tracking
    - Request duration monitoring
    - Integration with production monitor
    - Automatic slow request detection
    """

    def __init__(self, app: ASGIApp):
        """Initialize performance middleware."""
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with performance monitoring."""
        # Generate or extract request ID
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        correlation_id = request.headers.get("X-Correlation-ID", request_id)

        # Store in request state for access in handlers
        request.state.request_id = request_id
        request.state.correlation_id = correlation_id

        # Track request start
        monitor.track_request_start(request_id, request)
        start_time = time.time()

        # Add monitoring context
        request.state.query_count = 0
        request.state.cache_hits = 0
        request.state.cache_misses = 0

        try:
            # Process request
            response = await call_next(request)

            # Track request end
            duration_ms = monitor.track_request_end(request_id, response.status_code)

            # Add performance headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Correlation-ID"] = correlation_id
            if duration_ms:
                response.headers["X-Response-Time-MS"] = str(int(duration_ms))

            # Add performance metrics to response headers (useful for debugging)
            if hasattr(request.state, "query_count"):
                response.headers["X-DB-Query-Count"] = str(request.state.query_count)
            if hasattr(request.state, "cache_hits"):
                response.headers["X-Cache-Hits"] = str(request.state.cache_hits)
                response.headers["X-Cache-Misses"] = str(request.state.cache_misses)

            return response

        except Exception:
            # Track failed request
            duration_ms = (time.time() - start_time) * 1000
            monitor.track_request_end(request_id, 500)

            # Re-raise exception
            raise
