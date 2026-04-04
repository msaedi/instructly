# backend/app/tasks/celery_app.py
"""
Celery application configuration for InstaInstru.

This module sets up the Celery app with Redis as the broker and backend,
configures task serialization, timezone, and autodiscovery.
"""

from datetime import datetime, timezone
import json
import logging
import os
import time
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Mapping,
    Optional,
    ParamSpec,
    Protocol,
    TypeVar,
    cast,
)

from celery import Celery, Task, signals
from celery.schedules import crontab
from celery.signals import setup_logging, task_failure, task_postrun, task_prerun, task_retry

from app.core.config import secret_or_plain, settings
from app.core.request_context import attach_request_id_filter, reset_request_id, set_request_id
from app.database import get_db_session
from app.monitoring.otel import (
    get_current_trace_id,
    init_otel,
    instrument_additional_libraries,
    shutdown_otel,
)
from app.monitoring.sentry import init_sentry
from app.monitoring.sentry_crons import monitor_if_configured

if TYPE_CHECKING:
    from app.services.retention_service import RetentionResult

    class BaseTaskType:
        name: str
        request: Any

        def before_start(self, task_id: str, args: Any, kwargs: Any) -> None:
            ...

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

        def after_return(
            self,
            status: str,
            retval: Any,
            task_id: str,
            args: Any,
            kwargs: Any,
            einfo: Any,
        ) -> None:
            ...

        def retry(self, *args: Any, **kwargs: Any) -> Any:
            ...

else:
    BaseTaskType = Task


logger = logging.getLogger(__name__)

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

    Tracking: OPS-1274 (owner: @platform-infra, target: 2026-04-15)
    Remove after Celery ships an upstream fix for Redis pubsub reconnect compatibility.
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
        or secret_or_plain(settings.redis_url).strip()
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
            "app.tasks.referral_tasks",
            "app.tasks.retention_tasks",
            # Search history maintenance
            "app.tasks.search_history_cleanup",
            "app.tasks.notification_tasks",
            # NL Search embedding maintenance
            "app.tasks.embedding_migration",
            # Periodic DB maintenance (ANALYZE on high-churn tables)
            "app.tasks.db_maintenance",
            # Video session monitoring and no-show detection
            "app.tasks.video_tasks",
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


def _resolve_task_request_id(
    task_id: str | None,
    headers: Mapping[str, Any] | None,
    kwargs: Mapping[str, Any] | None,
) -> str:
    request_id: Any | None = None
    if headers:
        request_id = headers.get("request_id") or headers.get("x-request-id")
    if not request_id and kwargs:
        request_id = kwargs.get("request_id")
    if not request_id:
        return f"task-{task_id}" if task_id else "task-unknown"
    return str(request_id)


def _extract_app_request_id(
    headers: Mapping[str, Any] | None,
    kwargs: Mapping[str, Any] | None,
) -> str | None:
    request_id: Any | None = None
    if headers:
        request_id = (
            headers.get("request_id") or headers.get("x-request-id") or headers.get("X-Request-Id")
        )
    if not request_id and kwargs:
        request_id = kwargs.get("request_id") or kwargs.get("requestId")
    if request_id is None or request_id == "":
        return None
    return str(request_id)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _truncate_text(value: Any, max_length: int) -> str | None:
    if value is None:
        return None
    text_value = str(value)
    if not text_value:
        return None
    return text_value[:max_length]


def _summarize_result(value: Any) -> str | None:
    if value is None:
        return None
    try:
        summary = json.dumps(value, default=str, separators=(",", ":"))
    except Exception:
        summary = str(value)
    if not summary:
        return None
    return summary[:500]


def _extract_task_name(sender: Any, task: Any | None = None) -> str:
    candidate = getattr(task, "name", None) or getattr(sender, "name", None) or str(sender or "")
    return str(candidate or "")


def _should_record_task(sender: Any, task: Any | None = None) -> bool:
    task_name = _extract_task_name(sender, task)
    return bool(task_name) and not task_name.startswith("celery.")


def _extract_queue_name(request: Any) -> str | None:
    delivery_info = getattr(request, "delivery_info", None)
    if isinstance(delivery_info, Mapping):
        queue = delivery_info.get("routing_key") or delivery_info.get("queue")
        if queue:
            return str(queue)
    return None


def _get_request_retries(request: Any) -> int:
    retries = getattr(request, "retries", 0)
    try:
        return int(retries or 0)
    except (TypeError, ValueError):
        return 0


def _normalize_task_status(state: str | None) -> str:
    from app.models.task_execution import TaskExecutionStatus

    allowed = {
        TaskExecutionStatus.STARTED.value,
        TaskExecutionStatus.SUCCESS.value,
        TaskExecutionStatus.FAILURE.value,
        TaskExecutionStatus.RETRY.value,
    }
    if state in allowed:
        return str(state)
    return TaskExecutionStatus.FAILURE.value


def on_task_prerun(
    sender: Any = None,
    task_id: str | None = None,
    task: Any | None = None,
    args: Any = None,
    kwargs: Mapping[str, Any] | None = None,
    **_kw: Any,
) -> None:
    """Create or refresh the persistent execution row for a task attempt."""
    if not task_id or not _should_record_task(sender, task):
        return

    try:
        from app.repositories.factory import RepositoryFactory

        task_obj = task or sender
        request = getattr(task_obj, "request", None)
        if request is None:
            return

        started_at = _now_utc()
        request.task_execution_started_at = started_at
        request.task_execution_started_monotonic = time.monotonic()

        headers = getattr(request, "headers", None)
        header_map = headers if isinstance(headers, Mapping) else None
        kwargs_map = kwargs if isinstance(kwargs, Mapping) else None

        with get_db_session() as db:
            repo = RepositoryFactory.create_task_execution_repository(db)
            repo.record_start(
                celery_task_id=task_id,
                task_name=_extract_task_name(sender, task_obj),
                queue=_extract_queue_name(request),
                started_at=started_at,
                retries=_get_request_retries(request),
                worker=getattr(request, "hostname", None),
                trace_id=get_current_trace_id(),
                request_id=_extract_app_request_id(header_map, kwargs_map),
            )
    except Exception:
        logger.debug("Task execution recording failed during prerun", exc_info=True)


def on_task_failure(
    sender: Any = None,
    task_id: str | None = None,
    exception: BaseException | None = None,
    args: Any = None,
    kwargs: Mapping[str, Any] | None = None,
    traceback: Any = None,
    einfo: Any = None,
    **_kw: Any,
) -> None:
    """Persist failure details without interrupting the task failure flow."""
    del args, kwargs, traceback, einfo
    if not task_id or not _should_record_task(sender):
        return

    try:
        from app.models.task_execution import TaskExecutionStatus
        from app.repositories.factory import RepositoryFactory

        request = getattr(sender, "request", None)
        # task_postrun also fires for failed tasks. The later update uses the repository's
        # _UNSET sentinel so omitted error fields are preserved rather than overwritten.
        with get_db_session() as db:
            repo = RepositoryFactory.create_task_execution_repository(db)
            repo.update_on_completion(
                celery_task_id=task_id,
                status=TaskExecutionStatus.FAILURE.value,
                finished_at=_now_utc(),
                duration_ms=None,
                error_type=type(exception).__name__ if exception is not None else None,
                error_message=_truncate_text(exception, 2000),
                retries=_get_request_retries(request),
            )
    except Exception:
        logger.debug("Task execution recording failed during failure handling", exc_info=True)


def on_task_retry(
    sender: Any = None,
    request: Any | None = None,
    reason: BaseException | None = None,
    einfo: Any = None,
    **_kw: Any,
) -> None:
    """Persist retry details for the current attempt."""
    del einfo
    if request is None or not _should_record_task(sender):
        return

    try:
        from app.models.task_execution import TaskExecutionStatus
        from app.repositories.factory import RepositoryFactory

        task_id = getattr(request, "id", None)
        if not task_id:
            return

        with get_db_session() as db:
            repo = RepositoryFactory.create_task_execution_repository(db)
            repo.update_on_completion(
                celery_task_id=str(task_id),
                status=TaskExecutionStatus.RETRY.value,
                finished_at=_now_utc(),
                duration_ms=None,
                error_type=type(reason).__name__ if reason is not None else None,
                error_message=_truncate_text(reason, 2000),
                retries=_get_request_retries(request),
            )
    except Exception:
        logger.debug("Task execution recording failed during retry handling", exc_info=True)


def on_task_postrun(
    sender: Any = None,
    task_id: str | None = None,
    task: Any | None = None,
    args: Any = None,
    kwargs: Mapping[str, Any] | None = None,
    retval: Any = None,
    state: str | None = None,
    **_kw: Any,
) -> None:
    """Finalize the execution row with duration and success summary."""
    del args, kwargs
    if not task_id or not _should_record_task(sender, task):
        return

    try:
        from app.repositories.factory import RepositoryFactory

        task_obj = task or sender
        request = getattr(task_obj, "request", None)
        started_monotonic = getattr(request, "task_execution_started_monotonic", None)
        duration_ms: int | None = None
        if isinstance(started_monotonic, (int, float)):
            duration_ms = max(0, int((time.monotonic() - started_monotonic) * 1000))

        normalized_status = _normalize_task_status(state)
        update_kwargs: dict[str, Any] = {}
        if normalized_status == "SUCCESS":
            update_kwargs["result_summary"] = _summarize_result(retval)

        with get_db_session() as db:
            repo = RepositoryFactory.create_task_execution_repository(db)
            repo.update_on_completion(
                celery_task_id=task_id,
                status=normalized_status,
                finished_at=_now_utc(),
                duration_ms=duration_ms,
                retries=_get_request_retries(request),
                **update_kwargs,
            )
    except Exception:
        logger.debug("Task execution recording failed during postrun", exc_info=True)


task_prerun.connect(on_task_prerun)
task_failure.connect(on_task_failure)
task_retry.connect(on_task_retry)
task_postrun.connect(on_task_postrun)


@_connect_setup_logging
def config_loggers(*args: Any, **kwargs: Any) -> None:
    """Configure logging to integrate with the application's logging setup."""
    import logging

    # Set up basic logging configuration
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s - %(name)s - %(levelname)s - [%(request_id)s] "
            "[trace=%(otelTraceID)s span=%(otelSpanID)s] %(message)s"
        ),
    )
    attach_request_id_filter()

    # Reduce verbosity of Celery beat scheduler logs (keep task logs at INFO)
    # Beat scheduler logs "Sending due task" every time it dispatches - suppress these
    beat_logger = logging.getLogger("celery.beat")
    beat_logger.setLevel(logging.WARNING)  # Only show WARNING and above for beat scheduler


# Create the Celery app instance
celery_app = create_celery_app()

# Task modules are imported via autodiscovery in create_celery_app()
# and also via the force imports list in celery_app.conf.imports
# Ensure monitoring tasks are registered for alert processing.
from app.tasks import monitoring_tasks  # noqa: F401,E402


def _init_sentry_worker(**kwargs: Any) -> None:
    init_sentry()


def _init_sentry_beat(**kwargs: Any) -> None:
    init_sentry()


signals.celeryd_init.connect(_init_sentry_worker)
signals.beat_init.connect(_init_sentry_beat)


def _init_otel_worker(**kwargs: Any) -> None:
    service_name = os.getenv("OTEL_SERVICE_NAME", "instainstru-worker")
    if init_otel(service_name=service_name):
        instrument_additional_libraries()


def _shutdown_otel_worker(**kwargs: Any) -> None:
    shutdown_otel()


signals.worker_process_init.connect(_init_otel_worker)
signals.worker_shutdown.connect(_shutdown_otel_worker)


def _init_otel_beat(**kwargs: Any) -> None:
    service_name = os.getenv("OTEL_SERVICE_NAME", "instainstru-beat")
    if init_otel(service_name=service_name):
        instrument_additional_libraries()


signals.beat_init.connect(_init_otel_beat)
signals.beat_embedded_init.connect(_init_otel_beat)


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

    def before_start(self, task_id: str, args: Any, kwargs: Any) -> None:
        headers = getattr(self.request, "headers", None)
        request_id = _resolve_task_request_id(
            task_id,
            headers if isinstance(headers, Mapping) else None,
            kwargs if isinstance(kwargs, Mapping) else None,
        )
        token = set_request_id(request_id)
        self.request.request_id_token = token
        super().before_start(task_id, args, kwargs)

    def after_return(
        self,
        status: str,
        retval: Any,
        task_id: str,
        args: Any,
        kwargs: Any,
        einfo: Any,
    ) -> None:
        token = getattr(self.request, "request_id_token", None)
        if token is not None:
            reset_request_id(token)
            self.request.request_id_token = None
        super().after_return(status, retval, task_id, args, kwargs, einfo)

    def on_failure(self, exc: Exception, task_id: str, args: Any, kwargs: Any, einfo: Any) -> None:
        """Log task failures and clean up request context."""
        token = getattr(self.request, "request_id_token", None)
        if token is not None:
            try:
                reset_request_id(token)
            except Exception:
                import logging

                logging.getLogger(__name__).debug(
                    "Failed to reset request context after task failure",
                    exc_info=True,
                )
            self.request.request_id_token = None
        import logging

        logger = logging.getLogger(__name__)
        logger.error(
            "Task %s[%s] failed with exception: %s",
            self.name,
            task_id,
            exc,
            exc_info=True,
            extra={
                "task_id": task_id,
                "task_name": self.name,
                "task_args": str(args),  # Renamed to avoid conflict
                "task_kwargs": str(kwargs),  # Renamed to avoid conflict
            },
        )
        super_on_failure = getattr(super(), "on_failure", None)
        if super_on_failure:
            super_on_failure(exc, task_id, args, kwargs, einfo)

    def on_retry(self, exc: Exception, task_id: str, args: Any, kwargs: Any, einfo: Any) -> None:
        """Log task retries."""
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(
            "Task %s[%s] retry %s due to: %s",
            self.name,
            task_id,
            self.request.retries,
            exc,
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
            "Task %s[%s] completed successfully",
            self.name,
            task_id,
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


@typed_task(name="app.tasks.task_executions.purge_old")
def purge_old_task_executions() -> Dict[str, Any]:
    """Delete persistent task execution history past the configured retention window."""
    executed_at = _now_utc()
    retention_days = settings.task_execution_retention_days

    from app.repositories.factory import RepositoryFactory

    with get_db_session() as db:
        repo = RepositoryFactory.create_task_execution_repository(db)
        deleted_count = repo.cleanup_old(retention_days=retention_days)

    return {
        "deleted_count": deleted_count,
        "retention_days": retention_days,
        "executed_at": executed_at.isoformat(),
    }


@typed_task(name="app.tasks.availability_retention.run")
@monitor_if_configured("availability-retention-daily")
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
