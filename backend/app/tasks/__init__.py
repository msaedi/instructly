# backend/app/tasks/__init__.py
"""
Celery tasks package for InstaInstru.

This package contains all asynchronous tasks including:
- Email sending tasks
- Notification tasks
- Analytics processing
- Cleanup and maintenance tasks
"""

# Import all tasks to ensure they're registered with Celery
from app.tasks.analytics import (
    calculate_analytics,
    generate_daily_report,
    record_task_execution,
    update_service_metrics,
)
from app.tasks.celery_app import BaseTask, celery_app

# Import database configuration FIRST
from app.tasks.celery_init import *  # noqa: F403, F401
from app.tasks.monitoring_tasks import (
    cleanup_old_alerts,
    create_github_issue_for_alert,
    process_monitoring_alert,
    send_alert_email,
)

__all__ = [
    "celery_app",
    "BaseTask",
    "calculate_analytics",
    "generate_daily_report",
    "update_service_metrics",
    "record_task_execution",
    "process_monitoring_alert",
    "send_alert_email",
    "create_github_issue_for_alert",
    "cleanup_old_alerts",
]

# Import all_tasks to ensure task discovery
from app.tasks import all_tasks

# This allows running celery with: celery -A app.tasks worker
