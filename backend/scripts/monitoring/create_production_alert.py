#!/usr/bin/env python3
"""
Create alerts directly in the production monitoring system.

This script uses the production monitor to create alerts that will be
processed by Celery and saved to the production database.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# IMPORTANT: We want to use production database, not test
# DO NOT set USE_TEST_DATABASE

from app.monitoring.production_monitor import monitor


def create_test_alerts():
    """Create various test alerts in production."""
    print("=== Creating Production Alerts ===")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print()

    # 1. Create a test alert
    print("1. Creating test alert...")
    monitor._send_alert(
        alert_type="manual_test_alert",
        message=f"Manual test alert created at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        details={
            "source": "create_production_alert.py",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "purpose": "Testing alert system",
            "environment": "production",
        },
    )
    print("   ✅ Test alert sent")

    # 2. Create a performance warning
    print("\n2. Creating performance warning...")
    monitor._send_alert(
        alert_type="performance_check",
        message="Manual performance check - system monitoring test",
        details={
            "cpu_usage": "45%",
            "memory_usage": "62%",
            "active_connections": 12,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    print("   ✅ Performance alert sent")

    # 3. Simulate a slow request alert
    print("\n3. Simulating slow request alert...")
    # First register a fake slow request
    request_id = f"test-{datetime.now(timezone.utc).timestamp()}"
    monitor._active_requests[request_id] = {
        "start_time": datetime.now(timezone.utc).timestamp() - 6.5,  # 6.5 seconds ago
        "method": "GET",
        "path": "/api/test/manual-slow-endpoint",
        "client": "create_production_alert.py",
    }
    # Then end it to trigger the alert
    monitor.track_request_end(request_id, 200)
    print("   ✅ Slow request alert triggered")

    # 4. Create a critical alert (should send email if configured)
    print("\n4. Creating critical alert...")
    try:
        from app.tasks.monitoring_tasks import process_monitoring_alert

        # Use Celery task directly for critical alert
        result = process_monitoring_alert.delay(
            alert_type="manual_critical_test",
            severity="critical",
            title="[MANUAL TEST] Critical Alert Test",
            message=f"This is a manual critical alert test created at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            details={
                "source": "create_production_alert.py",
                "should_send_email": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        print(f"   ✅ Critical alert task queued with ID: {result.id}")

    except Exception as e:
        print(f"   ❌ Could not queue critical alert via Celery: {str(e)}")
        print("      Falling back to monitor._send_alert()")
        monitor._send_alert(
            alert_type="manual_critical_test",
            message="Critical alert test (fallback method)",
            details={"fallback": True, "error": str(e)},
        )


def check_celery_connection():
    """Check if we can connect to Celery."""
    print("\n=== Checking Celery Connection ===")

    try:
        from app.tasks.celery_app import celery_app

        # Check Redis connection
        broker_url = celery_app.conf.broker_url
        print(f"Broker URL: {broker_url.split('@')[1] if '@' in broker_url else broker_url}")

        # Try to inspect workers
        inspector = celery_app.control.inspect()
        stats = inspector.stats()

        if stats:
            print(f"✅ Found {len(stats)} Celery worker(s)")
            for worker in stats:
                print(f"   - {worker}")
        else:
            print("⚠️  No local Celery workers found")
            print("   (Production workers on Render will still process the alerts)")

    except Exception as e:
        print(f"❌ Celery check failed: {str(e)}")


def main():
    """Run the alert creation script."""
    print("=== Production Alert Creation Script ===")
    print("This will create real alerts in the production monitoring system.")
    print("These alerts will be processed by Celery and saved to Supabase.\n")

    # Check Celery first
    check_celery_connection()

    # Create alerts
    print()
    create_test_alerts()

    print("\n=== Summary ===")
    print("Alerts have been triggered in the production monitoring system.")
    print("\nTo verify they were created:")
    print("1. Run: python scripts/check_production_monitoring.py")
    print("2. Check the Celery worker logs on Render")
    print("3. Query the alert_history table in Supabase")
    print("\nNote: Alerts are processed asynchronously by Celery.")
    print("It may take a few seconds for them to appear in the database.")


if __name__ == "__main__":
    main()
