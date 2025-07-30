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
        # Reduce BRPOP frequency from 1s to 10s
        # This reduces polling operations by 90%
        "polling_interval": 10.0,
    }

    # Result backend settings
    # Disabled to reduce Redis operations unless we need task results
    # Uncomment if you need to track task results
    result_backend = None  # Saves significant Redis operations
    # result_backend = settings.redis_url or "redis://localhost:6379/0"
    # result_expires = 3600  # 1 hour
    # result_persistent = True
    # result_compression = "gzip"
    # result_serializer = "json"
    # result_backend_transport_options = broker_transport_options

    # Task execution settings
    task_serializer = "json"
    task_compression = "gzip"
    task_protocol = 2
    task_time_limit = 600  # 10 minutes hard limit
    task_soft_time_limit = 300  # 5 minutes soft limit
    task_acks_late = True
    task_reject_on_worker_lost = True
    task_ignore_result = True  # Since result_backend is None
    task_store_eager_result = True
    task_track_started = True
    task_send_sent_event = True
    accept_content = ["json"]

    # Worker settings - Balanced for monitoring and Redis optimization
    worker_prefetch_multiplier = 1  # Reduce connection pool usage
    worker_max_tasks_per_child = 1000  # Standard value for stability
    worker_disable_rate_limits = False
    worker_concurrency = os.cpu_count() or 4  # Proper testing capacity
    worker_enable_remote_control = True
    worker_send_task_events = True  # Keep enabled for Flower monitoring
    worker_hijack_root_logger = False
    worker_redirect_stdouts = True
    worker_redirect_stdouts_level = "INFO"

    # Heartbeat settings - Reduce frequency to minimize Redis operations
    # Default is 2 seconds, we increase to 30 seconds
    # This reduces heartbeat operations from 43,200/day to 2,880/day per worker
    worker_heartbeat_interval = 30  # seconds

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
    control_queue_ttl = 300
    control_queue_expires = 10.0

    # Monitoring (worker_enable_remote_control and task_send_sent_event already set above)

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
    "app.tasks.privacy.*": {
        "queue": "privacy",
        "routing_key": "privacy",
        "priority": 2,  # Important for GDPR compliance
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
    "privacy": {
        "exchange": "privacy",
        "routing_key": "privacy",
        "priority": 2,  # Important for GDPR compliance
    },
}


def get_celery_config() -> CeleryConfig:
    """
    Get Celery configuration instance.

    Returns:
        CeleryConfig: Configuration instance
    """
    return CeleryConfig()
