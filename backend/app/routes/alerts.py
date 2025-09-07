# backend/app/routes/alerts.py
"""
Alert viewing endpoints for monitoring.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.monitoring import AlertHistory
from ..schemas.alert_responses import (
    AlertDetail,
    AlertSummaryResponse,
    DailyAlertCount,
    LiveAlertItem,
    LiveAlertsResponse,
    RecentAlertsResponse,
)

router = APIRouter(
    prefix="/api/monitoring/alerts",
    tags=["monitoring"],
)


def verify_api_key(x_api_key: str = Header(...)) -> str:
    """Verify monitoring API key."""
    import os

    expected_key = os.getenv("MONITORING_API_KEY", "JVLJzfK6kkVNZGTNoyjdkcwVSBxV5TZr")
    if x_api_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return x_api_key


@router.get("/recent", response_model=RecentAlertsResponse)
def get_recent_alerts(
    hours: int = Query(24, description="Get alerts from last N hours"),
    limit: int = Query(50, description="Maximum number of alerts to return"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> RecentAlertsResponse:
    """Get recent alerts from the database."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    query = db.query(AlertHistory).filter(AlertHistory.created_at >= since)

    if severity:
        query = query.filter(AlertHistory.severity == severity.lower())

    alerts = query.order_by(desc(AlertHistory.created_at)).limit(limit).all()

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
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> AlertSummaryResponse:
    """Get alert summary statistics."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Get counts by type
    type_counts = (
        db.query(AlertHistory.alert_type, func.count(AlertHistory.id).label("count"))
        .filter(AlertHistory.created_at >= since)
        .group_by(AlertHistory.alert_type)
        .all()
    )

    # Get counts by severity
    severity_counts = (
        db.query(AlertHistory.severity, func.count(AlertHistory.id).label("count"))
        .filter(AlertHistory.created_at >= since)
        .group_by(AlertHistory.severity)
        .all()
    )

    # Get daily counts
    daily_alerts = []
    for i in range(days):
        day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0) - timedelta(
            days=i
        )
        day_end = day_start + timedelta(days=1)

        count = (
            db.query(AlertHistory)
            .filter(AlertHistory.created_at >= day_start)
            .filter(AlertHistory.created_at < day_end)
            .count()
        )

        daily_alerts.append(
            {
                "date": day_start.strftime("%Y-%m-%d"),
                "count": count,
            }
        )

    return AlertSummaryResponse(
        days=days,
        by_type={alert_type: count for alert_type, count in type_counts},
        by_severity={severity: count for severity, count in severity_counts},
        by_day=[DailyAlertCount(**alert) for alert in daily_alerts],
        total=sum(count for _, count in type_counts),
    )


@router.get("/live", response_model=LiveAlertsResponse)
def get_live_alerts(
    minutes: int = Query(5, description="Get alerts from last N minutes"),
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> LiveAlertsResponse:
    """Get very recent alerts (similar to live view)."""
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)

    alerts = (
        db.query(AlertHistory)
        .filter(AlertHistory.created_at >= since)
        .order_by(desc(AlertHistory.created_at))
        .all()
    )

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
