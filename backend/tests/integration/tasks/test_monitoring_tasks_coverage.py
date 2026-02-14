from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import sqlalchemy

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
        task._alert_repo_instance = None

    yield

    for task in tasks:
        task._db = None
        task._email_service = None
        task._email_config_service = None
        task._alert_repo_instance = None


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
    with patch.object(
        monitoring_tasks, "enqueue_task"
    ) as mock_enqueue, patch.object(
        monitoring_tasks, "should_create_github_issue", return_value=False
    ):
        monitoring_tasks.process_monitoring_alert.run(
            "slow_query", "warning", "Slow query", "Query took too long"
        )

    alert = db.query(AlertHistory).filter_by(alert_type="slow_query").first()
    assert alert is not None
    mock_enqueue.assert_not_called()


def test_process_monitoring_alert_critical_triggers_tasks(db, _task_db) -> None:
    with patch.object(
        monitoring_tasks, "enqueue_task"
    ) as mock_enqueue, patch.object(
        monitoring_tasks, "should_create_github_issue", return_value=True
    ):
        monitoring_tasks.process_monitoring_alert.run(
            "high_memory", "critical", "High memory", "Memory usage high"
        )

    assert mock_enqueue.call_count == 2
    task_names = {call.args[0] for call in mock_enqueue.call_args_list}
    assert task_names == {
        "app.tasks.monitoring_tasks.send_alert_email",
        "app.tasks.monitoring_tasks.create_github_issue_for_alert",
    }


def test_process_monitoring_alert_retries_on_failure(db, _task_db) -> None:
    with patch.object(db, "commit", side_effect=RuntimeError("boom")), patch.object(
        monitoring_tasks.process_monitoring_alert, "retry", side_effect=RuntimeError("retry")
    ) as mock_retry:
        with pytest.raises(RuntimeError, match="retry"):
            monitoring_tasks.process_monitoring_alert.run(
                "slow_query", "warning", "Slow query", "Query took too long"
            )

    assert mock_retry.called is True
    db.rollback()


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


def test_send_alert_email_fallback_admin_email(db, _task_db, monkeypatch) -> None:
    alert = _create_alert(db, alert_type="slow_request", severity="warning")

    email_service = MagicMock()
    email_config_service = MagicMock()
    email_config_service.get_monitoring_sender.return_value = "monitor@example.com"

    monitoring_tasks.send_alert_email._email_service = email_service
    monitoring_tasks.send_alert_email._email_config_service = email_config_service
    monkeypatch.setattr(
        monitoring_tasks, "settings", SimpleNamespace(admin_email="admin@example.com")
    )

    monitoring_tasks.send_alert_email.run(alert.id)

    assert email_service.send_email.called
    db.refresh(alert)
    assert alert.email_sent is True


def test_send_alert_email_no_admin_emails(db, _task_db, monkeypatch) -> None:
    alert = _create_alert(db, alert_type="slow_request", severity="warning")

    email_service = MagicMock()
    monitoring_tasks.send_alert_email._email_service = email_service
    monitoring_tasks.send_alert_email._email_config_service = MagicMock()
    monkeypatch.setattr(monitoring_tasks, "settings", SimpleNamespace())

    monitoring_tasks.send_alert_email.run(alert.id)

    email_service.send_email.assert_not_called()


def test_send_alert_email_handles_send_failure(db, _task_db, monkeypatch) -> None:
    alert = _create_alert(db, alert_type="slow_request", severity="critical")

    email_service = MagicMock()
    email_service.send_email.side_effect = RuntimeError("boom")

    email_config_service = MagicMock()
    email_config_service.get_monitoring_sender.return_value = "monitor@example.com"

    monitoring_tasks.send_alert_email._email_service = email_service
    monitoring_tasks.send_alert_email._email_config_service = email_config_service
    monkeypatch.setattr(
        monitoring_tasks, "settings", SimpleNamespace(admin_email="admin@example.com")
    )

    monitoring_tasks.send_alert_email.run(alert.id)
    db.refresh(alert)
    assert alert.email_sent is True


def test_send_alert_email_retries_on_error(db, _task_db, monkeypatch) -> None:
    alert = _create_alert(db, alert_type="slow_request", severity="critical")

    email_config_service = MagicMock()
    email_config_service.get_monitoring_sender.side_effect = RuntimeError("boom")

    monitoring_tasks.send_alert_email._email_service = MagicMock()
    monitoring_tasks.send_alert_email._email_config_service = email_config_service
    monkeypatch.setattr(
        monitoring_tasks, "settings", SimpleNamespace(admin_email="admin@example.com")
    )

    with patch.object(
        monitoring_tasks.send_alert_email, "retry", side_effect=RuntimeError("retry")
    ) as mock_retry:
        with pytest.raises(RuntimeError, match="retry"):
            monitoring_tasks.send_alert_email.run(alert.id)

    assert mock_retry.called is True


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


def test_create_github_issue_missing_alert(db, _task_db, monkeypatch) -> None:
    monkeypatch.setattr(monitoring_tasks, "settings", SimpleNamespace(github_token="t", github_repo="r"))
    monitoring_tasks.create_github_issue_for_alert.run("missing-alert")


def test_create_github_issue_not_configured(db, _task_db, monkeypatch) -> None:
    alert = _create_alert(db, alert_type="slow_query", severity="critical")
    monkeypatch.setattr(monitoring_tasks, "settings", SimpleNamespace())

    monitoring_tasks.create_github_issue_for_alert.run(alert.id)
    db.refresh(alert)
    assert alert.github_issue_created is False


def test_create_github_issue_retries_on_error(db, _task_db, monkeypatch) -> None:
    alert = _create_alert(db, alert_type="slow_query", severity="critical")

    monkeypatch.setattr(
        monitoring_tasks, "settings", SimpleNamespace(github_token="token", github_repo="owner/repo")
    )

    client = MagicMock()
    client.post.side_effect = RuntimeError("boom")
    client.__enter__.return_value = client
    client.__exit__.return_value = None

    with patch("app.tasks.monitoring_tasks.httpx.Client", return_value=client), patch.object(
        monitoring_tasks.create_github_issue_for_alert, "retry", side_effect=RuntimeError("retry")
    ) as mock_retry:
        with pytest.raises(RuntimeError, match="retry"):
            monitoring_tasks.create_github_issue_for_alert.run(alert.id)

    assert mock_retry.called is True


def test_should_create_github_issue(db) -> None:
    assert monitoring_tasks.should_create_github_issue(db, "slow_query", "critical") is True
    assert monitoring_tasks.should_create_github_issue(db, "slow_query", "info") is False

    now = datetime.now(timezone.utc)
    for idx in range(3):
        db.add(
            AlertHistory(
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


def test_cleanup_old_alerts_handles_error(monkeypatch) -> None:
    db = MagicMock()
    db.query.return_value.filter.return_value.delete.side_effect = RuntimeError("boom")
    monkeypatch.setattr(monitoring_tasks, "SessionLocal", lambda: db)

    monitoring_tasks.cleanup_old_alerts()

    assert db.close.called is True


def test_monitoring_task_uses_test_database(monkeypatch) -> None:
    task = monitoring_tasks.MonitoringTask()
    fake_session = MagicMock()

    monkeypatch.setenv("USE_TEST_DATABASE", "true")
    monkeypatch.setenv(
        "test_database_url", "postgresql://postgres:postgres@localhost:5432/instainstru_test"
    )
    monkeypatch.setattr(
        monitoring_tasks, "sessionmaker", lambda **kwargs: lambda: fake_session
    )
    monkeypatch.setattr(sqlalchemy, "create_engine", lambda *_args, **_kwargs: MagicMock())

    assert task.db is fake_session
    task.after_return("ok", None, "task-1", (), {}, None)
    fake_session.close.assert_called_once()


def test_monitoring_task_lazy_email_services(db, monkeypatch) -> None:
    task = monitoring_tasks.MonitoringTask()
    task._db = db

    email_service = MagicMock()
    email_config_service = MagicMock()

    monkeypatch.setattr(monitoring_tasks, "EmailService", lambda _db: email_service)
    monkeypatch.setattr(monitoring_tasks, "EmailConfigService", lambda _db: email_config_service)

    assert task.email_service is email_service
    assert task.email_config_service is email_config_service
