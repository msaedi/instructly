#!/usr/bin/env python3
"""
Test the complete alert system including email sending.
"""

import asyncio
import os
import sys
from datetime import datetime, timezone

# Add the backend directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set test database before imports
os.environ["USE_TEST_DATABASE"] = "true"

from sqlalchemy import func

from app.database import SessionLocal
from app.models.monitoring import AlertHistory
from app.tasks.monitoring_tasks import process_monitoring_alert


def test_direct_email():
    """Test sending an email directly."""
    print("\n=== Testing Direct Email ===")

    from app.core.config import settings
    from app.services.email import EmailService

    db = SessionLocal()
    email_service = EmailService(db, None)

    try:
        # Validate email configuration
        try:
            is_configured = email_service.validate_email_config()
            print(f"Email configuration valid: {is_configured}")
        except Exception as e:
            print(f"Configuration issue: {str(e)}")
            return

        # Send test email
        print(f"Sending test email to: {settings.admin_email}")
        response = email_service.send_email(
            to_email=settings.admin_email,
            subject="[TEST] InstaInstru Alert System Test",
            html_content="""
            <h2>Alert System Test</h2>
            <p>This is a test email from the InstaInstru monitoring system.</p>
            <p>If you received this email, the alert system is working correctly!</p>
            <hr>
            <p><small>Sent at: {}</small></p>
            """.format(
                datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            ),
        )

        if response:
            print(f"✅ Email sent successfully! Response: {response}")
        else:
            print("❌ Email sending failed - no response")

    except Exception as e:
        print(f"❌ Error sending email: {str(e)}")
    finally:
        db.close()


async def test_celery_alerts():
    """Test the full Celery alert pipeline."""
    print("\n=== Testing Celery Alert Pipeline ===")

    db = SessionLocal()

    try:
        # Clear existing test alerts
        db.query(AlertHistory).filter(AlertHistory.title.like("%TEST%")).delete()
        db.commit()

        # Test 1: Create a critical alert
        print("\n1. Dispatching critical alert...")
        result = process_monitoring_alert.delay(
            alert_type="test_critical",
            severity="critical",
            title="[TEST] Critical Alert Test",
            message="This is a test critical alert that should trigger an email",
            details={"test": True, "timestamp": datetime.now(timezone.utc).isoformat()},
        )
        print(f"   Task ID: {result.id}")

        # Test 2: Create warning alerts to trigger GitHub issue
        print("\n2. Dispatching warning alerts...")
        for i in range(3):
            result = process_monitoring_alert.delay(
                alert_type="test_warning",
                severity="warning",
                title=f"[TEST] Warning Alert {i+1}",
                message=f"Test warning {i+1} - should create GitHub issue after 3 warnings",
                details={"test": True, "warning_number": i + 1},
            )
            print(f"   Warning {i+1} Task ID: {result.id}")

        # Wait a moment for processing
        print("\n3. Waiting for Celery to process...")
        await asyncio.sleep(5)

        # Check database
        print("\n4. Checking database...")
        alert_count = db.query(func.count(AlertHistory.id)).filter(AlertHistory.title.like("%TEST%")).scalar()
        print(f"   Found {alert_count} test alerts in database")

        # Show alert details
        test_alerts = (
            db.query(AlertHistory)
            .filter(AlertHistory.title.like("%TEST%"))
            .order_by(AlertHistory.created_at.desc())
            .limit(5)
            .all()
        )

        for alert in test_alerts:
            print(f"\n   Alert: {alert.title}")
            print(f"   - Type: {alert.alert_type}, Severity: {alert.severity}")
            print(f"   - Email sent: {alert.email_sent}")
            print(f"   - GitHub issue: {alert.github_issue_created}")
            if alert.github_issue_url:
                print(f"   - Issue URL: {alert.github_issue_url}")

    except Exception as e:
        print(f"❌ Error in Celery test: {str(e)}")
    finally:
        db.close()


async def main():
    """Run all tests."""
    print("=== InstaInstru Alert System Test ===")
    print(f"Using database: {os.environ.get('test_database_url', 'test database')}")

    # Test direct email first
    test_direct_email()

    # Test Celery pipeline
    await test_celery_alerts()

    print("\n=== Test Complete ===")
    print("\nNOTE: Make sure Celery workers are running with:")
    print("USE_TEST_DATABASE=true celery -A app.tasks worker --loglevel=info")


if __name__ == "__main__":
    asyncio.run(main())
