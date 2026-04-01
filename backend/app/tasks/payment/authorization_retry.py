"""Authorization retry, cancellation, and failure handling."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Sequence, cast

from sqlalchemy.orm import Session

from app.models.booking import Booking, BookingStatus, PaymentStatus
from app.tasks.payment.common import PaymentTasksFacadeApi, RetryJobResults


def cancel_booking_payment_failed_impl(
    api: PaymentTasksFacadeApi,
    booking_id: str,
    hours_until_lesson: float,
    now: datetime,
) -> bool:
    """Cancel a booking due to payment failure."""
    from app.database import SessionLocal

    db: Session = SessionLocal()
    try:
        repo = api.BookingRepository(db)
        booking = repo.get_by_id(booking_id)
        if not booking or booking.status == BookingStatus.CANCELLED:
            return False
        booking.status = BookingStatus.CANCELLED
        booking.student_credit_amount = 0
        booking.refunded_to_card_amount = 0
        booking.cancelled_at = now
        booking.cancellation_reason = "Payment authorization failed after multiple attempts"
        payment = repo.ensure_payment(booking.id)
        payment.payment_status = PaymentStatus.SETTLED.value
        payment.settlement_outcome = "student_cancel_gt24_no_charge"
        payment.instructor_payout_amount = 0
        try:
            from app.services.credit_service import CreditService

            credit_service = CreditService(db)
            credit_service.release_credits_for_booking(booking_id=booking_id, use_transaction=False)
            payment.credits_reserved_cents = 0
        except Exception as exc:
            api.logger.warning(
                "Failed to release reserved credits for booking %s: %s", booking_id, exc
            )
        payment_repo = api.RepositoryFactory.create_payment_repository(db)
        payment_repo.create_payment_event(
            booking_id=booking_id,
            event_type="auth_abandoned",
            event_data={
                "reason": "T-12hr cancellation",
                "hours_until_lesson": round(hours_until_lesson, 1),
                "cancelled_at": now.isoformat(),
            },
        )
        api.NotificationService(db).send_booking_cancelled_payment_failed(booking)
        db.commit()
        api.logger.info(
            "Cancelled booking %s due to payment failure (T-%shr)",
            booking_id,
            f"{hours_until_lesson:.1f}",
        )
        return True
    except Exception as exc:
        api.logger.error("Error cancelling booking %s: %s", booking_id, exc)
        db.rollback()
        return False
    finally:
        db.close()


def load_retry_context(api: PaymentTasksFacadeApi, db: Session, booking_id: str) -> Dict[str, Any]:
    from app.repositories.instructor_profile_repository import InstructorProfileRepository

    booking = api.BookingRepository(db).get_by_id(booking_id)
    if not booking:
        return {"result": {"success": False, "error": "Booking not found"}}
    if booking.status == BookingStatus.CANCELLED:
        return {"result": {"success": False, "skipped": True, "reason": "cancelled"}}
    payment = booking.payment_detail
    if booking.status != BookingStatus.CONFIRMED:
        return {"result": {"success": False, "skipped": True, "reason": "not_eligible"}}
    if getattr(payment, "payment_status", None) != PaymentStatus.PAYMENT_METHOD_REQUIRED.value:
        return {"result": {"success": False, "skipped": True, "reason": "not_eligible"}}
    payment_repo = api.RepositoryFactory.create_payment_repository(db)
    payment_repo.create_payment_event(
        booking_id=booking_id,
        event_type="auth_retry_attempted",
        event_data={"attempted_at": api.datetime.now(timezone.utc).isoformat()},
    )
    if not payment_repo.get_customer_by_user_id(booking.student_id):
        return {
            "result": {
                "success": False,
                "error": f"No Stripe customer for student {booking.student_id}",
            }
        }
    instructor_profile = InstructorProfileRepository(db).get_by_user_id(booking.instructor_id)
    if instructor_profile is None:
        return {
            "result": {
                "success": False,
                "error": f"No instructor profile for {booking.instructor_id}",
            }
        }
    instructor_account = payment_repo.get_connected_account_by_instructor_id(instructor_profile.id)
    if not instructor_account:
        return {
            "result": {
                "success": False,
                "error": f"No Stripe account for instructor {booking.instructor_id}",
            }
        }
    return {"payment_method_id": getattr(payment, "payment_method_id", None)}


def build_retry_credits_only_result(ctx: Any) -> Dict[str, Any]:
    return {
        "success": True,
        "credits_only": True,
        "applied_credit_cents": ctx.applied_credit_cents,
    }


def build_retry_success_result(ctx: Any, payment_intent_id: str | None) -> Dict[str, Any]:
    return {
        "success": True,
        "payment_intent_id": payment_intent_id,
        "student_pay_cents": ctx.student_pay_cents,
        "application_fee_cents": ctx.application_fee_cents,
        "applied_credit_cents": ctx.applied_credit_cents,
    }


def persist_retry_result(
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
    payment = api.BookingRepository(db).ensure_payment(booking.id)
    attempted_at = api.datetime.now(timezone.utc)
    if stripe_result.get("success"):
        payment.payment_intent_id = (
            stripe_result.get("payment_intent_id") or payment.payment_intent_id
        )
        payment.payment_status = PaymentStatus.AUTHORIZED.value
        payment.auth_attempted_at = attempted_at
        payment.auth_failure_count = 0
        payment.auth_last_error = None
        payment_repo.create_payment_event(
            booking_id=booking_id,
            event_type="auth_retry_succeeded",
            event_data={
                "payment_intent_id": stripe_result.get("payment_intent_id"),
                "hours_until_lesson": round(hours_until_lesson, 1),
                "authorized_at": api.datetime.now(timezone.utc).isoformat(),
                "credits_applied_cents": stripe_result.get("applied_credit_cents"),
                "amount_cents": stripe_result.get("student_pay_cents"),
                "application_fee_cents": stripe_result.get("application_fee_cents"),
            },
        )
        api.logger.info(
            "Successfully retried authorization for booking %s (T-%shr)",
            booking_id,
            f"{hours_until_lesson:.1f}",
        )
    else:
        payment.payment_status = PaymentStatus.PAYMENT_METHOD_REQUIRED.value
        payment.auth_attempted_at = attempted_at
        payment.auth_failure_count = int(getattr(payment, "auth_failure_count", 0) or 0) + 1
        payment.auth_last_error = stripe_result.get("error")
        payment_repo.create_payment_event(
            booking_id=booking_id,
            event_type="auth_retry_failed",
            event_data={
                "error": stripe_result.get("error"),
                "hours_until_lesson": round(hours_until_lesson, 1),
                "failed_at": api.datetime.now(timezone.utc).isoformat(),
            },
        )
        api.logger.error("Retry failed for booking %s: %s", booking_id, stripe_result.get("error"))
    db.commit()
    return stripe_result


def _run_retry_warning(
    api: PaymentTasksFacadeApi,
    booking_id: str,
    hours_until_lesson: float,
    now: datetime,
) -> bool:
    from app.database import SessionLocal

    db_warn: Session = SessionLocal()
    try:
        repo = api.BookingRepository(db_warn)
        booking = repo.get_by_id(booking_id)
        payment = booking.payment_detail if booking else None
        if not booking or booking.status != BookingStatus.CONFIRMED:
            db_warn.commit()
            return False
        if getattr(payment, "payment_status", None) != PaymentStatus.PAYMENT_METHOD_REQUIRED.value:
            db_warn.commit()
            return False
        if getattr(payment, "capture_failed_at", None) is not None:
            db_warn.commit()
            return False
        payment_record = repo.ensure_payment(booking.id)
        if payment_record.auth_failure_t13_warning_sent_at is not None:
            db_warn.commit()
            return False
        api.NotificationService(db_warn).send_final_payment_warning(booking, hours_until_lesson)
        payment_record.auth_failure_t13_warning_sent_at = now
        api.RepositoryFactory.create_payment_repository(db_warn).create_payment_event(
            booking_id=booking_id,
            event_type="final_warning_sent",
            event_data={
                "hours_until_lesson": round(hours_until_lesson, 1),
                "sent_at": now.isoformat(),
            },
        )
        db_warn.commit()
        return True
    finally:
        db_warn.close()


def plan_retry_actions(
    api: PaymentTasksFacadeApi, db: Session, now: datetime
) -> List[Dict[str, Any]]:
    booking_repo = api.RepositoryFactory.create_booking_repository(db)
    payment_repo = api.RepositoryFactory.create_payment_repository(db)
    actions: List[Dict[str, Any]] = []
    for booking in cast(Sequence[Booking], booking_repo.get_bookings_for_payment_retry()):
        hours_until_lesson = api.TimezoneService.hours_until(api._get_booking_start_utc(booking))
        if hours_until_lesson < 0:
            continue
        if hours_until_lesson <= 12:
            actions.append(
                {
                    "booking_id": booking.id,
                    "hours_until_lesson": hours_until_lesson,
                    "action": "cancel",
                }
            )
            continue
        should_retry = api._should_retry_auth(booking, now)
        if hours_until_lesson <= 13:
            if not api.has_event_type(payment_repo, booking.id, "final_warning_sent"):
                actions.append(
                    {
                        "booking_id": booking.id,
                        "hours_until_lesson": hours_until_lesson,
                        "action": "warn_only",
                    }
                )
            if should_retry:
                actions.append(
                    {
                        "booking_id": booking.id,
                        "hours_until_lesson": hours_until_lesson,
                        "action": "retry_with_warning",
                    }
                )
            continue
        if should_retry:
            actions.append(
                {
                    "booking_id": booking.id,
                    "hours_until_lesson": hours_until_lesson,
                    "action": "silent_retry",
                }
            )
    return actions


def _run_retry_action(
    api: PaymentTasksFacadeApi,
    action_data: Dict[str, Any],
    now: datetime,
    results: RetryJobResults,
) -> None:
    booking_id = action_data["booking_id"]
    hours_until_lesson = action_data["hours_until_lesson"]
    action = action_data["action"]
    with api.booking_lock_sync(booking_id) as acquired:
        if not acquired:
            return
        if action == "cancel":
            results["cancelled"] += int(
                api._cancel_booking_payment_failed(booking_id, hours_until_lesson, now)
            )
            return
        if action == "warn_only":
            results["warnings_sent"] += int(
                _run_retry_warning(api, booking_id, hours_until_lesson, now)
            )
            return
        retry_result = api._process_retry_authorization(booking_id, hours_until_lesson)
        if retry_result.get("skipped"):
            return
        results["retried"] += 1
        results["success" if retry_result.get("success") else "failed"] += 1


def retry_failed_authorizations_impl(api: PaymentTasksFacadeApi) -> RetryJobResults:
    """Retry failed payment authorizations."""
    from app.database import SessionLocal

    now = api.datetime.now(timezone.utc)
    results: RetryJobResults = {
        "retried": 0,
        "success": 0,
        "failed": 0,
        "cancelled": 0,
        "warnings_sent": 0,
        "processed_at": now.isoformat(),
    }
    db_read: Session = SessionLocal()
    try:
        booking_actions = plan_retry_actions(api, db_read, now)
        db_read.commit()
    finally:
        db_read.close()
    for action_data in booking_actions:
        try:
            _run_retry_action(api, action_data, now, results)
        except Exception as exc:
            api.logger.error(
                "Error processing retry for booking %s: %s", action_data["booking_id"], exc
            )
            results["failed"] += 1
    api.logger.info(
        "Retry job completed: %s attempted, %s success, %s failed, %s cancelled, %s warnings sent",
        results["retried"],
        results["success"],
        results["failed"],
        results["cancelled"],
        results["warnings_sent"],
    )
    return results


def resolve_retry_accounts(
    booking: Booking,
    payment_repo: Any,
    db: Session,
) -> None:
    from app.repositories.instructor_profile_repository import InstructorProfileRepository

    student_customer = payment_repo.get_customer_by_user_id(booking.student_id)
    if not student_customer:
        raise Exception(f"No Stripe customer for student {booking.student_id}")
    instructor_profile = InstructorProfileRepository(db).get_by_user_id(booking.instructor_id)
    instructor_account = payment_repo.get_connected_account_by_instructor_id(
        instructor_profile.id if instructor_profile else None
    )
    if not instructor_account:
        raise Exception(f"No Stripe account for instructor {booking.instructor_id}")


def _record_attempt_event(
    api: PaymentTasksFacadeApi,
    booking: Booking,
    payment_repo: Any,
    hours_until_lesson: float,
) -> None:
    payment_repo.create_payment_event(
        booking_id=booking.id,
        event_type="auth_retry_attempted",
        event_data={
            "hours_until_lesson": round(hours_until_lesson, 1),
            "attempted_at": api.datetime.now(timezone.utc).isoformat(),
        },
    )


def _record_retry_success(
    api: PaymentTasksFacadeApi,
    booking: Booking,
    payment_repo: Any,
    payment: Any,
    hours_until_lesson: float,
    ctx: Any,
) -> None:
    payment.payment_status = PaymentStatus.AUTHORIZED.value
    payment_repo.create_payment_event(
        booking_id=booking.id,
        event_type="auth_retry_succeeded",
        event_data={
            "payment_intent_id": payment.payment_intent_id,
            "hours_until_lesson": round(hours_until_lesson, 1),
            "authorized_at": api.datetime.now(timezone.utc).isoformat(),
            "credits_applied_cents": ctx.applied_credit_cents,
            "amount_cents": ctx.student_pay_cents if ctx.student_pay_cents > 0 else None,
            "application_fee_cents": ctx.application_fee_cents
            if ctx.student_pay_cents > 0
            else None,
        },
    )


def _record_retry_failure(
    api: PaymentTasksFacadeApi,
    booking: Booking,
    payment_repo: Any,
    payment: Any,
    hours_until_lesson: float,
    exc: Exception,
) -> None:
    payment.payment_status = PaymentStatus.PAYMENT_METHOD_REQUIRED.value
    payment_repo.create_payment_event(
        booking_id=booking.id,
        event_type="auth_retry_failed",
        event_data={
            "error": str(exc),
            "hours_until_lesson": round(hours_until_lesson, 1),
            "failed_at": api.datetime.now(timezone.utc).isoformat(),
        },
    )
    api.logger.error("Retry failed for booking %s: %s", booking.id, exc)


def attempt_authorization_retry_impl(
    api: PaymentTasksFacadeApi,
    booking: Booking,
    payment_repo: Any,
    db: Session,
    hours_until_lesson: float,
    stripe_service: Any,
) -> bool:
    """Attempt to retry authorization for a booking."""
    payment = api.BookingRepository(db).ensure_payment(booking.id)
    try:
        _record_attempt_event(api, booking, payment_repo, hours_until_lesson)
        resolve_retry_accounts(booking, payment_repo, db)
        ctx = stripe_service.build_charge_context(
            booking_id=booking.id, requested_credit_cents=None
        )
        if ctx.student_pay_cents > 0:
            payment_intent = stripe_service.create_or_retry_booking_payment_intent(
                booking_id=booking.id,
                payment_method_id=payment.payment_method_id,
                requested_credit_cents=None,
            )
            payment.payment_intent_id = getattr(payment_intent, "id", None)
        _record_retry_success(api, booking, payment_repo, payment, hours_until_lesson, ctx)
        api.logger.info(
            "Successfully retried authorization for booking %s (T-%shr)",
            booking.id,
            f"{hours_until_lesson:.1f}",
        )
        return True
    except Exception as exc:
        _record_retry_failure(api, booking, payment_repo, payment, hours_until_lesson, exc)
        return False
