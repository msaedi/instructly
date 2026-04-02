"""Payment authorization helpers and orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Sequence, cast

from sqlalchemy.orm import Session

from app.models.booking import Booking, BookingStatus, PaymentStatus
from app.tasks.enqueue import enqueue_task
from app.tasks.payment.common import AuthorizationJobResults, PaymentTasksFacadeApi


def load_auth_booking_context(
    api: PaymentTasksFacadeApi,
    db: Session,
    booking_id: str,
) -> Dict[str, Any]:
    from app.repositories.instructor_profile_repository import InstructorProfileRepository

    booking = api.BookingRepository(db).get_by_id(booking_id)
    if not booking:
        return {"result": {"success": False, "error": "Booking not found"}}
    if booking.status in {BookingStatus.CANCELLED, BookingStatus.PAYMENT_FAILED}:
        return {"result": {"success": False, "skipped": True, "reason": "terminal"}}
    payment = booking.payment_detail
    if booking.status not in {BookingStatus.CONFIRMED, BookingStatus.PENDING}:
        return {"result": {"success": False, "skipped": True, "reason": "not_eligible"}}
    if getattr(payment, "payment_status", None) != PaymentStatus.SCHEDULED.value:
        return {"result": {"success": False, "skipped": True, "reason": "not_eligible"}}
    payment_repo = api.RepositoryFactory.create_payment_repository(db)
    intent_id = getattr(payment, "payment_intent_id", None)
    existing_intent_id = (
        intent_id if isinstance(intent_id, str) and intent_id.startswith("pi_") else None
    )
    student_customer = payment_repo.get_customer_by_user_id(booking.student_id)
    if not student_customer:
        return {"phase1_error": f"No Stripe customer for student {booking.student_id}"}
    instructor_profile = InstructorProfileRepository(db).get_by_user_id(booking.instructor_id)
    if instructor_profile is None:
        return {"phase1_error": f"No instructor profile for {booking.instructor_id}"}
    instructor_account = payment_repo.get_connected_account_by_instructor_id(instructor_profile.id)
    if not instructor_account or not instructor_account.stripe_account_id:
        return {"phase1_error": f"No Stripe account for instructor {booking.instructor_id}"}
    return {
        "payment_method_id": getattr(payment, "payment_method_id", None),
        "existing_payment_intent_id": existing_intent_id,
    }


def build_auth_credits_only_result(ctx: Any) -> Dict[str, Any]:
    return {
        "success": True,
        "credits_only": True,
        "base_price_cents": ctx.base_price_cents,
        "applied_credit_cents": ctx.applied_credit_cents,
    }


def build_auth_success_result(ctx: Any, payment_intent_id: str | None) -> Dict[str, Any]:
    return {
        "success": True,
        "payment_intent_id": payment_intent_id,
        "student_pay_cents": ctx.student_pay_cents,
        "application_fee_cents": ctx.application_fee_cents,
        "applied_credit_cents": ctx.applied_credit_cents,
    }


def classify_auth_exception(exc: Exception) -> Dict[str, Any]:
    error_message = str(exc)
    error_type = (
        "card_declined"
        if "card" in error_message.lower() or "declined" in error_message.lower()
        else "system_error"
    )
    return {"success": False, "error": error_message, "error_type": error_type}


def _notify_payment_failed_once(
    api: PaymentTasksFacadeApi,
    db: Session,
    booking: Booking,
    booking_id: str,
    previous_capture_retry_count: int,
) -> None:
    if previous_capture_retry_count > 0:
        return
    try:
        api.NotificationService(db).send_payment_failed_notification(booking)
    except Exception as exc:
        api.logger.warning(
            "Failed to send payment failed notification for booking %s: %s",
            booking_id,
            exc,
        )


def _record_auth_metrics(api: PaymentTasksFacadeApi, stripe_result: Dict[str, Any]) -> None:
    if not stripe_result.get("applied_credit_cents"):
        return
    try:
        from app.monitoring.prometheus_metrics import prometheus_metrics

        prometheus_metrics.inc_credits_applied("authorization")
    except Exception:
        api.logger.debug("Non-fatal error ignored", exc_info=True)


def _persist_auth_success(
    api: PaymentTasksFacadeApi,
    payment_repo: Any,
    booking: Booking,
    booking_payment: Any,
    booking_id: str,
    hours_until_lesson: float,
    stripe_result: Dict[str, Any],
    attempted_at: datetime,
) -> bool:
    send_confirmation_notifications = False
    if stripe_result.get("credits_only"):
        booking_payment.payment_status = PaymentStatus.AUTHORIZED.value
        payment_repo.create_payment_event(
            booking_id=booking_id,
            event_type="auth_succeeded_credits_only",
            event_data={
                "base_price_cents": stripe_result.get("base_price_cents"),
                "credits_applied_cents": stripe_result.get("applied_credit_cents"),
            },
        )
        api.logger.info("Booking %s fully covered by credits; no authorization needed", booking_id)
    else:
        booking_payment.payment_intent_id = stripe_result.get("payment_intent_id")
        _record_auth_metrics(api, stripe_result)
        payment_repo.create_payment_event(
            booking_id=booking_id,
            event_type="auth_succeeded",
            event_data={
                "payment_intent_id": stripe_result.get("payment_intent_id"),
                "amount_cents": stripe_result.get("student_pay_cents"),
                "application_fee_cents": stripe_result.get("application_fee_cents"),
                "authorized_at": api.datetime.now(timezone.utc).isoformat(),
                "hours_before_lesson": round(hours_until_lesson, 1),
                "credits_applied_cents": stripe_result.get("applied_credit_cents"),
            },
        )
        api.logger.info("Successfully authorized payment for booking %s", booking_id)
    booking_payment.payment_status = PaymentStatus.AUTHORIZED.value
    booking_payment.auth_attempted_at = attempted_at
    booking_payment.auth_failure_count = 0
    booking_payment.auth_last_error = None
    if booking.status == BookingStatus.PENDING:
        booking.status = BookingStatus.CONFIRMED
        booking.confirmed_at = attempted_at
        send_confirmation_notifications = True
    return send_confirmation_notifications


def _persist_auth_failure(
    api: PaymentTasksFacadeApi,
    payment_repo: Any,
    booking_payment: Any,
    booking_id: str,
    hours_until_lesson: float,
    stripe_result: Dict[str, Any],
    attempted_at: datetime,
) -> None:
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
            "failed_at": api.datetime.now(timezone.utc).isoformat(),
        },
    )
    api.logger.error(
        "Failed to authorize payment for booking %s: %s", booking_id, stripe_result.get("error")
    )


def persist_authorization_result(
    api: PaymentTasksFacadeApi,
    db: Session,
    booking_id: str,
    hours_until_lesson: float,
    stripe_result: Dict[str, Any],
) -> Dict[str, Any]:
    booking = api.BookingRepository(db).get_by_id(booking_id)
    if not booking:
        return {"success": False, "error": "Booking not found in Phase 3"}
    payment_repo = api.RepositoryFactory.create_payment_repository(db)
    booking_payment = api.BookingRepository(db).ensure_payment(booking.id)
    attempted_at = api.datetime.now(timezone.utc)
    previous_capture_retry_count = int(getattr(booking_payment, "capture_retry_count", 0) or 0)
    send_confirmation = False
    send_payment_failed = False
    if stripe_result.get("success"):
        send_confirmation = _persist_auth_success(
            api,
            payment_repo,
            booking,
            booking_payment,
            booking_id,
            hours_until_lesson,
            stripe_result,
            attempted_at,
        )
    else:
        _persist_auth_failure(
            api,
            payment_repo,
            booking_payment,
            booking_id,
            hours_until_lesson,
            stripe_result,
            attempted_at,
        )
        send_payment_failed = True
    db.commit()
    if send_confirmation:
        try:
            api.BookingService(db).send_booking_notifications_after_confirmation(booking_id)
        except Exception as exc:
            api.logger.warning(
                "Failed to send booking confirmation notifications for %s: %s", booking_id, exc
            )
    if send_payment_failed:
        _notify_payment_failed_once(api, db, booking, booking_id, previous_capture_retry_count)
    return stripe_result


def maybe_enqueue_immediate_auth_timeout(
    api: PaymentTasksFacadeApi,
    booking_id: str,
    hours_until_lesson: float,
    stripe_result: Dict[str, Any],
) -> None:
    if stripe_result.get("success") or hours_until_lesson >= 24:
        return
    try:
        enqueue_task(
            "app.tasks.payment_tasks.check_immediate_auth_timeout",
            args=(booking_id,),
            countdown=30 * 60,
        )
    except Exception:
        api.logger.debug("Non-fatal error ignored", exc_info=True)


def collect_authorization_candidates(
    api: PaymentTasksFacadeApi, db: Session, now: datetime
) -> List[Dict[str, Any]]:
    booking_repo = api.RepositoryFactory.create_booking_repository(db)
    candidates: List[Dict[str, Any]] = []
    for booking in cast(Sequence[Booking], booking_repo.get_bookings_for_payment_authorization()):
        booking_start_utc = api._get_booking_start_utc(booking)
        hours_until_lesson = api.TimezoneService.hours_until(booking_start_utc)
        scheduled_for = getattr(booking.payment_detail, "auth_scheduled_for", None)
        due_for_auth = (
            scheduled_for <= now
            if isinstance(scheduled_for, datetime)
            else 23.5 <= hours_until_lesson <= 24.5
        )
        if (
            getattr(booking.payment_detail, "payment_status", None) == PaymentStatus.SCHEDULED.value
            and due_for_auth
        ):
            candidates.append({"booking_id": booking.id, "hours_until_lesson": hours_until_lesson})
    return candidates


def send_t24_failure_warning_if_needed(
    api: PaymentTasksFacadeApi,
    booking_id: str,
    hours_until_lesson: float,
    auth_result: Dict[str, Any],
) -> None:
    from app.database import SessionLocal

    db_notify: Session = SessionLocal()
    try:
        payment_repo = api.RepositoryFactory.create_payment_repository(db_notify)
        if api.has_event_type(payment_repo, booking_id, "t24_first_failure_email_sent"):
            db_notify.commit()
            return
        repo_notify = api.BookingRepository(db_notify)
        booking_notify = repo_notify.get_by_id(booking_id)
        if not booking_notify:
            db_notify.commit()
            return
        payment = repo_notify.ensure_payment(booking_notify.id)
        if payment.auth_failure_first_email_sent_at is not None:
            db_notify.commit()
            return
        api.NotificationService(db_notify).send_final_payment_warning(
            booking_notify, hours_until_lesson
        )
        payment.auth_failure_first_email_sent_at = api.datetime.now(timezone.utc)
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


def process_authorization_batch(
    api: PaymentTasksFacadeApi,
    booking_data: List[Dict[str, Any]],
    results: AuthorizationJobResults,
) -> AuthorizationJobResults:
    for data in booking_data:
        booking_id = data["booking_id"]
        hours_until_lesson = data["hours_until_lesson"]
        try:
            with api.booking_lock_sync(booking_id) as acquired:
                if not acquired:
                    continue
                auth_result = api._process_authorization_for_booking(booking_id, hours_until_lesson)
            if auth_result.get("skipped"):
                continue
            if auth_result.get("success"):
                results["success"] += 1
                continue
            results["failed"] += 1
            results["failures"].append(
                {
                    "booking_id": booking_id,
                    "error": auth_result.get("error", "Unknown error"),
                    "type": auth_result.get("error_type", "system_error"),
                }
            )
            send_t24_failure_warning_if_needed(api, booking_id, hours_until_lesson, auth_result)
        except Exception as exc:
            api.logger.error("Error processing authorization for booking %s: %s", booking_id, exc)
            results["failed"] += 1
            results["failures"].append(
                {"booking_id": booking_id, "error": str(exc), "type": "system_error"}
            )
    return results


def process_scheduled_authorizations_impl(
    api: PaymentTasksFacadeApi,
) -> AuthorizationJobResults:
    """Process scheduled payment authorizations."""
    from app.database import SessionLocal

    now = api.datetime.now(timezone.utc)
    results: AuthorizationJobResults = {
        "success": 0,
        "failed": 0,
        "failures": [],
        "processed_at": now.isoformat(),
    }
    db_read: Session = SessionLocal()
    try:
        booking_data = collect_authorization_candidates(api, db_read, now)
        db_read.commit()
    finally:
        db_read.close()
    results = process_authorization_batch(api, booking_data, results)
    if results["failed"] > 0:
        api.logger.warning("Authorization job completed with %s failures", results["failed"])
    api.logger.info(
        "Authorization job completed: %s success, %s failed", results["success"], results["failed"]
    )
    return results


def check_immediate_auth_timeout_impl(
    api: PaymentTasksFacadeApi,
    booking_id: str,
) -> Dict[str, Any]:
    """Auto-mark immediate auth failures as payment failed after 30 minutes."""
    from app.database import SessionLocal

    db: Session = SessionLocal()
    now = api.datetime.now(timezone.utc)
    try:
        with api.booking_lock_sync(booking_id) as acquired:
            if not acquired:
                return {"skipped": True}
            booking = api.BookingRepository(db).get_by_id(booking_id)
            if not booking:
                return {"error": "Booking not found"}
            if booking.status in {BookingStatus.CANCELLED, BookingStatus.PAYMENT_FAILED}:
                return {"skipped": True, "reason": "terminal"}
            if booking.status != BookingStatus.PENDING:
                return {"skipped": True, "reason": "not_eligible"}
            payment = booking.payment_detail
            if (
                getattr(payment, "payment_status", None)
                != PaymentStatus.PAYMENT_METHOD_REQUIRED.value
            ):
                return {"resolved": True}
            attempted_at = getattr(payment, "auth_attempted_at", None)
            if (
                isinstance(attempted_at, datetime)
                and (now - attempted_at).total_seconds() < 30 * 60
            ):
                return {"skipped": True, "reason": "retry_window_open"}
            hours_until_lesson = api.TimezoneService.hours_until(
                api._get_booking_start_utc(booking)
            )
            return {
                "payment_failed": api._mark_booking_payment_failed(
                    booking_id,
                    hours_until_lesson,
                    now,
                )
            }
    finally:
        db.close()


def handle_authorization_failure_impl(
    api: PaymentTasksFacadeApi,
    booking: Booking,
    payment_repo: Any,
    error: str,
    error_type: str,
    hours_until_lesson: float,
) -> None:
    """Handle authorization failure by updating status and recording event."""
    from sqlalchemy.orm import object_session as object_session

    db = object_session(booking)
    if db is not None:
        api.BookingRepository(db).ensure_payment(
            booking.id
        ).payment_status = PaymentStatus.PAYMENT_METHOD_REQUIRED.value
    else:
        api.logger.warning(
            "Booking %s has no active session — payment status update skipped. Payment event was still recorded, manual reconciliation may be needed.",
            booking.id,
        )
    payment_repo.create_payment_event(
        booking_id=booking.id,
        event_type="auth_failed",
        event_data={
            "error": error,
            "error_type": error_type,
            "hours_until_lesson": round(hours_until_lesson, 1),
            "failed_at": api.datetime.now(timezone.utc).isoformat(),
        },
    )
    api.logger.error("Failed to authorize payment for booking %s: %s", booking.id, error)
