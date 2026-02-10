"""Celery tasks for badge maintenance."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Callable, Dict, TypeVar, cast

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.monitoring.sentry_crons import monitor_if_configured
from app.services.badge_award_service import BadgeAwardService
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

TaskFunc = TypeVar("TaskFunc", bound=Callable[..., Dict[str, int]])


def typed_task(*task_args: Any, **task_kwargs: Any) -> Callable[[TaskFunc], TaskFunc]:
    def decorator(func: TaskFunc) -> TaskFunc:
        task = celery_app.task(*task_args, **task_kwargs)(func)
        return cast(TaskFunc, task)

    return decorator


@typed_task(name="badges.finalize_pending")
@monitor_if_configured("badges-finalize-pending")
def finalize_pending_badges_task() -> Dict[str, int]:
    """
    Re-evaluate pending badge holds and finalize them.

    Returns:
        Summary dict with confirmed/revoked counts.
    """

    now_utc = datetime.now(timezone.utc)
    db: Session = SessionLocal()
    try:
        service = BadgeAwardService(db)
        summary = service.finalize_pending_badges(now_utc)
        logger.info("Finalized pending badges", extra={"summary": summary})
        return summary
    finally:
        db.close()
