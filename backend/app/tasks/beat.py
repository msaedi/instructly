#!/usr/bin/env python
# backend/app/tasks/beat.py
"""
Celery beat scheduler startup script for InstaInstru.

This script configures and starts the Celery beat scheduler for
periodic task execution.

Usage:
    python -m app.tasks.beat
    or
    celery -A app.tasks beat --loglevel=info
"""

import logging
import os
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from celery.bin import beat

from app.core.celery_config import CELERY_BEAT_SCHEDULE
from app.core.logging import setup_logging
from app.tasks import celery_app

# Configure logging
setup_logging()
logger = logging.getLogger(__name__)


def start_beat():
    """Start the Celery beat scheduler with configured settings."""
    logger.info("Starting Celery beat scheduler for InstaInstru")

    # Apply beat schedule
    celery_app.conf.beat_schedule = CELERY_BEAT_SCHEDULE

    # Log scheduled tasks
    logger.info(f"Configured {len(CELERY_BEAT_SCHEDULE)} periodic tasks:")
    for task_name, task_config in CELERY_BEAT_SCHEDULE.items():
        logger.info(f"  - {task_name}: {task_config['schedule']}")

    # Configure beat options
    beat_instance = beat.beat(app=celery_app)

    options = {
        "loglevel": os.getenv("CELERY_LOG_LEVEL", "INFO"),
        "traceback": True,
        "scheduler": "celery.beat:PersistentScheduler",
        "schedule_filename": "celerybeat-schedule",
        "max_interval": 5,  # Maximum seconds to sleep between schedule checks
        "sync_every": 10,  # Sync schedule to disk every N schedules
    }

    # Start beat scheduler
    beat_instance.run(**options)


if __name__ == "__main__":
    start_beat()
