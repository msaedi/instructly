"""
Minimal Celery configuration for Flower monitoring.

This module provides just enough configuration for Flower to connect
to the broker without requiring the full application configuration.
"""

import os

from celery import Celery

# Get Redis URL from environment
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Create minimal Celery app for Flower
celery_app = Celery(
    "instructly",
    broker=redis_url,
    backend=redis_url,
)

# Configure Celery
celery_app.conf.update(
    task_track_started=True,
    task_send_sent_event=True,
    worker_send_task_events=True,
    worker_pool_restarts=True,
)

# This allows Flower to connect without loading the full application
