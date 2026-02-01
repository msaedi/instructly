"""
Centralized task enqueue helper for guaranteed trace propagation.

IMPORTANT: Always use enqueue_task() instead of task.delay() or task.apply_async()
to ensure trace context propagates from HTTP requests to Celery tasks.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from celery import current_app

from app.core.request_context import get_request_id
from app.monitoring.otel import is_otel_enabled

logger = logging.getLogger(__name__)


def enqueue_task(
    task_name: str,
    args: Optional[Tuple[Any, ...]] = None,
    kwargs: Optional[Dict[str, Any]] = None,
    **options: Any,
) -> Any:
    """
    Enqueue a Celery task with trace context propagation.

    Args:
        task_name: Fully qualified task name (e.g., "app.tasks.payment_tasks.capture_payment")
        args: Positional arguments for the task
        kwargs: Keyword arguments for the task
        **options: Additional Celery apply_async options (countdown, eta, etc.)

    Returns:
        AsyncResult from Celery
    """
    args = args or ()
    kwargs = kwargs or {}

    # Ensure headers dict exists (Celery instrumentation requires this)
    headers = options.pop("headers", None) or {}

    if is_otel_enabled():
        try:
            from opentelemetry import propagate

            propagate.inject(headers)
        except Exception:
            # Trace propagation is best-effort - don't fail task enqueue
            # if OTel context injection fails.
            logger.warning(
                "Failed to inject OTel trace context into task headers",
                exc_info=True,
            )

    request_id = get_request_id()
    if request_id and request_id != "no-request":
        headers.setdefault("request_id", request_id)

    task = current_app.tasks[task_name]
    return task.apply_async(args=args, kwargs=kwargs, headers=headers, **options)
