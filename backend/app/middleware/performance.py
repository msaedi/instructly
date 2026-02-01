# backend/app/middleware/performance.py
"""
Performance monitoring middleware for production.

Integrates with the production monitor to track:
- Request performance
- Add correlation IDs
- Monitor slow endpoints
- Track database queries per request
"""

import uuid

from fastapi import Request
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ..core.constants import SSE_PATH_PREFIX
from ..core.request_context import reset_request_id, set_request_id
from ..monitoring.otel import get_current_trace_id, is_otel_enabled
from ..monitoring.production_monitor import monitor


class PerformanceMiddleware:
    """
    Middleware for comprehensive performance monitoring.

    Features:
    - Request ID and correlation ID tracking
    - Request duration monitoring
    - Integration with production monitor
    - Automatic slow request detection
    """

    def __init__(self, app: ASGIApp) -> None:
        """Initialize performance middleware."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI entrypoint for request performance monitoring."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        # Skip monitoring for SSE endpoints to avoid interfering with streaming.
        if path.startswith(SSE_PATH_PREFIX):
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)

        # Generate or extract request ID
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        correlation_id = request.headers.get("X-Correlation-ID", request_id)

        # Store in request state for access in handlers
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        state["correlation_id"] = correlation_id

        # Add monitoring context defaults
        state.setdefault("query_count", 0)
        state.setdefault("cache_hits", 0)
        state.setdefault("cache_misses", 0)

        # Track request start
        monitor.track_request_start(request_id, request)
        request_id_token = set_request_id(request_id)
        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]

                # Track request end
                duration_ms = monitor.track_request_end(request_id, status_code)

                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
                headers["X-Correlation-ID"] = correlation_id
                if duration_ms:
                    headers["X-Response-Time-MS"] = str(int(duration_ms))

                trace_id: str | None = None
                if is_otel_enabled():
                    trace_id = get_current_trace_id()
                if trace_id:
                    headers["X-Trace-ID"] = trace_id

                # Add performance metrics to response headers (useful for debugging)
                db_count = state.get("query_count")
                if db_count is not None:
                    headers.setdefault("x-db-query-count", str(db_count))
                    headers["X-DB-Query-Count"] = headers["x-db-query-count"]
                hits = state.get("cache_hits")
                misses = state.get("cache_misses")
                if hits is not None and misses is not None:
                    headers.setdefault("x-cache-hits", str(hits))
                    headers.setdefault("x-cache-misses", str(misses))
                    headers["X-Cache-Hits"] = headers["x-cache-hits"]
                    headers["X-Cache-Misses"] = headers["x-cache-misses"]

            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            if not response_started:
                monitor.track_request_end(request_id, 500)
            raise
        finally:
            reset_request_id(request_id_token)
