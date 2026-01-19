"""Additional coverage tests for analytics command module."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import app.commands.analytics as analytics_mod


def _db_gen(db):
    yield db


class DummyAsyncResult:
    def __init__(self, *, state: str, success: bool, failed: bool, result=None, info=None):
        self.state = state
        self._success = success
        self._failed = failed
        self.result = result
        self.info = info

    def successful(self) -> bool:
        return self._success

    def failed(self) -> bool:
        return self._failed


def test_run_analytics_async(monkeypatch):
    redis_client = MagicMock()
    monkeypatch.setattr(analytics_mod.Redis, "from_url", lambda *_: redis_client)

    cmd = analytics_mod.AnalyticsCommand()
    task = SimpleNamespace(id="task_123")

    with patch.object(analytics_mod.calculate_analytics, "delay", return_value=task):
        result = cmd.run_analytics(days_back=30, async_mode=True)

    assert result["status"] == "submitted"
    redis_client.set.assert_called_once()


def test_run_analytics_sync_success(monkeypatch):
    redis_client = MagicMock()
    monkeypatch.setattr(analytics_mod.Redis, "from_url", lambda *_: redis_client)

    db = MagicMock()
    calc = MagicMock()
    calc.calculate_all_analytics.return_value = 5
    calc.generate_report.return_value = {"ok": True}

    with patch.object(analytics_mod, "AnalyticsCalculator", return_value=calc):
        monkeypatch.setattr(analytics_mod, "get_db", lambda: _db_gen(db))
        cmd = analytics_mod.AnalyticsCommand()
        result = cmd.run_analytics(days_back=7, async_mode=False)

    assert result["status"] == "success"
    assert result["services_updated"] == 5
    db.close.assert_called_once()


def test_run_analytics_sync_failure(monkeypatch):
    redis_client = MagicMock()
    monkeypatch.setattr(analytics_mod.Redis, "from_url", lambda *_: redis_client)

    db = MagicMock()
    calc = MagicMock()
    calc.calculate_all_analytics.side_effect = RuntimeError("boom")

    with patch.object(analytics_mod, "AnalyticsCalculator", return_value=calc):
        monkeypatch.setattr(analytics_mod, "get_db", lambda: _db_gen(db))
        cmd = analytics_mod.AnalyticsCommand()
        result = cmd.run_analytics(days_back=7, async_mode=False)

    assert result["status"] == "failed"


def test_check_status_no_data(monkeypatch):
    redis_client = MagicMock()
    redis_client.get.return_value = None
    monkeypatch.setattr(analytics_mod.Redis, "from_url", lambda *_: redis_client)

    cmd = analytics_mod.AnalyticsCommand()
    result = cmd.check_status()

    assert result["status"] == "no_data"


def test_check_status_async_success_updates_cache(monkeypatch):
    redis_client = MagicMock()
    last_run = {"mode": "async", "task_id": "task_abc"}
    redis_client.get.return_value = json.dumps(last_run)
    monkeypatch.setattr(analytics_mod.Redis, "from_url", lambda *_: redis_client)

    db = MagicMock()
    db.query.return_value.scalar.return_value = 2
    db.query.return_value.order_by.return_value.first.return_value = SimpleNamespace(
        last_calculated=datetime(2030, 1, 1, tzinfo=timezone.utc)
    )

    monkeypatch.setattr(analytics_mod, "get_db", lambda: _db_gen(db))

    async_result = DummyAsyncResult(
        state="SUCCESS",
        success=True,
        failed=False,
        result={"status": "success", "completed_at": "done"},
    )

    with patch.object(analytics_mod, "AsyncResult", return_value=async_result):
        cmd = analytics_mod.AnalyticsCommand()
        result = cmd.check_status()

    assert result["last_run"]["status"] == "success"
    assert result["database_stats"]["total_records"] == 2


def test_check_status_async_pending(monkeypatch):
    redis_client = MagicMock()
    last_run = {"mode": "async", "task_id": "task_pending"}
    redis_client.get.return_value = json.dumps(last_run)
    monkeypatch.setattr(analytics_mod.Redis, "from_url", lambda *_: redis_client)

    db = MagicMock()
    db.query.return_value.scalar.return_value = 0
    db.query.return_value.order_by.return_value.first.return_value = None
    monkeypatch.setattr(analytics_mod, "get_db", lambda: _db_gen(db))

    async_result = DummyAsyncResult(state="PENDING", success=False, failed=False, info=None)
    with patch.object(analytics_mod, "AsyncResult", return_value=async_result):
        cmd = analytics_mod.AnalyticsCommand()
        result = cmd.check_status()

    assert result["last_run"]["status"] == "pending"


def test_check_status_async_started(monkeypatch):
    redis_client = MagicMock()
    last_run = {"mode": "async", "task_id": "task_started"}
    redis_client.get.return_value = json.dumps(last_run)
    monkeypatch.setattr(analytics_mod.Redis, "from_url", lambda *_: redis_client)

    db = MagicMock()
    db.query.return_value.scalar.return_value = 1
    db.query.return_value.order_by.return_value.first.return_value = None
    monkeypatch.setattr(analytics_mod, "get_db", lambda: _db_gen(db))

    async_result = DummyAsyncResult(state="STARTED", success=False, failed=False, info=None)
    with patch.object(analytics_mod, "AsyncResult", return_value=async_result):
        cmd = analytics_mod.AnalyticsCommand()
        result = cmd.check_status()

    assert result["last_run"]["status"] == "running"


def test_check_status_async_failed(monkeypatch):
    redis_client = MagicMock()
    last_run = {"mode": "async", "task_id": "task_failed"}
    redis_client.get.return_value = json.dumps(last_run)
    monkeypatch.setattr(analytics_mod.Redis, "from_url", lambda *_: redis_client)

    db = MagicMock()
    db.query.return_value.scalar.return_value = 0
    db.query.return_value.order_by.return_value.first.return_value = None
    monkeypatch.setattr(analytics_mod, "get_db", lambda: _db_gen(db))

    async_result = DummyAsyncResult(
        state="FAILURE", success=False, failed=True, info="boom", result=None
    )
    with patch.object(analytics_mod, "AsyncResult", return_value=async_result):
        cmd = analytics_mod.AnalyticsCommand()
        result = cmd.check_status()

    assert result["last_run"]["status"] == "failed"
    assert "boom" in result["last_run"]["status_message"]


def test_check_status_async_other_state(monkeypatch):
    redis_client = MagicMock()
    last_run = {"mode": "async", "task_id": "task_retry"}
    redis_client.get.return_value = json.dumps(last_run)
    monkeypatch.setattr(analytics_mod.Redis, "from_url", lambda *_: redis_client)

    db = MagicMock()
    db.query.return_value.scalar.return_value = 0
    db.query.return_value.order_by.return_value.first.return_value = None
    monkeypatch.setattr(analytics_mod, "get_db", lambda: _db_gen(db))

    async_result = DummyAsyncResult(state="RETRY", success=False, failed=False, info=None)
    with patch.object(analytics_mod, "AsyncResult", return_value=async_result):
        cmd = analytics_mod.AnalyticsCommand()
        result = cmd.check_status()

    assert result["last_run"]["status"] == "RETRY"


def test_format_status_response_includes_optional_fields(monkeypatch):
    redis_client = MagicMock()
    monkeypatch.setattr(analytics_mod.Redis, "from_url", lambda *_: redis_client)
    cmd = analytics_mod.AnalyticsCommand()

    payload = {
        "started_at": "start",
        "completed_at": "end",
        "status": "success",
        "mode": "sync",
        "execution_time": 12.34,
        "services_updated": 5,
        "error": "none",
        "task_id": "task",
        "status_message": "ok",
        "report": {"ok": True},
        "total_analytics_records": 3,
        "latest_update": "latest",
    }

    result = cmd._format_status_response(payload)

    assert result["last_run"]["execution_time"] == "12.34 seconds"
    assert result["last_run"]["services_updated"] == 5
    assert result["last_run"]["error"] == "none"
    assert result["last_run"]["task_id"] == "task"
    assert result["last_run"]["status_message"] == "ok"
    assert result["report"] == {"ok": True}
    assert result["database_stats"]["total_records"] == 3


def test_main_run_submitted(monkeypatch, capsys):
    runner = MagicMock()
    runner.run_analytics.return_value = {
        "status": "submitted",
        "message": "submitted",
    }

    monkeypatch.setattr(analytics_mod, "AnalyticsCommand", lambda: runner)
    monkeypatch.setattr(analytics_mod.sys, "argv", ["analytics", "run", "--async"])

    analytics_mod.main()
    out = capsys.readouterr().out
    assert "submitted" in out

def test_main_run_success(monkeypatch, capsys):
    runner = MagicMock()
    runner.run_analytics.return_value = {
        "status": "success",
        "execution_time": 1.23,
        "services_updated": 2,
    }

    monkeypatch.setattr(analytics_mod, "AnalyticsCommand", lambda: runner)
    monkeypatch.setattr(analytics_mod.sys, "argv", ["analytics", "run", "--days", "7"])

    analytics_mod.main()
    out = capsys.readouterr().out
    assert "Analytics completed successfully" in out


def test_main_run_failure_exits(monkeypatch):
    runner = MagicMock()
    runner.run_analytics.return_value = {"status": "failed", "error": "boom"}

    monkeypatch.setattr(analytics_mod, "AnalyticsCommand", lambda: runner)
    monkeypatch.setattr(analytics_mod.sys, "argv", ["analytics", "run"])

    with pytest.raises(SystemExit):
        analytics_mod.main()


def test_main_status_no_data(monkeypatch, capsys):
    runner = MagicMock()
    runner.check_status.return_value = {}

    monkeypatch.setattr(analytics_mod, "AnalyticsCommand", lambda: runner)
    monkeypatch.setattr(analytics_mod.sys, "argv", ["analytics", "status"])

    analytics_mod.main()
    out = capsys.readouterr().out
    assert "No analytics run information" in out


def test_main_status_with_report(monkeypatch, capsys):
    runner = MagicMock()
    runner.check_status.return_value = {
        "last_run": {
            "started_at": "start",
            "status": "success",
            "completed_at": "end",
            "execution_time": "1s",
            "services_updated": 2,
            "task_id": "task",
            "status_message": "ok",
            "error": "none",
        },
        "database_stats": {"total_records": 3, "latest_update": "latest"},
        "report": {"ok": True},
    }

    monkeypatch.setattr(analytics_mod, "AnalyticsCommand", lambda: runner)
    monkeypatch.setattr(analytics_mod.sys, "argv", ["analytics", "status"])

    analytics_mod.main()
    out = capsys.readouterr().out
    assert "Database Statistics" in out
    assert "Last Report Summary" in out


def test_main_unknown_command_shows_help(monkeypatch, capsys):
    runner = MagicMock()
    monkeypatch.setattr(analytics_mod, "AnalyticsCommand", lambda: runner)
    monkeypatch.setattr(analytics_mod.sys, "argv", ["analytics"])

    with pytest.raises(SystemExit):
        analytics_mod.main()

    out = capsys.readouterr().out
    assert "Analytics Management" in out
