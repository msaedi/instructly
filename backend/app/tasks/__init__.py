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

__all__ = [
    "celery_app",
    "BaseTask",
    "calculate_analytics",
    "generate_daily_report",
    "update_service_metrics",
    "record_task_execution",
]

# Import all_tasks to ensure task discovery
from app.tasks import all_tasks

# This allows running celery with: celery -A app.tasks worker
