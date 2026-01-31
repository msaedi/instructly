# backend/app/tasks/celery_app.py
"""
Celery application configuration for InstaInstru.

This module sets up the Celery app with Redis as the broker and backend,
configures task serialization, timezone, and autodiscovery.
"""

import os
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Optional,
    ParamSpec,
    Protocol,
    TypeVar,
    cast,
)

from celery import Celery, Task, signals
from celery.schedules import crontab
from celery.signals import setup_logging

from app.core.config import settings
from app.monitoring.sentry import init_sentry

if TYPE_CHECKING:
    from app.services.retention_service import RetentionResult

    class BaseTaskType:
        name: str
        request: Any

        def on_failure(
            self, exc: Exception, task_id: str, args: Any, kwargs: Any, einfo: Any
        ) -> None:
            ...

        def on_retry(
            self, exc: Exception, task_id: str, args: Any, kwargs: Any, einfo: Any
        ) -> None:
            ...

        def on_success(self, retval: Any, task_id: str, args: Any, kwargs: Any) -> None:
            ...

        def retry(self, *args: Any, **kwargs: Any) -> Any:
            ...

else:
    BaseTaskType = Task

# Import production config if available
if settings.environment == "production":
    try:
        from app.core.config_production import CELERY_WORKER_CONFIG as PROD_WORKER_CONFIG

        CELERY_WORKER_CONFIG: Optional[Dict[str, object]] = cast(
            Optional[Dict[str, object]], PROD_WORKER_CONFIG
        )
    except ImportError:
        CELERY_WORKER_CONFIG = None
else:
    CELERY_WORKER_CONFIG = None


def _patch_celery_redis_pubsub() -> None:
    """
    Compatibility patch for Celery 5.6.2 + redis-py 6.x.

    Celery's Redis result consumer calls the deprecated redis-py get_connection
    signature with args. This shim uses the new get_connection() API directly.

    TODO: Remove when Celery fixes this upstream (track: https://github.com/celery/celery/issues/XXXX)
    """
    try:
        from celery.backends.redis import ResultConsumer
    except Exception:
        return

    if getattr(ResultConsumer, "_instructly_pubsub_patch", False):
        return

    def _reconnect_pubsub(self: Any) -> None:
        self._pubsub = None
        self.backend.client.connection_pool.reset()
        if self.subscribed_to:
            metas = self.backend.client.mget(self.subscribed_to)
            metas = [meta for meta in metas if meta]
            for meta in metas:
                self.on_state_change(self._decode_result(meta), None)
        self._pubsub = self.backend.client.pubsub(
            ignore_subscribe_messages=True,
        )
        if self.subscribed_to:
            self._pubsub.subscribe(*self.subscribed_to)
        else:
            self._pubsub.connection = self._pubsub.connection_pool.get_connection()
            self._pubsub.connection.register_connect_callback(self._pubsub.on_connect)

    ResultConsumer._reconnect_pubsub = _reconnect_pubsub
    ResultConsumer._instructly_pubsub_patch = True


def create_celery_app() -> Celery:
    """
    Create and configure the Celery application.

    Returns:
        Celery: Configured Celery application instance
    """
    _patch_celery_redis_pubsub()
    # Create Celery instance
    # Allow environment variables to drive broker/backend for alignment with Flower/worker
    # Priority: CELERY_BROKER_URL -> REDIS_URL -> settings.redis_url -> default
    broker_url = (
        os.getenv("CELERY_BROKER_URL")
        or os.getenv("REDIS_URL")
        or settings.redis_url
        or "redis://localhost:6379"
    )
    # Ensure Redis URL includes database number
    if not broker_url.endswith("/0") and not any(broker_url.endswith(f"/{i}") for i in range(16)):
        broker_url = f"{broker_url}/0"

    result_backend = os.getenv("CELERY_RESULT_BACKEND") or broker_url

    celery_app = Celery(
        "instainstru",
        broker=broker_url,
        backend=result_backend,
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
                "worker_max_memory_per_child": CELERY_WORKER_CONFIG.get(
                    "worker_max_memory_per_child", 200000
                ),
                # Enable compression for production
                "task_compression": CELERY_WORKER_CONFIG.get("task_compression", "gzip"),
            }
        )

    celery_app.conf.update(base_config)

    # Force import of task modules so tasks are registered even if autodiscovery fails
    # This complements autodiscover and avoids "unregistered task" errors on some runners
    celery_app.conf.imports = tuple(
        set((celery_app.conf.imports or ()))
        | {
            "app.tasks.payment_tasks",
            "app.tasks.search_analytics",
            "app.tasks.location_learning",
            "app.tasks.analytics",
            "app.tasks.monitoring_tasks",
            "app.tasks.codebase_metrics",
            "app.tasks.badge_tasks",
            # Ensure privacy tasks are registered (fixes 'unregistered task' errors)
            "app.tasks.privacy_tasks",
            "app.tasks.referrals",
            "app.tasks.retention_tasks",
            # Include legacy cleanup module for completeness
            "app.tasks.search_history_cleanup",
            "app.tasks.notification_tasks",
            # NL Search embedding maintenance
            "app.tasks.embedding_migration",
        }
    )

    # Configure task routing if needed
    celery_app.conf.task_routes = {
        "app.tasks.email.*": {"queue": "email"},
        "app.tasks.notifications.*": {"queue": "notifications"},
        "app.tasks.analytics.*": {"queue": "analytics"},
        "app.tasks.search_analytics.*": {"queue": "analytics"},
        "app.tasks.cleanup.*": {"queue": "maintenance"},
        "app.tasks.payment_tasks.*": {"queue": "payments"},  # Critical payment tasks
        "outbox.*": {"queue": "notifications"},
    }

    # Set up task autodiscovery (search for 'tasks' in the 'app' package)
    celery_app.autodiscover_tasks(["app"])  # discover app.tasks and submodules

    # Import environment-aware beat schedule
    from app.tasks.beat_schedule import get_beat_schedule

    celery_app.conf.beat_schedule = get_beat_schedule(settings.environment)

    return celery_app


# Disable Celery's default logging configuration
F = TypeVar("F", bound=Callable[..., Any])


def _connect_setup_logging(func: F) -> F:
    setup_logging.connect(func)
    return func


@_connect_setup_logging
def config_loggers(*args: Any, **kwargs: Any) -> None:
    """Configure logging to integrate with the application's logging setup."""
    import logging

    # Set up basic logging configuration
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Reduce verbosity of Celery beat scheduler logs (keep task logs at INFO)
    # Beat scheduler logs "Sending due task" every time it dispatches - suppress these
    beat_logger = logging.getLogger("celery.beat")
    beat_logger.setLevel(logging.WARNING)  # Only show WARNING and above for beat scheduler


# Create the Celery app instance
celery_app = create_celery_app()

# Task modules are imported via autodiscovery in create_celery_app()
# and also via the force imports list in celery_app.conf.imports


@signals.celeryd_init.connect
def _init_sentry_worker(**kwargs: Any) -> None:
    init_sentry()


@signals.beat_init.connect
def _init_sentry_beat(**kwargs: Any) -> None:
    init_sentry()


P = ParamSpec("P")
R = TypeVar("R", covariant=True)


# Define base task class with error handling
class BaseTask(BaseTaskType):
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


# Register BaseTask as default task base for the app
# Note: celery_app.Task is read-only in Celery 5.x, use conf.task_cls instead
celery_app.conf.task_cls = BaseTask


class TaskWrapper(Protocol[P, R]):
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        ...

    delay: Callable[..., Any]
    apply_async: Callable[..., Any]


def typed_task(
    *task_args: Any, **task_kwargs: Any
) -> Callable[[Callable[P, R]], TaskWrapper[P, R]]:
    """Return a typed Celery task decorator for mypy."""

    return cast(
        Callable[[Callable[P, R]], TaskWrapper[P, R]],
        celery_app.task(*task_args, **task_kwargs),
    )


# Health check task
@typed_task(name="app.tasks.health_check")
def health_check() -> Dict[str, str]:
    """
    Simple health check task to verify Celery is working.

    Returns:
        dict: Health check response
    """
    from datetime import datetime, timezone

    # Get current task context
    current_task = celery_app.current_task

    hostname = current_task.request.hostname if current_task else None
    return {
        "status": "healthy",
        "worker": hostname if hostname else "unknown",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@typed_task(name="app.tasks.availability_retention.run")
def run_availability_retention() -> "RetentionResult":
    """
    Purge stale availability_days rows when retention is enabled.
    """
    from datetime import datetime, timezone

    from app.database import SessionLocal
    from app.services.retention_service import RetentionService

    run_day = datetime.now(timezone.utc).date()
    if not settings.availability_retention_enabled:
        return {
            "inspected_days": 0,
            "purged_days": 0,
            "ttl_days": settings.availability_retention_days,
            "keep_recent_days": settings.availability_retention_keep_recent_days,
            "dry_run": settings.availability_retention_dry_run,
            "cutoff_date": run_day,
        }

    db = SessionLocal()
    try:
        service = RetentionService(db)
        return service.purge_availability_days(today=run_day)
    finally:
        db.close()


if settings.availability_retention_enabled:
    celery_app.conf.beat_schedule.update(
        {
            "availability-retention-daily": {
                "task": "app.tasks.availability_retention.run",
                "schedule": crontab(minute=0, hour=2),
            }
        }
    )
