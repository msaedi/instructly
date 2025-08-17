# backend/app/tasks/celery_app.py
"""
Celery application configuration for InstaInstru.

This module sets up the Celery app with Redis as the broker and backend,
configures task serialization, timezone, and autodiscovery.
"""

from typing import Any

from celery import Celery
from celery.signals import setup_logging

from app.core.config import settings

# Import production config if available
if settings.environment == "production":
    try:
        from app.core.config_production import CELERY_WORKER_CONFIG
    except ImportError:
        CELERY_WORKER_CONFIG = None
else:
    CELERY_WORKER_CONFIG = None


def create_celery_app() -> Celery:
    """
    Create and configure the Celery application.

    Returns:
        Celery: Configured Celery application instance
    """
    # Create Celery instance
    # Ensure Redis URL includes database number
    redis_url = settings.redis_url or "redis://localhost:6379"
    if not redis_url.endswith("/0") and not any(redis_url.endswith(f"/{i}") for i in range(16)):
        redis_url = f"{redis_url}/0"

    celery_app = Celery(
        "instainstru",
        broker=redis_url,
        backend=redis_url,
    )

    # Base configuration
    base_config = {
        # Task settings
        "task_serializer": "json",
        "accept_content": ["json"],
        "result_serializer": "json",
        "timezone": "US/Eastern",
        "enable_utc": True,
        # Result backend settings - Disabled to reduce Redis operations
        # Only uncomment these if:
        # 1. You need to use task.get() to retrieve results
        # 2. You need to check task status from the API
        # 3. You're implementing async result polling
        # Otherwise, keeping these disabled saves ~50% of Redis operations
        # "result_expires": 3600,  # Results expire after 1 hour
        # "result_persistent": True,
        # "result_compression": "gzip",
        # Worker settings
        "worker_prefetch_multiplier": 4,
        "worker_max_tasks_per_child": 1000,
        "worker_disable_rate_limits": False,
        # Task execution settings
        "task_soft_time_limit": 300,  # 5 minutes soft limit
        "task_time_limit": 600,  # 10 minutes hard limit
        "task_acks_late": True,
        "task_reject_on_worker_lost": True,
        # Error handling
        "task_default_retry_delay": 60,  # 1 minute
        "task_max_retries": 3,
        # Beat scheduler settings (if using periodic tasks)
        "beat_schedule_filename": "celerybeat-schedule",
        # Security settings
        "worker_hijack_root_logger": False,
        "worker_redirect_stdouts": True,
        "worker_redirect_stdouts_level": "INFO",
        # Broker transport options - Reduce Redis polling frequency
        "broker_transport_options": {
            "visibility_timeout": 3600,
            "polling_interval": 10.0,  # Reduce BRPOP from 1s to 10s (90% reduction)
        },
    }

    # Apply production optimizations if available
    if CELERY_WORKER_CONFIG:
        base_config.update(
            {
                # Override with production settings
                "worker_prefetch_multiplier": CELERY_WORKER_CONFIG.get("prefetch_multiplier", 1),
                "worker_max_tasks_per_child": CELERY_WORKER_CONFIG.get("max_tasks_per_child", 100),
                "result_expires": CELERY_WORKER_CONFIG.get("result_expires", 900),
                "task_time_limit": CELERY_WORKER_CONFIG.get("task_time_limit", 300),
                "task_soft_time_limit": CELERY_WORKER_CONFIG.get("task_soft_time_limit", 240),
                # Add memory limit for production
                "worker_max_memory_per_child": CELERY_WORKER_CONFIG.get("worker_max_memory_per_child", 200000),
                # Enable compression for production
                "task_compression": CELERY_WORKER_CONFIG.get("task_compression", "gzip"),
            }
        )

    celery_app.conf.update(base_config)

    # Configure task routing if needed
    celery_app.conf.task_routes = {
        "app.tasks.email.*": {"queue": "email"},
        "app.tasks.notifications.*": {"queue": "notifications"},
        "app.tasks.analytics.*": {"queue": "analytics"},
        "app.tasks.cleanup.*": {"queue": "maintenance"},
    }

    # Set up task autodiscovery (namespace package)
    celery_app.autodiscover_tasks(["app.tasks"])  # base namespace

    # Explicitly import task modules to guarantee registration in all envs
    # (Celery autodiscovery expects 'tasks' modules; our tasks are under app.tasks.*)
    try:
        from app.tasks import analytics as _analytics  # noqa: F401
        from app.tasks import codebase_metrics as _codebase_metrics  # noqa: F401
        from app.tasks import monitoring_tasks as _monitoring_tasks  # noqa: F401
        from app.tasks import privacy_audit_task as _privacy_audit_task  # noqa: F401
        from app.tasks import privacy_tasks as _privacy_tasks  # noqa: F401
        from app.tasks import search_analytics as _search_analytics  # noqa: F401
    except Exception:
        # Avoid startup failure if a dev-only module is missing; workers still start
        pass

    # Import environment-aware beat schedule
    from app.tasks.beat_schedule import get_beat_schedule

    celery_app.conf.beat_schedule = get_beat_schedule(settings.environment)

    return celery_app


# Disable Celery's default logging configuration
@setup_logging.connect
def config_loggers(*args: Any, **kwargs: Any) -> None:
    """Configure logging to integrate with the application's logging setup."""
    import logging

    # Set up basic logging configuration
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


# Create the Celery app instance
celery_app = create_celery_app()


# Define base task class with error handling
class BaseTask(celery_app.Task):
    """Base task with automatic error handling and logging."""

    autoretry_for = (Exception,)
    retry_kwargs = {"max_retries": 3, "countdown": 60}
    retry_backoff = True
    retry_backoff_max = 600  # Max 10 minutes between retries
    retry_jitter = True

    def on_failure(self, exc: Exception, task_id: str, args: Any, kwargs: Any, einfo: Any) -> None:
        """Log task failures."""
        import logging

        logger = logging.getLogger(__name__)
        logger.error(
            f"Task {self.name}[{task_id}] failed with exception: {exc}",
            exc_info=True,
            extra={
                "task_id": task_id,
                "task_name": self.name,
                "task_args": str(args),  # Renamed to avoid conflict
                "task_kwargs": str(kwargs),  # Renamed to avoid conflict
            },
        )
        super().on_failure(exc, task_id, args, kwargs, einfo)

    def on_retry(self, exc: Exception, task_id: str, args: Any, kwargs: Any, einfo: Any) -> None:
        """Log task retries."""
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(
            f"Task {self.name}[{task_id}] retry {self.request.retries} due to: {exc}",
            extra={
                "task_id": task_id,
                "task_name": self.name,
                "retry_count": self.request.retries,
            },
        )
        super().on_retry(exc, task_id, args, kwargs, einfo)

    def on_success(self, retval: Any, task_id: str, args: Any, kwargs: Any) -> None:
        """Log successful task completion."""
        import logging

        logger = logging.getLogger(__name__)
        logger.info(
            f"Task {self.name}[{task_id}] completed successfully",
            extra={
                "task_id": task_id,
                "task_name": self.name,
                # Note: duration is not available in on_success callback
            },
        )
        super().on_success(retval, task_id, args, kwargs)


# Health check task
@celery_app.task(name="app.tasks.health_check")
def health_check() -> dict:
    """
    Simple health check task to verify Celery is working.

    Returns:
        dict: Health check response
    """
    from datetime import datetime, timezone

    # Get current task context
    current_task = celery_app.current_task

    return {
        "status": "healthy",
        "worker": current_task.request.hostname if current_task else "unknown",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
