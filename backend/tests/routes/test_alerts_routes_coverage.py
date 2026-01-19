from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.routes.v1 import alerts as routes


class _AlertsRepo:
    def __init__(self, rows):
        self._rows = rows

    def get_recent_alerts(self, _since, _limit, _severity):
        return self._rows

    def get_type_counts(self, _since):
        return [SimpleNamespace(alert_type="slow_query", count=2)]

    def get_severity_counts(self, _since):
        return [SimpleNamespace(severity="critical", count=1)]

    def count_alerts_in_range(self, _start, _end):
        return 5

    def get_live_alerts(self, _since):
        return self._rows


def test_verify_api_key_accepts(monkeypatch):
    monkeypatch.setenv("MONITORING_API_KEY", "good")
    assert routes.verify_api_key("good") == "good"


def test_verify_api_key_rejects(monkeypatch):
    monkeypatch.setenv("MONITORING_API_KEY", "good")
    with pytest.raises(Exception) as exc:
        routes.verify_api_key("bad")
    assert getattr(exc.value, "status_code", None) == 403


def test_get_recent_alerts_maps_rows():
    now = datetime.now(timezone.utc)
    rows = [
        SimpleNamespace(
            id="a1",
            alert_type="extremely_slow_query",
            severity="warning",
            title="Slow",
            message="Query slow",
            created_at=now,
            email_sent=False,
            github_issue_created=True,
            # Use typed details matching ExtremelySlowQueryDetails
            details={
                "alert_type": "extremely_slow_query",
                "duration_ms": 5000.0,
                "query_preview": "SELECT * FROM users...",
            },
        )
    ]
    repo = _AlertsRepo(rows)

    response = routes.get_recent_alerts(
        hours=1, limit=10, severity=None, repository=repo, _="ok"
    )

    assert response.total == 1
    assert response.alerts[0].id == "a1"


def test_get_alert_summary_builds_daily_counts():
    repo = _AlertsRepo([])
    response = routes.get_alert_summary(days=2, repository=repo, _="ok")

    assert response.days == 2
    assert response.total == 2
    assert response.by_type["slow_query"] == 2
    assert response.by_severity["critical"] == 1
    assert len(response.by_day) == 2


def test_get_live_alerts_truncates_message():
    now = datetime.now(timezone.utc)
    message = "x" * 150
    rows = [
        SimpleNamespace(
            id="a2",
            alert_type="memory",
            severity="critical",
            title="Memory",
            message=message,
            created_at=now,
            email_sent=False,
            github_issue_created=False,
            details=None,
        )
    ]
    repo = _AlertsRepo(rows)

    response = routes.get_live_alerts(minutes=5, repository=repo, _="ok")

    assert response.count == 1
    assert response.alerts[0].message.endswith("...")
