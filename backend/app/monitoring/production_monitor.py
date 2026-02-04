# backend/app/monitoring/production_monitor.py
"""
Production monitoring and alerting for Render deployment.

This module provides:
- Real-time performance monitoring
- Slow query detection and logging
- Database connection pool monitoring
- Cache performance tracking
- Memory usage monitoring
- Request tracking with correlation IDs
"""

import asyncio
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import gc
import logging
import os
import time
from typing import Any, AsyncIterator, Deque, Dict, Optional, Set, cast
import uuid

from fastapi import Request
import psutil
from sqlalchemy import event
from sqlalchemy.engine import Engine

from ..database import get_db_pool_status, get_db_pool_statuses

logger = logging.getLogger(__name__)

# Import Celery enqueue helper if available
try:
    from app.tasks.enqueue import enqueue_task as _enqueue_task

    CELERY_AVAILABLE = True
    enqueue_task = cast(Any, _enqueue_task)
except ImportError:
    CELERY_AVAILABLE = False
    logger.warning("Celery tasks not available - alerts will only be logged")


class PerformanceMonitor:
    """
    Production performance monitoring with alerting.

    Tracks:
    - Slow queries
    - Database pool usage
    - Cache hit rates
    - Memory usage
    - Request latency
    """

    def __init__(self, slow_query_threshold_ms: int = 100, slow_request_threshold_ms: int = 500):
        """Initialize performance monitor."""
        self.slow_query_threshold_ms = slow_query_threshold_ms
        self.slow_request_threshold_ms = slow_request_threshold_ms

        # Metrics storage (using deque for memory efficiency)
        self.slow_queries: Deque[Dict[str, Any]] = deque(maxlen=100)
        self.slow_requests: Deque[Dict[str, Any]] = deque(maxlen=100)
        self.db_pool_history: Deque[Dict[str, Any]] = deque(maxlen=60)  # Last 60 measurements
        self.cache_metrics_history: Deque[Dict[str, Any]] = deque(maxlen=60)

        # Alert tracking
        self._alerts_sent: Set[str] = set()
        self._alert_cooldown = timedelta(minutes=15)
        self._last_alert_time: Dict[str, datetime] = {}

        # Request tracking
        self._active_requests: Dict[str, Dict[str, Any]] = {}

        # Setup database query monitoring
        self._setup_query_monitoring()

    def _setup_query_monitoring(self) -> None:
        """Setup SQLAlchemy event listeners for query monitoring."""

        def before_cursor_execute(
            conn: Any,
            cursor: Any,
            statement: str,
            parameters: Any,
            context: Any,
            executemany: bool,
        ) -> None:
            """Track query start time."""
            context._query_start_time = time.time()
            context._query_statement = statement

        def after_cursor_execute(
            conn: Any,
            cursor: Any,
            statement: str,
            parameters: Any,
            context: Any,
            executemany: bool,
        ) -> None:
            """Log slow queries."""
            query_start = cast(float, getattr(context, "_query_start_time", time.time()))
            duration_ms = (time.time() - query_start) * 1000

            if duration_ms > self.slow_query_threshold_ms:
                # Ignore simple health check queries
                if "SELECT 1" in statement:
                    return

                # Extract first 200 chars of query
                query_preview = statement[:200].replace("\n", " ")
                if len(statement) > 200:
                    query_preview += "..."

                slow_query_info = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "duration_ms": round(duration_ms, 2),
                    "query": query_preview,
                    "full_query": statement
                    if duration_ms > 500
                    else None,  # Only store full query for very slow queries
                }

                self.slow_queries.append(slow_query_info)
                logger.warning(
                    f"Slow query detected ({duration_ms:.2f}ms): {query_preview}",
                    extra={"duration_ms": duration_ms},
                )

                # Alert if query is extremely slow
                if duration_ms > 1000:  # 1 second
                    self._send_alert(
                        "extremely_slow_query",
                        f"Query took {duration_ms:.0f}ms: {query_preview[:100]}",
                        details={
                            "duration_ms": duration_ms,
                            "query_preview": query_preview,
                            "full_query": statement if duration_ms > 2000 else None,
                        },
                    )

        event.listen(Engine, "before_cursor_execute", before_cursor_execute)
        event.listen(Engine, "after_cursor_execute", after_cursor_execute)

    def track_request_start(self, request_id: str, request: Request) -> None:
        """Track the start of a request."""
        self._active_requests[request_id] = {
            "start_time": time.time(),
            "method": request.method,
            "path": request.url.path,
            "client": request.client.host if request.client else "unknown",
        }

    def track_request_end(self, request_id: str, status_code: int) -> Optional[float]:
        """Track the end of a request and return duration."""
        if request_id not in self._active_requests:
            return None

        request_info = self._active_requests.pop(request_id)
        start_time = cast(float, request_info["start_time"])
        duration_ms = (time.time() - start_time) * 1000

        # Log slow requests
        if duration_ms > self.slow_request_threshold_ms:
            slow_request_info = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "duration_ms": round(duration_ms, 2),
                "method": request_info["method"],
                "path": request_info["path"],
                "status_code": status_code,
                "client": request_info["client"],
            }

            self.slow_requests.append(slow_request_info)
            logger.warning(
                f"Slow request: {request_info['method']} {request_info['path']} "
                f"took {duration_ms:.2f}ms (status: {status_code})"
            )

            # Alert for extremely slow requests
            if duration_ms > 5000:  # 5 seconds
                self._send_alert(
                    "extremely_slow_request",
                    f"{request_info['method']} {request_info['path']} took {duration_ms:.0f}ms",
                    details={
                        "duration_ms": duration_ms,
                        "method": request_info["method"],
                        "path": request_info["path"],
                        "status_code": status_code,
                        "client": request_info["client"],
                    },
                )

        return duration_ms

    def check_db_pool_health(self) -> Dict[str, Any]:
        """Check database connection pool health."""
        pool_statuses = cast(dict[str, dict[str, Any]], get_db_pool_statuses())
        if not pool_statuses:
            pool_statuses = {"api": cast(dict[str, Any], get_db_pool_status())}

        def _usage(status: Dict[str, Any]) -> float:
            size = float(status.get("size", 0))
            overflow = float(status.get("overflow", 0))
            checked_out = float(status.get("checked_out", 0))
            total_possible = size + overflow
            return (checked_out / total_possible * 100) if total_possible > 0 else 0.0

        primary_status = pool_statuses.get("api") or next(iter(pool_statuses.values()))
        primary_usage = _usage(primary_status)

        pool_health = {
            **primary_status,
            "usage_percent": round(primary_usage, 2),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "healthy": primary_usage < 80,
            "pools": {
                name: {**status, "usage_percent": round(_usage(status), 2)}
                for name, status in pool_statuses.items()
            },
        }

        # Store history
        self.db_pool_history.append(pool_health)

        # Alert if pool usage is high
        for name, status in pool_statuses.items():
            usage_percent = _usage(status)
            if usage_percent > 80:
                total_possible = float(status.get("size", 0)) + float(status.get("overflow", 0))
                self._send_alert(
                    "high_db_pool_usage",
                    f"{name} pool usage at {usage_percent:.0f}% "
                    f"({status.get('checked_out', 0)}/{total_possible} connections)",
                )

        return pool_health

    def check_memory_usage(self) -> Dict[str, Any]:
        """Check application memory usage."""
        process = psutil.Process()
        memory_info = process.memory_info()

        # Get system memory for percentage calculation
        system_memory = psutil.virtual_memory()

        memory_usage = {
            "rss_mb": round(memory_info.rss / 1024 / 1024, 2),
            "vms_mb": round(memory_info.vms / 1024 / 1024, 2),
            "percent": round(process.memory_percent(), 2),
            "system_available_mb": round(system_memory.available / 1024 / 1024, 2),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Alert if memory usage is high
        if memory_usage["percent"] > 80:
            self._send_alert(
                "high_memory_usage",
                f"Memory usage at {memory_usage['percent']}% ({memory_usage['rss_mb']}MB RSS)",
            )
            # Force garbage collection
            gc.collect()

        return memory_usage

    def check_cache_health(self, cache_stats: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze cache performance and health."""
        hit_rate_str = str(cache_stats.get("hit_rate", "0")).rstrip("%")
        try:
            hit_rate = float(hit_rate_str)
        except ValueError:
            hit_rate = 0.0
        errors_count = int(cache_stats.get("errors", 0) or 0)

        cache_health = {
            **cache_stats,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "healthy": hit_rate > 70,
            "recommendations": [],
        }

        # Store history
        self.cache_metrics_history.append(cache_health)

        # Generate recommendations
        if hit_rate < 70:
            cache_health["recommendations"].append(
                "Low cache hit rate. Consider warming cache or adjusting TTLs."
            )
            self._send_alert("low_cache_hit_rate", f"Cache hit rate at {hit_rate}% (target: >70%)")

        if errors_count > 10:
            cache_health["recommendations"].append(
                "High cache error count. Check Redis/Upstash connection."
            )

        return cache_health

    def _send_alert(
        self, alert_type: str, message: str, details: Optional[Dict[str, Any]] = None
    ) -> None:
        """Send alert if not in cooldown period."""
        now = datetime.now(timezone.utc)

        # Check cooldown
        if alert_type in self._last_alert_time:
            time_since_last = now - self._last_alert_time[alert_type]
            if time_since_last < self._alert_cooldown:
                return

        # Log alert
        logger.error(f"ALERT [{alert_type}]: {message}")

        # Determine severity based on alert type
        severity = "critical" if "extremely" in alert_type else "warning"

        # Dispatch to Celery if available
        if CELERY_AVAILABLE:
            try:
                enqueue_task(
                    "app.tasks.monitoring_tasks.process_monitoring_alert",
                    kwargs={
                        "alert_type": alert_type,
                        "severity": severity,
                        "title": f"Performance Alert: {alert_type.replace('_', ' ').title()}",
                        "message": message,
                        "details": details or {},
                    },
                )
                logger.info(f"Alert dispatched to Celery: {alert_type}")
            except Exception as e:
                logger.error(f"Failed to dispatch alert to Celery: {str(e)}")
                # Fall back to console logging
                print(f"🚨 PRODUCTION ALERT [{alert_type}]: {message}")
        else:
            # Fall back to console logging
            print(f"🚨 PRODUCTION ALERT [{alert_type}]: {message}")

        # Update last alert time
        self._last_alert_time[alert_type] = now

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance summary."""
        # Get latest metrics
        db_pool = self.check_db_pool_health()
        memory = self.check_memory_usage()

        # Calculate averages from history
        avg_pool_usage = 0.0
        if self.db_pool_history:
            usage_values = [cast(float, entry["usage_percent"]) for entry in self.db_pool_history]
            avg_pool_usage = sum(usage_values) / len(usage_values)

        summary = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "database": {
                "current_pool_usage_percent": db_pool["usage_percent"],
                "average_pool_usage_percent": round(avg_pool_usage, 2),
                "slow_queries_count": len(self.slow_queries),
                "recent_slow_queries": list(self.slow_queries)[-5:],  # Last 5
            },
            "requests": {
                "active_count": len(self._active_requests),
                "slow_requests_count": len(self.slow_requests),
                "recent_slow_requests": list(self.slow_requests)[-5:],  # Last 5
            },
            "memory": memory,
            "alerts": {
                "active_types": list(self._last_alert_time.keys()),
                "last_alert_times": {k: v.isoformat() for k, v in self._last_alert_time.items()},
            },
        }

        return summary

    def cleanup_stale_requests(self, timeout_seconds: int = 300) -> int:
        """Clean up requests that have been active too long."""
        now = time.time()
        stale_count = 0

        for request_id, info in list(self._active_requests.items()):
            start_time = cast(float, info["start_time"])
            if now - start_time > timeout_seconds:
                logger.warning(
                    f"Cleaning up stale request {request_id}: "
                    f"{info['method']} {info['path']} "
                    f"(active for {now - start_time:.0f}s)"
                )
                del self._active_requests[request_id]
                stale_count += 1

        return stale_count


# Global monitor instance
monitor = PerformanceMonitor(
    slow_query_threshold_ms=int(os.getenv("SLOW_QUERY_THRESHOLD_MS", "100")),
    slow_request_threshold_ms=int(os.getenv("SLOW_REQUEST_THRESHOLD_MS", "500")),
)


# Middleware for request tracking
@asynccontextmanager
async def track_request_performance(request: Request) -> AsyncIterator[str]:
    """Context manager for tracking request performance."""
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    # Track start
    monitor.track_request_start(request_id, request)

    try:
        yield request_id
    finally:
        # Track end (status code will be set by middleware)
        pass


# Background task for periodic health checks
async def periodic_health_check() -> None:
    """Run periodic health checks."""
    while True:
        try:
            # Check various health metrics
            monitor.check_db_pool_health()
            monitor.check_memory_usage()

            # Clean up stale requests
            stale_count = monitor.cleanup_stale_requests()
            if stale_count > 0:
                logger.warning(f"Cleaned up {stale_count} stale requests")

        except Exception as e:
            logger.error(f"Error in periodic health check: {e}")

        # Run every 60 seconds
        await asyncio.sleep(60)
