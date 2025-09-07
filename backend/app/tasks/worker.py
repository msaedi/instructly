#!/usr/bin/env python
# backend/app/tasks/worker.py
"""
Celery worker startup script for InstaInstru.

This script configures and starts the Celery worker with proper settings
for production deployment.

Usage:
    python -m app.tasks.worker
    or
    celery -A app.tasks worker --loglevel=info
"""

import logging
import os
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from celery.bin import worker  # noqa: E402 (path injected above)

from app.core.logging import setup_logging  # noqa: E402
from app.tasks import celery_app  # noqa: E402

# Configure logging
setup_logging()
logger = logging.getLogger(__name__)


def start_worker():
    """Start the Celery worker with configured settings."""
    logger.info("Starting Celery worker for InstaInstru")

    # Log configuration
    logger.info(f"Broker URL: {celery_app.conf.broker_url}")
    logger.info(f"Result backend: {celery_app.conf.result_backend}")
    logger.info(f"Timezone: {celery_app.conf.timezone}")

    # Configure worker options
    worker_instance = worker.worker(app=celery_app)

    options = {
        "loglevel": os.getenv("CELERY_LOG_LEVEL", "INFO"),
        "traceback": True,
        "pool": os.getenv("CELERY_POOL", "prefork"),  # or 'eventlet' for async
        "concurrency": int(os.getenv("CELERY_CONCURRENCY", os.cpu_count() or 4)),
        "hostname": os.getenv("CELERY_HOSTNAME", f"worker@{os.uname().nodename}"),
        "queues": os.getenv("CELERY_QUEUES", "celery,email,notifications,analytics,maintenance,bookings,cache"),
        "events": True,
        "heartbeat_interval": 30,
        "without_gossip": False,
        "without_mingle": False,
        "without_heartbeat": False,
        "time_limit": 600,  # 10 minutes hard limit
        "soft_time_limit": 300,  # 5 minutes soft limit
        "max_tasks_per_child": 1000,
        "task_events": True,
        "prefetch_multiplier": 4,
    }

    # Start worker
    worker_instance.run(**options)


if __name__ == "__main__":
    start_worker()
