# backend/app/repositories/alerts_repository.py
"""
Alerts Repository for InstaInstru Platform.

Handles data access for alert monitoring.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from ..models.monitoring import AlertHistory


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


class AlertsRepository:
    """Repository for alerts data access."""

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db

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
