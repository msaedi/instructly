from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import time
from typing import Any, Mapping

from celery.signals import task_failure, task_postrun, task_prerun, task_retry

from app.database import get_db_session
from app.monitoring.otel import get_current_trace_id

logger = logging.getLogger(__name__)

_SIGNALS_REGISTERED = False


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


def register_task_execution_signals() -> None:
    global _SIGNALS_REGISTERED

    if _SIGNALS_REGISTERED:
        return

    task_prerun.connect(on_task_prerun)
    task_failure.connect(on_task_failure)
    task_retry.connect(on_task_retry)
    task_postrun.connect(on_task_postrun)
    _SIGNALS_REGISTERED = True
