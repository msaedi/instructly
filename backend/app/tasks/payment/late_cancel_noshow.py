"""Late cancellation capture and no-show resolution."""

from __future__ import annotations

from datetime import timedelta, timezone
from typing import Any, Dict, Union

from sqlalchemy.orm import Session

from app.database import get_db_session
from app.models.booking import PaymentStatus
from app.tasks.payment.common import NoShowResolutionResults, PaymentTasksFacadeApi


def load_late_cancel_context(
    api: PaymentTasksFacadeApi,
    db: Session,
    booking_id: Union[int, str],
) -> Dict[str, Any]:
    payment_repo = api.RepositoryFactory.create_payment_repository(db)
    stripe_service = api.StripeService(
        db,
        config_service=api.ConfigService(db),
        pricing_service=api.PricingService(db),
    )
    booking_repo = api.RepositoryFactory.create_booking_repository(db)
    booking = booking_repo.get_by_id(str(booking_id))
    return {
        "db": db,
        "payment_repo": payment_repo,
        "stripe_service": stripe_service,
        "booking_repo": booking_repo,
        "booking": booking,
        "now": api.datetime.now(timezone.utc),
    }


def validate_late_cancel_window(
    api: PaymentTasksFacadeApi,
    context: Dict[str, Any],
    booking_id: Union[int, str],
) -> Dict[str, Any]:
    booking = context["booking"]
    if not booking:
        api.logger.error("Booking %s not found for late cancellation capture", booking_id)
        return {"success": False, "error": "Booking not found"}
    booking_start_utc = api._get_booking_start_utc(booking)
    hours_until_lesson = api.TimezoneService.hours_until(booking_start_utc)
    if hours_until_lesson >= 12:
        api.logger.warning(
            "Booking %s cancelled with %shr notice - no charge",
            booking_id,
            f"{hours_until_lesson:.1f}",
        )
        return {"success": False, "error": "Not a late cancellation"}
    payment = api.BookingRepository(context["db"]).ensure_payment(booking.id)
    if payment.payment_status in {PaymentStatus.SETTLED.value, PaymentStatus.LOCKED.value}:
        api.logger.info("Payment already captured for booking %s", booking_id)
        return {"success": True, "already_captured": True}
    if not payment.payment_intent_id:
        api.logger.error("No payment intent for booking %s", booking_id)
        return {"success": False, "error": "No payment intent"}
    context["hours_until_lesson"] = hours_until_lesson
    context["payment"] = payment
    return {"success": True}


def execute_late_cancel_capture(
    context: Dict[str, Any],
) -> Dict[str, Any]:
    booking = context["booking"]
    payment = context["payment"]
    stripe_service = context["stripe_service"]
    idempotency_key = f"capture_late_cancel_{booking.id}_{payment.payment_intent_id}"
    captured_intent = stripe_service.capture_booking_payment_intent(
        booking_id=booking.id,
        payment_intent_id=payment.payment_intent_id,
        idempotency_key=idempotency_key,
    )
    return {"captured_intent": captured_intent}


def persist_late_cancel_result(
    api: PaymentTasksFacadeApi,
    context: Dict[str, Any],
    capture_result: Dict[str, Any],
) -> Dict[str, Any]:
    booking = context["booking"]
    payment = context["payment"]
    payment_repo = context["payment_repo"]
    now = context["now"]
    hours_until_lesson = context["hours_until_lesson"]
    payment.payment_status = PaymentStatus.SETTLED.value
    if not payment.settlement_outcome:
        payment.settlement_outcome = "student_cancel_lt12_split_50_50"
    try:
        from app.services.credit_service import CreditService

        credit_service = CreditService(context["db"])
        credit_service.forfeit_credits_for_booking(booking_id=booking.id, use_transaction=False)
        payment.credits_reserved_cents = 0
    except Exception as exc:
        api.logger.warning(
            "Failed to forfeit reserved credits for booking %s: %s",
            booking.id,
            exc,
        )
    amount_received = getattr(capture_result["captured_intent"], "amount_received", None)
    payment_repo.create_payment_event(
        booking_id=booking.id,
        event_type="late_cancellation_captured",
        event_data={
            "payment_intent_id": payment.payment_intent_id,
            "amount_captured_cents": amount_received,
            "hours_before_lesson": round(hours_until_lesson, 1),
            "captured_at": now.isoformat(),
            "cancellation_policy": "Full charge for <12hr cancellation",
        },
    )
    context["db"].commit()
    api.logger.info(
        "Successfully captured late cancellation for booking %s (%shr before lesson)",
        booking.id,
        f"{hours_until_lesson:.1f}",
    )
    return {
        "success": True,
        "amount_captured": amount_received,
        "hours_before_lesson": round(hours_until_lesson, 1),
    }


def persist_late_cancel_failure(
    api: PaymentTasksFacadeApi,
    context: Dict[str, Any],
    error: Exception,
) -> Dict[str, Any]:
    booking = context["booking"]
    payment_repo = context["payment_repo"]
    payment = context.get("payment")
    payment_repo.create_payment_event(
        booking_id=booking.id,
        event_type="late_cancellation_capture_failed",
        event_data={
            "error": str(error),
            "payment_intent_id": getattr(payment, "payment_intent_id", None),
            "hours_before_lesson": round(context.get("hours_until_lesson", 0), 1),
        },
    )
    context["db"].commit()
    api.logger.error("Failed to capture late cancellation for %s: %s", booking.id, error)
    return {"success": False, "error": str(error)}


def capture_late_cancellation_impl(
    api: PaymentTasksFacadeApi,
    task_self: Any,
    booking_id: Union[int, str],
) -> Dict[str, Any]:
    """Immediately capture payment for late cancellations."""
    try:
        with api.booking_lock_sync(str(booking_id)) as acquired:
            if not acquired:
                return {"success": False, "skipped": True, "error": "lock_unavailable"}
            with get_db_session() as db:
                context = load_late_cancel_context(api, db, booking_id)
                validation = validate_late_cancel_window(api, context, booking_id)
                if not validation.get("success") or validation.get("already_captured"):
                    return validation
                try:
                    capture_result = execute_late_cancel_capture(context)
                except api.stripe.error.InvalidRequestError as exc:
                    if "already been captured" in str(exc).lower():
                        context["payment"].payment_status = PaymentStatus.SETTLED.value
                        context["db"].commit()
                        return {"success": True, "already_captured": True}
                    return persist_late_cancel_failure(api, context, exc)
                except Exception as exc:
                    return persist_late_cancel_failure(api, context, exc)
                return persist_late_cancel_result(api, context, capture_result)
    except Exception as exc:
        api.logger.error("Late cancellation capture task failed for %s: %s", booking_id, exc)
        raise task_self.retry(exc=exc, countdown=60)


def resolve_undisputed_no_shows_impl(api: PaymentTasksFacadeApi) -> NoShowResolutionResults:
    """Auto-resolve no-show reports that were not disputed within 24 hours."""
    now = api.datetime.now(timezone.utc)
    results: NoShowResolutionResults = {
        "resolved": 0,
        "skipped": 0,
        "failed": 0,
        "processed_at": now.isoformat(),
    }
    with get_db_session() as db:
        booking_repo = api.RepositoryFactory.create_booking_repository(db)
        booking_service = api.BookingService(db)
        cutoff = now - timedelta(hours=24)
        pending = booking_repo.get_no_show_reports_due_for_resolution(reported_before=cutoff)
        for booking in pending:
            try:
                with api.booking_lock_sync(str(booking.id)) as acquired:
                    if not acquired:
                        results["skipped"] += 1
                        continue
                    result = booking_service.resolve_no_show(
                        booking_id=booking.id,
                        resolution="confirmed_no_dispute",
                        resolved_by=None,
                        admin_notes=None,
                    )
                    results["resolved" if result.get("success") else "failed"] += 1
            except Exception as exc:
                api.logger.error("Failed to resolve no-show for %s: %s", booking.id, exc)
                results["failed"] += 1
        return results
