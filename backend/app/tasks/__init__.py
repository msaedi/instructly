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

# Export the Celery app and base task for CLI usage.
from app.tasks.celery_app import BaseTask, celery_app  # noqa: E402

__all__ = ["celery_app", "BaseTask"]

# This allows running celery with: celery -A app.tasks worker
