from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.monitoring import production_monitor as monitor_module


def _make_request():
    return SimpleNamespace(
        method="GET",
        url=SimpleNamespace(path="/path"),
        client=SimpleNamespace(host="127.0.0.1"),
        state=SimpleNamespace(),
    )


def test_check_db_pool_health_alerts(monkeypatch):
    monkeypatch.setattr(
        monitor_module, "get_db_pool_status", lambda: {"size": 1, "overflow": 0, "checked_out": 2}
    )
    sent = {}

    monitor = monitor_module.PerformanceMonitor(slow_query_threshold_ms=1, slow_request_threshold_ms=1)
    monkeypatch.setattr(monitor, "_send_alert", lambda *args, **kwargs: sent.setdefault("hit", True))

    result = monitor.check_db_pool_health()

    assert result["usage_percent"] > 80
    assert sent.get("hit") is True


def test_check_memory_usage_triggers_gc(monkeypatch):
    class _Proc:
        def memory_info(self):
            return SimpleNamespace(rss=1024 * 1024 * 10, vms=1024 * 1024 * 20)

        def memory_percent(self):
            return 90.0

    monkeypatch.setattr(monitor_module.psutil, "Process", lambda: _Proc())
    monkeypatch.setattr(
        monitor_module.psutil, "virtual_memory", lambda: SimpleNamespace(available=1024 * 1024 * 5)
    )
    called = {}
    monkeypatch.setattr(monitor_module.gc, "collect", lambda: called.setdefault("gc", True))

    monitor = monitor_module.PerformanceMonitor()
    result = monitor.check_memory_usage()

    assert result["percent"] == 90.0
    assert called.get("gc") is True


def test_check_cache_health_recommendations(monkeypatch):
    monitor = monitor_module.PerformanceMonitor()
    called = {}
    monkeypatch.setattr(monitor, "_send_alert", lambda *_args, **_kwargs: called.setdefault("alert", 1))

    result = monitor.check_cache_health({"hit_rate": "65%", "errors": 15})

    assert result["healthy"] is False
    assert result["recommendations"]
    assert called.get("alert") == 1


def test_send_alert_respects_cooldown(monkeypatch):
    monitor = monitor_module.PerformanceMonitor()
    calls = {}

    class _Task:
        def apply_async(self, **_kwargs):
            calls["count"] = calls.get("count", 0) + 1

    monkeypatch.setattr(monitor_module, "CELERY_AVAILABLE", True)
    monkeypatch.setattr(monitor_module, "process_monitoring_alert", _Task())

    monitor._send_alert("extremely_slow_request", "first")
    monitor._send_alert("extremely_slow_request", "second")

    assert calls["count"] == 1


def test_track_request_start_end(monkeypatch):
    monitor = monitor_module.PerformanceMonitor(slow_request_threshold_ms=1)
    sent = {}
    monkeypatch.setattr(monitor, "_send_alert", lambda *_args, **_kwargs: sent.setdefault("alert", 1))

    values = [0.0, 10.0]

    def _time():
        return values.pop(0) if values else 10.0

    monkeypatch.setattr(monitor_module.time, "time", _time)

    request = _make_request()
    monitor.track_request_start("req-1", request)
    duration = monitor.track_request_end("req-1", 200)

    assert duration == 10000.0
    assert sent.get("alert") == 1


def test_track_request_end_missing_returns_none():
    monitor = monitor_module.PerformanceMonitor()
    assert monitor.track_request_end("missing", 200) is None


def test_track_request_end_extremely_slow(monkeypatch):
    monitor = monitor_module.PerformanceMonitor(slow_request_threshold_ms=1)
    sent = {}
    monkeypatch.setattr(monitor, "_send_alert", lambda *_args, **_kwargs: sent.setdefault("alert", 1))
    monkeypatch.setattr(monitor_module.time, "time", lambda: 6.0)

    monitor._active_requests["req-2"] = {
        "start_time": 0.0,
        "method": "GET",
        "path": "/slow",
        "client": "127.0.0.1",
    }

    duration = monitor.track_request_end("req-2", 504)

    assert duration == 6000.0
    assert sent.get("alert") == 1


def test_query_monitoring_slow_queries(monkeypatch):
    listeners = {}

    def _listen(_engine, event_name, fn):
        listeners[event_name] = fn

    monkeypatch.setattr(monitor_module.event, "listen", _listen)
    monkeypatch.setattr(monitor_module.time, "time", lambda: 2.0)

    monitor = monitor_module.PerformanceMonitor(slow_query_threshold_ms=1)
    sent = {}
    monkeypatch.setattr(monitor, "_send_alert", lambda *_args, **_kwargs: sent.setdefault("alert", 1))

    context = SimpleNamespace(_query_start_time=0.0)
    listeners["after_cursor_execute"](None, None, "SELECT 1", None, context, False)
    assert not monitor.slow_queries

    listeners["after_cursor_execute"](None, None, "SELECT * FROM table", None, context, False)
    assert monitor.slow_queries
    assert sent.get("alert") == 1


def test_get_performance_summary(monkeypatch):
    monitor = monitor_module.PerformanceMonitor()
    monitor.db_pool_history.append({"usage_percent": 10})
    monitor.db_pool_history.append({"usage_percent": 30})
    monitor.slow_queries.append({"query": "q1"})
    monitor.slow_requests.append({"path": "/slow"})
    monitor._last_alert_time["warning"] = datetime.now(timezone.utc)

    monkeypatch.setattr(monitor, "check_db_pool_health", lambda: {"usage_percent": 20})
    monkeypatch.setattr(monitor, "check_memory_usage", lambda: {"percent": 50})

    summary = monitor.get_performance_summary()

    assert summary["database"]["average_pool_usage_percent"] == 20.0
    assert summary["requests"]["slow_requests_count"] == 1


def test_cleanup_stale_requests():
    monitor = monitor_module.PerformanceMonitor()
    monitor._active_requests["req-1"] = {"start_time": 0, "method": "GET", "path": "/x"}

    count = monitor.cleanup_stale_requests(timeout_seconds=1)

    assert count == 1
    assert "req-1" not in monitor._active_requests


@pytest.mark.asyncio
async def test_periodic_health_check_handles_error(monkeypatch):
    called = {}

    def _boom():
        raise RuntimeError("fail")

    monkeypatch.setattr(monitor_module.monitor, "check_db_pool_health", _boom)
    monkeypatch.setattr(monitor_module.monitor, "check_memory_usage", lambda: None)
    monkeypatch.setattr(monitor_module.monitor, "cleanup_stale_requests", lambda: 0)

    async def _sleep(_seconds):
        called["sleep"] = True
        raise asyncio.CancelledError

    monkeypatch.setattr(monitor_module.asyncio, "sleep", _sleep)

    with pytest.raises(asyncio.CancelledError):
        await monitor_module.periodic_health_check()

    assert called.get("sleep") is True


@pytest.mark.asyncio
async def test_track_request_performance_context_manager():
    request = _make_request()
    async with monitor_module.track_request_performance(request) as request_id:
        assert request.state.request_id == request_id
