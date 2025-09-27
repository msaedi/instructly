#!/usr/bin/env python3
"""View production alerts from the database."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import desc

from app.database import SessionLocal
from app.models.monitoring import AlertHistory


def view_recent_alerts(hours=24):
    """View alerts from the last N hours."""
    db = SessionLocal()
    try:
        # Get alerts from the last N hours
        since = datetime.now(timezone.utc) - timedelta(hours=hours)

        alerts = (
            db.query(AlertHistory)
            .filter(AlertHistory.created_at >= since)
            .order_by(desc(AlertHistory.created_at))
            .all()
        )

        print(f"=== Production Alerts (Last {hours} hours) ===")
        print(f"Total alerts: {len(alerts)}\n")

        if not alerts:
            print("No alerts found in the specified time period.")
            return

        # Group by severity
        by_severity = {}
        for alert in alerts:
            if alert.severity not in by_severity:
                by_severity[alert.severity] = []
            by_severity[alert.severity].append(alert)

        # Show summary
        print("Summary by Severity:")
        for severity, alerts_list in by_severity.items():
            print(f"  {severity.upper()}: {len(alerts_list)} alerts")
        print()

        # Show recent alerts
        print("Recent Alerts:")
        print("-" * 80)

        for alert in alerts[:10]:  # Show last 10
            print(f"[{alert.severity.upper()}] {alert.alert_type}")
            print(f"Title: {alert.title}")
            print(f"Message: {alert.message}")
            print(f"Time: {alert.created_at}")
            print(f"Email sent: {alert.email_sent}")
            if alert.details:
                print(f"Details: {alert.details}")
            print("-" * 80)

    finally:
        db.close()


def view_alert_summary():
    """View alert summary statistics."""
    db = SessionLocal()
    try:
        from sqlalchemy import func

        # Get alert counts by type
        type_counts = (
            db.query(AlertHistory.alert_type, func.count(AlertHistory.id).label("count"))
            .group_by(AlertHistory.alert_type)
            .all()
        )

        print("\n=== Alert Type Summary ===")
        for alert_type, count in type_counts:
            print(f"{alert_type}: {count} occurrences")

        # Get alert counts by day
        print("\n=== Alerts by Day (Last 7 days) ===")
        for i in range(7):
            day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0) - timedelta(days=i)
            day_end = day_start + timedelta(days=1)

            count = (
                db.query(AlertHistory)
                .filter(AlertHistory.created_at >= day_start)
                .filter(AlertHistory.created_at < day_end)
                .count()
            )

            print(f"{day_start.strftime('%Y-%m-%d')}: {count} alerts")

    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="View production alerts")
    parser.add_argument("--hours", type=int, default=24, help="Show alerts from last N hours")
    parser.add_argument("--summary", action="store_true", help="Show summary statistics")

    args = parser.parse_args()

    if args.summary:
        view_alert_summary()
    else:
        view_recent_alerts(args.hours)
