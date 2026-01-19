# backend/app/tasks/email.py
"""
Email-related Celery tasks for InstaInstru.

This module contains asynchronous email sending tasks.

Note: Booking confirmation, reminder, and cancellation notifications are
handled by NotificationService (app/services/notification_service.py).
Password reset emails are sent directly by PasswordResetService.
"""

import logging
from typing import Any, Sequence

from sqlalchemy.orm import Session

from app.database import get_db
from app.services.beta_service import BetaService
from app.tasks.celery_app import BaseTask, typed_task

logger = logging.getLogger(__name__)


@typed_task(
    base=BaseTask,
    name="app.tasks.email.send_beta_invites_batch",
    bind=True,
    max_retries=2,
)
def send_beta_invites_batch(
    self: BaseTask,
    emails: Sequence[str],
    role: str,
    expires_in_days: int,
    source: str | None,
    base_url: str | None,
) -> dict[str, Any]:
    """
    Send beta invites to a list of emails, reporting progress.

    Returns a summary dict with counts and per-email status.
    """
    from celery import current_task

    db_iter = get_db()
    db: Session = next(db_iter)
    try:
        svc = BetaService(db)

        total = len(emails)
        sent = 0
        failed = 0
        results: dict[str, Any] = {"sent": [], "failed": []}

        for idx, em in enumerate(emails, start=1):
            try:
                invite, join_url, welcome_url = svc.send_invite_email(
                    to_email=em,
                    role=role,
                    expires_in_days=expires_in_days,
                    source=source,
                    base_url=base_url,
                )
                sent += 1
                results["sent"].append(
                    {
                        "id": invite.id,
                        "code": invite.code,
                        "email": em,
                        "join_url": join_url,
                        "welcome_url": welcome_url,
                    }
                )
            except Exception as e:
                failed += 1
                results["failed"].append({"email": em, "reason": str(e)})

            # Update task meta for progress UI
            if current_task:
                current_task.update_state(
                    state="PROGRESS",
                    meta={
                        "current": idx,
                        "total": total,
                        "sent": sent,
                        "failed": failed,
                    },
                )

        return {
            "status": "success",
            "current": total,
            "total": total,
            "sent": sent,
            "failed": failed,
            **results,
        }
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)
    finally:
        db.close()
