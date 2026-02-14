"""
Celery tasks for payment processing.

Handles scheduled authorizations, retries, captures, and payouts.
Implements proper retry timing windows based on lesson time.
"""

import datetime as datetime_module
from datetime import date, datetime, time, timedelta, timezone
import logging
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    ParamSpec,
    Protocol,
    Sequence,
    TypedDict,
    TypeVar,
    Union,
    cast,
)

from celery.result import AsyncResult
from sqlalchemy.orm import Session
import stripe

from app.core.booking_lock import booking_lock_sync
from app.core.config import settings
from app.core.exceptions import RepositoryException, ServiceException
from app.database import get_db
from app.models.booking import Booking, BookingStatus, PaymentStatus
from app.models.payment import PaymentEvent
from app.models.user import User
from app.monitoring.sentry_crons import monitor_if_configured
from app.repositories.booking_repository import BookingRepository
from app.repositories.factory import RepositoryFactory
from app.services.booking_service import BookingService
from app.services.config_service import ConfigService
from app.services.notification_service import NotificationService
from app.services.pricing_service import PricingService
from app.services.stripe_service import StripeService
from app.services.student_credit_service import StudentCreditService
from app.services.timezone_service import TimezoneService
from app.tasks.celery_app import celery_app
from app.tasks.enqueue import enqueue_task

P = ParamSpec("P")
R = TypeVar("R", covariant=True)


class TaskWrapper(Protocol[P, R]):
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        ...

    delay: "Callable[..., AsyncResult[Any]]"
    apply_async: "Callable[..., AsyncResult[Any]]"


def typed_task(
    *task_args: Any, **task_kwargs: Any
) -> Callable[[Callable[P, R]], TaskWrapper[P, R]]:
    """Return a typed Celery task decorator for mypy."""

    return cast(
        Callable[[Callable[P, R]], TaskWrapper[P, R]],
        celery_app.task(*task_args, **task_kwargs),
    )


class AuthorizationJobResults(TypedDict):
    success: int
    failed: int
    failures: List[Dict[str, Any]]
    processed_at: str


class RetryJobResults(TypedDict):
    retried: int
    success: int
    failed: int
    cancelled: int
    warnings_sent: int
    processed_at: str


class CaptureJobResults(TypedDict):
    captured: int
    failed: int
    auto_completed: int
    expired_handled: int
    processed_at: str


class CaptureRetryResults(TypedDict):
    retried: int
    succeeded: int
    escalated: int
    skipped: int
    processed_at: str


class NoShowResolutionResults(TypedDict):
    resolved: int
    skipped: int
    failed: int
    processed_at: str


logger = logging.getLogger(__name__)

# Configure Stripe
stripe.api_key = (
    settings.stripe_secret_key.get_secret_value() if settings.stripe_secret_key else None
)
STRIPE_CURRENCY = settings.stripe_currency if hasattr(settings, "stripe_currency") else "usd"


def _resolve_lesson_timezone(booking: Booking) -> str:
    lesson_tz = getattr(booking, "lesson_timezone", None)
    if not isinstance(lesson_tz, str) or not lesson_tz:
        lesson_tz = getattr(booking, "instructor_tz_at_booking", None)
    if isinstance(lesson_tz, str) and lesson_tz:
        return lesson_tz
    instructor = getattr(booking, "instructor", None)
    if instructor is not None:
        instructor_tz = getattr(instructor, "timezone", None)
        if isinstance(instructor_tz, str) and instructor_tz:
            return instructor_tz
        instructor_user = getattr(instructor, "user", None)
        instructor_user_tz = getattr(instructor_user, "timezone", None) if instructor_user else None
        if isinstance(instructor_user_tz, str) and instructor_user_tz:
            return instructor_user_tz
    return TimezoneService.DEFAULT_TIMEZONE


def _resolve_end_date(booking: Booking) -> date:
    """Resolve end date for legacy bookings that end at midnight."""
    booking_date = cast(date, booking.booking_date)
    if not isinstance(booking.end_time, time) or not isinstance(booking.start_time, time):
        return booking_date
    midnight = time(0, 0)
    if booking.end_time == midnight and booking.start_time != midnight:
        return booking_date + timedelta(days=1)
    return booking_date


def _get_booking_start_utc(booking: Booking) -> datetime:
    """Get booking start time in UTC, with fallback for legacy bookings."""
    booking_start_utc = getattr(booking, "booking_start_utc", None)
    if isinstance(booking_start_utc, datetime_module.datetime):
        return booking_start_utc

    lesson_tz = _resolve_lesson_timezone(booking)
    try:
        return TimezoneService.local_to_utc(
            booking.booking_date,
            booking.start_time,
            lesson_tz,
        )
    except ValueError as exc:
        logger.warning(
            "Failed to convert booking %s start to UTC (%s); falling back to UTC combine.",
            booking.id,
            exc,
        )
        return datetime.combine(  # tz-pattern-ok: DST fallback for legacy bookings
            booking.booking_date,
            booking.start_time,
            tzinfo=timezone.utc,  # tz-pattern-ok: legacy fallback
        )


def _get_booking_end_utc(booking: Booking) -> datetime:
    """Get booking end time in UTC, with fallback for legacy bookings."""
    booking_end_utc = getattr(booking, "booking_end_utc", None)
    if isinstance(booking_end_utc, datetime_module.datetime):
        return booking_end_utc

    lesson_tz = _resolve_lesson_timezone(booking)
    end_date = _resolve_end_date(booking)
    try:
        return TimezoneService.local_to_utc(
            end_date,
            booking.end_time,
            lesson_tz,
        )
    except ValueError as exc:
        logger.warning(
            "Failed to convert booking %s end to UTC (%s); falling back to UTC combine.",
            booking.id,
            exc,
        )
        return datetime.combine(  # tz-pattern-ok: DST fallback for legacy bookings
            end_date, booking.end_time, tzinfo=timezone.utc  # tz-pattern-ok: legacy fallback
        )


def _process_authorization_for_booking(
    booking_id: str,
    hours_until_lesson: float,
) -> Dict[str, Any]:
    """
    Process payment authorization for a single booking using 3-phase pattern.

    Phase 1: Quick transaction to read booking and customer data
    Phase 2: Stripe authorization call (no transaction)
    Phase 3: Quick transaction to update booking status

    Returns:
        Dict with success status and details
    """
    from app.database import SessionLocal
    from app.repositories.instructor_profile_repository import InstructorProfileRepository

    # ========== PHASE 1: Read booking and validate (quick transaction) ==========
    db1: Session = SessionLocal()
    phase1_error: str | None = None
    payment_method_id: str | None = None
    existing_payment_intent_id: str | None = None
    try:
        booking = BookingRepository(db1).get_by_id(booking_id)
        if not booking:
            # Can't continue without booking
            return {"success": False, "error": "Booking not found"}

        if booking.status == BookingStatus.CANCELLED:
            db1.commit()
            return {"success": False, "skipped": True, "reason": "cancelled"}

        pd = booking.payment_detail
        if booking.status not in {BookingStatus.CONFIRMED, BookingStatus.PENDING} or (
            (getattr(pd, "payment_status", None)) not in [PaymentStatus.SCHEDULED.value]
        ):
            db1.commit()
            return {"success": False, "skipped": True, "reason": "not_eligible"}

        payment_repo = RepositoryFactory.get_payment_repository(db1)
        _pd_intent = getattr(pd, "payment_intent_id", None)
        existing_payment_intent_id = (
            _pd_intent if isinstance(_pd_intent, str) and _pd_intent.startswith("pi_") else None
        )

        # Get student's Stripe customer
        student_customer = payment_repo.get_customer_by_user_id(booking.student_id)
        if not student_customer:
            phase1_error = f"No Stripe customer for student {booking.student_id}"
        else:
            # Get instructor's Stripe account
            instructor_repo = InstructorProfileRepository(db1)
            instructor_profile = instructor_repo.get_by_user_id(booking.instructor_id)
            if instructor_profile is None:
                phase1_error = f"No instructor profile for {booking.instructor_id}"
            else:
                instructor_account = payment_repo.get_connected_account_by_instructor_id(
                    instructor_profile.id
                )
                if not instructor_account or not instructor_account.stripe_account_id:
                    phase1_error = f"No Stripe account for instructor {booking.instructor_id}"
                else:
                    # Extract data needed for Stripe call
                    payment_method_id = getattr(pd, "payment_method_id", None)

        db1.commit()  # Release lock immediately
    finally:
        db1.close()

    # If Phase 1 failed, skip to Phase 3 to record failure
    if phase1_error:
        stripe_result: Dict[str, Any] = {
            "success": False,
            "error": phase1_error,
            "error_type": "validation_error",
        }
        # Skip to Phase 3 to update booking status
    else:
        # ========== PHASE 2: Stripe authorization (NO transaction) ==========
        stripe_result = {"success": False}
        try:
            db_stripe: Session = SessionLocal()
            try:
                config_service = ConfigService(db_stripe)
                pricing_service = PricingService(db_stripe)
                stripe_service = StripeService(
                    db_stripe,
                    config_service=config_service,
                    pricing_service=pricing_service,
                )

                ctx = stripe_service.build_charge_context(
                    booking_id=booking_id, requested_credit_cents=None
                )

                if ctx.student_pay_cents <= 0:
                    stripe_result = {
                        "success": True,
                        "credits_only": True,
                        "base_price_cents": ctx.base_price_cents,
                        "applied_credit_cents": ctx.applied_credit_cents,
                    }
                else:
                    if not payment_method_id:
                        raise ServiceException("Payment method required for authorization")

                    if existing_payment_intent_id:
                        payment_record = stripe_service.confirm_payment_intent(
                            existing_payment_intent_id,
                            payment_method_id,
                        )
                        payment_status = getattr(payment_record, "status", None)
                        if payment_status not in {"requires_capture", "succeeded"}:
                            raise ServiceException(
                                f"Unexpected PaymentIntent status: {payment_status}"
                            )
                        stripe_result = {
                            "success": True,
                            "payment_intent_id": existing_payment_intent_id,
                            "student_pay_cents": ctx.student_pay_cents,
                            "application_fee_cents": ctx.application_fee_cents,
                            "applied_credit_cents": ctx.applied_credit_cents,
                        }
                    else:
                        # Make Stripe authorization call
                        payment_intent = stripe_service.create_or_retry_booking_payment_intent(
                            booking_id=booking_id,
                            payment_method_id=payment_method_id,
                            requested_credit_cents=None,
                        )

                        stripe_result = {
                            "success": True,
                            "payment_intent_id": getattr(payment_intent, "id", None),
                            "student_pay_cents": ctx.student_pay_cents,
                            "application_fee_cents": ctx.application_fee_cents,
                            "applied_credit_cents": ctx.applied_credit_cents,
                        }

                db_stripe.commit()
            finally:
                db_stripe.close()

        except Exception as e:
            error_message = str(e)
            error_type = (
                "card_declined"
                if "card" in error_message.lower() or "declined" in error_message.lower()
                else "system_error"
            )
            stripe_result = {
                "success": False,
                "error": error_message,
                "error_type": error_type,
            }

    # ========== PHASE 3: Write results (quick transaction) ==========
    db3: Session = SessionLocal()
    send_confirmation_notifications = False
    send_payment_failed_notification = False
    try:
        repo3 = BookingRepository(db3)
        booking = repo3.get_by_id(booking_id)
        if not booking:
            return {"success": False, "error": "Booking not found in Phase 3"}

        payment_repo = RepositoryFactory.get_payment_repository(db3)
        booking_payment = repo3.ensure_payment(booking.id)
        previous_capture_retry_count = int(getattr(booking_payment, "capture_retry_count", 0) or 0)

        def _notify_payment_failed_once() -> None:
            if previous_capture_retry_count > 0:
                return
            try:
                notification_service = NotificationService(db3)
                notification_service.send_payment_failed_notification(booking)
            except Exception as exc:
                logger.warning(
                    "Failed to send payment failed notification for booking %s: %s",
                    booking_id,
                    exc,
                )

        attempted_at = datetime.now(timezone.utc)

        if stripe_result.get("success"):
            if stripe_result.get("credits_only"):
                booking_payment.payment_status = PaymentStatus.AUTHORIZED.value
                booking_payment.auth_attempted_at = attempted_at
                booking_payment.auth_failure_count = 0
                booking_payment.auth_last_error = None
                if booking.status == BookingStatus.PENDING:
                    booking.status = BookingStatus.CONFIRMED
                    booking.confirmed_at = attempted_at
                    send_confirmation_notifications = True
                payment_repo.create_payment_event(
                    booking_id=booking_id,
                    event_type="auth_succeeded_credits_only",
                    event_data={
                        "base_price_cents": stripe_result.get("base_price_cents"),
                        "credits_applied_cents": stripe_result.get("applied_credit_cents"),
                    },
                )
                logger.info(
                    f"Booking {booking_id} fully covered by credits; no authorization needed"
                )
            else:
                booking_payment.payment_intent_id = stripe_result.get("payment_intent_id")
                booking_payment.payment_status = PaymentStatus.AUTHORIZED.value
                booking_payment.auth_attempted_at = attempted_at
                booking_payment.auth_failure_count = 0
                booking_payment.auth_last_error = None
                if booking.status == BookingStatus.PENDING:
                    booking.status = BookingStatus.CONFIRMED
                    booking.confirmed_at = attempted_at
                    send_confirmation_notifications = True

                # Record metrics
                if stripe_result.get("applied_credit_cents"):
                    try:
                        from app.monitoring.prometheus_metrics import prometheus_metrics

                        prometheus_metrics.inc_credits_applied("authorization")
                    except Exception:
                        logger.debug("Non-fatal error ignored", exc_info=True)
                payment_repo.create_payment_event(
                    booking_id=booking_id,
                    event_type="auth_succeeded",
                    event_data={
                        "payment_intent_id": stripe_result.get("payment_intent_id"),
                        "amount_cents": stripe_result.get("student_pay_cents"),
                        "application_fee_cents": stripe_result.get("application_fee_cents"),
                        "authorized_at": datetime.now(timezone.utc).isoformat(),
                        "hours_before_lesson": round(hours_until_lesson, 1),
                        "credits_applied_cents": stripe_result.get("applied_credit_cents"),
                    },
                )
                # TODO: Notify student on authorization success (Issue #10).
                logger.info(f"Successfully authorized payment for booking {booking_id}")
        else:
            # Record failure
            booking_payment.payment_status = PaymentStatus.PAYMENT_METHOD_REQUIRED.value
            booking_payment.auth_attempted_at = attempted_at
            booking_payment.auth_failure_count = (
                int(getattr(booking_payment, "auth_failure_count", 0) or 0) + 1
            )
            booking_payment.auth_last_error = stripe_result.get("error")
            payment_repo.create_payment_event(
                booking_id=booking_id,
                event_type="auth_failed",
                event_data={
                    "error": stripe_result.get("error"),
                    "error_type": stripe_result.get("error_type"),
                    "hours_until_lesson": round(hours_until_lesson, 1),
                    "failed_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            logger.error(
                f"Failed to authorize payment for booking {booking_id}: {stripe_result.get('error')}"
            )
            send_payment_failed_notification = True

        db3.commit()  # Commit and release lock immediately

        if send_confirmation_notifications:
            try:
                from app.services.booking_service import BookingService

                BookingService(db3).send_booking_notifications_after_confirmation(booking_id)
            except Exception as exc:
                logger.warning(
                    "Failed to send booking confirmation notifications for %s: %s",
                    booking_id,
                    exc,
                )
        if send_payment_failed_notification:
            _notify_payment_failed_once()
    finally:
        db3.close()

    if not stripe_result.get("success") and hours_until_lesson < 24:
        try:
            enqueue_task(
                "app.tasks.payment_tasks.check_immediate_auth_timeout",
                args=(booking_id,),
                countdown=30 * 60,
            )
        except Exception:
            logger.debug("Non-fatal error ignored", exc_info=True)
    return stripe_result


@typed_task(
    bind=True, max_retries=3, name="app.tasks.payment_tasks.process_scheduled_authorizations"
)
@monitor_if_configured("process-scheduled-authorizations")
def process_scheduled_authorizations(self: Any) -> AuthorizationJobResults:
    """
    Process scheduled payment authorizations.

    Runs every 30 minutes to authorize payments for bookings
    that are approaching their 24-hour pre-authorization window.

    Uses 3-phase pattern to minimize lock contention:
    - Phase 1: Quick read (release lock immediately)
    - Phase 2: Stripe call (no lock held)
    - Phase 3: Quick write (release lock immediately)

    Returns:
        Dict with success/failure counts and details
    """
    from app.database import SessionLocal

    now = datetime.now(timezone.utc)
    failures: List[Dict[str, Any]] = []
    results: AuthorizationJobResults = {
        "success": 0,
        "failed": 0,
        "failures": failures,
        "processed_at": now.isoformat(),
    }

    # ========== Collect booking IDs to process (quick read) ==========
    db_read: Session = SessionLocal()
    try:
        booking_repo = RepositoryFactory.get_booking_repository(db_read)

        bookings_to_authorize = cast(
            Sequence[Booking],
            booking_repo.get_bookings_for_payment_authorization(),
        )

        # Collect booking IDs and hours_until_lesson for each
        booking_data: List[Dict[str, Any]] = []
        for booking in bookings_to_authorize:
            booking_start_utc = _get_booking_start_utc(booking)
            hours_until_lesson = TimezoneService.hours_until(booking_start_utc)

            due_for_auth = False
            pd = booking.payment_detail
            if getattr(pd, "payment_status", None) == PaymentStatus.SCHEDULED.value:
                scheduled_for = getattr(pd, "auth_scheduled_for", None)
                if isinstance(scheduled_for, datetime):
                    due_for_auth = scheduled_for <= now
                else:
                    # Legacy path: process if in the 23.5-24.5 hour window
                    due_for_auth = 23.5 <= hours_until_lesson <= 24.5

            if due_for_auth:
                booking_data.append(
                    {
                        "booking_id": booking.id,
                        "hours_until_lesson": hours_until_lesson,
                        "student_id": booking.student_id,
                    }
                )

        db_read.commit()  # Release locks from read phase
    finally:
        db_read.close()

    # ========== Process each booking with 3-phase pattern ==========
    for data in booking_data:
        booking_id = data["booking_id"]
        hours_until_lesson = data["hours_until_lesson"]

        try:
            with booking_lock_sync(booking_id) as acquired:
                if not acquired:
                    continue
                auth_result = _process_authorization_for_booking(booking_id, hours_until_lesson)

            if auth_result.get("skipped"):
                continue

            if auth_result.get("success"):
                results["success"] += 1
            else:
                results["failed"] += 1
                results["failures"].append(
                    {
                        "booking_id": booking_id,
                        "error": auth_result.get("error", "Unknown error"),
                        "type": auth_result.get("error_type", "system_error"),
                    }
                )

                # Send T-24 first failure email
                try:
                    db_notify: Session = SessionLocal()
                    try:
                        payment_repo = RepositoryFactory.get_payment_repository(db_notify)
                        if not has_event_type(
                            payment_repo, booking_id, "t24_first_failure_email_sent"
                        ):
                            notification_service = NotificationService(db_notify)
                            repo_notify = BookingRepository(db_notify)
                            booking_notify: Booking | None = repo_notify.get_by_id(booking_id)
                            if booking_notify:
                                bp_notify = repo_notify.ensure_payment(booking_notify.id)
                                if bp_notify.auth_failure_first_email_sent_at is not None:
                                    db_notify.commit()
                                    continue
                                notification_service.send_final_payment_warning(
                                    booking_notify, hours_until_lesson
                                )
                                bp_notify.auth_failure_first_email_sent_at = datetime.now(
                                    timezone.utc
                                )
                                payment_repo.create_payment_event(
                                    booking_id=booking_id,
                                    event_type="t24_first_failure_email_sent",
                                    event_data={
                                        "hours_until_lesson": round(hours_until_lesson, 1),
                                        "error": auth_result.get("error"),
                                    },
                                )
                        db_notify.commit()
                    finally:
                        db_notify.close()
                except Exception as mail_err:
                    logger.error(
                        f"Failed to send T-24 failure email for booking {booking_id}: {mail_err}"
                    )

        except Exception as e:
            logger.error(f"Error processing authorization for booking {booking_id}: {e}")
            results["failed"] += 1
            results["failures"].append(
                {
                    "booking_id": booking_id,
                    "error": str(e),
                    "type": "system_error",
                }
            )

    # Log results
    if results["failed"] > 0:
        logger.warning(f"Authorization job completed with {results['failed']} failures")

    logger.info(
        f"Authorization job completed: {results['success']} success, {results['failed']} failed"
    )
    return results


def _cancel_booking_payment_failed(
    booking_id: str, hours_until_lesson: float, now: datetime
) -> bool:
    """
    Cancel a booking due to payment failure using 3-phase pattern.

    Returns:
        True if cancelled successfully
    """
    from app.database import SessionLocal

    db: Session = SessionLocal()
    try:
        repo = BookingRepository(db)
        booking = repo.get_by_id(booking_id)
        if not booking:
            return False

        if booking.status == BookingStatus.CANCELLED:
            return False

        booking.status = BookingStatus.CANCELLED
        booking.student_credit_amount = 0
        booking.refunded_to_card_amount = 0
        booking.cancelled_at = now
        booking.cancellation_reason = "Payment authorization failed after multiple attempts"

        bp_cancel = repo.ensure_payment(booking.id)
        bp_cancel.payment_status = PaymentStatus.SETTLED.value
        bp_cancel.settlement_outcome = "student_cancel_gt24_no_charge"
        bp_cancel.instructor_payout_amount = 0

        payment_repo = RepositoryFactory.get_payment_repository(db)
        try:
            from app.services.credit_service import CreditService

            credit_service = CreditService(db)
            credit_service.release_credits_for_booking(booking_id=booking_id, use_transaction=False)
            bp_cancel.credits_reserved_cents = 0
        except Exception as exc:
            logger.warning(
                "Failed to release reserved credits for booking %s: %s",
                booking_id,
                exc,
            )
        payment_repo.create_payment_event(
            booking_id=booking_id,
            event_type="auth_abandoned",
            event_data={
                "reason": "T-12hr cancellation",
                "hours_until_lesson": round(hours_until_lesson, 1),
                "cancelled_at": now.isoformat(),
            },
        )

        # Send cancellation notification
        notification_service = NotificationService(db)
        notification_service.send_booking_cancelled_payment_failed(booking)

        db.commit()
        logger.info(
            f"Cancelled booking {booking_id} due to payment failure (T-{hours_until_lesson:.1f}hr)"
        )
        return True
    except Exception as e:
        logger.error(f"Error cancelling booking {booking_id}: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def _process_retry_authorization(booking_id: str, hours_until_lesson: float) -> Dict[str, Any]:
    """
    Process authorization retry for a single booking using 3-phase pattern.

    Returns:
        Dict with success status
    """
    from app.database import SessionLocal
    from app.repositories.instructor_profile_repository import InstructorProfileRepository

    # ========== PHASE 1: Read booking data (quick transaction) ==========
    db1: Session = SessionLocal()
    try:
        booking = BookingRepository(db1).get_by_id(booking_id)
        if not booking:
            return {"success": False, "error": "Booking not found"}

        if booking.status == BookingStatus.CANCELLED:
            db1.commit()
            return {"success": False, "skipped": True, "reason": "cancelled"}

        pd = booking.payment_detail
        if booking.status != BookingStatus.CONFIRMED or getattr(pd, "payment_status", None) not in [
            PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
        ]:
            db1.commit()
            return {"success": False, "skipped": True, "reason": "not_eligible"}

        payment_repo = RepositoryFactory.get_payment_repository(db1)

        # Record retry attempt
        payment_repo.create_payment_event(
            booking_id=booking_id,
            event_type="auth_retry_attempted",
            event_data={
                "hours_until_lesson": round(hours_until_lesson, 1),
                "attempted_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        # Get student's Stripe customer
        student_customer = payment_repo.get_customer_by_user_id(booking.student_id)
        if not student_customer:
            return {
                "success": False,
                "error": f"No Stripe customer for student {booking.student_id}",
            }

        # Get instructor's Stripe account
        instructor_repo = InstructorProfileRepository(db1)
        instructor_profile = instructor_repo.get_by_user_id(booking.instructor_id)
        if instructor_profile is None:
            return {"success": False, "error": f"No instructor profile for {booking.instructor_id}"}

        instructor_account = payment_repo.get_connected_account_by_instructor_id(
            instructor_profile.id
        )
        if not instructor_account:
            return {
                "success": False,
                "error": f"No Stripe account for instructor {booking.instructor_id}",
            }

        # Extract data needed for Stripe call
        payment_method_id = getattr(pd, "payment_method_id", None)

        db1.commit()  # Release lock immediately
    finally:
        db1.close()

    # ========== PHASE 2: Stripe retry (NO transaction) ==========
    stripe_result: Dict[str, Any] = {"success": False}
    try:
        db_stripe: Session = SessionLocal()
        try:
            config_service = ConfigService(db_stripe)
            pricing_service = PricingService(db_stripe)
            stripe_service = StripeService(
                db_stripe,
                config_service=config_service,
                pricing_service=pricing_service,
            )

            ctx = stripe_service.build_charge_context(
                booking_id=booking_id, requested_credit_cents=None
            )

            if ctx.student_pay_cents <= 0:
                stripe_result = {
                    "success": True,
                    "credits_only": True,
                    "applied_credit_cents": ctx.applied_credit_cents,
                }
            else:
                payment_intent = stripe_service.create_or_retry_booking_payment_intent(
                    booking_id=booking_id,
                    payment_method_id=payment_method_id,
                    requested_credit_cents=None,
                )
                stripe_result = {
                    "success": True,
                    "payment_intent_id": getattr(payment_intent, "id", None),
                    "student_pay_cents": ctx.student_pay_cents,
                    "application_fee_cents": ctx.application_fee_cents,
                    "applied_credit_cents": ctx.applied_credit_cents,
                }

            db_stripe.commit()
        finally:
            db_stripe.close()

    except Exception as e:
        stripe_result = {"success": False, "error": str(e)}

    # ========== PHASE 3: Write results (quick transaction) ==========
    db3: Session = SessionLocal()
    try:
        repo3 = BookingRepository(db3)
        booking = repo3.get_by_id(booking_id)
        if not booking:
            return {"success": False, "error": "Booking not found in Phase 3"}

        payment_repo = RepositoryFactory.get_payment_repository(db3)
        bp_retry = repo3.ensure_payment(booking.id)

        attempted_at = datetime.now(timezone.utc)

        if stripe_result.get("success"):
            bp_retry.payment_intent_id = (
                stripe_result.get("payment_intent_id") or bp_retry.payment_intent_id
            )
            bp_retry.payment_status = PaymentStatus.AUTHORIZED.value
            bp_retry.auth_attempted_at = attempted_at
            bp_retry.auth_failure_count = 0
            bp_retry.auth_last_error = None

            payment_repo.create_payment_event(
                booking_id=booking_id,
                event_type="auth_retry_succeeded",
                event_data={
                    "payment_intent_id": stripe_result.get("payment_intent_id"),
                    "hours_until_lesson": round(hours_until_lesson, 1),
                    "authorized_at": datetime.now(timezone.utc).isoformat(),
                    "credits_applied_cents": stripe_result.get("applied_credit_cents"),
                    "amount_cents": stripe_result.get("student_pay_cents"),
                    "application_fee_cents": stripe_result.get("application_fee_cents"),
                },
            )
            logger.info(
                f"Successfully retried authorization for booking {booking_id} (T-{hours_until_lesson:.1f}hr)"
            )
        else:
            bp_retry.payment_status = PaymentStatus.PAYMENT_METHOD_REQUIRED.value
            bp_retry.auth_attempted_at = attempted_at
            bp_retry.auth_failure_count = int(getattr(bp_retry, "auth_failure_count", 0) or 0) + 1
            bp_retry.auth_last_error = stripe_result.get("error")
            payment_repo.create_payment_event(
                booking_id=booking_id,
                event_type="auth_retry_failed",
                event_data={
                    "error": stripe_result.get("error"),
                    "hours_until_lesson": round(hours_until_lesson, 1),
                    "failed_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            logger.error(f"Retry failed for booking {booking_id}: {stripe_result.get('error')}")

        db3.commit()  # Commit and release lock immediately
    finally:
        db3.close()

    return stripe_result


@typed_task(bind=True, max_retries=5, name="app.tasks.payment_tasks.retry_failed_authorizations")
@monitor_if_configured("retry-failed-authorizations")
def retry_failed_authorizations(self: Any) -> RetryJobResults:
    """
    Retry failed payment authorizations based on time since last attempt.

    Retry schedule:
    - After first failure: wait 1 hour
    - After second failure: wait 4 hours
    - After third+ failures: wait 8 hours
    - T-13hr: Final warning email (and retry if eligible)
    - T-12hr: Cancel booking if still failing

    Uses 3-phase pattern to minimize lock contention:
    - Phase 1: Quick read (release lock immediately)
    - Phase 2: Stripe call (no lock held)
    - Phase 3: Quick write (release lock immediately)

    Returns:
        Dict with retry results
    """
    from app.database import SessionLocal

    now = datetime.now(timezone.utc)
    results: RetryJobResults = {
        "retried": 0,
        "success": 0,
        "failed": 0,
        "cancelled": 0,
        "warnings_sent": 0,
        "processed_at": now.isoformat(),
    }

    # ========== Collect booking data to process (quick read) ==========
    db_read: Session = SessionLocal()
    try:
        booking_repo = RepositoryFactory.get_booking_repository(db_read)
        payment_repo = RepositoryFactory.get_payment_repository(db_read)

        bookings_to_retry = cast(
            Sequence[Booking],
            booking_repo.get_bookings_for_payment_retry(),
        )

        # Collect booking data with their action type
        booking_actions: List[Dict[str, Any]] = []
        for booking in bookings_to_retry:
            booking_start_utc = _get_booking_start_utc(booking)
            hours_until_lesson = TimezoneService.hours_until(booking_start_utc)

            # Skip if lesson already happened
            if hours_until_lesson < 0:
                continue

            if hours_until_lesson <= 12:
                booking_actions.append(
                    {
                        "booking_id": booking.id,
                        "hours_until_lesson": hours_until_lesson,
                        "action": "cancel",
                    }
                )
                continue

            should_retry = _should_retry_auth(booking, now)

            if hours_until_lesson <= 13:
                has_warning = has_event_type(payment_repo, booking.id, "final_warning_sent")
                if not has_warning:
                    booking_actions.append(
                        {
                            "booking_id": booking.id,
                            "hours_until_lesson": hours_until_lesson,
                            "action": "warn_only",
                            "needs_warning": True,
                        }
                    )

                if should_retry:
                    booking_actions.append(
                        {
                            "booking_id": booking.id,
                            "hours_until_lesson": hours_until_lesson,
                            "action": "retry_with_warning",
                            "needs_warning": False,
                        }
                    )
                continue

            if should_retry:
                booking_actions.append(
                    {
                        "booking_id": booking.id,
                        "hours_until_lesson": hours_until_lesson,
                        "action": "silent_retry",
                    }
                )

        db_read.commit()  # Release locks from read phase
    finally:
        db_read.close()

    # ========== Process each booking with 3-phase pattern ==========
    for action_data in booking_actions:
        booking_id = action_data["booking_id"]
        hours_until_lesson = action_data["hours_until_lesson"]
        action = action_data["action"]

        try:
            with booking_lock_sync(booking_id) as acquired:
                if not acquired:
                    continue

                if action == "cancel":
                    if _cancel_booking_payment_failed(booking_id, hours_until_lesson, now):
                        results["cancelled"] += 1

                elif action == "warn_only":
                    db_warn_retry: Session = SessionLocal()
                    try:
                        repo_warn = BookingRepository(db_warn_retry)
                        booking_warn: Booking | None = repo_warn.get_by_id(booking_id)
                        pd_warn = booking_warn.payment_detail if booking_warn else None
                        if (
                            booking_warn
                            and booking_warn.status == BookingStatus.CONFIRMED
                            and getattr(pd_warn, "payment_status", None)
                            == PaymentStatus.PAYMENT_METHOD_REQUIRED.value
                            and getattr(pd_warn, "capture_failed_at", None) is None
                        ):
                            bp_warn = repo_warn.ensure_payment(booking_warn.id)
                            if bp_warn.auth_failure_t13_warning_sent_at is not None:
                                db_warn_retry.commit()
                                continue
                            notification_service = NotificationService(db_warn_retry)
                            notification_service.send_final_payment_warning(
                                booking_warn, hours_until_lesson
                            )
                            bp_warn.auth_failure_t13_warning_sent_at = now

                            payment_repo = RepositoryFactory.get_payment_repository(db_warn_retry)
                            payment_repo.create_payment_event(
                                booking_id=booking_id,
                                event_type="final_warning_sent",
                                event_data={
                                    "hours_until_lesson": round(hours_until_lesson, 1),
                                    "sent_at": now.isoformat(),
                                },
                            )
                            results["warnings_sent"] += 1
                        db_warn_retry.commit()
                    finally:
                        db_warn_retry.close()

                elif action == "retry_with_warning":
                    # Retry authorization (warning is handled by a separate warn_only action)
                    retry_result = _process_retry_authorization(booking_id, hours_until_lesson)
                    if retry_result.get("skipped"):
                        continue
                    if retry_result.get("success"):
                        results["success"] += 1
                    else:
                        results["failed"] += 1
                    results["retried"] += 1

                elif action == "silent_retry":
                    retry_result = _process_retry_authorization(booking_id, hours_until_lesson)
                    if retry_result.get("skipped"):
                        continue
                    if retry_result.get("success"):
                        results["success"] += 1
                    else:
                        results["failed"] += 1
                    results["retried"] += 1

        except Exception as e:
            logger.error(f"Error processing retry for booking {booking_id}: {e}")
            results["failed"] += 1

    logger.info(
        f"Retry job completed: {results['retried']} attempted, "
        f"{results['success']} success, {results['failed']} failed, "
        f"{results['cancelled']} cancelled, {results['warnings_sent']} warnings sent"
    )
    return results


@typed_task(name="app.tasks.payment_tasks.check_immediate_auth_timeout")
def check_immediate_auth_timeout(booking_id: str) -> Dict[str, Any]:
    """
    Auto-cancel immediate auth failures after 30 minutes.
    """
    from app.database import SessionLocal

    db: Session = SessionLocal()
    now = datetime.now(timezone.utc)
    try:
        with booking_lock_sync(booking_id) as acquired:
            if not acquired:
                return {"skipped": True}

            booking = BookingRepository(db).get_by_id(booking_id)
            if not booking:
                return {"error": "Booking not found"}

            if booking.status == BookingStatus.CANCELLED:
                return {"skipped": True, "reason": "cancelled"}

            pd_timeout = booking.payment_detail
            if (
                getattr(pd_timeout, "payment_status", None)
                != PaymentStatus.PAYMENT_METHOD_REQUIRED.value
            ):
                return {"resolved": True}

            attempted_at = getattr(pd_timeout, "auth_attempted_at", None)
            if isinstance(attempted_at, datetime):
                if (now - attempted_at).total_seconds() < 30 * 60:
                    return {"skipped": True, "reason": "retry_window_open"}

            hours_until_lesson = TimezoneService.hours_until(_get_booking_start_utc(booking))
            cancelled = _cancel_booking_payment_failed(booking_id, hours_until_lesson, now)
            return {"cancelled": cancelled}
    finally:
        db.close()


@typed_task(bind=True, max_retries=3, name="app.tasks.payment_tasks.retry_failed_captures")
@monitor_if_configured("retry-failed-captures")
def retry_failed_captures(self: Any) -> CaptureRetryResults:
    """
    Retry failed captures every 4 hours and escalate after 72 hours.
    """
    from app.database import SessionLocal

    now = datetime.now(timezone.utc)
    results: CaptureRetryResults = {
        "retried": 0,
        "succeeded": 0,
        "escalated": 0,
        "skipped": 0,
        "processed_at": now.isoformat(),
    }

    db_read: Session = SessionLocal()
    try:
        booking_ids = BookingRepository(db_read).get_failed_capture_booking_ids()
    finally:
        db_read.close()

    for booking_id in booking_ids:
        try:
            with booking_lock_sync(booking_id) as acquired:
                if not acquired:
                    results["skipped"] += 1
                    continue

                db_check: Session = SessionLocal()
                try:
                    booking = BookingRepository(db_check).get_by_id(booking_id)
                    if not booking:
                        results["skipped"] += 1
                        continue

                    pd_check = booking.payment_detail
                    if (
                        getattr(pd_check, "payment_status", None)
                        != PaymentStatus.PAYMENT_METHOD_REQUIRED.value
                        or getattr(pd_check, "capture_failed_at", None) is None
                    ):
                        results["skipped"] += 1
                        continue

                    hours_since_failure = (
                        now - cast(datetime, pd_check.capture_failed_at)
                    ).total_seconds() / 3600

                    if hours_since_failure >= 72:
                        _escalate_capture_failure(booking_id, now)
                        results["escalated"] += 1
                        continue

                    if not _should_retry_capture(booking, now):
                        results["skipped"] += 1
                        continue
                finally:
                    db_check.close()

                retry_result = _process_capture_for_booking(booking_id, "retry_failed_capture")
                if retry_result.get("skipped"):
                    results["skipped"] += 1
                    continue

                results["retried"] += 1
                if retry_result.get("success") or retry_result.get("already_captured"):
                    results["succeeded"] += 1

        except Exception as exc:
            logger.error(f"Capture retry failed for booking {booking_id}: {exc}")

    return results


def _escalate_capture_failure(booking_id: str, now: datetime) -> None:
    """Escalate capture failure after retry window expires."""
    from app.database import SessionLocal

    instructor_account_id: Optional[str] = None
    payout_cents: Optional[int] = None

    # Phase 1: Read booking + resolve payout/account ids.
    db_read: Session = SessionLocal()
    try:
        booking = BookingRepository(db_read).get_by_id(booking_id)
        if not booking:
            return

        payment_repo = RepositoryFactory.get_payment_repository(db_read)
        instructor_repo = RepositoryFactory.create_instructor_profile_repository(db_read)

        try:
            payment_record = payment_repo.get_payment_by_booking_id(booking.id)
        except RepositoryException:
            logger.warning(
                "Failed to load payment record for booking %s during escalation",
                booking.id,
                exc_info=True,
            )
            payment_record = None

        payout_value = (
            getattr(payment_record, "instructor_payout_cents", None) if payment_record else None
        )
        if payout_value is not None:
            try:
                payout_cents = int(payout_value)
            except (TypeError, ValueError):
                payout_cents = None

        if payout_cents is None:
            pricing_service = PricingService(db_read)
            pricing = pricing_service.compute_booking_pricing(
                booking_id=booking.id, applied_credit_cents=0, persist=False
            )
            payout_cents = int(pricing.get("target_instructor_payout_cents", 0) or 0)

        instructor_profile = instructor_repo.get_by_user_id(booking.instructor_id)
        if instructor_profile:
            account = payment_repo.get_connected_account_by_instructor_id(instructor_profile.id)
            if account and account.stripe_account_id:
                instructor_account_id = account.stripe_account_id
    finally:
        db_read.close()

    transfer_id: Optional[str] = None
    transfer_error: Optional[str] = None

    if instructor_account_id and payout_cents:
        db_stripe: Session = SessionLocal()
        try:
            stripe_service = StripeService(
                db_stripe,
                config_service=ConfigService(db_stripe),
                pricing_service=PricingService(db_stripe),
            )
            transfer_result = stripe_service.create_manual_transfer(
                booking_id=booking_id,
                destination_account_id=instructor_account_id,
                amount_cents=int(payout_cents),
                idempotency_key=f"capture_failure_payout_{booking_id}",
                metadata={"reason": "capture_failure_escalated"},
            )
            transfer_id = transfer_result.get("transfer_id")
            db_stripe.commit()
        except Exception as exc:
            transfer_error = str(exc)
        finally:
            db_stripe.close()

    # Phase 3: Persist escalation + account lock.
    db_write: Session = SessionLocal()
    try:
        booking_repo = BookingRepository(db_write)
        booking = booking_repo.get_by_id(booking_id)
        if not booking:
            return
        bp_escalate = booking_repo.ensure_payment(booking.id)

        bp_escalate.payment_status = PaymentStatus.MANUAL_REVIEW.value
        bp_escalate.settlement_outcome = (
            "capture_failure_instructor_paid" if transfer_id else "capture_failure_escalated"
        )
        bp_escalate.capture_escalated_at = now
        bp_escalate.instructor_payout_amount = int(payout_cents or 0) if transfer_id else 0
        booking.student_credit_amount = 0
        booking.refunded_to_card_amount = 0
        transfer_record = booking_repo.ensure_transfer(booking.id)
        if transfer_id:
            transfer_record.advanced_payout_transfer_id = transfer_id
            transfer_record.payout_transfer_id = transfer_id
            transfer_record.stripe_transfer_id = transfer_id
        else:
            transfer_record.payout_transfer_failed_at = now
            transfer_record.payout_transfer_error = transfer_error
            transfer_record.payout_transfer_retry_count = (
                int(getattr(transfer_record, "payout_transfer_retry_count", 0) or 0) + 1
            )
            transfer_record.transfer_failed_at = transfer_record.payout_transfer_failed_at
            transfer_record.transfer_error = transfer_record.payout_transfer_error
            transfer_record.transfer_retry_count = (
                int(getattr(transfer_record, "transfer_retry_count", 0) or 0) + 1
            )

        # repo-pattern-migrate: TODO: move to UserRepository.lock_account()
        student = db_write.query(User).filter(User.id == booking.student_id).first()
        if student:
            student.account_locked = True
            student.account_locked_at = now
            student.account_locked_reason = f"capture_failure_escalated:{booking.id}"

        payment_repo = RepositoryFactory.get_payment_repository(db_write)
        payment_repo.create_payment_event(
            booking_id=booking.id,
            event_type="capture_failure_escalated",
            event_data={
                "hours_since_failure": 72,
                "transfer_id": transfer_id,
                "transfer_error": transfer_error,
                "student_locked": True,
            },
        )

        db_write.commit()
    finally:
        db_write.close()


def handle_authorization_failure(
    booking: Booking, payment_repo: Any, error: str, error_type: str, hours_until_lesson: float
) -> None:
    """Handle authorization failure by updating status and recording event."""
    from sqlalchemy.orm import object_session as _obj_session

    _db = _obj_session(booking)
    if _db is not None:
        bp_fail = BookingRepository(_db).ensure_payment(booking.id)
        bp_fail.payment_status = PaymentStatus.PAYMENT_METHOD_REQUIRED.value
    else:
        logger.warning(
            "Booking %s has no active session — payment status update skipped. "
            "Payment event was still recorded, manual reconciliation may be needed.",
            booking.id,
        )

    payment_repo.create_payment_event(
        booking_id=booking.id,
        event_type="auth_failed",
        event_data={
            "error": error,
            "error_type": error_type,
            "hours_until_lesson": round(hours_until_lesson, 1),
            "failed_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    logger.error(f"Failed to authorize payment for booking {booking.id}: {error}")


def attempt_authorization_retry(
    booking: Booking,
    payment_repo: Any,
    db: Session,
    hours_until_lesson: float,
    stripe_service: StripeService,
) -> bool:
    """
    Attempt to retry authorization for a booking.

    Returns:
        True if successful, False otherwise
    """
    bp_attempt = BookingRepository(db).ensure_payment(booking.id)
    try:
        # Record retry attempt
        payment_repo.create_payment_event(
            booking_id=booking.id,
            event_type="auth_retry_attempted",
            event_data={
                "hours_until_lesson": round(hours_until_lesson, 1),
                "attempted_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        # Get student's Stripe customer
        student_customer = payment_repo.get_customer_by_user_id(booking.student_id)
        if not student_customer:
            raise Exception(f"No Stripe customer for student {booking.student_id}")

        # Get instructor's Stripe account
        from app.repositories.instructor_profile_repository import InstructorProfileRepository

        instructor_repo = InstructorProfileRepository(db)
        instructor_profile = instructor_repo.get_by_user_id(booking.instructor_id)
        instructor_account = payment_repo.get_connected_account_by_instructor_id(
            instructor_profile.id if instructor_profile else None
        )

        if not instructor_account:
            raise Exception(f"No Stripe account for instructor {booking.instructor_id}")

        ctx = stripe_service.build_charge_context(
            booking_id=booking.id, requested_credit_cents=None
        )

        if ctx.student_pay_cents <= 0:
            bp_attempt.payment_status = PaymentStatus.AUTHORIZED.value
            payment_repo.create_payment_event(
                booking_id=booking.id,
                event_type="auth_retry_succeeded",
                event_data={
                    "payment_intent_id": bp_attempt.payment_intent_id,
                    "hours_until_lesson": round(hours_until_lesson, 1),
                    "authorized_at": datetime.now(timezone.utc).isoformat(),
                    "credits_applied_cents": ctx.applied_credit_cents,
                },
            )
            return True

        payment_intent = stripe_service.create_or_retry_booking_payment_intent(
            booking_id=booking.id,
            payment_method_id=bp_attempt.payment_method_id,
            requested_credit_cents=None,
        )

        bp_attempt.payment_intent_id = getattr(payment_intent, "id", None)
        bp_attempt.payment_status = PaymentStatus.AUTHORIZED.value

        payment_repo.create_payment_event(
            booking_id=booking.id,
            event_type="auth_retry_succeeded",
            event_data={
                "payment_intent_id": payment_intent.id,
                "hours_until_lesson": round(hours_until_lesson, 1),
                "authorized_at": datetime.now(timezone.utc).isoformat(),
                "credits_applied_cents": ctx.applied_credit_cents,
                "amount_cents": ctx.student_pay_cents,
                "application_fee_cents": ctx.application_fee_cents,
            },
        )

        logger.info(
            f"Successfully retried authorization for booking {booking.id} (T-{hours_until_lesson:.1f}hr)"
        )
        return True

    except Exception as e:
        # Record failure
        payment_repo.create_payment_event(
            booking_id=booking.id,
            event_type="auth_retry_failed",
            event_data={
                "error": str(e),
                "hours_until_lesson": round(hours_until_lesson, 1),
                "failed_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        bp_attempt.payment_status = PaymentStatus.PAYMENT_METHOD_REQUIRED.value
        logger.error(f"Retry failed for booking {booking.id}: {e}")
        return False


def _should_retry_auth(booking: Booking, now: datetime) -> bool:
    """
    Determine if a failed authorization should be retried based on retry intervals.

    Retry intervals (hours since last attempt):
    - failure_count 1 -> 1 hour
    - failure_count 2 -> 4 hours
    - failure_count 3+ -> 8 hours
    """
    pd = booking.payment_detail
    attempted_at = getattr(pd, "auth_attempted_at", None)
    if not isinstance(attempted_at, datetime):
        return True

    hours_since_attempt = (now - attempted_at).total_seconds() / 3600
    failure_count = int(getattr(pd, "auth_failure_count", 0) or 0)

    if failure_count <= 1:
        required_wait = 1
    elif failure_count == 2:
        required_wait = 4
    else:
        required_wait = 8

    return hours_since_attempt >= required_wait


def _should_retry_capture(booking: Booking, now: datetime) -> bool:
    """Return True if enough time has passed since the last capture failure."""
    pd = booking.payment_detail
    failed_at = getattr(pd, "capture_failed_at", None)
    if not isinstance(failed_at, datetime):
        return False
    hours_since_failure = (now - failed_at).total_seconds() / 3600
    return hours_since_failure >= 4


def has_event_type(payment_repo: Any, booking_id: Union[int, str], event_type: str) -> bool:
    """Check if a booking has a specific event type in its history."""
    events = cast(
        Sequence[PaymentEvent],
        payment_repo.get_payment_events_for_booking(booking_id),
    )
    return any(e.event_type == event_type for e in events)


def _resolve_locked_booking_from_task(locked_booking_id: str, resolution: str) -> Dict[str, Any]:
    """Resolve a LOCKed booking from a task context."""
    from app.database import SessionLocal
    from app.services.booking_service import BookingService

    db: Session = SessionLocal()
    try:
        service = BookingService(db)
        result = service.resolve_lock_for_booking(locked_booking_id, resolution)
        db.commit()
        return result
    finally:
        db.close()


def _mark_child_booking_settled(booking_id: str) -> None:
    """Mark a rescheduled booking as settled after lock resolution."""
    from app.database import SessionLocal

    db: Session = SessionLocal()
    try:
        repo = BookingRepository(db)
        booking = repo.get_by_id(booking_id)
        if booking:
            bp_child = repo.ensure_payment(booking.id)
            bp_child.payment_status = PaymentStatus.SETTLED.value
            db.commit()
    finally:
        db.close()


def _process_capture_for_booking(
    booking_id: str,
    capture_reason: str,
) -> Dict[str, Any]:
    """
    Process payment capture for a single booking using 3-phase pattern.

    Phase 1: Quick transaction to read booking data
    Phase 2: Stripe call (no transaction)
    Phase 3: Quick transaction to update booking status

    Returns:
        Dict with success status and capture result
    """
    from app.database import SessionLocal

    # ========== PHASE 1: Read booking data (quick transaction) ==========
    db1: Session = SessionLocal()
    try:
        booking = BookingRepository(db1).get_by_id(booking_id)
        if not booking:
            return {"success": False, "error": "Booking not found"}

        if booking.status == BookingStatus.CANCELLED:
            db1.commit()
            return {"success": True, "skipped": True, "reason": "cancelled"}

        if (
            getattr(booking, "has_locked_funds", False) is True
            and booking.rescheduled_from_booking_id
        ):
            locked_booking_id = booking.rescheduled_from_booking_id
            db1.commit()
            lock_result = _resolve_locked_booking_from_task(
                locked_booking_id, "new_lesson_completed"
            )
            if lock_result.get("success") or lock_result.get("skipped"):
                _mark_child_booking_settled(booking_id)
            return {
                "success": True,
                "skipped": True,
                "reason": "locked_funds",
                "lock_result": lock_result,
            }

        # Extract data needed for Stripe call
        pd_cap = booking.payment_detail
        payment_intent_id = getattr(pd_cap, "payment_intent_id", None)
        current_payment_status = getattr(pd_cap, "payment_status", None)

        if not payment_intent_id:
            return {"success": False, "error": "No payment_intent_id"}

        if current_payment_status == PaymentStatus.MANUAL_REVIEW.value:
            db1.commit()
            return {"success": True, "skipped": True, "reason": "disputed"}

        if current_payment_status == PaymentStatus.SETTLED.value:
            return {"success": True, "already_captured": True}

        eligible_statuses = {PaymentStatus.AUTHORIZED.value}
        if capture_reason == "retry_failed_capture":
            eligible_statuses.add(PaymentStatus.PAYMENT_METHOD_REQUIRED.value)

        if current_payment_status not in eligible_statuses:
            db1.commit()
            return {"success": True, "skipped": True, "reason": "not_eligible"}

        if (
            current_payment_status == PaymentStatus.PAYMENT_METHOD_REQUIRED.value
            and getattr(pd_cap, "capture_failed_at", None) is None
        ):
            db1.commit()
            return {"success": True, "skipped": True, "reason": "not_capture_failure"}

        db1.commit()  # Release lock immediately
    finally:
        db1.close()

    # ========== PHASE 2: Stripe call (NO transaction) ==========
    stripe_result: Dict[str, Any] = {"success": False}
    try:
        db_stripe: Session = SessionLocal()
        try:
            config_service = ConfigService(db_stripe)
            pricing_service = PricingService(db_stripe)
            stripe_service = StripeService(
                db_stripe,
                config_service=config_service,
                pricing_service=pricing_service,
            )
            db_stripe.commit()  # Release any locks from service init
        finally:
            db_stripe.close()

        # Make Stripe call with NO database transaction
        idempotency_key = f"capture_{capture_reason}_{booking_id}_{payment_intent_id}"
        capture_payload = stripe_service.capture_booking_payment_intent(
            booking_id=booking_id,
            payment_intent_id=payment_intent_id,
            idempotency_key=idempotency_key,
        )

        payment_intent = None
        amount_received = None
        transfer_id = None

        if isinstance(capture_payload, dict):
            payment_intent = capture_payload.get("payment_intent")
            amount_received = capture_payload.get("amount_received")
            transfer_id = capture_payload.get("transfer_id")
        else:
            payment_intent = capture_payload

        if amount_received is None and payment_intent is not None:
            amount_received = getattr(payment_intent, "amount_received", None)

        if amount_received is None and payment_intent is not None:
            amount_received = getattr(payment_intent, "amount", None)

        stripe_result = {
            "success": True,
            "amount_received": amount_received,
            "payment_intent_id": payment_intent_id,
            "transfer_id": transfer_id,
        }

    except stripe.error.InvalidRequestError as e:
        error_code = e.code if hasattr(e, "code") else None

        if "already been captured" in str(e).lower():
            stripe_result = {"success": True, "already_captured": True}
        elif "expired" in str(e).lower() or error_code == "payment_intent_unexpected_state":
            stripe_result = {"success": False, "expired": True, "error": str(e)}
        else:
            stripe_result = {"success": False, "error": str(e), "error_code": error_code}

    except stripe.error.CardError as e:
        stripe_result = {
            "success": False,
            "card_error": True,
            "error": str(e),
            "error_code": e.code if hasattr(e, "code") else None,
        }

    except Exception as e:
        stripe_result = {"success": False, "error": str(e)}

    # ========== PHASE 3: Write results (quick transaction) ==========
    db3: Session = SessionLocal()
    try:
        booking_repo = BookingRepository(db3)
        booking = booking_repo.get_by_id(booking_id)
        if not booking:
            return {"success": False, "error": "Booking not found in Phase 3"}
        bp_cap3 = booking_repo.ensure_payment(booking.id)

        payment_repo = RepositoryFactory.get_payment_repository(db3)
        previous_capture_retry_count = int(getattr(bp_cap3, "capture_retry_count", 0) or 0)

        def _notify_payment_failed_once() -> None:
            if previous_capture_retry_count > 0:
                return
            try:
                notification_service = NotificationService(db3)
                notification_service.send_payment_failed_notification(booking)
            except Exception as exc:
                logger.warning(
                    "Failed to send payment failed notification for booking %s: %s",
                    booking_id,
                    exc,
                )

        def _resolve_payout_cents() -> Optional[int]:
            try:
                payment_record = payment_repo.get_payment_by_booking_id(booking_id)
            except RepositoryException:
                logger.warning(
                    "Failed to load payment record for booking %s during capture",
                    booking_id,
                    exc_info=True,
                )
                return None
            if not payment_record:
                return None
            payout_cents = getattr(payment_record, "instructor_payout_cents", None)
            if payout_cents is None:
                return None
            try:
                return int(payout_cents)
            except (TypeError, ValueError):
                return None

        if stripe_result.get("success"):
            from app.services.credit_service import CreditService

            bp_cap3.payment_status = PaymentStatus.SETTLED.value
            if stripe_result.get("transfer_id"):
                transfer_record = booking_repo.ensure_transfer(booking.id)
                transfer_record.stripe_transfer_id = stripe_result.get("transfer_id")
            try:
                credit_service = CreditService(db3)
                credit_service.forfeit_credits_for_booking(
                    booking_id=booking_id, use_transaction=False
                )
                bp_cap3.credits_reserved_cents = 0
            except Exception as exc:
                logger.warning(
                    "Failed to forfeit reserved credits for booking %s: %s",
                    booking_id,
                    exc,
                )
            if booking.status == BookingStatus.COMPLETED:
                bp_cap3.settlement_outcome = "lesson_completed_full_payout"
                booking.student_credit_amount = 0
                bp_cap3.instructor_payout_amount = _resolve_payout_cents()
                booking.refunded_to_card_amount = 0
            payment_repo.create_payment_event(
                booking_id=booking_id,
                event_type="payment_captured",
                event_data={
                    "payment_intent_id": stripe_result.get("payment_intent_id"),
                    "amount_captured_cents": stripe_result.get("amount_received"),
                    "capture_reason": capture_reason,
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            logger.info(
                f"Successfully captured payment for booking {booking_id} (reason: {capture_reason})"
            )

        elif stripe_result.get("expired"):
            bp_cap3.payment_status = PaymentStatus.PAYMENT_METHOD_REQUIRED.value
            bp_cap3.capture_failed_at = datetime.now(timezone.utc)
            bp_cap3.capture_retry_count = int(getattr(bp_cap3, "capture_retry_count", 0) or 0) + 1
            bp_cap3.capture_error = stripe_result.get("error")
            _notify_payment_failed_once()
            payment_repo.create_payment_event(
                booking_id=booking_id,
                event_type="capture_failed_expired",
                event_data={
                    "payment_intent_id": payment_intent_id,
                    "error": stripe_result.get("error"),
                    "capture_reason": capture_reason,
                },
            )

        elif stripe_result.get("card_error"):
            bp_cap3.payment_status = PaymentStatus.PAYMENT_METHOD_REQUIRED.value
            bp_cap3.capture_failed_at = datetime.now(timezone.utc)
            bp_cap3.capture_retry_count = int(getattr(bp_cap3, "capture_retry_count", 0) or 0) + 1
            bp_cap3.capture_error = stripe_result.get("error")
            _notify_payment_failed_once()
            payment_repo.create_payment_event(
                booking_id=booking_id,
                event_type="capture_failed_card",
                event_data={
                    "payment_intent_id": payment_intent_id,
                    "error": stripe_result.get("error"),
                    "error_code": stripe_result.get("error_code"),
                    "capture_reason": capture_reason,
                },
            )

        else:
            bp_cap3.payment_status = PaymentStatus.PAYMENT_METHOD_REQUIRED.value
            bp_cap3.capture_failed_at = datetime.now(timezone.utc)
            bp_cap3.capture_retry_count = int(getattr(bp_cap3, "capture_retry_count", 0) or 0) + 1
            bp_cap3.capture_error = stripe_result.get("error")
            _notify_payment_failed_once()
            payment_repo.create_payment_event(
                booking_id=booking_id,
                event_type="capture_failed",
                event_data={
                    "payment_intent_id": payment_intent_id,
                    "error": stripe_result.get("error"),
                    "capture_reason": capture_reason,
                },
            )
            logger.error(
                f"Failed to capture payment for booking {booking_id}: {stripe_result.get('error')}"
            )

        db3.commit()  # Commit and release lock immediately
    finally:
        db3.close()

    return stripe_result


def _auto_complete_booking(booking_id: str, now: datetime) -> Dict[str, Any]:
    """
    Auto-complete a booking and capture payment using 3-phase pattern.

    Returns:
        Dict with success status
    """
    from app.database import SessionLocal

    # ========== PHASE 1: Read and update booking status (quick transaction) ==========
    db1: Session = SessionLocal()
    payment_intent_id: Optional[str] = None
    locked_parent_id: Optional[str] = None
    has_locked_funds = False
    try:
        booking = BookingRepository(db1).get_by_id(booking_id)
        if not booking:
            return {"success": False, "error": "Booking not found"}

        if booking.status == BookingStatus.CANCELLED:
            db1.commit()
            return {
                "success": True,
                "auto_completed": False,
                "skipped": True,
                "reason": "cancelled",
            }

        pd_auto = booking.payment_detail
        if getattr(pd_auto, "payment_status", None) == PaymentStatus.MANUAL_REVIEW.value:
            db1.commit()
            return {"success": True, "auto_completed": False, "skipped": True, "reason": "disputed"}

        if booking.status != BookingStatus.CONFIRMED or (
            getattr(pd_auto, "payment_status", None) != PaymentStatus.AUTHORIZED.value
            and getattr(booking, "has_locked_funds", False) is not True
        ):
            db1.commit()
            return {
                "success": True,
                "auto_completed": False,
                "skipped": True,
                "reason": "not_eligible",
            }

        # Calculate lesson end in UTC
        lesson_end = _get_booking_end_utc(booking)

        # Mark as completed
        booking.status = BookingStatus.COMPLETED
        booking.completed_at = lesson_end
        instructor_id = booking.instructor_id
        completed_booking_id = booking.id
        completed_at = booking.completed_at

        # Issue milestone credit
        credit_service = StudentCreditService(db1)
        credit_service.maybe_issue_milestone_credit(
            student_id=booking.student_id,
            booking_id=booking.id,
        )

        # Record auto-completion event
        payment_repo = RepositoryFactory.get_payment_repository(db1)
        payment_repo.create_payment_event(
            booking_id=booking.id,
            event_type="auto_completed",
            event_data={
                "reason": "No instructor confirmation within 24hr",
                "lesson_end": lesson_end.isoformat(),
                "auto_completed_at": now.isoformat(),
            },
        )

        payment_intent_id = getattr(pd_auto, "payment_intent_id", None)
        if (
            getattr(booking, "has_locked_funds", False) is True
            and booking.rescheduled_from_booking_id
        ):
            has_locked_funds = True
            locked_parent_id = booking.rescheduled_from_booking_id
        db1.commit()  # Commit status change immediately

        try:
            from app.services.referral_service import ReferralService

            referral_service = ReferralService(db1)
            referral_service.on_instructor_lesson_completed(
                instructor_user_id=instructor_id,
                booking_id=completed_booking_id,
                completed_at=completed_at,
            )
        except Exception as exc:
            logger.error(
                "Failed to process instructor referral for auto-completed booking %s: %s",
                completed_booking_id,
                exc,
                exc_info=True,
            )
    finally:
        db1.close()

    # ========== PHASE 2 & 3: Capture payment (uses 3-phase internally) ==========
    if has_locked_funds and locked_parent_id:
        lock_result = _resolve_locked_booking_from_task(locked_parent_id, "new_lesson_completed")
        if lock_result.get("success") or lock_result.get("skipped"):
            _mark_child_booking_settled(booking_id)
        return {
            "success": True,
            "auto_completed": True,
            "captured": bool(lock_result.get("success") or lock_result.get("skipped")),
            "capture_attempted": True,
            "lock_result": lock_result,
        }

    if not payment_intent_id:
        logger.warning(f"Skipping capture for booking {booking_id}: no payment_intent_id")
        return {
            "success": True,
            "auto_completed": True,
            "captured": False,
            "capture_attempted": False,
        }

    capture_result = _process_capture_for_booking(booking_id, "auto_completed")

    return {
        "success": True,
        "auto_completed": True,
        "captured": capture_result.get("success", False),
        "capture_attempted": True,
    }


@typed_task(bind=True, max_retries=3, name="app.tasks.payment_tasks.capture_completed_lessons")
@monitor_if_configured("capture-completed-lessons")
def capture_completed_lessons(self: Any) -> CaptureJobResults:
    """
    Capture payments for completed lessons.

    Runs hourly to:
    1. Capture payments 24hr after lesson end (booking_end_utc)
    2. Auto-complete and capture lessons not marked complete within 24hr of end
    3. Handle expired authorizations (>7 days old)

    Uses 3-phase pattern to minimize lock contention:
    - Phase 1: Quick read (release lock immediately)
    - Phase 2: Stripe call (no lock held)
    - Phase 3: Quick write (release lock immediately)

    Returns:
        Dict with capture results
    """
    from app.database import SessionLocal

    now = datetime.now(timezone.utc)
    results: CaptureJobResults = {
        "captured": 0,
        "failed": 0,
        "auto_completed": 0,
        "expired_handled": 0,
        "processed_at": now.isoformat(),
    }

    # ========== Collect booking IDs to process (quick read) ==========
    db_read: Session = SessionLocal()
    try:
        booking_repo = RepositoryFactory.get_booking_repository(db_read)
        payment_repo = RepositoryFactory.get_payment_repository(db_read)

        # 1. Find booking IDs ready for capture
        all_completed_bookings = cast(
            Sequence[Booking],
            booking_repo.get_bookings_for_payment_capture(),
        )
        capture_booking_ids: List[str] = []
        capture_cutoff = now - timedelta(hours=24)
        for booking in all_completed_bookings:
            lesson_end_utc = _get_booking_end_utc(booking)
            if lesson_end_utc <= capture_cutoff and (
                getattr(booking.payment_detail, "payment_intent_id", None)
                or booking.has_locked_funds
            ):
                capture_booking_ids.append(booking.id)

        # 2. Find booking IDs for auto-completion
        auto_complete_cutoff = now - timedelta(hours=24)
        all_confirmed_bookings = cast(
            Sequence[Booking],
            booking_repo.get_bookings_for_auto_completion(),
        )
        auto_complete_booking_ids: List[str] = []
        for booking in all_confirmed_bookings:
            lesson_end_utc = _get_booking_end_utc(booking)
            if lesson_end_utc <= auto_complete_cutoff:
                auto_complete_booking_ids.append(booking.id)

        # 3. Find booking IDs with expired auth
        seven_days_ago = now - timedelta(days=7)
        bookings_with_expired_auth = cast(
            Sequence[Booking],
            booking_repo.get_bookings_with_expired_auth(),
        )
        expired_auth_data: List[Dict[str, Any]] = []
        for booking in bookings_with_expired_auth:
            auth_events = cast(
                Sequence[PaymentEvent],
                payment_repo.get_payment_events_for_booking(booking.id),
            )
            auth_event = next(
                (
                    e
                    for e in auth_events
                    if e.event_type in ["auth_succeeded", "auth_retry_succeeded"]
                ),
                None,
            )
            if auth_event and auth_event.created_at <= seven_days_ago:
                expired_auth_data.append(
                    {
                        "booking_id": booking.id,
                        "status": booking.status,
                        "auth_created_at": auth_event.created_at.isoformat(),
                    }
                )

        db_read.commit()  # Release locks from read phase
    finally:
        db_read.close()

    # ========== Process each booking with 3-phase pattern ==========

    # 1. Process instructor-completed bookings
    for booking_id in capture_booking_ids:
        try:
            with booking_lock_sync(booking_id) as acquired:
                if not acquired:
                    continue
                capture_result = _process_capture_for_booking(booking_id, "instructor_completed")
            if capture_result.get("success"):
                results["captured"] += 1
            elif not capture_result.get("skipped"):
                results["failed"] += 1
        except Exception as e:
            logger.error(f"Error processing capture for booking {booking_id}: {e}")
            results["failed"] += 1

    # 2. Process auto-complete bookings
    for booking_id in auto_complete_booking_ids:
        try:
            with booking_lock_sync(booking_id) as acquired:
                if not acquired:
                    continue
                auto_result = _auto_complete_booking(booking_id, now)
            if auto_result.get("auto_completed"):
                results["auto_completed"] += 1
            if auto_result.get("captured"):
                results["captured"] += 1
            elif auto_result.get("capture_attempted") and not auto_result.get("captured"):
                # Count as failed only if we tried to capture but failed
                results["failed"] += 1
        except Exception as e:
            logger.error(f"Error auto-completing booking {booking_id}: {e}")
            results["failed"] += 1

    # 3. Process expired authorizations
    for expired_data in expired_auth_data:
        booking_id = expired_data["booking_id"]
        try:
            with booking_lock_sync(booking_id) as acquired:
                if not acquired:
                    continue
                db_expired: Session = SessionLocal()
                try:
                    repo_expired = BookingRepository(db_expired)
                    booking_exp: Booking | None = repo_expired.get_by_id(booking_id)
                    if not booking_exp:
                        continue

                    if booking_exp.status == BookingStatus.CANCELLED:
                        continue

                    pd_exp = booking_exp.payment_detail
                    if getattr(pd_exp, "payment_status", None) == PaymentStatus.MANUAL_REVIEW.value:
                        continue

                    if getattr(pd_exp, "payment_status", None) != PaymentStatus.AUTHORIZED.value:
                        continue

                    if booking_exp.status == BookingStatus.COMPLETED:
                        # Try capture first (uses 3-phase internally)
                        capture_result = _process_capture_for_booking(booking_id, "expired_auth")
                        if not capture_result.get("success"):
                            # Create new auth and capture (3-phase pattern)
                            payment_repo = RepositoryFactory.get_payment_repository(db_expired)
                            new_auth_result = create_new_authorization_and_capture(
                                booking_exp, payment_repo, db_expired, lock_acquired=True
                            )
                            db_expired.commit()
                            if new_auth_result["success"]:
                                results["captured"] += 1
                            else:
                                results["failed"] += 1
                        else:
                            results["captured"] += 1
                    else:
                        # Mark as expired
                        bp_exp = repo_expired.ensure_payment(booking_exp.id)
                        bp_exp.payment_status = PaymentStatus.PAYMENT_METHOD_REQUIRED.value
                        bp_exp.capture_failed_at = now
                        bp_exp.capture_retry_count = (
                            int(getattr(bp_exp, "capture_retry_count", 0) or 0) + 1
                        )
                        payment_repo = RepositoryFactory.get_payment_repository(db_expired)
                        payment_repo.create_payment_event(
                            booking_id=booking_id,
                            event_type="auth_expired",
                            event_data={
                                "payment_intent_id": getattr(pd_exp, "payment_intent_id", None),
                                "expired_at": now.isoformat(),
                                "auth_created_at": expired_data["auth_created_at"],
                            },
                        )
                        db_expired.commit()

                    results["expired_handled"] += 1
                finally:
                    db_expired.close()
        except Exception as e:
            logger.error(f"Error handling expired auth for booking {booking_id}: {e}")
            results["failed"] += 1

    logger.info(
        f"Capture job completed: {results['captured']} captured, "
        f"{results['failed']} failed, {results['auto_completed']} auto-completed, "
        f"{results['expired_handled']} expired handled"
    )
    return results


def attempt_payment_capture(
    booking: Booking,
    payment_repo: Any,
    capture_reason: str,
    stripe_service: StripeService,
) -> Dict[str, Any]:
    """
    Attempt to capture a payment for a booking.

    Handles various error cases:
    - Already captured
    - Authorization expired
    - Authorization cancelled
    - Insufficient funds

    Returns:
        Dict with success status and error details
    """
    from sqlalchemy.orm import object_session as _obj_session

    _db = _obj_session(booking)
    bp_apc = BookingRepository(_db).ensure_payment(booking.id) if _db else None
    _pd_apc = bp_apc if bp_apc is not None else booking.payment_detail
    try:
        # Check if already captured/settled
        if getattr(_pd_apc, "payment_status", None) in {
            PaymentStatus.SETTLED.value,
            PaymentStatus.LOCKED.value,
        }:
            logger.info(f"Payment already captured for booking {booking.id}")
            return {"success": True, "already_captured": True}

        _intent_id: str | None = getattr(_pd_apc, "payment_intent_id", None)
        if not _intent_id:
            logger.warning(f"No payment_intent_id for booking {booking.id} — skipping capture")
            return {"success": False, "error": "missing_payment_intent"}
        idempotency_key = f"capture_{capture_reason}_{booking.id}_{_intent_id}"
        capture_payload = stripe_service.capture_booking_payment_intent(
            booking_id=booking.id,
            payment_intent_id=_intent_id,
            idempotency_key=idempotency_key,
        )

        if bp_apc is not None:
            bp_apc.payment_status = PaymentStatus.SETTLED.value

        payment_intent = None
        amount_received = None

        if isinstance(capture_payload, dict):
            payment_intent = capture_payload.get("payment_intent")
            amount_received = capture_payload.get("amount_received")
        else:
            payment_intent = capture_payload

        if amount_received is None and payment_intent is not None:
            amount_received = getattr(payment_intent, "amount_received", None)

        if amount_received is None and payment_intent is not None:
            amount_received = getattr(payment_intent, "amount", None)

        payment_repo.create_payment_event(
            booking_id=booking.id,
            event_type="payment_captured",
            event_data={
                "payment_intent_id": _intent_id,
                "amount_captured_cents": amount_received,
                "capture_reason": capture_reason,
                "captured_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        logger.info(
            f"Successfully captured payment for booking {booking.id} (reason: {capture_reason})"
        )
        return {"success": True}

    except stripe.error.InvalidRequestError as e:
        error_code = e.code if hasattr(e, "code") else None
        _intent_id = getattr(_pd_apc, "payment_intent_id", None)

        if "already been captured" in str(e).lower():
            # Already captured - update our records
            if bp_apc is not None:
                bp_apc.payment_status = PaymentStatus.SETTLED.value
                bp_apc.capture_failed_at = None
                bp_apc.capture_retry_count = 0
            payment_repo.create_payment_event(
                booking_id=booking.id,
                event_type="capture_already_done",
                event_data={
                    "payment_intent_id": _intent_id,
                    "error": str(e),
                },
            )
            return {"success": True, "already_captured": True}

        elif "expired" in str(e).lower() or error_code == "payment_intent_unexpected_state":
            # Authorization expired
            payment_repo.create_payment_event(
                booking_id=booking.id,
                event_type="capture_failed_expired",
                event_data={
                    "payment_intent_id": _intent_id,
                    "error": str(e),
                    "capture_reason": capture_reason,
                },
            )
            if bp_apc is not None:
                bp_apc.payment_status = PaymentStatus.PAYMENT_METHOD_REQUIRED.value
                bp_apc.capture_failed_at = datetime.now(timezone.utc)
                bp_apc.capture_retry_count = int(getattr(bp_apc, "capture_retry_count", 0) or 0) + 1
            return {"success": False, "expired": True}

        else:
            # Other invalid request error
            payment_repo.create_payment_event(
                booking_id=booking.id,
                event_type="capture_failed",
                event_data={
                    "payment_intent_id": _intent_id,
                    "error": str(e),
                    "error_code": error_code,
                    "capture_reason": capture_reason,
                },
            )
            return {"success": False, "error": str(e)}

    except stripe.error.CardError as e:
        # Insufficient funds or card issue at capture time
        _intent_id = getattr(_pd_apc, "payment_intent_id", None)
        payment_repo.create_payment_event(
            booking_id=booking.id,
            event_type="capture_failed_card",
            event_data={
                "payment_intent_id": _intent_id,
                "error": str(e),
                "error_code": e.code if hasattr(e, "code") else None,
                "capture_reason": capture_reason,
            },
        )
        if bp_apc is not None:
            bp_apc.payment_status = PaymentStatus.PAYMENT_METHOD_REQUIRED.value
            bp_apc.capture_failed_at = datetime.now(timezone.utc)
            bp_apc.capture_retry_count = int(getattr(bp_apc, "capture_retry_count", 0) or 0) + 1
        return {"success": False, "card_error": True}

    except Exception as e:
        # Unexpected error
        _intent_id = getattr(_pd_apc, "payment_intent_id", None)
        payment_repo.create_payment_event(
            booking_id=booking.id,
            event_type="capture_failed",
            event_data={
                "payment_intent_id": _intent_id,
                "error": str(e),
                "capture_reason": capture_reason,
            },
        )
        if bp_apc is not None:
            bp_apc.payment_status = PaymentStatus.PAYMENT_METHOD_REQUIRED.value
            bp_apc.capture_failed_at = datetime.now(timezone.utc)
            bp_apc.capture_retry_count = int(getattr(bp_apc, "capture_retry_count", 0) or 0) + 1
        logger.error(f"Failed to capture payment for booking {booking.id}: {e}")
        return {"success": False, "error": str(e)}


def create_new_authorization_and_capture(
    booking: Booking,
    payment_repo: Any,
    db: Session,
    *,
    lock_acquired: bool = False,
) -> Dict[str, Any]:
    """
    Create a new authorization and immediately capture for expired authorizations.

    Used when the original authorization has expired but we still need to charge.

    Returns:
        Dict with success status
    """
    if not lock_acquired:
        with booking_lock_sync(booking.id) as acquired:
            if not acquired:
                return {"success": False, "skipped": True, "error": "lock_unavailable"}
            return create_new_authorization_and_capture(
                booking, payment_repo, db, lock_acquired=True
            )

    from app.database import SessionLocal

    bp_reauth = BookingRepository(db).ensure_payment(booking.id)
    original_intent_id = bp_reauth.payment_intent_id

    try:
        # Ensure we are not holding a transaction during Stripe calls.
        try:
            db.commit()
        except Exception:
            logger.error("Pre-capture commit failed for booking %s", booking.id, exc_info=True)
            return {"success": False, "error": "pre_capture_commit_failed"}
        # ========== Phase 2: Stripe calls (NO transaction) ==========
        db_stripe: Session = SessionLocal()
        try:
            config_service = ConfigService(db_stripe)
            pricing_service = PricingService(db_stripe)
            stripe_service = StripeService(
                db_stripe,
                config_service=config_service,
                pricing_service=pricing_service,
            )

            # Recreate authorization via service so pricing comes from pricing_service
            new_intent = stripe_service.create_or_retry_booking_payment_intent(
                booking_id=booking.id,
                payment_method_id=bp_reauth.payment_method_id,
            )
            intent_id = getattr(new_intent, "id", None)
            if intent_id is None and isinstance(new_intent, dict):
                intent_id = new_intent.get("id")

            resolved_intent_id = intent_id or bp_reauth.payment_intent_id
            if not resolved_intent_id:
                raise Exception(
                    f"No payment intent id after reauthorization for booking {booking.id}"
                )

            idempotency_key = f"capture_reauth_{booking.id}_{resolved_intent_id}"
            capture_result = stripe_service.capture_booking_payment_intent(
                booking_id=booking.id,
                payment_intent_id=str(resolved_intent_id),
                idempotency_key=idempotency_key,
            )
            db_stripe.commit()
        finally:
            db_stripe.close()

        # ========== Phase 3: Write results (quick transaction) ==========
        resolved_intent_id = str(resolved_intent_id)
        bp_reauth.payment_status = PaymentStatus.SETTLED.value
        bp_reauth.payment_intent_id = resolved_intent_id
        try:
            from app.services.credit_service import CreditService

            credit_service = CreditService(db)
            credit_service.forfeit_credits_for_booking(booking_id=booking.id, use_transaction=False)
            bp_reauth.credits_reserved_cents = 0
        except Exception as exc:
            logger.warning(
                "Failed to forfeit reserved credits for booking %s: %s",
                booking.id,
                exc,
            )
        if booking.status == BookingStatus.COMPLETED:
            payout_cents: Optional[int] = None
            try:
                payment_record = payment_repo.get_payment_by_booking_id(booking.id)
            except RepositoryException:
                logger.warning(
                    "Failed to load payment record for booking %s during reauth",
                    booking.id,
                    exc_info=True,
                )
                payment_record = None
            if payment_record:
                payout_value = getattr(payment_record, "instructor_payout_cents", None)
                if payout_value is not None:
                    try:
                        payout_cents = int(payout_value)
                    except (TypeError, ValueError):
                        payout_cents = None
            bp_reauth.settlement_outcome = "lesson_completed_full_payout"
            booking.student_credit_amount = 0
            bp_reauth.instructor_payout_amount = payout_cents
            booking.refunded_to_card_amount = 0

        payment_repo.create_payment_event(
            booking_id=booking.id,
            event_type="reauth_and_capture_success",
            event_data={
                "new_payment_intent_id": resolved_intent_id,
                "original_payment_intent_id": original_intent_id,
                "amount_captured_cents": capture_result.get("amount_received"),
                "top_up_transfer_cents": capture_result.get("top_up_transfer_cents"),
                "captured_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        logger.info(f"Successfully created new auth and captured for booking {booking.id}")
        return {"success": True}

    except Exception as e:
        payment_repo.create_payment_event(
            booking_id=booking.id,
            event_type="reauth_and_capture_failed",
            event_data={
                "error": str(e),
                "original_payment_intent_id": original_intent_id
                if "original_intent_id" in locals()
                else getattr(bp_reauth, "payment_intent_id", None),
            },
        )
        logger.error(f"Failed to reauth and capture for booking {booking.id}: {e}")
        return {"success": False, "error": str(e)}


@typed_task(bind=True, max_retries=3, name="app.tasks.payment_tasks.capture_late_cancellation")
def capture_late_cancellation(self: Any, booking_id: Union[int, str]) -> Dict[str, Any]:
    """
    Immediately capture payment for late cancellations (<12hr before lesson).

    Called when a booking is cancelled within 12 hours of the lesson.
    Student is charged the full amount as per cancellation policy.

    Args:
        booking_id: The booking ID to capture payment for

    Returns:
        Dict with capture result
    """
    db: Optional[Session] = None
    try:
        with booking_lock_sync(str(booking_id)) as acquired:
            if not acquired:
                return {"success": False, "skipped": True, "error": "lock_unavailable"}

            db = cast(Session, next(get_db()))
            _payment_repo = RepositoryFactory.get_payment_repository(db)
            config_service = ConfigService(db)
            pricing_service = PricingService(db)
            stripe_service = StripeService(
                db,
                config_service=config_service,
                pricing_service=pricing_service,
            )

            # Get the booking
            booking_repo = RepositoryFactory.get_booking_repository(db)
            booking = booking_repo.get_by_id(booking_id)
            if not booking:
                logger.error(f"Booking {booking_id} not found for late cancellation capture")
                return {"success": False, "error": "Booking not found"}

            # Verify this is a late cancellation
            now = datetime.now(timezone.utc)
            booking_start_utc = _get_booking_start_utc(booking)
            hours_until_lesson = TimezoneService.hours_until(booking_start_utc)

            if hours_until_lesson >= 12:
                logger.warning(
                    f"Booking {booking_id} cancelled with {hours_until_lesson:.1f}hr notice - no charge"
                )
                return {"success": False, "error": "Not a late cancellation"}

            # Check if payment is already captured/settled
            bp_late = BookingRepository(db).ensure_payment(booking.id)
            if bp_late.payment_status in {
                PaymentStatus.SETTLED.value,
                PaymentStatus.LOCKED.value,
            }:
                logger.info(f"Payment already captured for booking {booking_id}")
                return {"success": True, "already_captured": True}

            # Ensure we have an authorization to capture
            if not bp_late.payment_intent_id:
                logger.error(f"No payment intent for booking {booking_id}")
                return {"success": False, "error": "No payment intent"}

            # Attempt immediate capture
            try:
                idempotency_key = f"capture_late_cancel_{booking.id}_{bp_late.payment_intent_id}"
                captured_intent = stripe_service.capture_booking_payment_intent(
                    booking_id=booking.id,
                    payment_intent_id=bp_late.payment_intent_id,
                    idempotency_key=idempotency_key,
                )

                bp_late.payment_status = PaymentStatus.SETTLED.value
                if not bp_late.settlement_outcome:
                    bp_late.settlement_outcome = "student_cancel_lt12_split_50_50"
                try:
                    from app.services.credit_service import CreditService

                    credit_service = CreditService(db)
                    credit_service.forfeit_credits_for_booking(
                        booking_id=booking.id, use_transaction=False
                    )
                    bp_late.credits_reserved_cents = 0
                except Exception as exc:
                    logger.warning(
                        "Failed to forfeit reserved credits for booking %s: %s",
                        booking.id,
                        exc,
                    )

                amount_received = getattr(captured_intent, "amount_received", None)
                _payment_repo.create_payment_event(
                    booking_id=booking.id,
                    event_type="late_cancellation_captured",
                    event_data={
                        "payment_intent_id": bp_late.payment_intent_id,
                        "amount_captured_cents": amount_received,
                        "hours_before_lesson": round(hours_until_lesson, 1),
                        "captured_at": now.isoformat(),
                        "cancellation_policy": "Full charge for <12hr cancellation",
                    },
                )

                db.commit()

                logger.info(
                    f"Successfully captured late cancellation for booking {booking_id} "
                    f"({hours_until_lesson:.1f}hr before lesson)"
                )
                return {
                    "success": True,
                    "amount_captured": amount_received,
                    "hours_before_lesson": round(hours_until_lesson, 1),
                }

            except stripe.error.InvalidRequestError as e:
                if "already been captured" in str(e).lower():
                    # Already captured
                    bp_late.payment_status = PaymentStatus.SETTLED.value
                    db.commit()
                    return {"success": True, "already_captured": True}
                else:
                    # Log the error
                    _payment_repo.create_payment_event(
                        booking_id=booking.id,
                        event_type="late_cancellation_capture_failed",
                        event_data={
                            "error": str(e),
                            "payment_intent_id": bp_late.payment_intent_id,
                            "hours_before_lesson": round(hours_until_lesson, 1),
                        },
                    )
                    db.commit()
                    logger.error(f"Failed to capture late cancellation for {booking_id}: {e}")
                    return {"success": False, "error": str(e)}

            except Exception as e:
                _payment_repo.create_payment_event(
                    booking_id=booking.id,
                    event_type="late_cancellation_capture_failed",
                    event_data={
                        "error": str(e),
                        "payment_intent_id": bp_late.payment_intent_id,
                        "hours_before_lesson": round(hours_until_lesson, 1),
                    },
                )
                db.commit()
                logger.error(f"Failed to capture late cancellation for {booking_id}: {e}")
                return {"success": False, "error": str(e)}

    except Exception as exc:
        logger.error(f"Late cancellation capture task failed for {booking_id}: {exc}")
        raise self.retry(exc=exc, countdown=60)  # Retry in 1 minute
    finally:
        if db is not None:
            db.close()


@typed_task(name="app.tasks.payment_tasks.resolve_undisputed_no_shows")
@monitor_if_configured("resolve-undisputed-no-shows")
def resolve_undisputed_no_shows() -> NoShowResolutionResults:
    """
    Auto-resolve no-show reports that were not disputed within 24 hours.
    """
    db: Optional[Session] = None
    now = datetime.now(timezone.utc)
    results: NoShowResolutionResults = {
        "resolved": 0,
        "skipped": 0,
        "failed": 0,
        "processed_at": now.isoformat(),
    }
    try:
        db = cast(Session, next(get_db()))
        booking_repo = RepositoryFactory.get_booking_repository(db)
        booking_service = BookingService(db)
        cutoff = now - timedelta(hours=24)

        pending = booking_repo.get_no_show_reports_due_for_resolution(reported_before=cutoff)
        for booking in pending:
            booking_id = booking.id
            try:
                with booking_lock_sync(str(booking_id)) as acquired:
                    if not acquired:
                        results["skipped"] += 1
                        continue
                    result = booking_service.resolve_no_show(
                        booking_id=booking_id,
                        resolution="confirmed_no_dispute",
                        resolved_by=None,
                        admin_notes=None,
                    )
                    if result.get("success"):
                        results["resolved"] += 1
                    else:
                        results["failed"] += 1
            except Exception as exc:
                logger.error("Failed to resolve no-show for %s: %s", booking_id, exc)
                results["failed"] += 1

        return results
    finally:
        if db is not None:
            db.close()


@typed_task(name="app.tasks.payment_tasks.check_authorization_health")
@monitor_if_configured("payment-health-check")
def check_authorization_health() -> Dict[str, Any]:
    """
    Health check for authorization system.

    Runs every 15 minutes to ensure the authorization system is healthy.
    Acts as a dead man's switch - alerts if jobs aren't running.

    Returns:
        Health status dict
    """
    db: Optional[Session] = None
    try:
        db = cast(Session, next(get_db()))
        _payment_repo = RepositoryFactory.get_payment_repository(db)

        now = datetime.now(timezone.utc)

        # Check for bookings that should have been authorized but weren't
        # These are bookings less than 24 hours away that are still "scheduled"
        overdue_bookings = []
        booking_repo = RepositoryFactory.get_booking_repository(db)

        scheduled_bookings = cast(
            Sequence[Booking],
            booking_repo.get_bookings_for_payment_authorization(),
        )

        for booking in scheduled_bookings:
            booking_start_utc = _get_booking_start_utc(booking)
            hours_until_lesson = TimezoneService.hours_until(booking_start_utc)

            if hours_until_lesson < 24:  # Should have been authorized
                overdue_bookings.append(
                    {
                        "booking_id": booking.id,
                        "hours_until_lesson": round(hours_until_lesson, 1),
                    }
                )

        # Check last successful authorization
        # Note: This is a simplified approach - in a full implementation,
        # we'd add a method to payment_repo to get latest events across all bookings
        last_auth_event = None
        try:
            last_auth_event = (
                # repo-pattern-ignore: Health check needs cross-booking event query
                db.query(PaymentEvent)  # repo-pattern-ignore: health check query
                .filter(
                    PaymentEvent.event_type.in_(["auth_succeeded", "auth_retry_succeeded"])
                )  # repo-pattern-ignore: health check query
                .order_by(PaymentEvent.created_at.desc())
                .first()  # repo-pattern-ignore: health check query
            )
        except Exception:
            logger.debug(
                "Unable to fetch last authorization event for health check",
                exc_info=True,
            )

        minutes_since_last_auth = None
        if last_auth_event:
            time_diff = now - last_auth_event.created_at
            minutes_since_last_auth = int(time_diff.total_seconds() / 60)

        health_status = {
            "healthy": True,
            "overdue_count": len(overdue_bookings),
            "overdue_bookings": overdue_bookings[:10],  # Limit to 10 for response size
            "minutes_since_last_auth": minutes_since_last_auth,
            "checked_at": now.isoformat(),
        }

        # Alert if system appears unhealthy
        if len(overdue_bookings) > 5:
            health_status["healthy"] = False
            logger.error(f"ALERT: {len(overdue_bookings)} bookings are overdue for authorization")

        if minutes_since_last_auth and minutes_since_last_auth > 120:  # 2 hours
            health_status["healthy"] = False
            logger.warning(f"No successful authorizations in {minutes_since_last_auth} minutes")

        return health_status

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "healthy": False,
            "error": str(e),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        if db is not None:
            db.close()


@typed_task(bind=True, max_retries=3, name="app.tasks.payment_tasks.audit_and_fix_payout_schedules")
@monitor_if_configured("payout-schedule-audit")
def audit_and_fix_payout_schedules(self: Any) -> Dict[str, Any]:
    """
    Nightly audit to ensure all connected accounts use weekly Tuesday payouts.
    """
    from app.database import SessionLocal

    db: Session = SessionLocal()
    try:
        payment_repo = RepositoryFactory.get_payment_repository(db)
        config_service = ConfigService(db)
        pricing_service = PricingService(db)
        stripe_service = StripeService(
            db,
            config_service=config_service,
            pricing_service=pricing_service,
        )

        accounts = payment_repo.get_all_connected_accounts()
        fixed = 0
        checked = 0
        for acc in accounts:
            checked += 1
            try:
                # Fetch live settings
                acct = stripe.Account.retrieve(acc.stripe_account_id)
                current = getattr(acct, "settings", {}).get("payouts", {}).get("schedule", {})
                interval = current.get("interval")
                weekly_anchor = current.get("weekly_anchor")
                if interval != "weekly" or weekly_anchor != "tuesday":
                    stripe_service.set_payout_schedule_for_account(
                        instructor_profile_id=acc.instructor_profile_id,
                        interval="weekly",
                        weekly_anchor="tuesday",
                    )
                    fixed += 1
            except Exception as e:
                logger.warning(f"Payout schedule audit failed for {acc.stripe_account_id}: {e}")

        result = {"checked": checked, "fixed": fixed}
        logger.info(f"Payout schedule audit completed: {result}")
        return result
    except Exception as exc:
        logger.error(f"Payout schedule audit failed: {exc}")
        raise self.retry(exc=exc, countdown=900)
    finally:
        db.close()
