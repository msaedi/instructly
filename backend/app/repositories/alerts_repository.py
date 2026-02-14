# backend/app/repositories/alerts_repository.py
"""
Alerts Repository for InstaInstru Platform.

Handles data access for alert monitoring.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, func
from sqlalchemy.orm import Session
import ulid

from ..models.monitoring import AlertHistory
from .base_repository import BaseRepository


@dataclass
class AlertData:
    """Alert history data."""

    id: str
    alert_type: str
    severity: str
    title: str
    message: str
    created_at: datetime
    email_sent: bool
    github_issue_created: bool
    details: Optional[Dict[str, Any]]


@dataclass
class TypeCountData:
    """Alert type count."""

    alert_type: str
    count: int


@dataclass
class SeverityCountData:
    """Alert severity count."""

    severity: str
    count: int


class AlertsRepository(BaseRepository["AlertHistory"]):
    """Repository for alerts data access."""

    def __init__(self, db: Session):
        """Initialize with AlertHistory model."""
        super().__init__(db, AlertHistory)

    def get_recent_alerts(
        self,
        since: datetime,
        limit: int = 50,
        severity: Optional[str] = None,
    ) -> List[AlertData]:
        """
        Get recent alerts since a given time.

        Args:
            since: Get alerts after this time
            limit: Maximum number of alerts to return
            severity: Optional severity filter

        Returns:
            List of alert data
        """
        query = self.db.query(AlertHistory).filter(AlertHistory.created_at >= since)

        if severity:
            query = query.filter(AlertHistory.severity == severity.lower())

        alerts = query.order_by(desc(AlertHistory.created_at)).limit(limit).all()

        return [
            AlertData(
                id=alert.id,
                alert_type=alert.alert_type,
                severity=alert.severity,
                title=alert.title,
                message=alert.message,
                created_at=alert.created_at,
                email_sent=alert.email_sent,
                github_issue_created=alert.github_issue_created,
                details=alert.details,
            )
            for alert in alerts
        ]

    def get_type_counts(self, since: datetime) -> List[TypeCountData]:
        """
        Get alert counts by type.

        Args:
            since: Count alerts after this time

        Returns:
            List of type count data
        """
        rows = (
            self.db.query(AlertHistory.alert_type, func.count(AlertHistory.id).label("count"))
            .filter(AlertHistory.created_at >= since)
            .group_by(AlertHistory.alert_type)
            .all()
        )

        return [TypeCountData(alert_type=row[0], count=row[1]) for row in rows]

    def get_severity_counts(self, since: datetime) -> List[SeverityCountData]:
        """
        Get alert counts by severity.

        Args:
            since: Count alerts after this time

        Returns:
            List of severity count data
        """
        rows = (
            self.db.query(AlertHistory.severity, func.count(AlertHistory.id).label("count"))
            .filter(AlertHistory.created_at >= since)
            .group_by(AlertHistory.severity)
            .all()
        )

        return [SeverityCountData(severity=row[0], count=row[1]) for row in rows]

    def count_alerts_in_range(self, start: datetime, end: datetime) -> int:
        """
        Count alerts in a time range.

        Args:
            start: Start of time range
            end: End of time range

        Returns:
            Count of alerts
        """
        result: int = (
            self.db.query(AlertHistory)
            .filter(AlertHistory.created_at >= start)
            .filter(AlertHistory.created_at < end)
            .count()
        )
        return result

    def get_live_alerts(self, since: datetime) -> List[AlertData]:
        """
        Get live alerts since a given time.

        Args:
            since: Get alerts after this time

        Returns:
            List of alert data
        """
        alerts = (
            self.db.query(AlertHistory)
            .filter(AlertHistory.created_at >= since)
            .order_by(desc(AlertHistory.created_at))
            .all()
        )

        return [
            AlertData(
                id=alert.id,
                alert_type=alert.alert_type,
                severity=alert.severity,
                title=alert.title,
                message=alert.message,
                created_at=alert.created_at,
                email_sent=alert.email_sent,
                github_issue_created=alert.github_issue_created,
                details=alert.details,
            )
            for alert in alerts
        ]

    # ==========================================
    # Alert Lifecycle Methods (used by monitoring_tasks)
    # ==========================================

    def create_alert(
        self,
        alert_type: str,
        severity: str,
        title: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> AlertHistory:
        """Create a new alert record."""
        alert = AlertHistory(
            id=str(ulid.ULID()),
            alert_type=alert_type,
            severity=severity,
            title=title,
            message=message,
            details=details or {},
        )
        self.db.add(alert)
        self.db.flush()
        return alert

    def mark_email_sent(self, alert_id: str) -> None:
        """Mark an alert as having email notification sent."""
        alert = self.get_by_id(alert_id)
        if alert:
            alert.email_sent = True
            alert.notified_at = datetime.now(timezone.utc)
            self.db.flush()

    def mark_github_issue_created(self, alert_id: str, issue_url: str) -> None:
        """Mark an alert as having a GitHub issue created."""
        alert = self.get_by_id(alert_id)
        if alert:
            alert.github_issue_created = True
            alert.github_issue_url = issue_url
            self.db.flush()

    def count_warnings_since(self, alert_type: str, since: datetime) -> int:
        """Count warning alerts of a specific type since a given time."""
        return (
            self.db.query(func.count(AlertHistory.id))
            .filter(
                AlertHistory.alert_type == alert_type,
                AlertHistory.severity == "warning",
                AlertHistory.created_at >= since,
            )
            .scalar()
        ) or 0

    def delete_older_than(self, cutoff_date: datetime) -> int:
        """Delete alerts older than the cutoff date. Returns count deleted."""
        result: int = (
            self.db.query(AlertHistory).filter(AlertHistory.created_at < cutoff_date).delete()
        )
        return result
