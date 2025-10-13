"""
Celery tasks for payment processing.

Handles scheduled authorizations, retries, captures, and payouts.
Implements proper retry timing windows based on lesson time.
"""

from datetime import datetime, timedelta, timezone
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

from app.core.config import settings
from app.database import get_db
from app.models.booking import Booking, BookingStatus
from app.models.payment import PaymentEvent
from app.repositories.factory import RepositoryFactory
from app.services.notification_service import NotificationService
from app.services.stripe_service import StripeService
from app.services.student_credit_service import StudentCreditService
from app.tasks.celery_app import celery_app

P = ParamSpec("P")
R = TypeVar("R", covariant=True)


class TaskWrapper(Protocol[P, R]):
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        ...

    delay: Callable[..., AsyncResult]
    apply_async: Callable[..., AsyncResult]


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


logger = logging.getLogger(__name__)

# Configure Stripe
stripe.api_key = (
    settings.stripe_secret_key.get_secret_value() if settings.stripe_secret_key else None
)
STRIPE_CURRENCY = settings.stripe_currency if hasattr(settings, "stripe_currency") else "usd"


@typed_task(
    bind=True, max_retries=3, name="app.tasks.payment_tasks.process_scheduled_authorizations"
)
def process_scheduled_authorizations(self: Any) -> AuthorizationJobResults:
    """
    Process scheduled payment authorizations.

    Runs every 30 minutes to authorize payments for bookings
    that are approaching their 24-hour pre-authorization window.

    Returns:
        Dict with success/failure counts and details
    """
    from app.database import SessionLocal

    db: Session = SessionLocal()
    try:
        _payment_repo = RepositoryFactory.get_payment_repository(db)
        booking_repo = RepositoryFactory.get_booking_repository(db)
        stripe_service = StripeService(db)
        notification_service = NotificationService(db)

        # Find bookings that need authorization (T-24 hours)
        now = datetime.now(timezone.utc)
        _auth_window_start = now + timedelta(hours=23, minutes=30)  # 23.5 hours
        _auth_window_end = now + timedelta(hours=24, minutes=30)  # 24.5 hours

        # Get bookings that need authorization
        bookings_to_authorize = cast(
            Sequence[Booking],
            booking_repo.get_bookings_for_payment_authorization(),
        )

        failures: List[Dict[str, Any]] = []
        results: AuthorizationJobResults = {
            "success": 0,
            "failed": 0,
            "failures": failures,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }

        for booking in bookings_to_authorize:
            # Calculate exact time until lesson
            # Make booking_datetime timezone-aware (assuming UTC for booking times)
            booking_datetime = datetime.combine(
                booking.booking_date, booking.start_time, tzinfo=timezone.utc
            )
            hours_until_lesson = (booking_datetime - now).total_seconds() / 3600

            # Only process if in the 23.5-24.5 hour window
            if not (23.5 <= hours_until_lesson <= 24.5):
                continue

            try:
                # Get student's Stripe customer
                student_customer = _payment_repo.get_customer_by_user_id(booking.student_id)
                if not student_customer:
                    raise Exception(f"No Stripe customer for student {booking.student_id}")

                # Get instructor's Stripe account
                from app.repositories.instructor_profile_repository import (
                    InstructorProfileRepository,
                )

                instructor_repo = InstructorProfileRepository(db)
                instructor_profile = instructor_repo.get_by_user_id(booking.instructor_id)
                if instructor_profile is None:
                    raise Exception(f"No instructor profile for {booking.instructor_id}")
                instructor_account = _payment_repo.get_connected_account_by_instructor_id(
                    instructor_profile.id
                )

                if not instructor_account or not instructor_account.stripe_account_id:
                    raise Exception(f"No Stripe account for instructor {booking.instructor_id}")

                ctx = stripe_service.build_charge_context(
                    booking_id=booking.id, requested_credit_cents=None
                )

                if ctx.student_pay_cents <= 0:
                    booking.payment_status = "authorized"
                    _payment_repo.create_payment_event(
                        booking_id=booking.id,
                        event_type="auth_succeeded_credits_only",
                        event_data={
                            "base_price_cents": ctx.base_price_cents,
                            "credits_applied_cents": ctx.applied_credit_cents,
                        },
                    )
                    results["success"] += 1
                    logger.info(
                        f"Booking {booking.id} fully covered by credits; no authorization needed"
                    )
                    continue

                payment_intent = stripe_service.create_or_retry_booking_payment_intent(
                    booking_id=booking.id,
                    payment_method_id=booking.payment_method_id,
                    requested_credit_cents=None,
                )

                booking.payment_intent_id = getattr(payment_intent, "id", None)
                booking.payment_status = "authorized"

                # Record success event
                if ctx.applied_credit_cents:
                    try:
                        from app.monitoring.prometheus_metrics import prometheus_metrics

                        prometheus_metrics.inc_credits_applied("authorization")
                    except Exception:
                        pass

                _payment_repo.create_payment_event(
                    booking_id=booking.id,
                    event_type="auth_succeeded",
                    event_data={
                        "payment_intent_id": getattr(payment_intent, "id", None),
                        "amount_cents": ctx.student_pay_cents,
                        "application_fee_cents": ctx.application_fee_cents,
                        "authorized_at": datetime.now(timezone.utc).isoformat(),
                        "hours_before_lesson": round(hours_until_lesson, 1),
                        "credits_applied_cents": ctx.applied_credit_cents,
                    },
                )

                results["success"] += 1
                logger.info(f"Successfully authorized payment for booking {booking.id}")

            except Exception as e:
                # Card was declined
                # Map likely Stripe card errors to a consistent type without importing patched classes
                error_message = str(e)
                error_type = (
                    "card_declined"
                    if "card" in error_message.lower() or "declined" in error_message.lower()
                    else "system_error"
                )
                handle_authorization_failure(
                    booking, _payment_repo, error_message, error_type, hours_until_lesson
                )
                # T-24 first failure email: send urgent update-card notice on initial failure
                try:
                    # Only send once
                    if not has_event_type(
                        _payment_repo, booking.id, "t24_first_failure_email_sent"
                    ):
                        notification_service.send_final_payment_warning(
                            booking, hours_until_lesson
                        )  # reuse template
                        _payment_repo.create_payment_event(
                            booking_id=booking.id,
                            event_type="t24_first_failure_email_sent",
                            event_data={
                                "hours_until_lesson": round(hours_until_lesson, 1),
                                "error": error_message,
                            },
                        )
                except Exception as mail_err:
                    logger.error(
                        f"Failed to send T-24 failure email for booking {booking.id}: {mail_err}"
                    )
                results["failed"] += 1
                results["failures"].append(
                    {
                        "booking_id": booking.id,
                        "error": error_message,
                        "type": error_type,
                    }
                )

        db.commit()

        # Log results
        if results["failed"] > 0:
            logger.warning(f"Authorization job completed with {results['failed']} failures")

        logger.info(
            f"Authorization job completed: {results['success']} success, {results['failed']} failed"
        )
        return results

    except Exception as exc:
        logger.error(f"Authorization job failed: {exc}")
        raise self.retry(exc=exc, countdown=300)  # Retry in 5 minutes
    finally:
        db.close()


@typed_task(bind=True, max_retries=5, name="app.tasks.payment_tasks.retry_failed_authorizations")
def retry_failed_authorizations(self: Any) -> RetryJobResults:
    """
    Retry failed payment authorizations at specific time windows.

    Retry windows:
    - T-22hr: First retry
    - T-20hr: Second retry
    - T-18hr: Third retry
    - T-12hr: Final warning email + retry
    - T-6hr: Cancel booking if still failing

    Returns:
        Dict with retry results
    """
    from app.database import SessionLocal

    db: Session = SessionLocal()
    try:
        _payment_repo = RepositoryFactory.get_payment_repository(db)
        booking_repo = RepositoryFactory.get_booking_repository(db)
        stripe_service = StripeService(db)
        notification_service = NotificationService(db)

        now = datetime.now(timezone.utc)

        # Find bookings with failed auth
        bookings_to_retry = cast(
            Sequence[Booking],
            booking_repo.get_bookings_for_payment_retry(),
        )

        results: RetryJobResults = {
            "retried": 0,
            "success": 0,
            "failed": 0,
            "cancelled": 0,
            "warnings_sent": 0,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }

        for booking in bookings_to_retry:
            # Calculate hours until lesson
            booking_datetime = datetime.combine(
                booking.booking_date, booking.start_time, tzinfo=timezone.utc
            )
            hours_until_lesson = (booking_datetime - now).total_seconds() / 3600

            # Skip if lesson already happened
            if hours_until_lesson < 0:
                continue

            # Determine action based on time until lesson
            if hours_until_lesson <= 6:
                # Too late - cancel the booking
                booking.status = BookingStatus.CANCELLED
                booking.payment_status = "auth_abandoned"
                booking.cancelled_at = now
                booking.cancellation_reason = "Payment authorization failed after multiple attempts"

                _payment_repo.create_payment_event(
                    booking_id=booking.id,
                    event_type="auth_abandoned",
                    event_data={
                        "reason": "T-6hr cancellation",
                        "hours_until_lesson": round(hours_until_lesson, 1),
                        "cancelled_at": now.isoformat(),
                    },
                )

                # Send cancellation notification
                notification_service.send_booking_cancelled_payment_failed(booking)
                results["cancelled"] += 1
                logger.info(
                    f"Cancelled booking {booking.id} due to payment failure (T-{hours_until_lesson:.1f}hr)"
                )

            elif hours_until_lesson <= 12:
                # T-12hr: Send final warning and retry
                if not has_event_type(_payment_repo, booking.id, "final_warning_sent"):
                    # Send final warning email
                    notification_service.send_final_payment_warning(booking, hours_until_lesson)

                    _payment_repo.create_payment_event(
                        booking_id=booking.id,
                        event_type="final_warning_sent",
                        event_data={
                            "hours_until_lesson": round(hours_until_lesson, 1),
                            "sent_at": now.isoformat(),
                        },
                    )
                    results["warnings_sent"] += 1

                # Attempt retry
                if attempt_authorization_retry(
                    booking, _payment_repo, db, hours_until_lesson, stripe_service
                ):
                    results["success"] += 1
                else:
                    results["failed"] += 1

                results["retried"] += 1

            elif 17 <= hours_until_lesson < 23:  # T-18hr, T-20hr, T-22hr windows
                # Silent retry at specific windows
                retry_windows = [18, 20, 22]
                should_retry = any(
                    abs(hours_until_lesson - window) < 0.5 for window in retry_windows
                )

                if should_retry:
                    # Check if we already retried at this window
                    recent_events = _payment_repo.get_payment_events_for_booking(booking.id)
                    recent_retry_times = [
                        e.created_at
                        for e in recent_events
                        if e.event_type in ["auth_retry_attempted", "auth_retry_succeeded"]
                        and (now - e.created_at).total_seconds() < 3600  # Within last hour
                    ]

                    if not recent_retry_times:  # Haven't retried recently
                        if attempt_authorization_retry(
                            booking, _payment_repo, db, hours_until_lesson, stripe_service
                        ):
                            results["success"] += 1
                        else:
                            results["failed"] += 1
                        results["retried"] += 1

        db.commit()

        logger.info(
            f"Retry job completed: {results['retried']} attempted, "
            f"{results['success']} success, {results['failed']} failed, "
            f"{results['cancelled']} cancelled, {results['warnings_sent']} warnings sent"
        )
        return results

    except Exception as exc:
        logger.error(f"Retry job failed: {exc}")
        raise self.retry(exc=exc, countdown=600)  # Retry in 10 minutes
    finally:
        db.close()


def handle_authorization_failure(
    booking: Booking, payment_repo: Any, error: str, error_type: str, hours_until_lesson: float
) -> None:
    """Handle authorization failure by updating status and recording event."""
    booking.payment_status = "auth_failed"

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
            booking.payment_status = "authorized"
            payment_repo.create_payment_event(
                booking_id=booking.id,
                event_type="auth_retry_succeeded",
                event_data={
                    "payment_intent_id": booking.payment_intent_id,
                    "hours_until_lesson": round(hours_until_lesson, 1),
                    "authorized_at": datetime.now(timezone.utc).isoformat(),
                    "credits_applied_cents": ctx.applied_credit_cents,
                },
            )
            return True

        payment_intent = stripe_service.create_or_retry_booking_payment_intent(
            booking_id=booking.id,
            payment_method_id=booking.payment_method_id,
            requested_credit_cents=None,
        )

        booking.payment_intent_id = getattr(payment_intent, "id", None)
        booking.payment_status = "authorized"

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

        booking.payment_status = "auth_retry_failed"
        logger.error(f"Retry failed for booking {booking.id}: {e}")
        return False


def has_event_type(payment_repo: Any, booking_id: Union[int, str], event_type: str) -> bool:
    """Check if a booking has a specific event type in its history."""
    events = cast(
        Sequence[PaymentEvent],
        payment_repo.get_payment_events_for_booking(booking_id),
    )
    return any(e.event_type == event_type for e in events)


@typed_task(bind=True, max_retries=3, name="app.tasks.payment_tasks.capture_completed_lessons")
def capture_completed_lessons(self: Any) -> CaptureJobResults:
    """
    Capture payments for completed lessons.

    Runs hourly to:
    1. Capture payments 24hr after instructor marks complete
    2. Auto-complete and capture lessons not marked complete within 24hr of end
    3. Handle expired authorizations (>7 days old)

    Returns:
        Dict with capture results
    """
    from app.database import SessionLocal

    db: Session = SessionLocal()
    try:
        _payment_repo = RepositoryFactory.get_payment_repository(db)
        booking_repo = RepositoryFactory.get_booking_repository(db)
        stripe_service = StripeService(db)
        credit_service = StudentCreditService(db)
        now = datetime.now(timezone.utc)

        results: CaptureJobResults = {
            "captured": 0,
            "failed": 0,
            "auto_completed": 0,
            "expired_handled": 0,
            "processed_at": now.isoformat(),
        }

        # 1. Find bookings ready for capture (24hr after instructor marked complete)
        all_completed_bookings = cast(
            Sequence[Booking],
            booking_repo.get_bookings_for_payment_capture(),
        )
        bookings_to_capture = [
            booking
            for booking in all_completed_bookings
            if booking.completed_at and booking.completed_at <= now - timedelta(hours=24)
        ]

        for booking in bookings_to_capture:
            capture_result = attempt_payment_capture(
                booking, _payment_repo, "instructor_completed", stripe_service
            )
            if capture_result["success"]:
                results["captured"] += 1
            else:
                results["failed"] += 1

        # 2. Auto-complete lessons not marked complete within 24hr of end
        auto_complete_cutoff = now - timedelta(hours=24)
        all_confirmed_bookings = cast(
            Sequence[Booking],
            booking_repo.get_bookings_for_auto_completion(),
        )

        # Filter to only bookings where lesson ended >24hr ago
        bookings_to_auto_complete: List[Booking] = []
        for booking in all_confirmed_bookings:
            lesson_end = datetime.combine(
                booking.booking_date, booking.end_time, tzinfo=timezone.utc
            )
            if lesson_end <= auto_complete_cutoff:
                bookings_to_auto_complete.append(booking)

        for booking in bookings_to_auto_complete:
            # Auto-complete the booking
            booking.status = BookingStatus.COMPLETED
            booking.completed_at = now

            credit_service.maybe_issue_milestone_credit(
                student_id=booking.student_id,
                booking_id=booking.id,
            )

            _payment_repo.create_payment_event(
                booking_id=booking.id,
                event_type="auto_completed",
                event_data={
                    "reason": "No instructor confirmation within 24hr",
                    "lesson_end": datetime.combine(
                        booking.booking_date, booking.end_time, tzinfo=timezone.utc
                    ).isoformat(),
                    "auto_completed_at": now.isoformat(),
                },
            )

            # Attempt capture
            capture_result = attempt_payment_capture(
                booking, _payment_repo, "auto_completed", stripe_service
            )
            if capture_result["success"]:
                results["captured"] += 1
            else:
                results["failed"] += 1

            results["auto_completed"] += 1

        # 3. Handle expired authorizations (>7 days old)
        seven_days_ago = now - timedelta(days=7)
        bookings_with_expired_auth = cast(
            Sequence[Booking],
            booking_repo.get_bookings_with_expired_auth(),
        )

        for booking in bookings_with_expired_auth:
            # Check when authorization was created
            auth_events = cast(
                Sequence[PaymentEvent],
                _payment_repo.get_payment_events_for_booking(booking.id),
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
                # Authorization is expired, need to handle it
                if booking.status == BookingStatus.COMPLETED:
                    # Try to capture anyway (might fail)
                    capture_result = attempt_payment_capture(
                        booking, _payment_repo, "expired_auth", stripe_service
                    )
                    if not capture_result["success"]:
                        # Create new authorization and capture
                        new_auth_result = create_new_authorization_and_capture(
                            booking, _payment_repo, db
                        )
                        if new_auth_result["success"]:
                            results["captured"] += 1
                        else:
                            results["failed"] += 1
                else:
                    # Mark as expired, will need manual intervention
                    booking.payment_status = "auth_expired"
                    _payment_repo.create_payment_event(
                        booking_id=booking.id,
                        event_type="auth_expired",
                        event_data={
                            "payment_intent_id": booking.payment_intent_id,
                            "expired_at": now.isoformat(),
                            "auth_created_at": auth_event.created_at.isoformat(),
                        },
                    )

                results["expired_handled"] += 1

        db.commit()

        logger.info(
            f"Capture job completed: {results['captured']} captured, "
            f"{results['failed']} failed, {results['auto_completed']} auto-completed, "
            f"{results['expired_handled']} expired handled"
        )
        return results

    except Exception as exc:
        logger.error(f"Capture job failed: {exc}")
        raise self.retry(exc=exc, countdown=300)  # Retry in 5 minutes
    finally:
        db.close()


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
    try:
        # Check if already captured
        if booking.payment_status == "captured":
            logger.info(f"Payment already captured for booking {booking.id}")
            return {"success": True, "already_captured": True}

        # Exclude cancelled bookings that were already captured
        if booking.status == BookingStatus.CANCELLED and booking.payment_status == "captured":
            logger.info(f"Skipping cancelled booking {booking.id} - already captured")
            return {"success": True, "skipped": True}

        capture_payload = stripe_service.capture_booking_payment_intent(
            booking_id=booking.id,
            payment_intent_id=booking.payment_intent_id,
        )

        booking.payment_status = "captured"

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
                "payment_intent_id": booking.payment_intent_id,
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

        if "already been captured" in str(e).lower():
            # Already captured - update our records
            booking.payment_status = "captured"
            payment_repo.create_payment_event(
                booking_id=booking.id,
                event_type="capture_already_done",
                event_data={
                    "payment_intent_id": booking.payment_intent_id,
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
                    "payment_intent_id": booking.payment_intent_id,
                    "error": str(e),
                    "capture_reason": capture_reason,
                },
            )
            booking.payment_status = "auth_expired"
            return {"success": False, "expired": True}

        else:
            # Other invalid request error
            payment_repo.create_payment_event(
                booking_id=booking.id,
                event_type="capture_failed",
                event_data={
                    "payment_intent_id": booking.payment_intent_id,
                    "error": str(e),
                    "error_code": error_code,
                    "capture_reason": capture_reason,
                },
            )
            return {"success": False, "error": str(e)}

    except stripe.error.CardError as e:
        # Insufficient funds or card issue at capture time
        payment_repo.create_payment_event(
            booking_id=booking.id,
            event_type="capture_failed_card",
            event_data={
                "payment_intent_id": booking.payment_intent_id,
                "error": str(e),
                "error_code": e.code if hasattr(e, "code") else None,
                "capture_reason": capture_reason,
            },
        )
        booking.payment_status = "capture_failed"
        return {"success": False, "card_error": True}

    except Exception as e:
        # Unexpected error
        payment_repo.create_payment_event(
            booking_id=booking.id,
            event_type="capture_failed",
            event_data={
                "payment_intent_id": booking.payment_intent_id,
                "error": str(e),
                "capture_reason": capture_reason,
            },
        )
        logger.error(f"Failed to capture payment for booking {booking.id}: {e}")
        return {"success": False, "error": str(e)}


def create_new_authorization_and_capture(
    booking: Booking, payment_repo: Any, db: Session
) -> Dict[str, Any]:
    """
    Create a new authorization and immediately capture for expired authorizations.

    Used when the original authorization has expired but we still need to charge.

    Returns:
        Dict with success status
    """
    try:
        stripe_service = StripeService(db)
        original_intent_id = booking.payment_intent_id

        # Recreate authorization via service so pricing comes from pricing_service
        new_intent = stripe_service.create_or_retry_booking_payment_intent(
            booking_id=booking.id,
            payment_method_id=booking.payment_method_id,
        )
        intent_id = getattr(new_intent, "id", None)
        if intent_id is None and isinstance(new_intent, dict):
            intent_id = new_intent.get("id")

        resolved_intent_id = intent_id or booking.payment_intent_id
        if not resolved_intent_id:
            raise Exception(f"No payment intent id after reauthorization for booking {booking.id}")

        capture_result = stripe_service.capture_booking_payment_intent(
            booking_id=booking.id,
            payment_intent_id=str(resolved_intent_id),
        )

        booking.payment_status = "captured"
        new_payment_intent_id = booking.payment_intent_id or resolved_intent_id

        payment_repo.create_payment_event(
            booking_id=booking.id,
            event_type="reauth_and_capture_success",
            event_data={
                "new_payment_intent_id": new_payment_intent_id,
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
                else booking.payment_intent_id,
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
    try:
        db = cast(Session, next(get_db()))
        _payment_repo = RepositoryFactory.get_payment_repository(db)
        stripe_service = StripeService(db)

        # Get the booking
        booking_repo = RepositoryFactory.get_booking_repository(db)
        booking = booking_repo.get_by_id(booking_id)
        if not booking:
            logger.error(f"Booking {booking_id} not found for late cancellation capture")
            return {"success": False, "error": "Booking not found"}

        # Verify this is a late cancellation
        now = datetime.now(timezone.utc)
        lesson_datetime = datetime.combine(
            booking.booking_date, booking.start_time, tzinfo=timezone.utc
        )
        hours_until_lesson = (lesson_datetime - now).total_seconds() / 3600

        if hours_until_lesson >= 12:
            logger.warning(
                f"Booking {booking_id} cancelled with {hours_until_lesson:.1f}hr notice - no charge"
            )
            return {"success": False, "error": "Not a late cancellation"}

        # Check if payment is already captured
        if booking.payment_status == "captured":
            logger.info(f"Payment already captured for booking {booking_id}")
            return {"success": True, "already_captured": True}

        # Ensure we have an authorization to capture
        if not booking.payment_intent_id:
            logger.error(f"No payment intent for booking {booking_id}")
            return {"success": False, "error": "No payment intent"}

        # Attempt immediate capture
        try:
            captured_intent = stripe_service.capture_booking_payment_intent(
                booking_id=booking.id,
                payment_intent_id=booking.payment_intent_id,
            )

            booking.payment_status = "captured"

            amount_received = getattr(captured_intent, "amount_received", None)
            _payment_repo.create_payment_event(
                booking_id=booking.id,
                event_type="late_cancellation_captured",
                event_data={
                    "payment_intent_id": booking.payment_intent_id,
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
                booking.payment_status = "captured"
                db.commit()
                return {"success": True, "already_captured": True}
            else:
                # Log the error
                _payment_repo.create_payment_event(
                    booking_id=booking.id,
                    event_type="late_cancellation_capture_failed",
                    event_data={
                        "error": str(e),
                        "payment_intent_id": booking.payment_intent_id,
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
                    "payment_intent_id": booking.payment_intent_id,
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
        db.close()


@typed_task(name="app.tasks.payment_tasks.check_authorization_health")
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
            booking_datetime = datetime.combine(
                booking.booking_date, booking.start_time, tzinfo=timezone.utc
            )
            hours_until_lesson = (booking_datetime - now).total_seconds() / 3600

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
            # repo-pattern-ignore: Health check needs cross-booking event query
            last_auth_event = (
                db.query(PaymentEvent)
                .filter(PaymentEvent.event_type.in_(["auth_succeeded", "auth_retry_succeeded"]))
                .order_by(PaymentEvent.created_at.desc())
                .first()
            )
        except Exception:
            pass  # If this fails, we'll just report no recent auth

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
def audit_and_fix_payout_schedules(self: Any) -> Dict[str, Any]:
    """
    Nightly audit to ensure all connected accounts use weekly Tuesday payouts.
    """
    from app.database import SessionLocal

    db: Session = SessionLocal()
    try:
        _payment_repo = RepositoryFactory.get_payment_repository(db)
        stripe_service = StripeService(db)

        # repo-pattern-ignore: Simple scan over connected accounts table
        from app.models.payment import StripeConnectedAccount

        accounts = db.query(StripeConnectedAccount).all()
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
