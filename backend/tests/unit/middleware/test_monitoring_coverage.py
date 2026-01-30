"""Unit tests for monitoring middleware coverage."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.middleware.monitoring import MonitoringMiddleware, PerformanceMonitor, monitor


class TestPerformanceMonitorGetStats:
    """Tests for PerformanceMonitor.get_stats method."""

    def test_get_stats_returns_no_data_message_when_empty(self) -> None:
        """Lines 55-56: Returns 'No data yet' message when no response times recorded."""
        perf_monitor = PerformanceMonitor()
        # Ensure response_times is empty
        assert len(perf_monitor.response_times) == 0

        stats = perf_monitor.get_stats()

        assert stats == {"message": "No data yet"}

    def test_get_stats_returns_statistics_when_data_exists(self) -> None:
        """Lines 58-78: Returns full statistics when data exists."""
        perf_monitor = PerformanceMonitor()

        # Add some response times
        perf_monitor.record_request("/api/test", "GET", 100.0, 200)
        perf_monitor.record_request("/api/test", "GET", 200.0, 200)
        perf_monitor.record_request("/api/test", "GET", 600.0, 500)  # Slow request

        stats = perf_monitor.get_stats()

        assert "overall" in stats
        assert stats["overall"]["count"] == 3
        assert stats["overall"]["avg_ms"] == 300.0
        assert stats["overall"]["min_ms"] == 100.0
        assert stats["overall"]["max_ms"] == 600.0
        assert stats["overall"]["slow_requests"] == 1

        assert "by_endpoint" in stats
        assert "GET /api/test" in stats["by_endpoint"]

        assert "recent_slow_requests" in stats


class TestPerformanceMonitorRecordRequest:
    """Tests for PerformanceMonitor.record_request method."""

    def test_record_request_tracks_slow_requests(self) -> None:
        """Lines 38-47: Tracks slow requests (>500ms)."""
        perf_monitor = PerformanceMonitor()

        # Record a slow request
        perf_monitor.record_request("/api/slow", "POST", 600.0, 200)

        assert len(perf_monitor.slow_requests) == 1
        slow = perf_monitor.slow_requests[0]
        assert slow["endpoint"] == "/api/slow"
        assert slow["method"] == "POST"
        assert slow["duration_ms"] == 600.0
        assert slow["status_code"] == 200

    def test_record_request_tracks_hourly_stats(self) -> None:
        """Lines 49-51: Tracks hourly aggregation."""
        perf_monitor = PerformanceMonitor()

        perf_monitor.record_request("/api/test", "GET", 100.0, 200)

        # Should have one hour key
        assert len(perf_monitor.hourly_stats) == 1


class TestMonitoringMiddlewareSkipPaths:
    """Tests for MonitoringMiddleware path skipping."""

    @pytest.mark.asyncio
    async def test_skips_sse_paths(self) -> None:
        """Lines 98-100: Skips SSE prefix paths."""
        app = AsyncMock()

        middleware = MonitoringMiddleware(app)

        # Use the actual SSE_PATH_PREFIX value
        scope = {
            "type": "http",
            "path": "/api/v1/messages/stream/test",  # SSE path
            "method": "GET",
        }
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)

        # App should be called directly without send wrapper
        app.assert_awaited_once_with(scope, receive, send)

    @pytest.mark.asyncio
    async def test_skips_metrics_paths(self) -> None:
        """Lines 98-100: Skips /metrics paths."""
        app = AsyncMock()

        middleware = MonitoringMiddleware(app)

        scope = {
            "type": "http",
            "path": "/metrics",
            "method": "GET",
        }
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)

        # App should be called directly without send wrapper
        app.assert_awaited_once_with(scope, receive, send)

    @pytest.mark.asyncio
    async def test_skips_non_http_requests(self) -> None:
        """Lines 92-94: Skips non-HTTP requests."""
        app = AsyncMock()

        middleware = MonitoringMiddleware(app)

        scope = {
            "type": "websocket",
            "path": "/ws",
        }
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)

        # App should be called directly
        app.assert_awaited_once_with(scope, receive, send)


class TestMonitoringMiddlewareRecording:
    """Tests for MonitoringMiddleware request recording."""

    @pytest.mark.asyncio
    async def test_records_http_request_metrics(self) -> None:
        """Lines 102-127: Records HTTP request metrics."""

        async def mock_app(scope: dict, receive: Any, send: Any) -> None:
            # Simulate sending response
            await send({"type": "http.response.start", "status": 200})
            await send({"type": "http.response.body", "body": b"OK"})

        middleware = MonitoringMiddleware(mock_app)

        scope = {
            "type": "http",
            "path": "/api/v1/test",
            "method": "GET",
        }
        receive = AsyncMock()
        send = AsyncMock()

        # Clear monitor before test
        monitor.response_times.clear()
        monitor.endpoint_stats.clear()

        await middleware(scope, receive, send)

        # Verify metrics were recorded
        assert len(monitor.response_times) > 0
        assert "GET /api/v1/test" in monitor.endpoint_stats

    @pytest.mark.asyncio
    async def test_logs_slow_requests(self) -> None:
        """Lines 122-123: Logs slow requests (>500ms)."""

        async def slow_app(scope: dict, receive: Any, send: Any) -> None:
            # Simulate a slow response
            await asyncio.sleep(0.001)  # Small delay
            await send({"type": "http.response.start", "status": 200})
            await send({"type": "http.response.body", "body": b"OK"})

        middleware = MonitoringMiddleware(slow_app)

        scope = {
            "type": "http",
            "path": "/api/v1/slow",
            "method": "POST",
        }
        receive = AsyncMock()
        send = AsyncMock()

        # Mock time to simulate slow request
        with patch("app.middleware.monitoring.time") as mock_time:
            mock_time.time.side_effect = [0.0, 0.6]  # 600ms

            with patch("app.middleware.monitoring.logger") as mock_logger:
                await middleware(scope, receive, send)

                # Should log warning for slow request
                mock_logger.warning.assert_called()


class TestPerformanceMonitorStats:
    """Additional tests for statistics calculations."""

    def test_get_stats_with_many_requests(self) -> None:
        """Lines 66: p95 calculation with >20 requests."""
        perf_monitor = PerformanceMonitor()

        # Add more than 20 requests for p95 calculation
        for i in range(25):
            perf_monitor.record_request("/api/test", "GET", float(i * 10), 200)

        stats = perf_monitor.get_stats()

        # p95 should be calculated from sorted list
        assert stats["overall"]["count"] == 25
        assert "p95_ms" in stats["overall"]

    def test_get_stats_with_few_requests_uses_max_for_p95(self) -> None:
        """Lines 66: p95 uses max when fewer than 20 requests."""
        perf_monitor = PerformanceMonitor()

        # Add fewer than 20 requests
        for i in range(5):
            perf_monitor.record_request("/api/test", "GET", float(i * 10), 200)

        stats = perf_monitor.get_stats()

        # p95 should be max when count <= 20
        assert stats["overall"]["count"] == 5
        assert stats["overall"]["p95_ms"] == stats["overall"]["max_ms"]

    def test_endpoint_stats_filters_empty(self) -> None:
        """Lines 74-75: Filters out empty endpoint stats."""
        perf_monitor = PerformanceMonitor()

        # Record some requests
        perf_monitor.record_request("/api/a", "GET", 100.0, 200)

        stats = perf_monitor.get_stats()

        # All endpoints in by_endpoint should have data
        for endpoint, endpoint_stats in stats["by_endpoint"].items():
            assert endpoint_stats["count"] > 0
