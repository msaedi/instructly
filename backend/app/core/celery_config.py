# backend/app/core/celery_config.py
"""
Celery configuration module for InstaInstru.

This module contains all Celery-specific configuration including
broker settings, result backend, serialization, and beat schedules.
"""

import os

from app.core.config import settings


class CeleryConfig:
    """Celery configuration class with all settings."""

    # Broker settings
    broker_url = settings.redis_url or "redis://localhost:6379/0"
    broker_connection_retry = True
    broker_connection_retry_on_startup = True
    broker_connection_max_retries = 10
    broker_transport_options = {
        "visibility_timeout": 3600,  # 1 hour
        "fanout_prefix": True,
        "fanout_patterns": True,
        "socket_keepalive": True,
        "socket_keepalive_options": {
            1: 3,  # TCP_KEEPIDLE
            2: 3,  # TCP_KEEPINTVL
            3: 5,  # TCP_KEEPCNT
        },
    }

    # Result backend settings
    result_backend = settings.redis_url or "redis://localhost:6379/0"
    result_expires = 3600  # 1 hour
    result_persistent = True
    result_compression = "gzip"
    result_serializer = "json"
    result_backend_transport_options = broker_transport_options

    # Task execution settings
    task_serializer = "json"
    task_compression = "gzip"
    task_protocol = 2
    task_time_limit = 600  # 10 minutes hard limit
    task_soft_time_limit = 300  # 5 minutes soft limit
    task_acks_late = True
    task_reject_on_worker_lost = True
    task_ignore_result = False
    task_store_eager_result = True
    task_track_started = True
    task_send_sent_event = True
    accept_content = ["json"]

    # Worker settings
    worker_prefetch_multiplier = 4
    worker_max_tasks_per_child = 1000
    worker_disable_rate_limits = False
    worker_concurrency = os.cpu_count() or 4
    worker_enable_remote_control = True
    worker_send_task_events = True
    worker_hijack_root_logger = False
    worker_redirect_stdouts = True
    worker_redirect_stdouts_level = "INFO"

    # Timezone settings
    timezone = "US/Eastern"
    enable_utc = True

    # Error handling
    task_default_retry_delay = 60  # 1 minute
    task_max_retries = 3
    task_autoretry_for = (Exception,)
    task_retry_backoff = True
    task_retry_backoff_max = 600  # Max 10 minutes
    task_retry_jitter = True

    # Security settings
    worker_enable_remote_control = True
    control_queue_ttl = 300
    control_queue_expires = 10.0

    # Monitoring
    worker_send_task_events = True
    task_send_sent_event = True

    # Beat scheduler configuration
    beat_schedule_filename = "celerybeat-schedule"
    beat_scheduler = "celery.beat:PersistentScheduler"
    beat_sync_every = 10  # Sync every 10 tasks
    beat_max_loop_interval = 5  # Max 5 seconds between schedule checks


# Import beat schedule from the dedicated module
from app.tasks.beat_schedule import CELERYBEAT_SCHEDULE

# For backward compatibility, also export it here
CELERY_BEAT_SCHEDULE = CELERYBEAT_SCHEDULE


# Task routing configuration
CELERY_TASK_ROUTES = {
    "app.tasks.email.*": {
        "queue": "email",
        "routing_key": "email",
        "priority": 5,
    },
    "app.tasks.notifications.*": {
        "queue": "notifications",
        "routing_key": "notifications",
        "priority": 5,
    },
    "app.tasks.analytics.*": {
        "queue": "analytics",
        "routing_key": "analytics",
        "priority": 3,
    },
    "app.tasks.cleanup.*": {
        "queue": "maintenance",
        "routing_key": "maintenance",
        "priority": 1,
    },
    "app.tasks.bookings.*": {
        "queue": "bookings",
        "routing_key": "bookings",
        "priority": 7,
    },
    "app.tasks.cache.*": {
        "queue": "cache",
        "routing_key": "cache",
        "priority": 4,
    },
}


# Queue configuration
CELERY_TASK_QUEUES = {
    "celery": {
        "exchange": "celery",
        "routing_key": "celery",
        "priority": 10,
    },
    "email": {
        "exchange": "email",
        "routing_key": "email",
        "priority": 5,
    },
    "notifications": {
        "exchange": "notifications",
        "routing_key": "notifications",
        "priority": 5,
    },
    "analytics": {
        "exchange": "analytics",
        "routing_key": "analytics",
        "priority": 3,
    },
    "maintenance": {
        "exchange": "maintenance",
        "routing_key": "maintenance",
        "priority": 1,
    },
    "bookings": {
        "exchange": "bookings",
        "routing_key": "bookings",
        "priority": 7,
    },
    "cache": {
        "exchange": "cache",
        "routing_key": "cache",
        "priority": 4,
    },
}


def get_celery_config() -> CeleryConfig:
    """
    Get Celery configuration instance.

    Returns:
        CeleryConfig: Configuration instance
    """
    return CeleryConfig()
