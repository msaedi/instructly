#!/usr/bin/env python3
"""Test email authentication fix for monitoring alerts"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timezone

from app.database import SessionLocal
from app.models.monitoring import AlertHistory
from app.services.email_config import EmailConfigService
from app.tasks.monitoring_tasks import send_alert_email


def test_email_config():
    """Test new email configuration"""
    db = SessionLocal()
    service = EmailConfigService(db)

    print("Testing Email Configuration:")
    print("-" * 40)

    # Test monitoring sender
    monitoring = service.get_monitoring_sender()
    print(f"Monitoring: {monitoring}")
    assert "auth.instainstru.com" not in monitoring
    assert "noreply" not in monitoring.lower()
    assert "@instainstru.com" in monitoring

    # Test other senders
    transactional = service.get_transactional_sender()
    print(f"Transactional: {transactional}")

    booking = service.get_booking_sender()
    print(f"Booking: {booking}")

    security = service.get_security_sender()
    print(f"Security: {security}")

    print("✅ All email configurations valid!")
    db.close()


def test_monitoring_alert():
    """Test actual monitoring alert email"""
    db = SessionLocal()

    try:
        # Create test alert record
        alert = AlertHistory(
            alert_type="test",
            severity="info",
            title="Email Authentication Test",
            message="Testing new email configuration",
            details={
                "purpose": "Verify SPF/DKIM/DMARC authentication",
                "expected": "Email should be delivered to admin@instainstru.com",
                "sender": "alerts@instainstru.com",
            },
            created_at=datetime.now(timezone.utc),
        )

        db.add(alert)
        db.commit()

        print(f"\nSending test monitoring alert (ID: {alert.id})...")
        send_alert_email.delay(alert.id)
        print("✅ Alert dispatched to Celery queue")

    except Exception as e:
        print(f"❌ Error creating test alert: {str(e)}")
    finally:
        db.close()


def verify_no_subdomain_usage():
    """Verify no auth subdomain usage remains in constants"""
    print("\nVerifying No Subdomain Usage:")
    print("-" * 40)

    # Check constants (these should be updated)
    from app.core.config import settings
    from app.core.constants import MONITORING_EMAIL, NOREPLY_EMAIL

    # Check constants for auth subdomain usage
    assert "auth.instainstru.com" not in NOREPLY_EMAIL
    assert "auth.instainstru.com" not in MONITORING_EMAIL

    print("✅ No auth subdomain found in constants")

    # Check if environment variables are overriding settings
    import os

    env_from_email = os.getenv("from_email")
    if env_from_email and "auth.instainstru.com" in env_from_email:
        print("⚠️  Warning: Environment variable 'from_email' contains auth subdomain")
        print(f"   Current value: {env_from_email}")
        print("   Update your .env file to use: InstaInstru <hello@instainstru.com>")
    elif env_from_email:
        print(f"✅ Environment from_email: {env_from_email}")
    else:
        print(f"✅ Default from_email: {settings.from_email}")

    # Check for noreply usage in constants only
    emails_to_check = [NOREPLY_EMAIL, MONITORING_EMAIL]
    noreply_found = any("noreply" in email.lower() for email in emails_to_check if email)

    if noreply_found:
        print("⚠️  Warning: 'noreply' found in email constants")
        print("   This may impact sender reputation")
    else:
        print("✅ No 'noreply' addresses found in constants")


def test_email_content_improvements():
    """Test that emails include both HTML and text versions"""
    print("\nTesting Email Content Improvements:")
    print("-" * 40)

    from app.services.email import EmailService

    db = SessionLocal()
    service = EmailService(db)

    # Test HTML to text conversion
    html_content = "<h1>Test Alert</h1><p>This is a <strong>test</strong> email.</p>"
    text_content = service._html_to_text(html_content)

    assert "Test Alert" in text_content
    assert "test email" in text_content
    assert "<h1>" not in text_content
    assert "<strong>" not in text_content

    print("✅ HTML to text conversion working")
    print(f"   HTML: {html_content}")
    print(f"   Text: {text_content}")

    db.close()


if __name__ == "__main__":
    print("🚀 Testing Email Authentication Fix")
    print("=" * 50)

    try:
        test_email_config()
        verify_no_subdomain_usage()
        test_email_content_improvements()
        test_monitoring_alert()

        print("\n🎉 Email authentication fix applied successfully!")
        print("\nNext Steps:")
        print("1. Configure DNS records as documented")
        print("2. Verify domains in Resend Dashboard")
        print("3. Test email delivery")
        print("4. Monitor bounce rates")

    except Exception as e:
        print(f"❌ Test failed: {str(e)}")
        sys.exit(1)
