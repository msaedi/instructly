"""Capture reauthorization helpers."""

from __future__ import annotations

from datetime import timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.core.exceptions import RepositoryException
from app.models.booking import Booking, BookingStatus, PaymentStatus
from app.tasks.payment.common import PaymentTasksFacadeApi


def run_reauth_lock_guard(
    api: PaymentTasksFacadeApi,
    booking: Booking,
    payment_repo: Any,
    db: Session,
    lock_acquired: bool,
) -> Dict[str, Any] | None:
    if lock_acquired:
        return None
    with api.booking_lock_sync(booking.id) as acquired:
        if not acquired:
            return {"success": False, "skipped": True, "error": "lock_unavailable"}
        return api.create_new_authorization_and_capture(
            booking,
            payment_repo,
            db,
            lock_acquired=True,
        )


def run_reauthorization(
    api: PaymentTasksFacadeApi,
    booking: Booking,
    payment: Any,
) -> Dict[str, Any]:
    from app.database import SessionLocal

    db_stripe: Session = SessionLocal()
    try:
        stripe_service = api.StripeService(
            db_stripe,
            config_service=api.ConfigService(db_stripe),
            pricing_service=api.PricingService(db_stripe),
        )
        new_intent = stripe_service.create_or_retry_booking_payment_intent(
            booking_id=booking.id,
            payment_method_id=payment.payment_method_id,
        )
        intent_id = getattr(new_intent, "id", None) or (
            new_intent.get("id") if isinstance(new_intent, dict) else None
        )
        resolved_intent_id = intent_id or payment.payment_intent_id
        if not resolved_intent_id:
            raise Exception(f"No payment intent id after reauthorization for booking {booking.id}")
        capture_result = stripe_service.capture_booking_payment_intent(
            booking_id=booking.id,
            payment_intent_id=str(resolved_intent_id),
            idempotency_key=f"capture_reauth_{booking.id}_{resolved_intent_id}",
        )
        db_stripe.commit()
        return {"resolved_intent_id": str(resolved_intent_id), "capture_result": capture_result}
    finally:
        db_stripe.close()


def resolve_reauth_payout_cents(
    api: PaymentTasksFacadeApi,
    payment_repo: Any,
    booking_id: str,
) -> Optional[int]:
    try:
        payment_record = payment_repo.get_payment_by_booking_id(booking_id)
    except RepositoryException:
        api.logger.warning(
            "Failed to load payment record for booking %s during reauth",
            booking_id,
            exc_info=True,
        )
        return None
    payout_value = (
        getattr(payment_record, "instructor_payout_cents", None) if payment_record else None
    )
    if payout_value is None:
        return None
    try:
        return int(payout_value)
    except (TypeError, ValueError):
        return None


def persist_reauth_capture_result(
    api: PaymentTasksFacadeApi,
    db: Session,
    booking: Booking,
    payment_repo: Any,
    payment: Any,
    original_intent_id: str | None,
    reauth_result: Dict[str, Any],
) -> Dict[str, Any]:
    from app.services.credit_service import CreditService

    payment.payment_status = PaymentStatus.SETTLED.value
    payment.payment_intent_id = reauth_result["resolved_intent_id"]
    try:
        CreditService(db).forfeit_credits_for_booking(
            booking_id=booking.id,
            use_transaction=False,
        )
        payment.credits_reserved_cents = 0
    except Exception as exc:
        api.logger.warning("Failed to forfeit reserved credits for booking %s: %s", booking.id, exc)
    if booking.status == BookingStatus.COMPLETED:
        payment.settlement_outcome = "lesson_completed_full_payout"
        booking.student_credit_amount = 0
        payment.instructor_payout_amount = resolve_reauth_payout_cents(
            api, payment_repo, booking.id
        )
        booking.refunded_to_card_amount = 0
    payment_repo.create_payment_event(
        booking_id=booking.id,
        event_type="reauth_and_capture_success",
        event_data={
            "new_payment_intent_id": reauth_result["resolved_intent_id"],
            "original_payment_intent_id": original_intent_id,
            "amount_captured_cents": reauth_result["capture_result"].get("amount_received"),
            "top_up_transfer_cents": reauth_result["capture_result"].get("top_up_transfer_cents"),
            "captured_at": api.datetime.now(timezone.utc).isoformat(),
        },
    )
    api.logger.info("Successfully created new auth and captured for booking %s", booking.id)
    return {"success": True}


def persist_reauth_capture_failure(
    api: PaymentTasksFacadeApi,
    booking: Booking,
    payment_repo: Any,
    original_intent_id: str | None,
    exc: Exception,
    payment: Any,
) -> Dict[str, Any]:
    payment_repo.create_payment_event(
        booking_id=booking.id,
        event_type="reauth_and_capture_failed",
        event_data={
            "error": str(exc),
            "original_payment_intent_id": original_intent_id
            or getattr(payment, "payment_intent_id", None),
        },
    )
    api.logger.error("Failed to reauth and capture for booking %s: %s", booking.id, exc)
    return {"success": False, "error": str(exc)}


def create_new_authorization_and_capture_impl(
    api: PaymentTasksFacadeApi,
    booking: Booking,
    payment_repo: Any,
    db: Session,
    *,
    lock_acquired: bool = False,
) -> Dict[str, Any]:
    """Create a new authorization and immediately capture for expired authorizations."""
    guard_result = run_reauth_lock_guard(api, booking, payment_repo, db, lock_acquired)
    if guard_result is not None:
        return guard_result
    payment = api.BookingRepository(db).ensure_payment(booking.id)
    original_intent_id = payment.payment_intent_id
    try:
        db.commit()
    except Exception:
        api.logger.error("Pre-capture commit failed for booking %s", booking.id, exc_info=True)
        return {"success": False, "error": "pre_capture_commit_failed"}
    try:
        reauth_result = run_reauthorization(api, booking, payment)
        return persist_reauth_capture_result(
            api,
            db,
            booking,
            payment_repo,
            payment,
            original_intent_id,
            reauth_result,
        )
    except Exception as exc:
        return persist_reauth_capture_failure(
            api,
            booking,
            payment_repo,
            original_intent_id,
            exc,
            payment,
        )
