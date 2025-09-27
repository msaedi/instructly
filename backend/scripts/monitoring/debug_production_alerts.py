#!/usr/bin/env python3
"""
Debug why production alerts aren't being created.
"""

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text

from app.core.config import settings


def check_alert_details():
    """Check detailed alert information."""
    print("=== Production Alert Debugging ===")
    print(f"Database: {settings.database_url.split('@')[1].split('/')[0]}")
    print(f"Environment: {settings.environment} (SITE_MODE={os.getenv('SITE_MODE','')})")
    print(f"Redis URL: {settings.redis_url}")
    print()

    engine = create_engine(settings.database_url)

    try:
        with engine.connect() as conn:
            # Get the most recent alerts with more details
            print("=== Last 5 Alerts (with full details) ===")
            result = conn.execute(
                text(
                    """
                SELECT
                    created_at,
                    alert_type,
                    severity,
                    title,
                    message,
                    details,
                    email_sent,
                    github_issue_created
                FROM alert_history
                ORDER BY created_at DESC
                LIMIT 5
            """
                )
            )

            for row in result:
                print(f"\n{row.created_at}")
                print(f"Type: {row.alert_type}, Severity: {row.severity}")
                print(f"Title: {row.title}")
                print(f"Message: {row.message}")
                print(f"Details: {row.details}")
                print(f"Email sent: {row.email_sent}, GitHub issue: {row.github_issue_created}")

            # Check for alerts in last 5 minutes
            print("\n=== Alerts in Last 5 Minutes ===")
            five_min_ago = datetime.now(timezone.utc) - timedelta(minutes=5)
            result = conn.execute(
                text(
                    """
                SELECT COUNT(*) as count
                FROM alert_history
                WHERE created_at > :since
            """
                ),
                {"since": five_min_ago},
            )

            count = result.scalar()
            print(f"Alerts created in last 5 minutes: {count}")

            # Check unique alert sources
            print("\n=== Alert Sources (from details) ===")
            result = conn.execute(
                text(
                    """
                SELECT DISTINCT details->>'source' as source, COUNT(*) as count
                FROM alert_history
                WHERE details->>'source' IS NOT NULL
                GROUP BY source
                ORDER BY count DESC
            """
                )
            )

            for row in result:
                print(f"  {row.source}: {row.count} alerts")

    except Exception as e:
        print(f"Error: {str(e)}")
    finally:
        engine.dispose()


def check_monitoring_config():
    """Check monitoring configuration."""
    print("\n=== Monitoring Configuration ===")

    try:
        from app.monitoring.production_monitor import monitor

        print(f"Slow query threshold: {monitor.slow_query_threshold_ms}ms")
        print(f"Slow request threshold: {monitor.slow_request_threshold_ms}ms")
        print(f"Alert cooldown: {monitor.ALERT_COOLDOWN_SECONDS}s")
        print(f"Active requests: {len(monitor._active_requests)}")
        print(f"Slow queries recorded: {len(monitor.slow_queries)}")
        print(f"Slow requests recorded: {len(monitor.slow_requests)}")

        if monitor._last_alert_time:
            print("\nLast alert times:")
            for alert_type, timestamp in monitor._last_alert_time.items():
                print(f"  {alert_type}: {timestamp}")

    except Exception as e:
        print(f"Error checking monitor: {str(e)}")


def check_celery_queues():
    """Check Celery queue status."""
    print("\n=== Celery Queue Status ===")

    try:
        from app.tasks.celery_app import celery_app

        # Try to inspect queues
        inspector = celery_app.control.inspect()

        # Get queue lengths (this might timeout if not connected)
        try:
            reserved = inspector.reserved()
            if reserved:
                for worker, tasks in reserved.items():
                    print(f"Worker {worker} has {len(tasks)} reserved tasks")
            else:
                print("No reserved tasks or no workers connected")

            # Check scheduled tasks
            scheduled = inspector.scheduled()
            if scheduled:
                for worker, tasks in scheduled.items():
                    print(f"Worker {worker} has {len(tasks)} scheduled tasks")

        except Exception as e:
            print(f"Cannot inspect queues: {str(e)}")
            print("(This is normal if connected to local Redis instead of production)")

    except Exception as e:
        print(f"Error with Celery: {str(e)}")


def main():
    """Run all debugging checks."""
    check_alert_details()
    check_monitoring_config()
    check_celery_queues()

    print("\n=== Debugging Summary ===")
    print("If no new alerts are appearing:")
    print("1. Check that Celery workers on Render are running")
    print("2. Verify they're connected to the same Redis as the API")
    print("3. Check Render logs for the Celery worker service")
    print("4. Ensure monitoring middleware is active in production")
    print("5. Check if alert cooldown is preventing new alerts")


if __name__ == "__main__":
    main()
