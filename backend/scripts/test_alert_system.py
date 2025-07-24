#!/usr/bin/env python3
"""
Test the monitoring alert system locally.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
import time

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.monitoring.production_monitor import monitor

# Use test database for this script
TEST_DATABASE_URL = os.getenv("test_database_url", "postgresql://postgres:postgres@localhost:5432/instainstru_test")
engine = create_engine(TEST_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_slow_query_alert():
    """Simulate a slow query to trigger an alert."""
    print("\n=== Testing Slow Query Alert ===")

    # Temporarily lower the threshold to make testing easier
    original_threshold = monitor.slow_query_threshold_ms
    monitor.slow_query_threshold_ms = 50  # 50ms for testing

    try:
        # This query should be slow enough to trigger
        db = SessionLocal()
        from sqlalchemy import text

        # Run a deliberately slow query
        result = db.execute(
            text(
                """
            SELECT
                i.id,
                i.user_id,
                i.bio,
                COUNT(DISTINCT s.id) as service_count
            FROM instructor_profiles i
            LEFT JOIN instructor_services s ON i.id = s.instructor_profile_id
            GROUP BY i.id, i.user_id, i.bio
            HAVING COUNT(DISTINCT s.id) > 0
        """
            )
        )

        # Force multiple slow queries to trigger alert
        for _ in range(3):
            db.execute(
                text(
                    """
                SELECT pg_sleep(0.1)
            """
                )
            )
            time.sleep(0.1)

        db.close()
        print("✓ Slow queries executed")

    finally:
        # Restore original threshold
        monitor.slow_query_threshold_ms = original_threshold


def test_direct_alert():
    """Test sending an alert directly."""
    print("\n=== Testing Direct Alert ===")

    # Send a test alert
    monitor._send_alert(
        alert_type="test_alert",
        message="This is a test alert from the monitoring system",
        details={"test": True, "timestamp": time.time(), "environment": settings.environment},
    )
    print("✓ Test alert sent")


def check_celery_status():
    """Check if Celery is available and working."""
    print("\n=== Checking Celery Status ===")

    try:
        from app.tasks.monitoring_tasks import process_monitoring_alert

        print("✓ Celery tasks imported successfully")

        # Try to send a test task
        result = process_monitoring_alert.delay(
            alert_type="test_celery",
            severity="info",
            title="Celery Test",
            message="Testing Celery connectivity",
            details={"test": True},
        )

        print(f"✓ Test task dispatched with ID: {result.id}")
        print("  Check Celery worker logs to see if it was processed")

    except ImportError:
        print("✗ Celery tasks not available")
        print("  Alerts will only be logged to console")
    except Exception as e:
        print(f"✗ Celery error: {str(e)}")
        print("  Make sure Celery workers are running:")
        print("  celery -A app.tasks worker --loglevel=info")


def check_alert_history():
    """Check if alerts are being saved to database."""
    print("\n=== Checking Alert History ===")

    db = SessionLocal()
    try:
        from app.models.monitoring import AlertHistory

        # Count existing alerts
        count = db.query(AlertHistory).count()
        print(f"Total alerts in database: {count}")

        # Show recent alerts
        recent = db.query(AlertHistory).order_by(AlertHistory.created_at.desc()).limit(5).all()

        if recent:
            print("\nRecent alerts:")
            for alert in recent:
                print(f"  - [{alert.severity}] {alert.alert_type}: {alert.title}")
                print(f"    Created: {alert.created_at}")
                print(f"    Email sent: {alert.email_sent}")
                print(f"    GitHub issue: {alert.github_issue_created}")
        else:
            print("No alerts in database yet")

    finally:
        db.close()


def simulate_production_scenario():
    """Simulate a production-like scenario with multiple issues."""
    print("\n=== Simulating Production Scenario ===")

    # 1. Simulate high memory usage
    print("1. Simulating high memory usage...")
    # This would normally trigger based on actual memory usage
    monitor._send_alert(
        "high_memory_usage", "Memory usage at 85% (1700MB RSS)", details={"memory_mb": 1700, "percent": 85}
    )

    # 2. Simulate low cache hit rate
    print("2. Simulating low cache hit rate...")
    monitor._send_alert(
        "low_cache_hit_rate", "Cache hit rate at 45% (target: >70%)", details={"hit_rate": 45, "target": 70}
    )

    # 3. Simulate extremely slow request
    print("3. Simulating extremely slow request...")
    request_id = "test-request-123"
    monitor._active_requests[request_id] = {
        "start_time": time.time() - 6,  # 6 seconds ago
        "method": "GET",
        "path": "/api/services/catalog",
        "client": "127.0.0.1",
    }
    monitor.track_request_end(request_id, 200)

    print("✓ Production scenario simulated")


def main():
    """Run all tests."""
    print("=== Testing Monitoring Alert System ===")
    print(f"Environment: {settings.environment}")
    print(f"Database: {TEST_DATABASE_URL.split('@')[1].split('/')[0]}")
    print("Using TEST database, not production!")
    print("")

    # Check Celery first
    check_celery_status()

    # Test alerts
    test_direct_alert()
    test_slow_query_alert()
    simulate_production_scenario()

    # Check results
    print("\n" + "=" * 50)
    check_alert_history()

    print("\n=== Test Complete ===")
    print("\nNext steps:")
    print("1. Check Celery worker logs for task execution")
    print("2. Check console output for alert messages")
    print("3. Query alert_history table to see saved alerts")
    print("4. If using email, check SMTP configuration")


if __name__ == "__main__":
    main()
