#!/usr/bin/env python3
"""
Check production monitoring and alert status.

This script checks if the monitoring system is working and if alerts
are being created in the production database.
"""

import os
import sys
from datetime import datetime, timedelta

# Add the backend directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# DO NOT set USE_TEST_DATABASE - we want production
from sqlalchemy import create_engine, text

from app.core.config import settings


def check_production_alerts():
    """Check alerts directly in production database."""
    print("=== Checking Production Alerts ===")
    print(f"Database: {settings.database_url.split('@')[1].split('/')[0]}")

    # Create engine directly to production database
    engine = create_engine(settings.database_url)

    try:
        with engine.connect() as conn:
            # Check if alert_history table exists
            result = conn.execute(
                text(
                    """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'alert_history'
                )
            """
                )
            )
            table_exists = result.scalar()

            if not table_exists:
                print("❌ alert_history table does not exist in production!")
                return

            print("✅ alert_history table exists")

            # Count total alerts
            result = conn.execute(text("SELECT COUNT(*) FROM alert_history"))
            total_count = result.scalar()
            print(f"\nTotal alerts in production: {total_count}")

            # Get recent alerts (last 24 hours)
            result = conn.execute(
                text(
                    """
                SELECT created_at, alert_type, severity, title, email_sent
                FROM alert_history
                WHERE created_at > :since
                ORDER BY created_at DESC
                LIMIT 10
            """
                ),
                {"since": datetime.utcnow() - timedelta(hours=24)},
            )

            recent_alerts = result.fetchall()

            if recent_alerts:
                print(f"\nRecent alerts (last 24 hours):")
                for alert in recent_alerts:
                    print(f"\n{alert.created_at} - {alert.title}")
                    print(f"  Type: {alert.alert_type}, Severity: {alert.severity}")
                    print(f"  Email sent: {alert.email_sent}")
            else:
                print("\nNo alerts in the last 24 hours")

            # Check for different alert types
            result = conn.execute(
                text(
                    """
                SELECT alert_type, COUNT(*) as count
                FROM alert_history
                GROUP BY alert_type
                ORDER BY count DESC
            """
                )
            )

            alert_types = result.fetchall()

            if alert_types:
                print("\nAlert types breakdown:")
                for alert_type in alert_types:
                    print(f"  {alert_type.alert_type}: {alert_type.count}")

            # Check last alert time
            result = conn.execute(
                text(
                    """
                SELECT MAX(created_at) as last_alert
                FROM alert_history
            """
                )
            )
            last_alert = result.scalar()

            if last_alert:
                print(f"\nLast alert created: {last_alert}")
                time_since = datetime.utcnow() - last_alert
                print(f"Time since last alert: {time_since}")

    except Exception as e:
        print(f"❌ Error checking production database: {str(e)}")
    finally:
        engine.dispose()


def check_celery_workers():
    """Check if Celery workers are processing tasks."""
    print("\n=== Checking Celery Status ===")

    try:
        # Try to import Celery and check broker connection
        from app.tasks.celery_app import celery_app

        # Get registered tasks
        registered_tasks = list(celery_app.tasks.keys())
        monitoring_tasks = [t for t in registered_tasks if "monitoring" in t]

        print(f"Monitoring tasks registered: {len(monitoring_tasks)}")
        for task in monitoring_tasks:
            print(f"  - {task}")

        # Check if we can inspect the workers (requires Redis connection)
        try:
            from celery import current_app

            inspector = current_app.control.inspect()

            # This will timeout if no workers are running
            stats = inspector.stats()

            if stats:
                print(f"\n✅ Found {len(stats)} Celery worker(s) running:")
                for worker_name, worker_stats in stats.items():
                    print(f"  - {worker_name}")
            else:
                print("\n❌ No Celery workers detected (they might be running on Render)")
        except Exception as e:
            print(f"\n⚠️  Cannot connect to Celery workers: {str(e)}")
            print("   (This is normal if workers are only running on Render)")

    except Exception as e:
        print(f"❌ Error checking Celery: {str(e)}")


def main():
    """Run all checks."""
    print("=== InstaInstru Production Monitoring Check ===")
    print(f"Environment: {settings.environment}")
    print(f"Timestamp: {datetime.utcnow().isoformat()}")
    print()

    # Check production alerts
    check_production_alerts()

    # Check Celery status
    check_celery_workers()

    print("\n=== Summary ===")
    print("If alerts are being created in production:")
    print("1. The monitoring system is detecting issues")
    print("2. Celery workers on Render are processing them")
    print("3. They're being saved to the Supabase database")
    print("\nIf no recent alerts:")
    print("1. The system might be running smoothly")
    print("2. Or Celery workers might not be running")
    print("3. Or monitoring thresholds might not be triggered")


if __name__ == "__main__":
    main()
