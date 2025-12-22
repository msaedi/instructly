# backend/app/routes/alerts.py
"""
Alert viewing endpoints for monitoring.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories.alerts_repository import AlertsRepository
from app.schemas.alert_responses import (
    AlertDetail,
    AlertSummaryResponse,
    DailyAlertCount,
    LiveAlertItem,
    LiveAlertsResponse,
    RecentAlertsResponse,
)

router = APIRouter(
    tags=["monitoring"],
)


def verify_api_key(x_api_key: str = Header(...)) -> str:
    """Verify monitoring API key."""
    import os

    expected_key = os.getenv("MONITORING_API_KEY", "JVLJzfK6kkVNZGTNoyjdkcwVSBxV5TZr")
    if x_api_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return x_api_key


def get_alerts_repository(db: Session = Depends(get_db)) -> AlertsRepository:
    """Get an instance of the alerts repository."""
    return AlertsRepository(db)


@router.get("/recent", response_model=RecentAlertsResponse)
def get_recent_alerts(
    hours: int = Query(24, description="Get alerts from last N hours"),
    limit: int = Query(50, description="Maximum number of alerts to return"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    repository: AlertsRepository = Depends(get_alerts_repository),
    _: str = Depends(verify_api_key),
) -> RecentAlertsResponse:
    """Get recent alerts from the database."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    alerts = repository.get_recent_alerts(since, limit, severity)

    return RecentAlertsResponse(
        total=len(alerts),
        hours=hours,
        alerts=[
            AlertDetail(
                id=alert.id,
                type=alert.alert_type,
                severity=alert.severity,
                title=alert.title,
                message=alert.message,
                created_at=alert.created_at.isoformat(),
                email_sent=alert.email_sent,
                github_issue=alert.github_issue_created,
                details=alert.details,
            )
            for alert in alerts
        ],
    )


@router.get("/summary", response_model=AlertSummaryResponse)
def get_alert_summary(
    days: int = Query(7, description="Number of days to summarize"),
    repository: AlertsRepository = Depends(get_alerts_repository),
    _: str = Depends(verify_api_key),
) -> AlertSummaryResponse:
    """Get alert summary statistics."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Get counts by type
    type_counts = repository.get_type_counts(since)

    # Get counts by severity
    severity_counts = repository.get_severity_counts(since)

    # Get daily counts
    daily_alerts = []
    for i in range(days):
        day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0) - timedelta(
            days=i
        )
        day_end = day_start + timedelta(days=1)

        count = repository.count_alerts_in_range(day_start, day_end)

        daily_alerts.append(
            {
                "date": day_start.strftime("%Y-%m-%d"),
                "count": count,
            }
        )

    return AlertSummaryResponse(
        days=days,
        by_type={tc.alert_type: tc.count for tc in type_counts},
        by_severity={sc.severity: sc.count for sc in severity_counts},
        by_day=[DailyAlertCount(**alert) for alert in daily_alerts],
        total=sum(tc.count for tc in type_counts),
    )


@router.get("/live", response_model=LiveAlertsResponse)
def get_live_alerts(
    minutes: int = Query(5, description="Get alerts from last N minutes"),
    repository: AlertsRepository = Depends(get_alerts_repository),
    _: str = Depends(verify_api_key),
) -> LiveAlertsResponse:
    """Get very recent alerts (similar to live view)."""
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)

    alerts = repository.get_live_alerts(since)

    return LiveAlertsResponse(
        minutes=minutes,
        count=len(alerts),
        alerts=[
            LiveAlertItem(
                time=alert.created_at.strftime("%H:%M:%S"),
                severity=alert.severity.upper(),
                type=alert.alert_type,
                message=alert.message[:100] + "..." if len(alert.message) > 100 else alert.message,
            )
            for alert in alerts
        ],
    )
