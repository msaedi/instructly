# backend/app/middleware/monitoring.py
"""
Simple performance monitoring to track real-world metrics.
"""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone
import logging
import time
from typing import Any, DefaultDict, Deque

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ..core.constants import SSE_PATH_PREFIX

logger = logging.getLogger(__name__)


class PerformanceMonitor:
    """Track performance metrics for analysis."""

    def __init__(self, window_size: int = 1000) -> None:
        self.response_times: Deque[float] = deque(maxlen=window_size)
        self.endpoint_stats: DefaultDict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=100))
        self.slow_requests: Deque[dict[str, Any]] = deque(maxlen=50)
        self.hourly_stats: DefaultDict[str, list[float]] = defaultdict(list)

    def record_request(
        self, endpoint: str, method: str, duration_ms: float, status_code: int
    ) -> None:
        """Record a request's performance."""
        self.response_times.append(duration_ms)
        self.endpoint_stats[f"{method} {endpoint}"].append(duration_ms)

        # Track slow requests (>500ms)
        if duration_ms > 500:
            self.slow_requests.append(
                {
                    "endpoint": endpoint,
                    "method": method,
                    "duration_ms": duration_ms,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "status_code": status_code,
                }
            )

        # Hourly aggregation
        hour_key = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:00")
        self.hourly_stats[hour_key].append(duration_ms)

    def get_stats(self) -> dict[str, Any]:
        """Get current performance statistics."""
        if not self.response_times:
            return {"message": "No data yet"}

        times = list(self.response_times)
        return {
            "overall": {
                "count": len(times),
                "avg_ms": sum(times) / len(times),
                "min_ms": min(times),
                "max_ms": max(times),
                "p50_ms": sorted(times)[len(times) // 2],
                "p95_ms": sorted(times)[int(len(times) * 0.95)] if len(times) > 20 else max(times),
                "slow_requests": len([t for t in times if t > 500]),
            },
            "by_endpoint": {
                endpoint: {
                    "avg_ms": sum(endpoint_times) / len(endpoint_times),
                    "count": len(endpoint_times),
                }
                for endpoint, endpoint_times in self.endpoint_stats.items()
                if endpoint_times
            },
            "recent_slow_requests": list(self.slow_requests)[-10:],
        }


# Global instance
monitor = PerformanceMonitor()


class MonitoringMiddleware:
    """Middleware to track performance metrics."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Skip monitoring for SSE and Prometheus metrics endpoints to avoid interference
        path = scope.get("path", "")
        if path.startswith(SSE_PATH_PREFIX) or path.startswith("/metrics"):
            await self.app(scope, receive, send)
            return

        start_time = time.time()

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                # Calculate duration when response starts
                duration_ms = (time.time() - start_time) * 1000

                # Extract request info
                path = scope.get("path", "")
                method = scope.get("method", "")

                # Record metrics
                monitor.record_request(
                    endpoint=path,
                    method=method,
                    duration_ms=duration_ms,
                    status_code=message.get("status", 0),
                )

                # Log slow requests
                if duration_ms > 500:
                    logger.warning(f"Slow request: {method} {path} " f"took {duration_ms:.2f}ms")

            await send(message)

        await self.app(scope, receive, send_wrapper)
