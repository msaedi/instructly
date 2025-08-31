# backend/app/tasks/__init__.py
"""
Celery tasks package for InstaInstru.

This package contains all asynchronous tasks including:
- Email sending tasks
- Notification tasks
- Analytics processing
- Cleanup and maintenance tasks
"""

import os

# Ensure Celery environment is initialized BEFORE importing modules that may touch the DB
if not os.getenv("FLOWER_RUNTIME"):
    from app.tasks.celery_init import *  # noqa: F403, F401

# Import all tasks to ensure they're registered with Celery (after env init and app setup)
from app.tasks.analytics import (  # noqa: E402
    calculate_analytics,
    generate_daily_report,
    record_task_execution,
    update_service_metrics,
)
from app.tasks.celery_app import BaseTask, celery_app
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
]

# Import all_tasks to ensure task discovery
from app.tasks import all_tasks

# This allows running celery with: celery -A app.tasks worker
