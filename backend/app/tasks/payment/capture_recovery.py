"""Capture retry and escalation helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, cast

from sqlalchemy.orm import Session

from app.core.exceptions import RepositoryException
from app.models.booking import PaymentStatus
from app.tasks.payment.common import CaptureRetryResults, PaymentTasksFacadeApi


def load_escalation_context(
    api: PaymentTasksFacadeApi,
    db: Session,
    booking_id: str,
) -> Dict[str, Any]:
    booking = api.BookingRepository(db).get_by_id(booking_id)
    if not booking:
        return {}
    payment_repo = api.RepositoryFactory.create_payment_repository(db)
    instructor_repo = api.RepositoryFactory.create_instructor_profile_repository(db)
    payout_cents = None
    try:
        payment_record = payment_repo.get_payment_by_booking_id(booking.id)
    except RepositoryException:
        api.logger.warning(
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
        pricing = api.PricingService(db).compute_booking_pricing(
            booking_id=booking.id,
            applied_credit_cents=0,
        )
        payout_cents = int(pricing.get("target_instructor_payout_cents", 0) or 0)
    instructor_account_id = None
    instructor_profile = instructor_repo.get_by_user_id(booking.instructor_id)
    if instructor_profile:
        account = payment_repo.get_connected_account_by_instructor_id(instructor_profile.id)
        if account and account.stripe_account_id:
            instructor_account_id = account.stripe_account_id
    return {
        "booking": booking,
        "payout_cents": payout_cents,
        "instructor_account_id": instructor_account_id,
    }


def attempt_manual_transfer(
    api: PaymentTasksFacadeApi,
    booking_id: str,
    instructor_account_id: str | None,
    payout_cents: int | None,
) -> Dict[str, Any]:
    from app.database import SessionLocal

    if not instructor_account_id or not payout_cents:
        return {"transfer_id": None, "transfer_error": None}
    db_stripe: Session = SessionLocal()
    try:
        stripe_service = api.StripeService(
            db_stripe,
            config_service=api.ConfigService(db_stripe),
            pricing_service=api.PricingService(db_stripe),
        )
        transfer_result = stripe_service.create_manual_transfer(
            booking_id=booking_id,
            destination_account_id=instructor_account_id,
            amount_cents=int(payout_cents),
            idempotency_key=f"capture_failure_payout_{booking_id}",
            metadata={"reason": "capture_failure_escalated"},
        )
        db_stripe.commit()
        return {"transfer_id": transfer_result.get("transfer_id"), "transfer_error": None}
    except Exception as exc:
        return {"transfer_id": None, "transfer_error": str(exc)}
    finally:
        db_stripe.close()


def persist_capture_escalation(
    api: PaymentTasksFacadeApi,
    db: Session,
    booking_id: str,
    now: datetime,
    payout_cents: int | None,
    transfer_result: Dict[str, Any],
) -> None:
    booking_repo = api.BookingRepository(db)
    booking = booking_repo.get_by_id(booking_id)
    if not booking:
        return
    payment = booking_repo.ensure_payment(booking.id)
    payment.payment_status = PaymentStatus.MANUAL_REVIEW.value
    payment.settlement_outcome = (
        "capture_failure_instructor_paid"
        if transfer_result["transfer_id"]
        else "capture_failure_escalated"
    )
    payment.capture_escalated_at = now
    payment.instructor_payout_amount = (
        int(payout_cents or 0) if transfer_result["transfer_id"] else 0
    )
    booking.student_credit_amount = 0
    booking.refunded_to_card_amount = 0
    transfer_record = booking_repo.ensure_transfer(booking.id)
    if transfer_result["transfer_id"]:
        transfer_record.advanced_payout_transfer_id = transfer_result["transfer_id"]
        transfer_record.payout_transfer_id = transfer_result["transfer_id"]
        transfer_record.stripe_transfer_id = transfer_result["transfer_id"]
    else:
        transfer_record.payout_transfer_failed_at = now
        transfer_record.payout_transfer_error = transfer_result["transfer_error"]
        transfer_record.payout_transfer_retry_count = (
            int(getattr(transfer_record, "payout_transfer_retry_count", 0) or 0) + 1
        )
        transfer_record.transfer_failed_at = transfer_record.payout_transfer_failed_at
        transfer_record.transfer_error = transfer_record.payout_transfer_error
        transfer_record.transfer_retry_count = (
            int(getattr(transfer_record, "transfer_retry_count", 0) or 0) + 1
        )
    api.RepositoryFactory.create_user_repository(db).lock_account(
        booking.student_id,
        f"capture_failure_escalated:{booking.id}",
    )
    api.RepositoryFactory.create_payment_repository(db).create_payment_event(
        booking_id=booking.id,
        event_type="capture_failure_escalated",
        event_data={
            "hours_since_failure": 72,
            "transfer_id": transfer_result["transfer_id"],
            "transfer_error": transfer_result["transfer_error"],
            "student_locked": True,
        },
    )
    db.commit()


def escalate_capture_failure_impl(
    api: PaymentTasksFacadeApi,
    booking_id: str,
    now: datetime,
) -> None:
    """Escalate capture failure after retry window expires."""
    from app.database import SessionLocal

    db_read: Session = SessionLocal()
    try:
        escalation_context = load_escalation_context(api, db_read, booking_id)
    finally:
        db_read.close()
    transfer_result = attempt_manual_transfer(
        api,
        booking_id,
        escalation_context.get("instructor_account_id"),
        escalation_context.get("payout_cents"),
    )
    db_write: Session = SessionLocal()
    try:
        persist_capture_escalation(
            api,
            db_write,
            booking_id,
            now,
            escalation_context.get("payout_cents"),
            transfer_result,
        )
    finally:
        db_write.close()


def retry_failed_captures_impl(api: PaymentTasksFacadeApi) -> CaptureRetryResults:
    """Retry failed captures every 4 hours and escalate after 72 hours."""
    from app.database import SessionLocal

    now = api.datetime.now(timezone.utc)
    results: CaptureRetryResults = {
        "retried": 0,
        "succeeded": 0,
        "escalated": 0,
        "skipped": 0,
        "processed_at": now.isoformat(),
    }
    db_read: Session = SessionLocal()
    try:
        booking_ids = api.BookingRepository(db_read).get_failed_capture_booking_ids()
    finally:
        db_read.close()
    for booking_id in booking_ids:
        try:
            with api.booking_lock_sync(booking_id) as acquired:
                if not acquired:
                    results["skipped"] += 1
                    continue
                db_check: Session = SessionLocal()
                try:
                    booking = api.BookingRepository(db_check).get_by_id(booking_id)
                    if not booking:
                        results["skipped"] += 1
                        continue
                    payment = booking.payment_detail
                    if (
                        getattr(payment, "payment_status", None)
                        != PaymentStatus.PAYMENT_METHOD_REQUIRED.value
                    ):
                        results["skipped"] += 1
                        continue
                    if getattr(payment, "capture_failed_at", None) is None:
                        results["skipped"] += 1
                        continue
                    hours_since_failure = (
                        now - cast(datetime, payment.capture_failed_at)
                    ).total_seconds() / 3600
                    if hours_since_failure >= 72:
                        api._escalate_capture_failure(booking_id, now)
                        results["escalated"] += 1
                        continue
                    if not api._should_retry_capture(booking, now):
                        results["skipped"] += 1
                        continue
                finally:
                    db_check.close()
                retry_result = api._process_capture_for_booking(booking_id, "retry_failed_capture")
                if retry_result.get("skipped"):
                    results["skipped"] += 1
                    continue
                results["retried"] += 1
                if retry_result.get("success") or retry_result.get("already_captured"):
                    results["succeeded"] += 1
        except Exception as exc:
            api.logger.error("Capture retry failed for booking %s: %s", booking_id, exc)
    return results
