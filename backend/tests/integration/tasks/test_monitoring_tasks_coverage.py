from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.models.monitoring import AlertHistory
from app.tasks import monitoring_tasks


@pytest.fixture
def _task_db(db):
    tasks = [
        monitoring_tasks.process_monitoring_alert,
        monitoring_tasks.send_alert_email,
        monitoring_tasks.create_github_issue_for_alert,
    ]
    for task in tasks:
        task._db = db
        task._email_service = None
        task._email_config_service = None

    yield

    for task in tasks:
        task._db = None
        task._email_service = None
        task._email_config_service = None


def _create_alert(db, alert_type: str = "slow_query", severity: str = "warning") -> AlertHistory:
    alert = AlertHistory(
        alert_type=alert_type,
        severity=severity,
        title="Alert",
        message="Something happened",
        details={"count": 1},
        created_at=datetime.now(timezone.utc),
    )
    db.add(alert)
    db.commit()
    return alert


def test_process_monitoring_alert_warning_records(db, _task_db) -> None:
    with patch.object(monitoring_tasks.send_alert_email, "delay") as mock_email, patch.object(
        monitoring_tasks.create_github_issue_for_alert, "delay"
    ) as mock_issue, patch.object(
        monitoring_tasks, "should_create_github_issue", return_value=False
    ):
        monitoring_tasks.process_monitoring_alert.run(
            "slow_query", "warning", "Slow query", "Query took too long"
        )

    alert = db.query(AlertHistory).filter_by(alert_type="slow_query").first()
    assert alert is not None
    mock_email.assert_not_called()
    mock_issue.assert_not_called()


def test_process_monitoring_alert_critical_triggers_tasks(db, _task_db) -> None:
    with patch.object(monitoring_tasks.send_alert_email, "delay") as mock_email, patch.object(
        monitoring_tasks.create_github_issue_for_alert, "delay"
    ) as mock_issue, patch.object(
        monitoring_tasks, "should_create_github_issue", return_value=True
    ):
        monitoring_tasks.process_monitoring_alert.run(
            "high_memory", "critical", "High memory", "Memory usage high"
        )

    mock_email.assert_called_once()
    mock_issue.assert_called_once()


def test_send_alert_email_missing_alert(db, _task_db) -> None:
    monitoring_tasks.send_alert_email.run("missing-alert")


def test_send_alert_email_sends_to_admin(db, _task_db, admin_user) -> None:
    alert = _create_alert(db, alert_type="slow_request", severity="critical")

    email_service = MagicMock()
    email_config_service = MagicMock()
    email_config_service.get_monitoring_sender.return_value = "monitor@example.com"

    monitoring_tasks.send_alert_email._email_service = email_service
    monitoring_tasks.send_alert_email._email_config_service = email_config_service

    monitoring_tasks.send_alert_email.run(alert.id)

    assert email_service.send_email.called
    db.refresh(alert)
    assert alert.email_sent is True
    assert alert.notified_at is not None


def test_create_github_issue_for_alert(db, _task_db, monkeypatch) -> None:
    alert = _create_alert(db, alert_type="slow_query", severity="critical")

    fake_settings = SimpleNamespace(github_token="token", github_repo="owner/repo")
    monkeypatch.setattr(monitoring_tasks, "settings", fake_settings)

    response = MagicMock()
    response.json.return_value = {"html_url": "https://github.com/owner/repo/issues/1"}
    response.raise_for_status.return_value = None

    client = MagicMock()
    client.post.return_value = response
    client.__enter__.return_value = client
    client.__exit__.return_value = None

    with patch("app.tasks.monitoring_tasks.httpx.Client", return_value=client):
        monitoring_tasks.create_github_issue_for_alert.run(alert.id)

    db.refresh(alert)
    assert alert.github_issue_created is True
    assert alert.github_issue_url


def test_should_create_github_issue(db) -> None:
    assert monitoring_tasks.should_create_github_issue(db, "slow_query", "critical") is True
    assert monitoring_tasks.should_create_github_issue(db, "slow_query", "info") is False

    now = datetime.now(timezone.utc)
    for idx in range(3):
        db.add(
            AlertHistory(
                id=f"01KMONWARN000000000000000{idx}",
                alert_type="slow_query",
                severity="warning",
                title="Warn",
                message="Warn",
                details={},
                created_at=now - timedelta(minutes=5),
            )
        )
    db.commit()

    assert monitoring_tasks.should_create_github_issue(db, "slow_query", "warning") is True


def test_cleanup_old_alerts(db, monkeypatch) -> None:
    old_alert = AlertHistory(
        id="01KMONOLD0000000000000000",
        alert_type="slow_query",
        severity="warning",
        title="Old",
        message="Old",
        details={},
        created_at=datetime.now(timezone.utc) - timedelta(days=40),
    )
    db.add(old_alert)
    db.commit()

    monkeypatch.setattr(monitoring_tasks, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)

    monitoring_tasks.cleanup_old_alerts()
    assert db.query(AlertHistory).filter_by(id=old_alert.id).first() is None
