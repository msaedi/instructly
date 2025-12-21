# backend/app/middleware/timing.py
"""
Request timing middleware for performance monitoring.
"""

from collections.abc import Awaitable, Callable
import logging
import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class TimingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to measure and log request processing time.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Skip timing for health and metrics endpoints
        if request.url.path == "/api/v1/health":
            return await call_next(request)

        start_time = time.time()

        # Process the request
        response = await call_next(request)

        # Calculate processing time
        process_time = (time.time() - start_time) * 1000  # Convert to ms

        # Add timing header
        response.headers["X-Process-Time"] = f"{process_time:.2f}ms"

        # Log slow requests
        if process_time > 100:  # Log requests slower than 100ms
            logger.warning(
                f"Slow request: {request.method} {request.url.path} " f"took {process_time:.2f}ms"
            )

        return response
