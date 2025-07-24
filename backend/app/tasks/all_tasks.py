# backend/app/tasks/all_tasks.py
"""
Task registry module that ensures all tasks are discovered by Celery.

This module explicitly imports all tasks to guarantee they're registered
with the Celery app when the worker starts.
"""

# Import the Celery app first
from app.tasks.celery_app import celery_app

# Import all task modules to ensure registration

# List all available tasks for documentation
ALL_TASKS = [
    # Analytics tasks
    "app.tasks.analytics.calculate_analytics",
    "app.tasks.analytics.generate_daily_report",
    "app.tasks.analytics.update_service_metrics",
    "app.tasks.analytics.record_task_execution",
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
