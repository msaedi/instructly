from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.monitoring import AlertHistory
from app.repositories.alerts_repository import AlertsRepository


def _create_alert(db, *, alert_type="slow", severity="warning"):
    alert = AlertHistory(
        alert_type=alert_type,
        severity=severity,
        title="title",
        message="message",
        details={"a": 1},
        email_sent=False,
        github_issue_created=True,
    )
    db.add(alert)
    db.commit()
    return alert


def test_get_recent_alerts_and_live(db):
    db.query(AlertHistory).delete()
    db.commit()

    repo = AlertsRepository(db)
    alert = _create_alert(db, alert_type="slow", severity="warning")
    since = datetime.now(timezone.utc) - timedelta(hours=1)

    rows = repo.get_recent_alerts(since, limit=10)
    assert any(r.id == alert.id for r in rows)

    live = repo.get_live_alerts(since)
    assert any(r.id == alert.id for r in live)


def test_get_recent_alerts_with_severity(db):
    db.query(AlertHistory).delete()
    db.commit()

    repo = AlertsRepository(db)
    _create_alert(db, alert_type="slow", severity="critical")
    since = datetime.now(timezone.utc) - timedelta(hours=1)

    rows = repo.get_recent_alerts(since, limit=10, severity="CRITICAL")
    assert rows[0].severity == "critical"


def test_counts(db):
    db.query(AlertHistory).delete()
    db.commit()

    repo = AlertsRepository(db)
    _create_alert(db, alert_type="slow", severity="warning")
    _create_alert(db, alert_type="memory", severity="warning")
    since = datetime.now(timezone.utc) - timedelta(hours=1)

    types = repo.get_type_counts(since)
    severities = repo.get_severity_counts(since)

    assert {t.alert_type for t in types} >= {"slow", "memory"}
    assert any(severity.severity == "warning" for severity in severities)

    start = datetime.now(timezone.utc) - timedelta(days=1)
    end = datetime.now(timezone.utc) + timedelta(days=1)
    assert repo.count_alerts_in_range(start, end) >= 2
