# backend/app/tasks/all_tasks.py
"""
Task registry module that ensures all tasks are discovered by Celery.

This module explicitly imports all tasks to guarantee they're registered
with the Celery app when the worker starts.
"""

# Import all task modules to ensure registration
# These imports trigger the @celery_app.task decorators to register tasks
from app.tasks import analytics  # noqa: F401
from app.tasks import monitoring_tasks  # noqa: F401

# Import the Celery app first
from app.tasks.celery_app import celery_app

# List all available tasks for documentation
ALL_TASKS = [
    # Analytics tasks
    "app.tasks.analytics.calculate_analytics",
    "app.tasks.analytics.generate_daily_report",
    "app.tasks.analytics.update_service_metrics",
    "app.tasks.analytics.record_task_execution",
    # Monitoring tasks
    "app.tasks.monitoring_tasks.process_monitoring_alert",
    "app.tasks.monitoring_tasks.send_alert_email",
    "app.tasks.monitoring_tasks.create_github_issue_for_alert",
    "app.tasks.monitoring_tasks.cleanup_old_alerts",
    # Health check (defined in celery_app.py)
    "app.tasks.health_check",
]


# Verify tasks are registered
def verify_task_registration():
    """Verify all expected tasks are registered with Celery."""
    registered_tasks = list(celery_app.tasks.keys())

    missing_tasks = []
    for task_name in ALL_TASKS:
        if task_name not in registered_tasks:
            missing_tasks.append(task_name)

    if missing_tasks:
        print(f"WARNING: Missing tasks: {missing_tasks}")
    else:
        print(f"All {len(ALL_TASKS)} tasks registered successfully")

    return registered_tasks


# Optional: print registered tasks when module is imported
if __name__ == "__main__":
    print("Registered Celery tasks:")
    for task in sorted(verify_task_registration()):
        if not task.startswith("celery."):  # Skip built-in Celery tasks
            print(f"  - {task}")
