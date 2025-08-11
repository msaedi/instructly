# backend/app/tasks/email.py
"""
Email-related Celery tasks for InstaInstru.

This module contains all asynchronous email sending tasks including
booking confirmations, reminders, and notifications.
"""

import logging
from typing import Any, Dict, Optional

from app.core.database import get_db
from app.models.booking import Booking
from app.models.user import User
from app.services.email import EmailService
from app.tasks import BaseTask, celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    base=BaseTask,
    name="app.tasks.email.send_booking_confirmation",
    bind=True,
    max_retries=3,
)
def send_booking_confirmation(self, booking_id: int) -> Dict[str, Any]:
    """
    Send booking confirmation email to student and instructor.

    Args:
        booking_id: ID of the booking

    Returns:
        dict: Result of email sending operation
    """
    try:
        db = next(get_db())

        # Get booking with related data
        booking = db.query(Booking).filter(Booking.id == booking_id).first()
        if not booking:
            logger.error(f"Booking {booking_id} not found")
            return {"status": "error", "message": f"Booking {booking_id} not found"}

        # Initialize email service
        email_service = EmailService(db)

        # Send confirmation to student
        student_result = email_service.send_booking_confirmation_to_student(booking)

        # Send notification to instructor
        instructor_result = email_service.send_booking_notification_to_instructor(booking)

        db.close()

        return {
            "status": "success",
            "booking_id": booking_id,
            "student_email_sent": student_result,
            "instructor_email_sent": instructor_result,
        }

    except Exception as exc:
        logger.error(f"Failed to send booking confirmation for booking {booking_id}: {exc}")
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))


@celery_app.task(
    base=BaseTask,
    name="app.tasks.email.send_booking_reminder",
    bind=True,
    max_retries=2,
)
def send_booking_reminder(self, booking_id: int, hours_before: int = 24) -> Dict[str, Any]:
    """
    Send booking reminder email.

    Args:
        booking_id: ID of the booking
        hours_before: Hours before the booking to send reminder

    Returns:
        dict: Result of email sending operation
    """
    try:
        db = next(get_db())

        booking = db.query(Booking).filter(Booking.id == booking_id).first()
        if not booking:
            return {"status": "error", "message": f"Booking {booking_id} not found"}

        email_service = EmailService(db)

        # Send reminder to student
        student_result = email_service.send_booking_reminder_to_student(booking, hours_before=hours_before)

        # Send reminder to instructor
        instructor_result = email_service.send_booking_reminder_to_instructor(booking, hours_before=hours_before)

        db.close()

        return {
            "status": "success",
            "booking_id": booking_id,
            "hours_before": hours_before,
            "student_reminder_sent": student_result,
            "instructor_reminder_sent": instructor_result,
        }

    except Exception as exc:
        logger.error(f"Failed to send booking reminder for booking {booking_id}: {exc}")
        raise self.retry(exc=exc, countdown=300)  # Retry in 5 minutes


@celery_app.task(
    base=BaseTask,
    name="app.tasks.email.send_cancellation_notification",
    bind=True,
    max_retries=3,
)
def send_cancellation_notification(
    self, booking_id: int, cancelled_by_id: int, reason: Optional[str] = None
) -> Dict[str, Any]:
    """
    Send booking cancellation notification emails.

    Args:
        booking_id: ID of the cancelled booking
        cancelled_by_id: ID of user who cancelled
        reason: Cancellation reason

    Returns:
        dict: Result of email sending operation
    """
    try:
        db = next(get_db())

        booking = db.query(Booking).filter(Booking.id == booking_id).first()
        if not booking:
            return {"status": "error", "message": f"Booking {booking_id} not found"}

        cancelled_by = db.query(User).filter(User.id == cancelled_by_id).first()
        if not cancelled_by:
            return {"status": "error", "message": f"User {cancelled_by_id} not found"}

        email_service = EmailService(db)

        # Send cancellation notification
        result = email_service.send_cancellation_notification(booking=booking, cancelled_by=cancelled_by, reason=reason)

        db.close()

        return {
            "status": "success",
            "booking_id": booking_id,
            "cancelled_by_first_name": cancelled_by.first_name,
            "cancelled_by_last_name": cancelled_by.last_name,
            "notification_sent": result,
        }

    except Exception as exc:
        logger.error(f"Failed to send cancellation notification for booking {booking_id}: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))


@celery_app.task(
    base=BaseTask,
    name="app.tasks.email.send_password_reset",
    bind=True,
    max_retries=2,
)
def send_password_reset_email(self, email: str, reset_token: str) -> Dict[str, Any]:
    """
    Send password reset email.

    Args:
        email: User's email address
        reset_token: Password reset token

    Returns:
        dict: Result of email sending operation
    """
    try:
        db = next(get_db())

        user = db.query(User).filter(User.email == email).first()
        if not user:
            return {"status": "error", "message": f"User with email {email} not found"}

        email_service = EmailService(db)

        # Send password reset email
        result = email_service.send_password_reset_email(user=user, reset_token=reset_token)

        db.close()

        return {
            "status": "success",
            "email": email,
            "email_sent": result,
        }

    except Exception as exc:
        logger.error(f"Failed to send password reset email to {email}: {exc}")
        raise self.retry(exc=exc, countdown=60)
