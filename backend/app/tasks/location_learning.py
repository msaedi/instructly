# backend/app/tasks/location_learning.py
"""Celery tasks for self-learning location aliases."""

from __future__ import annotations

import logging
from typing import Any, Dict

from celery.app.task import Task

from app.database import get_db_session
from app.monitoring.sentry_crons import monitor_if_configured
from app.services.search.alias_learning_service import AliasLearningService
from app.tasks.celery_app import typed_task

logger = logging.getLogger(__name__)


@typed_task(
    name="app.tasks.location_learning.process_location_learning",
    bind=True,
    max_retries=0,
)
@monitor_if_configured("learn-location-aliases")
def process_location_learning(self: "Task[Any, Any]", limit: int = 500) -> Dict[str, Any]:
    """Process learnable unresolved location queries and create aliases."""
    try:
        with get_db_session() as db:
            service = AliasLearningService(db)
            learned = service.process_pending(limit=limit)
            return {
                "status": "success",
                "learned_count": len(learned),
                "learned": [l.__dict__ for l in learned],
            }
    except Exception as exc:
        logger.exception("Failed to process location learning: %s", str(exc))
        return {"status": "error", "error": str(exc)}
