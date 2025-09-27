#!/usr/bin/env python
"""Test Celery Beat with frequent schedule for development."""

from datetime import timedelta
from pathlib import Path
import sys

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.tasks import celery_app

# Override beat schedule for testing
test_schedule = {
    # Health check every 30 seconds
    "test-health-check": {
        "task": "app.tasks.health_check",
        "schedule": timedelta(seconds=30),
        "options": {
            "queue": "celery",
            "priority": 10,
        },
    },
    # Analytics every 60 seconds (for testing only!)
    "test-analytics": {
        "task": "app.tasks.analytics.calculate_analytics",
        "schedule": timedelta(seconds=60),
        "args": (1,),  # Only 1 day of data for quick testing
        "kwargs": {},
        "options": {
            "queue": "analytics",
            "priority": 3,
        },
    },
}

# Apply test schedule
celery_app.conf.beat_schedule = test_schedule

print("Test Beat Schedule Applied:")
print("-" * 50)
for name, config in test_schedule.items():
    print(f"{name}:")
    print(f"  Task: {config['task']}")
    print(f"  Schedule: {config['schedule']}")
    print()

print("To run beat with this test schedule:")
print("celery -A scripts.test_beat_schedule:celery_app beat --loglevel=info")
print()
print("To run worker for these tasks:")
print("celery -A app.tasks worker --loglevel=info -Q celery,analytics")
