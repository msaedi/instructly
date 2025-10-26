"""Celery tasks for badge maintenance."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Dict

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.services.badge_award_service import BadgeAwardService
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="badges.finalize_pending")
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
