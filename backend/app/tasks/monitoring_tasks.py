"""
Celery tasks for monitoring alerts and notifications.
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, Optional

import httpx
from celery import Task
from sqlalchemy import func

from app.core.config import settings
from app.database import SessionLocal
from app.models import User
from app.models.monitoring import AlertHistory
from app.services.email import EmailService
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


class MonitoringTask(Task):
    """Base task with database session management."""

    def __init__(self):
        self._db = None
        self._email_service = None

    @property
    def db(self):
        if self._db is None:
            # Check if we should use test database
            if os.getenv("USE_TEST_DATABASE") == "true":
                test_db_url = os.getenv(
                    "test_database_url", "postgresql://postgres:postgres@localhost:5432/instainstru_test"
                )
                from sqlalchemy import create_engine
                from sqlalchemy.orm import sessionmaker

                engine = create_engine(test_db_url)
                TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
                self._db = TestSessionLocal()
                logger.info(f"MonitoringTask using TEST database: {test_db_url.split('@')[1]}")
            else:
                self._db = SessionLocal()
        return self._db

    @property
    def email_service(self):
        if self._email_service is None:
            self._email_service = EmailService(self.db)
        return self._email_service

    def after_return(self, status, retval, task_id, args, kwargs, einfo):
        """Clean up the database session after task execution."""
        if self._db is not None:
            self._db.close()
            self._db = None


@celery_app.task(base=MonitoringTask, bind=True, max_retries=3)
def process_monitoring_alert(
    self, alert_type: str, severity: str, title: str, message: str, details: Optional[Dict] = None
):
    """
    Process a monitoring alert by sending notifications and creating issues.

    Args:
        alert_type: Type of alert (slow_query, slow_request, high_memory, etc.)
        severity: Alert severity (critical, warning, info)
        title: Alert title
        message: Alert message
        details: Additional alert details
    """
    try:
        # Create alert history record
        alert = AlertHistory(
            alert_type=alert_type, severity=severity, title=title, message=message, details=details or {}
        )
        self.db.add(alert)
        self.db.commit()

        # Send email for critical alerts
        if severity == "critical":
            send_alert_email.delay(alert.id)

        # Create GitHub issue for persistent problems
        if should_create_github_issue(self.db, alert_type, severity):
            create_github_issue_for_alert.delay(alert.id)

        logger.info(f"Processed {severity} alert: {title}")

    except Exception as e:
        logger.error(f"Failed to process monitoring alert: {str(e)}")
        raise self.retry(exc=e, countdown=60)


@celery_app.task(base=MonitoringTask, bind=True, max_retries=3)
def send_alert_email(self, alert_id: int):
    """Send email notification for an alert."""
    try:
        alert = self.db.query(AlertHistory).filter_by(id=alert_id).first()
        if not alert:
            logger.error(f"Alert {alert_id} not found")
            return

        # Get admin users
        admin_users = self.db.query(User).filter_by(role="admin", is_active=True).all()

        if not admin_users:
            # Fallback to configured admin email
            admin_emails = [settings.admin_email] if hasattr(settings, "admin_email") else []
        else:
            admin_emails = [user.email for user in admin_users]

        if not admin_emails:
            logger.warning("No admin emails configured for alerts")
            return

        # Prepare email content
        subject = f"[{alert.severity.upper()}] InstaInstru Alert: {alert.title}"

        details_html = ""
        if alert.details:
            details_html = "<h3>Details:</h3><pre>" + json.dumps(alert.details, indent=2) + "</pre>"

        html_content = f"""
        <h2>Monitoring Alert</h2>
        <p><strong>Type:</strong> {alert.alert_type}</p>
        <p><strong>Severity:</strong> {alert.severity}</p>
        <p><strong>Time:</strong> {alert.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}</p>

        <h3>Message:</h3>
        <p>{alert.message}</p>

        {details_html}

        <hr>
        <p><small>This is an automated alert from InstaInstru monitoring system.</small></p>
        """

        # Send email to all admins
        for email in admin_emails:
            try:
                self.email_service.send_email(to_email=email, subject=subject, html_content=html_content)
            except Exception as e:
                logger.error(f"Failed to send alert email to {email}: {str(e)}")

        # Update alert record
        alert.email_sent = True
        alert.notified_at = datetime.utcnow()
        self.db.commit()

        logger.info(f"Alert email sent for alert {alert_id}")

    except Exception as e:
        logger.error(f"Failed to send alert email: {str(e)}")
        raise self.retry(exc=e, countdown=300)


@celery_app.task(base=MonitoringTask, bind=True, max_retries=3)
def create_github_issue_for_alert(self, alert_id: int):
    """Create a GitHub issue for persistent alerts."""
    try:
        alert = self.db.query(AlertHistory).filter_by(id=alert_id).first()
        if not alert:
            logger.error(f"Alert {alert_id} not found")
            return

        # Check if GitHub integration is configured
        github_token = settings.github_token if hasattr(settings, "github_token") else None
        github_repo = settings.github_repo if hasattr(settings, "github_repo") else None

        if not github_token or not github_repo:
            logger.warning("GitHub integration not configured")
            return

        # Prepare issue content
        issue_title = f"[{alert.severity.upper()}] {alert.title}"

        details_md = ""
        if alert.details:
            details_md = "\n\n### Details:\n```json\n" + json.dumps(alert.details, indent=2) + "\n```"

        issue_body = f"""
## Monitoring Alert

**Type:** {alert.alert_type}
**Severity:** {alert.severity}
**Time:** {alert.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}

### Message:
{alert.message}
{details_md}

---
*This issue was automatically created by the InstaInstru monitoring system.*
"""

        # Create GitHub issue
        headers = {"Authorization": f"token {github_token}", "Accept": "application/vnd.github.v3+json"}

        issue_data = {
            "title": issue_title,
            "body": issue_body,
            "labels": ["monitoring", alert.severity, alert.alert_type],
        }

        with httpx.Client() as client:
            response = client.post(
                f"https://api.github.com/repos/{github_repo}/issues", headers=headers, json=issue_data
            )
            response.raise_for_status()

            issue_url = response.json()["html_url"]

            # Update alert record
            alert.github_issue_created = True
            alert.github_issue_url = issue_url
            self.db.commit()

            logger.info(f"GitHub issue created for alert {alert_id}: {issue_url}")

    except Exception as e:
        logger.error(f"Failed to create GitHub issue: {str(e)}")
        raise self.retry(exc=e, countdown=600)


def should_create_github_issue(db, alert_type: str, severity: str) -> bool:
    """
    Determine if a GitHub issue should be created based on alert history.

    Creates issues for:
    - Any critical alert
    - Repeated warnings (3+ in last hour)
    """
    if severity == "critical":
        return True

    if severity == "warning":
        # Check for repeated warnings
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        recent_count = (
            db.query(func.count(AlertHistory.id))
            .filter(
                AlertHistory.alert_type == alert_type,
                AlertHistory.severity == "warning",
                AlertHistory.created_at >= one_hour_ago,
            )
            .scalar()
        )

        return recent_count >= 3

    return False


@celery_app.task
def cleanup_old_alerts():
    """Clean up old alert history records (keep last 30 days)."""
    try:
        db = SessionLocal()
        cutoff_date = datetime.utcnow() - timedelta(days=30)

        deleted_count = db.query(AlertHistory).filter(AlertHistory.created_at < cutoff_date).delete()

        db.commit()
        db.close()

        logger.info(f"Cleaned up {deleted_count} old alert records")

    except Exception as e:
        logger.error(f"Failed to cleanup old alerts: {str(e)}")
        if db:
            db.close()
