"""
Celery tasks for monitoring alerts and notifications.
"""

from datetime import datetime, timedelta, timezone
import json
import logging
import os
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional, Tuple, TypeVar, cast

from celery.app.task import Task
import httpx
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.database import SessionLocal
from app.services.email import EmailService
from app.services.email_config import EmailConfigService
from app.tasks.celery_app import celery_app
from app.tasks.enqueue import enqueue_task

TaskCallable = TypeVar("TaskCallable", bound=Callable[..., Any])
if TYPE_CHECKING:
    from app.repositories.alerts_repository import AlertsRepository

    class MonitoringTaskBase:
        _db: Optional[Session]
        _email_service: Optional[EmailService]
        _email_config_service: Optional[EmailConfigService]
        _alert_repo_instance: Optional["AlertsRepository"]

        def after_return(
            self,
            status: str,
            retval: object,
            task_id: str,
            args: Tuple[Any, ...],
            kwargs: Dict[str, Any],
            einfo: Any,
        ) -> None:
            ...

        def retry(self, *args: Any, **kwargs: Any) -> Any:
            ...

else:
    MonitoringTaskBase = Task


def typed_task(*task_args: Any, **task_kwargs: Any) -> Callable[[TaskCallable], TaskCallable]:
    """Return a typed Celery task decorator for mypy."""

    return cast(Callable[[TaskCallable], TaskCallable], celery_app.task(*task_args, **task_kwargs))


logger = logging.getLogger(__name__)


class MonitoringTask(MonitoringTaskBase):
    """Base task with database session management."""

    _db: Optional[Session]
    _email_service: Optional[EmailService]
    _email_config_service: Optional[EmailConfigService]
    _alert_repo_instance: Optional["AlertsRepository"]

    def __init__(self) -> None:
        self._db = None
        self._email_service = None
        self._email_config_service = None
        self._alert_repo_instance = None

    @property
    def db(self) -> Session:
        if self._db is None:
            # Check if we should use test database
            if os.getenv("USE_TEST_DATABASE") == "true":
                test_db_url = os.getenv(
                    "test_database_url",
                    "postgresql://postgres:postgres@localhost:5432/instainstru_test",
                )
                from sqlalchemy import create_engine

                engine = create_engine(test_db_url)
                test_session_factory: sessionmaker[Session] = sessionmaker(
                    autocommit=False,
                    autoflush=False,
                    bind=engine,
                )
                self._db = test_session_factory()
                logger.info(f"MonitoringTask using TEST database: {test_db_url.split('@')[1]}")
            else:
                self._db = SessionLocal()
        return self._db

    @property
    def email_service(self) -> EmailService:
        if self._email_service is None:
            self._email_service = EmailService(self.db)
        return self._email_service

    @property
    def email_config_service(self) -> EmailConfigService:
        if self._email_config_service is None:
            self._email_config_service = EmailConfigService(self.db)
        return self._email_config_service

    @property
    def alert_repo(self) -> "AlertsRepository":
        if not hasattr(self, "_alert_repo_instance") or self._alert_repo_instance is None:
            from app.repositories.alerts_repository import AlertsRepository

            self._alert_repo_instance = AlertsRepository(self.db)
        return self._alert_repo_instance

    def after_return(
        self,
        status: str,
        retval: object,
        task_id: str,
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
        einfo: Any,
    ) -> None:
        """Clean up the database session after task execution."""
        if self._db is not None:
            self._db.close()
            self._db = None
        self._alert_repo_instance = None


@typed_task(base=MonitoringTask, bind=True, max_retries=3)
def process_monitoring_alert(
    self: MonitoringTask,
    alert_type: str,
    severity: str,
    title: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
) -> None:
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
        # Create alert history record via repository
        with self.alert_repo.transaction():
            alert = self.alert_repo.create_alert(
                alert_type=alert_type,
                severity=severity,
                title=title,
                message=message,
                details=details,
            )

        # Send email for critical alerts
        if severity == "critical":
            enqueue_task(
                "app.tasks.monitoring_tasks.send_alert_email",
                args=(alert.id,),
            )

        # Create GitHub issue for persistent problems
        if should_create_github_issue(self.db, alert_type, severity):
            enqueue_task(
                "app.tasks.monitoring_tasks.create_github_issue_for_alert",
                args=(alert.id,),
            )

        logger.info(f"Processed {severity} alert: {title}")

    except Exception as e:
        logger.error(f"Failed to process monitoring alert: {str(e)}")
        raise self.retry(exc=e, countdown=60)


@typed_task(base=MonitoringTask, bind=True, max_retries=3)
def send_alert_email(self: MonitoringTask, alert_id: str) -> None:
    """Send email notification for an alert."""
    try:
        alert = self.alert_repo.get_by_id(alert_id)
        if not alert:
            logger.error(f"Alert {alert_id} not found")
            return

        from app.repositories.user_repository import UserRepository

        user_repo = UserRepository(self.db)
        admin_users = user_repo.get_active_admin_users()

        if not admin_users:
            # Fallback to configured admin email
            admin_emails = [settings.admin_email] if hasattr(settings, "admin_email") else []
        else:
            admin_emails = [user.email for user in admin_users]

        if not admin_emails:
            logger.warning("No admin emails configured for alerts")
            return

        # Get monitoring-specific sender
        from_email = self.email_config_service.get_monitoring_sender()

        # Prepare email content
        subject = f"[{alert.severity.upper()}] iNSTAiNSTRU Alert: {alert.title}"

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
        <p><small>This is an automated alert from iNSTAiNSTRU monitoring system.</small></p>
        """

        # Create plain text version for better deliverability
        text_content = f"""
        MONITORING ALERT - {alert.severity.upper()}

        Type: {alert.alert_type}
        Severity: {alert.severity}
        Time: {alert.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}

        Message:
        {alert.message}

        {'Details: ' + json.dumps(alert.details, indent=2) if alert.details else ''}

        --
        This is an automated alert from iNSTAiNSTRU monitoring system.
        """

        # Send email to all admins
        for email in admin_emails:
            try:
                self.email_service.send_email(
                    to_email=email,
                    subject=subject,
                    html_content=html_content,
                    text_content=text_content,
                    from_email=from_email,
                )
            except Exception as e:
                logger.error(f"Failed to send alert email to {email}: {str(e)}")

        # Update alert record
        with self.alert_repo.transaction():
            self.alert_repo.mark_email_sent(alert_id)

        logger.info(f"Alert email sent for alert {alert_id}")

    except Exception as e:
        logger.error(f"Failed to send alert email: {str(e)}")
        raise self.retry(exc=e, countdown=300)


@typed_task(base=MonitoringTask, bind=True, max_retries=3)
def create_github_issue_for_alert(self: MonitoringTask, alert_id: str) -> None:
    """Create a GitHub issue for persistent alerts."""
    try:
        alert = self.alert_repo.get_by_id(alert_id)
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
            details_md = (
                "\n\n### Details:\n```json\n" + json.dumps(alert.details, indent=2) + "\n```"
            )

        issue_body = f"""
## Monitoring Alert

**Type:** {alert.alert_type}
**Severity:** {alert.severity}
**Time:** {alert.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}

### Message:
{alert.message}
{details_md}

---
*This issue was automatically created by the iNSTAiNSTRU monitoring system.*
"""

        # Create GitHub issue
        headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github.v3+json",
        }

        issue_data = {
            "title": issue_title,
            "body": issue_body,
            "labels": ["monitoring", alert.severity, alert.alert_type],
        }

        with httpx.Client() as client:
            response = client.post(
                f"https://api.github.com/repos/{github_repo}/issues",
                headers=headers,
                json=issue_data,
            )
            response.raise_for_status()

            issue_url = response.json()["html_url"]

            # Update alert record
            with self.alert_repo.transaction():
                self.alert_repo.mark_github_issue_created(alert_id, issue_url)

            logger.info(f"GitHub issue created for alert {alert_id}: {issue_url}")

    except Exception as e:
        logger.error(f"Failed to create GitHub issue: {str(e)}")
        raise self.retry(exc=e, countdown=600)


def should_create_github_issue(db: Session, alert_type: str, severity: str) -> bool:
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
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        from app.repositories.alerts_repository import AlertsRepository

        alert_repo = AlertsRepository(db)
        recent_count = alert_repo.count_warnings_since(alert_type, one_hour_ago)
        return recent_count >= 3

    return False


@typed_task
def cleanup_old_alerts() -> None:
    """Clean up old alert history records (keep last 30 days)."""
    db: Optional[Session] = None
    try:
        db = SessionLocal()
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)

        from app.repositories.alerts_repository import AlertsRepository

        alert_repo = AlertsRepository(db)
        with alert_repo.transaction():
            deleted_count = alert_repo.delete_older_than(cutoff_date)

        db.close()

        logger.info(f"Cleaned up {deleted_count} old alert records")

    except Exception as e:
        logger.error(f"Failed to cleanup old alerts: {str(e)}")
        if db is not None:
            db.close()
