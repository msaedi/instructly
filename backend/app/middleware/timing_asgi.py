"""
Pure ASGI Timing Middleware

This is a pure ASGI implementation that avoids the BaseHTTPMiddleware
"No response returned" issue.
"""

import logging
import time

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ..core.constants import SSE_PATH_PREFIX

logger = logging.getLogger(__name__)


class TimingMiddlewareASGI:
    """
    Pure ASGI middleware to measure and log request processing time.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI application entrypoint."""

        # Only handle HTTP requests
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Get the path
        path = scope.get("path", "")
        method = scope.get("method", "")

        # Skip timing for health and metrics endpoints
        if path == "/health" or path == "/internal/metrics":
            await self.app(scope, receive, send)
            return

        # Skip timing for SSE endpoints to avoid interference with streaming
        if path.startswith(SSE_PATH_PREFIX):
            await self.app(scope, receive, send)
            return

        # Log request start
        logger.info(f"[TIMING] Starting request: {method} {path}")
        start_time = time.time()

        # Create a wrapper for send to add timing header
        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                # Calculate processing time
                process_time = (time.time() - start_time) * 1000  # Convert to ms

                # Log response timing
                logger.info(f"[TIMING] Response for: {path}, duration: {process_time:.2f}ms")

                # Add timing header
                headers = MutableHeaders(scope=message)
                headers["X-Process-Time"] = f"{process_time:.2f}ms"

                # Log slow requests
                if process_time > 100:  # Log requests slower than 100ms
                    logger.warning(
                        f"[TIMING] Slow request: {method} {path} took {process_time:.2f}ms"
                    )

            await send(message)

        try:
            # Process the request with our wrapped send
            await self.app(scope, receive, send_wrapper)
        except Exception as e:
            # Log any errors
            process_time = (time.time() - start_time) * 1000
            logger.error(f"[TIMING] Error in request {path} after {process_time:.2f}ms: {str(e)}")
            raise
