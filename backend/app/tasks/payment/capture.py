"""Payment capture core helpers."""

from __future__ import annotations

from datetime import timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.core.exceptions import RepositoryException
from app.models.booking import Booking, BookingStatus, PaymentStatus
from app.tasks.payment.common import PaymentTasksFacadeApi


def load_capture_context(
    api: PaymentTasksFacadeApi,
    db: Session,
    booking_id: str,
    capture_reason: str,
) -> Dict[str, Any]:
    booking = api.BookingRepository(db).get_by_id(booking_id)
    if not booking:
        return {"result": {"success": False, "error": "Booking not found"}}
    if booking.status in {BookingStatus.CANCELLED, BookingStatus.PAYMENT_FAILED}:
        return {"result": {"success": True, "skipped": True, "reason": "terminal"}}
    if getattr(booking, "has_locked_funds", False) is True and booking.rescheduled_from_booking_id:
        return {"locked_booking_id": booking.rescheduled_from_booking_id}
    payment = booking.payment_detail
    payment_intent_id = getattr(payment, "payment_intent_id", None)
    if not payment_intent_id:
        return {"result": {"success": False, "error": "No payment_intent_id"}}
    current_status = getattr(payment, "payment_status", None)
    if current_status == PaymentStatus.MANUAL_REVIEW.value:
        return {"result": {"success": True, "skipped": True, "reason": "disputed"}}
    if current_status == PaymentStatus.SETTLED.value:
        return {"result": {"success": True, "already_captured": True}}
    eligible_statuses = {PaymentStatus.AUTHORIZED.value}
    if capture_reason == "retry_failed_capture":
        eligible_statuses.add(PaymentStatus.PAYMENT_METHOD_REQUIRED.value)
    if current_status not in eligible_statuses:
        return {"result": {"success": True, "skipped": True, "reason": "not_eligible"}}
    if (
        current_status == PaymentStatus.PAYMENT_METHOD_REQUIRED.value
        and getattr(payment, "capture_failed_at", None) is None
    ):
        return {"result": {"success": True, "skipped": True, "reason": "not_capture_failure"}}
    return {"payment_intent_id": payment_intent_id}


def build_capture_success_result(
    payment_intent_id: str,
    capture_payload: Any,
) -> Dict[str, Any]:
    payment_intent = (
        capture_payload.get("payment_intent")
        if isinstance(capture_payload, dict)
        else capture_payload
    )
    amount_received = (
        capture_payload.get("amount_received") if isinstance(capture_payload, dict) else None
    )
    transfer_id = capture_payload.get("transfer_id") if isinstance(capture_payload, dict) else None
    if amount_received is None and payment_intent is not None:
        amount_received = getattr(payment_intent, "amount_received", None)
    if amount_received is None and payment_intent is not None:
        amount_received = getattr(payment_intent, "amount", None)
    return {
        "success": True,
        "amount_received": amount_received,
        "payment_intent_id": payment_intent_id,
        "transfer_id": transfer_id,
    }


def classify_capture_exception(api: PaymentTasksFacadeApi, exc: Exception) -> Dict[str, Any]:
    if isinstance(exc, api.stripe.error.InvalidRequestError):
        error_code = exc.code if hasattr(exc, "code") else None
        if "already been captured" in str(exc).lower():
            return {"success": True, "already_captured": True}
        if "expired" in str(exc).lower() or error_code == "payment_intent_unexpected_state":
            return {"success": False, "expired": True, "error": str(exc)}
        return {"success": False, "error": str(exc), "error_code": error_code}
    if isinstance(exc, api.stripe.error.CardError):
        return {
            "success": False,
            "card_error": True,
            "error": str(exc),
            "error_code": exc.code if hasattr(exc, "code") else None,
        }
    return {"success": False, "error": str(exc)}


def notify_capture_failure_once(
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


def resolve_payout_cents(
    api: PaymentTasksFacadeApi, payment_repo: Any, booking_id: str
) -> Optional[int]:
    try:
        payment_record = payment_repo.get_payment_by_booking_id(booking_id)
    except RepositoryException:
        api.logger.warning(
            "Failed to load payment record for booking %s during capture", booking_id, exc_info=True
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


def _persist_capture_success(
    api: PaymentTasksFacadeApi,
    db: Session,
    booking: Booking,
    payment: Any,
    payment_repo: Any,
    booking_id: str,
    capture_reason: str,
    stripe_result: Dict[str, Any],
) -> None:
    from app.services.credit_service import CreditService

    payment.payment_status = PaymentStatus.SETTLED.value
    if stripe_result.get("transfer_id"):
        db_booking = api.BookingRepository(db)
        db_booking.ensure_transfer(booking.id).stripe_transfer_id = stripe_result.get("transfer_id")
    try:
        CreditService(db).forfeit_credits_for_booking(booking_id=booking_id, use_transaction=False)
        payment.credits_reserved_cents = 0
    except Exception as exc:
        api.logger.warning("Failed to forfeit reserved credits for booking %s: %s", booking_id, exc)
    if booking.status == BookingStatus.COMPLETED:
        payment.settlement_outcome = "lesson_completed_full_payout"
        booking.student_credit_amount = 0
        payment.instructor_payout_amount = resolve_payout_cents(api, payment_repo, booking_id)
        booking.refunded_to_card_amount = 0
    payment_repo.create_payment_event(
        booking_id=booking_id,
        event_type="payment_captured",
        event_data={
            "payment_intent_id": stripe_result.get("payment_intent_id"),
            "amount_captured_cents": stripe_result.get("amount_received"),
            "capture_reason": capture_reason,
            "captured_at": api.datetime.now(timezone.utc).isoformat(),
        },
    )
    api.logger.info(
        "Successfully captured payment for booking %s (reason: %s)", booking_id, capture_reason
    )


def _persist_capture_failure(
    api: PaymentTasksFacadeApi,
    booking: Booking,
    payment: Any,
    payment_repo: Any,
    booking_id: str,
    capture_reason: str,
    payment_intent_id: str,
    stripe_result: Dict[str, Any],
) -> None:
    event_type = "capture_failed"
    if stripe_result.get("expired"):
        event_type = "capture_failed_expired"
    elif stripe_result.get("card_error"):
        event_type = "capture_failed_card"
    payment.payment_status = PaymentStatus.PAYMENT_METHOD_REQUIRED.value
    payment.capture_failed_at = api.datetime.now(timezone.utc)
    payment.capture_retry_count = int(getattr(payment, "capture_retry_count", 0) or 0) + 1
    payment.capture_error = stripe_result.get("error")
    payment_repo.create_payment_event(
        booking_id=booking_id,
        event_type=event_type,
        event_data={
            "payment_intent_id": payment_intent_id,
            "error": stripe_result.get("error"),
            "error_code": stripe_result.get("error_code"),
            "capture_reason": capture_reason,
        },
    )
    if event_type == "capture_failed":
        api.logger.error(
            "Failed to capture payment for booking %s: %s", booking_id, stripe_result.get("error")
        )


def persist_capture_result(
    api: PaymentTasksFacadeApi,
    db: Session,
    booking_id: str,
    capture_reason: str,
    payment_intent_id: str,
    stripe_result: Dict[str, Any],
) -> Dict[str, Any]:
    booking_repo = api.BookingRepository(db)
    booking = booking_repo.get_by_id(booking_id)
    if not booking:
        return {"success": False, "error": "Booking not found in Phase 3"}
    payment = booking_repo.ensure_payment(booking.id)
    payment_repo = api.RepositoryFactory.create_payment_repository(db)
    previous_capture_retry_count = int(getattr(payment, "capture_retry_count", 0) or 0)
    if stripe_result.get("success"):
        _persist_capture_success(
            api, db, booking, payment, payment_repo, booking_id, capture_reason, stripe_result
        )
    else:
        _persist_capture_failure(
            api,
            booking,
            payment,
            payment_repo,
            booking_id,
            capture_reason,
            payment_intent_id,
            stripe_result,
        )
        notify_capture_failure_once(api, db, booking, booking_id, previous_capture_retry_count)
    db.commit()
    return stripe_result


def attempt_stripe_capture(
    api: PaymentTasksFacadeApi,
    booking: Booking,
    capture_reason: str,
    stripe_service: Any,
) -> Dict[str, Any]:
    payment = booking.payment_detail
    if getattr(payment, "payment_status", None) in {
        PaymentStatus.SETTLED.value,
        PaymentStatus.LOCKED.value,
    }:
        api.logger.info("Payment already captured for booking %s", booking.id)
        return {"success": True, "already_captured": True, "record_event": False}
    intent_id = getattr(payment, "payment_intent_id", None)
    if not intent_id:
        api.logger.warning("No payment_intent_id for booking %s — skipping capture", booking.id)
        return {"success": False, "error": "missing_payment_intent"}
    idempotency_key = f"capture_{capture_reason}_{booking.id}_{intent_id}"
    try:
        capture_payload = stripe_service.capture_booking_payment_intent(
            booking_id=booking.id,
            payment_intent_id=intent_id,
            idempotency_key=idempotency_key,
        )
        return build_capture_success_result(intent_id, capture_payload)
    except Exception as exc:
        capture_result = classify_capture_exception(api, exc)
        if capture_result.get("already_captured"):
            capture_result["record_event"] = True
        return capture_result


def _record_capture_success(
    api: PaymentTasksFacadeApi,
    booking: Booking,
    payment_repo: Any,
    payment: Any,
    capture_reason: str,
    capture_result: Dict[str, Any],
) -> Dict[str, Any]:
    payment.payment_status = PaymentStatus.SETTLED.value
    payment.capture_failed_at = None
    payment.capture_retry_count = 0
    payment_repo.create_payment_event(
        booking_id=booking.id,
        event_type="payment_captured",
        event_data={
            "payment_intent_id": getattr(payment, "payment_intent_id", None),
            "amount_captured_cents": capture_result.get("amount_received"),
            "capture_reason": capture_reason,
            "captured_at": api.datetime.now(timezone.utc).isoformat(),
        },
    )
    api.logger.info(
        "Successfully captured payment for booking %s (reason: %s)", booking.id, capture_reason
    )
    return {"success": True}


def _record_capture_failure(
    api: PaymentTasksFacadeApi,
    booking: Booking,
    payment_repo: Any,
    payment: Any,
    capture_reason: str,
    capture_result: Dict[str, Any],
    *,
    persist_state: bool,
) -> Dict[str, Any]:
    if persist_state:
        payment.payment_status = PaymentStatus.PAYMENT_METHOD_REQUIRED.value
        payment.capture_failed_at = api.datetime.now(timezone.utc)
        payment.capture_retry_count = int(getattr(payment, "capture_retry_count", 0) or 0) + 1
    event_type = "capture_failed_card" if capture_result.get("card_error") else "capture_failed"
    if capture_result.get("expired"):
        event_type = "capture_failed_expired"
    payment_repo.create_payment_event(
        booking_id=booking.id,
        event_type=event_type,
        event_data={
            "payment_intent_id": getattr(payment, "payment_intent_id", None),
            "error": capture_result.get("error"),
            "error_code": capture_result.get("error_code"),
            "capture_reason": capture_reason,
        },
    )
    api.logger.error(
        "Failed to capture payment for booking %s: %s", booking.id, capture_result.get("error")
    )
    response: Dict[str, Any] = {"success": False}
    if capture_result.get("expired"):
        response["expired"] = True
        return response
    if capture_result.get("card_error"):
        response["card_error"] = True
        return response
    if capture_result.get("error") is not None:
        response["error"] = capture_result.get("error")
    return response


def attempt_payment_capture_impl(
    api: PaymentTasksFacadeApi,
    booking: Booking,
    payment_repo: Any,
    capture_reason: str,
    stripe_service: Any,
) -> Dict[str, Any]:
    """Attempt to capture a payment for a booking."""
    from sqlalchemy.orm import object_session as object_session

    db = object_session(booking)
    payment = api.BookingRepository(db).ensure_payment(booking.id) if db else booking.payment_detail
    capture_result = attempt_stripe_capture(api, booking, capture_reason, stripe_service)
    if capture_result.get("error") == "missing_payment_intent":
        return {"success": False, "error": "missing_payment_intent"}
    if capture_result.get("success"):
        if capture_result.get("already_captured"):
            if db:
                payment.payment_status = PaymentStatus.SETTLED.value
                payment.capture_failed_at = None
                payment.capture_retry_count = 0
            if capture_result.get("record_event"):
                payment_repo.create_payment_event(
                    booking_id=booking.id,
                    event_type="capture_already_done",
                    event_data={
                        "payment_intent_id": getattr(payment, "payment_intent_id", None),
                        "error": "already captured",
                    },
                )
            return {"success": True, "already_captured": True}
        return _record_capture_success(
            api, booking, payment_repo, payment, capture_reason, capture_result
        )
    return _record_capture_failure(
        api,
        booking,
        payment_repo,
        payment,
        capture_reason,
        capture_result,
        persist_state=db is not None,
    )
