from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from importlib import import_module
import logging
from typing import TYPE_CHECKING, Any, Optional

import stripe

from ...core.exceptions import (
    BookingCancelledException,
    BookingNotFoundException,
    ServiceException,
)
from ...models.booking import BookingStatus, PaymentStatus
from ...models.payment import PaymentIntent
from ...models.user import User
from ...schemas.payment_schemas import CheckoutResponse, CreateCheckoutRequest
from ..base import BaseService
from .helpers import ChargeContext

if TYPE_CHECKING:
    from datetime import datetime as DateTime

    from ...repositories.booking_repository import BookingRepository
    from ...repositories.instructor_profile_repository import InstructorProfileRepository
    from ...repositories.payment_repository import PaymentRepository
    from ..booking_service import BookingService

logger = logging.getLogger(__name__)


def _stripe_service_module() -> Any:
    return import_module("app.services.stripe_service")


@dataclass(slots=True)
class _PaymentProcessingContext:
    booking_id: str
    student_id: str
    stripe_account_id: str
    immediate_auth: bool
    auth_scheduled_for: Optional[DateTime]
    hours_until_lesson: float


class StripePaymentMixin(BaseService):
    """Checkout orchestration and high-level booking payment processing."""

    booking_repository: BookingRepository
    instructor_repository: InstructorProfileRepository
    payment_repository: PaymentRepository
    _last_client_secret: Optional[str]

    if TYPE_CHECKING:

        def _void_or_refund_payment(self, payment_intent_id: Optional[str]) -> None:
            ...

        def create_payment_intent(self, *args: Any, **kwargs: Any) -> PaymentIntent:
            ...

        def get_or_create_customer(self, user_id: str) -> Any:
            ...

        def save_payment_method(
            self, user_id: str, payment_method_id: str, set_as_default: bool = False
        ) -> Any:
            ...

        def build_charge_context(
            self, booking_id: str, requested_credit_cents: Optional[int] = None
        ) -> ChargeContext:
            ...

    def _load_checkout_booking(self, *, current_user: User, payload: CreateCheckoutRequest) -> Any:
        if not current_user.is_student:
            raise ServiceException("Only students can pay for bookings", code="forbidden")
        booking = self.booking_repository.get_booking_for_student(
            payload.booking_id, current_user.id
        )
        if not booking:
            raise ServiceException("Booking not found", code="not_found")
        if booking.status not in ["CONFIRMED", "PENDING"]:
            raise ServiceException(
                f"Cannot process payment for booking with status: {booking.status}",
                code="invalid_booking_status",
            )
        existing_payment = self.payment_repository.get_payment_by_booking_id(booking.id)
        if existing_payment and existing_payment.status == "succeeded":
            raise ServiceException("Booking has already been paid", code="already_paid")
        return booking

    def _maybe_save_checkout_payment_method(
        self, *, current_user: User, payload: CreateCheckoutRequest
    ) -> None:
        if payload.save_payment_method and payload.payment_method_id:
            self.save_payment_method(
                user_id=current_user.id,
                payment_method_id=payload.payment_method_id,
                set_as_default=False,
            )

    def _finalize_checkout_booking(
        self,
        *,
        booking: Any,
        payment_result: dict[str, Any],
        booking_service: Any,
    ) -> None:
        if not (
            payment_result["success"]
            and payment_result["status"] in {"succeeded", "requires_capture", "scheduled"}
        ):
            return
        payment_intent_id = payment_result.get("payment_intent_id")
        fresh_booking = self.booking_repository.get_by_id_for_update(
            booking.id, load_relationships=False
        )
        if not fresh_booking:
            self._void_or_refund_payment(payment_intent_id)
            raise BookingNotFoundException("Booking no longer exists. Payment has been refunded.")
        if fresh_booking.status == BookingStatus.CANCELLED.value:
            self._void_or_refund_payment(payment_intent_id)
            raise BookingCancelledException(
                "This booking was cancelled by the instructor during checkout. Your payment has been refunded."
            )
        if fresh_booking.status not in {BookingStatus.PENDING.value, BookingStatus.CONFIRMED.value}:
            self._void_or_refund_payment(payment_intent_id)
            raise ServiceException(
                f"Booking is in unexpected state '{fresh_booking.status}'. Payment has been refunded.",
                code="invalid_booking_state",
            )
        was_confirmed = fresh_booking.status == BookingStatus.CONFIRMED.value
        fresh_booking.status = BookingStatus.CONFIRMED.value
        if fresh_booking.confirmed_at is None:
            fresh_booking.confirmed_at = datetime.now(timezone.utc)
        if payment_result["status"] in ("requires_capture", "scheduled"):
            booking_payment = self.booking_repository.ensure_payment(fresh_booking.id)
            booking_payment.payment_status = (
                PaymentStatus.AUTHORIZED.value
                if payment_result["status"] == "requires_capture"
                else PaymentStatus.SCHEDULED.value
            )
        booking_service.repository.flush()
        try:
            booking_service.invalidate_booking_cache(fresh_booking)
        except Exception as exc:
            logger.warning(
                "Failed to invalidate booking cache after checkout confirmation: %s",
                str(exc),
                extra={"booking_id": fresh_booking.id},
                exc_info=True,
            )
        try:
            service_name = "Lesson"
            if fresh_booking.instructor_service and fresh_booking.instructor_service.name:
                service_name = fresh_booking.instructor_service.name
            booking_service.system_message_service.create_booking_created_message(
                student_id=fresh_booking.student_id,
                instructor_id=fresh_booking.instructor_id,
                booking_id=fresh_booking.id,
                service_name=service_name,
                booking_date=fresh_booking.booking_date,
                start_time=fresh_booking.start_time,
            )
        except Exception as exc:
            logger.warning(
                "Failed to create booking-created message after checkout confirmation: %s",
                str(exc),
                extra={"booking_id": fresh_booking.id},
                exc_info=True,
            )
        if not was_confirmed:
            try:
                booking_service.send_booking_notifications_after_confirmation(fresh_booking.id)
            except Exception as exc:
                logger.warning(
                    "Failed to send booking confirmation notifications after checkout: %s",
                    str(exc),
                    extra={"booking_id": fresh_booking.id},
                    exc_info=True,
                )

    def _build_checkout_response(self, payment_result: dict[str, Any]) -> CheckoutResponse:
        status = payment_result.get("status")
        client_secret = (
            payment_result.get("client_secret")
            if status in ["requires_action", "requires_confirmation", "requires_payment_method"]
            else None
        )
        return CheckoutResponse(
            success=payment_result["success"],
            payment_intent_id=payment_result["payment_intent_id"],
            status=payment_result["status"],
            amount=payment_result["amount"],
            application_fee=payment_result["application_fee"],
            client_secret=client_secret,
            requires_action=status
            in [
                "requires_action",
                "requires_confirmation",
                "requires_payment_method",
            ],
        )

    @BaseService.measure_operation("stripe_create_booking_checkout")
    def create_booking_checkout(
        self,
        *,
        current_user: User,
        payload: CreateCheckoutRequest,
        booking_service: "BookingService",
    ) -> CheckoutResponse:
        """Process booking checkout and return payment response."""
        booking = self._load_checkout_booking(current_user=current_user, payload=payload)
        self._maybe_save_checkout_payment_method(current_user=current_user, payload=payload)
        payment_result = self.process_booking_payment(
            payload.booking_id,
            payload.payment_method_id,
            payload.requested_credit_cents,
            save_payment_method=not payload.payment_method_id,
        )
        self._finalize_checkout_booking(
            booking=booking,
            payment_result=payment_result,
            booking_service=booking_service,
        )
        return self._build_checkout_response(payment_result)

    def _load_payment_processing_context(self, *, booking_id: str) -> _PaymentProcessingContext:
        booking = self.booking_repository.get_by_id(booking_id)
        if not booking:
            raise ServiceException(f"Booking {booking_id} not found")
        instructor_profile = self.instructor_repository.get_by_user_id(booking.instructor_id)
        if not instructor_profile:
            raise ServiceException(f"Instructor profile not found for user {booking.instructor_id}")
        connected_account = self.payment_repository.get_connected_account_by_instructor_id(
            instructor_profile.id
        )
        if not connected_account or not connected_account.onboarding_completed:
            raise ServiceException("Instructor payment account not set up")
        booking_start_utc = booking.booking_start_utc
        if not isinstance(booking_start_utc, datetime):
            booking_start_utc = datetime.combine(
                booking.booking_date,
                booking.start_time,
                tzinfo=timezone.utc,
            )
        elif booking_start_utc.tzinfo is None:
            booking_start_utc = booking_start_utc.replace(tzinfo=timezone.utc)
        hours_until_lesson = (booking_start_utc - datetime.now(timezone.utc)).total_seconds() / 3600
        immediate_auth = hours_until_lesson < 24
        return _PaymentProcessingContext(
            booking_id=booking_id,
            student_id=booking.student_id,
            stripe_account_id=connected_account.stripe_account_id,
            immediate_auth=immediate_auth,
            auth_scheduled_for=booking_start_utc - timedelta(hours=24)
            if not immediate_auth
            else None,
            hours_until_lesson=hours_until_lesson,
        )

    def _handle_credit_only_payment(
        self, *, booking_id: str, charge_context: ChargeContext
    ) -> dict[str, Any]:
        with self.transaction():
            booking = self.booking_repository.get_by_id(booking_id)
            if booking:
                try:
                    self.payment_repository.create_payment_event(
                        booking_id=booking.id,
                        event_type="auth_succeeded_credits_only",
                        event_data={
                            "base_price_cents": charge_context.base_price_cents,
                            "credits_applied_cents": charge_context.applied_credit_cents,
                            "authorized_at": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to record credits-only authorization event: %s",
                        str(exc),
                        extra={"booking_id": booking.id},
                        exc_info=True,
                    )
                booking_payment = self.booking_repository.ensure_payment(booking.id)
                booking_payment.payment_status = PaymentStatus.AUTHORIZED.value
                booking_payment.auth_attempted_at = datetime.now(timezone.utc)
                booking_payment.auth_failure_count = 0
                booking_payment.auth_last_error = None
        return {
            "success": True,
            "payment_intent_id": "credit_only",
            "status": "succeeded",
            "amount": 0,
            "application_fee": 0,
            "client_secret": _stripe_service_module()._ABSENT,
        }

    def _create_payment_element_intent(
        self,
        *,
        context: _PaymentProcessingContext,
        customer_id: str,
        charge_context: ChargeContext,
        save_payment_method: bool,
    ) -> dict[str, Any]:
        self._last_client_secret = None
        payment_record = self.create_payment_intent(
            booking_id=context.booking_id,
            customer_id=customer_id,
            destination_account_id=context.stripe_account_id,
            charge_context=charge_context,
            save_payment_method=save_payment_method,
        )
        return {
            "success": True,
            "payment_intent_id": payment_record.stripe_payment_intent_id,
            "status": "requires_payment_method",
            "amount": payment_record.amount,
            "application_fee": payment_record.application_fee,
            "requires_action": True,
            "client_secret": self._last_client_secret,
        }

    def _confirm_immediate_authorization(
        self, *, payment_intent_id: str, payment_method_id: str
    ) -> tuple[Optional[Any], Optional[str]]:
        facade_module = _stripe_service_module()
        stripe_sdk = facade_module.stripe
        try:
            return (
                stripe_sdk.PaymentIntent.confirm(
                    payment_intent_id,
                    payment_method=payment_method_id,
                    return_url=f"{facade_module.settings.frontend_url}/student/payment/complete",
                ),
                None,
            )
        except stripe.error.CardError as exc:
            return None, str(exc)
        except Exception as exc:
            return None, str(exc)

    def _persist_authorization_state(
        self,
        *,
        context: _PaymentProcessingContext,
        payment_record: PaymentIntent,
        payment_method_id: str,
        stripe_intent: Optional[Any],
        stripe_error: Optional[str],
    ) -> None:
        booking = self.booking_repository.get_by_id(context.booking_id)
        if not booking:
            return
        booking_payment = self.booking_repository.ensure_payment(booking.id)
        booking_payment.payment_intent_id = payment_record.stripe_payment_intent_id
        booking_payment.payment_method_id = payment_method_id
        if context.immediate_auth:
            now = datetime.now(timezone.utc)
            if stripe_intent and stripe_intent.status in {"requires_capture", "succeeded"}:
                try:
                    self.payment_repository.update_payment_status(
                        payment_record.stripe_payment_intent_id,
                        stripe_intent.status,
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to persist immediate authorization status: %s",
                        str(exc),
                        extra={"payment_intent_id": payment_record.stripe_payment_intent_id},
                        exc_info=True,
                    )
                booking_payment.payment_status = PaymentStatus.AUTHORIZED.value
                booking_payment.auth_attempted_at = now
                booking_payment.auth_failure_count = 0
                booking_payment.auth_last_error = None
                booking_payment.auth_scheduled_for = None
                return
            booking_payment.payment_status = PaymentStatus.PAYMENT_METHOD_REQUIRED.value
            booking_payment.auth_attempted_at = now
            booking_payment.auth_failure_count = (
                int(getattr(booking_payment, "auth_failure_count", 0) or 0) + 1
            )
            booking_payment.auth_last_error = stripe_error or "authorization_failed"
            booking_payment.auth_scheduled_for = None
            return
        booking_payment.payment_status = PaymentStatus.SCHEDULED.value
        booking_payment.auth_scheduled_for = context.auth_scheduled_for
        booking_payment.auth_failure_count = 0
        booking_payment.auth_last_error = None
        try:
            self.payment_repository.create_payment_event(
                booking_id=booking.id,
                event_type="auth_scheduled",
                event_data={
                    "payment_method_id": payment_method_id,
                    "scheduled_for": context.auth_scheduled_for.isoformat()
                    if context.auth_scheduled_for
                    else None,
                    "hours_until_lesson": context.hours_until_lesson,
                },
            )
        except Exception as exc:
            logger.warning(
                "Failed to record scheduled authorization event: %s",
                str(exc),
                extra={"booking_id": booking.id},
                exc_info=True,
            )

    def _build_process_payment_response(
        self,
        *,
        payment_record: PaymentIntent,
        immediate_auth: bool,
        stripe_intent: Optional[Any],
    ) -> dict[str, Any]:
        if not immediate_auth:
            return {
                "success": True,
                "payment_intent_id": payment_record.stripe_payment_intent_id,
                "status": "scheduled",
                "amount": payment_record.amount,
                "application_fee": payment_record.application_fee,
                "client_secret": _stripe_service_module()._ABSENT,
            }
        if stripe_intent is None:
            return {
                "success": False,
                "payment_intent_id": payment_record.stripe_payment_intent_id,
                "status": "auth_failed",
                "amount": payment_record.amount,
                "application_fee": payment_record.application_fee,
                "client_secret": _stripe_service_module()._ABSENT,
            }
        requires_action = stripe_intent.status in ["requires_action", "requires_confirmation"]
        return {
            "success": stripe_intent.status in {"requires_capture", "succeeded"},
            "payment_intent_id": payment_record.stripe_payment_intent_id,
            "status": stripe_intent.status,
            "amount": payment_record.amount,
            "application_fee": payment_record.application_fee,
            "client_secret": getattr(stripe_intent, "client_secret", None)
            if requires_action
            else None,
        }

    @BaseService.measure_operation("stripe_process_booking_payment")
    def process_booking_payment(
        self,
        booking_id: str,
        payment_method_id: Optional[str] = None,
        requested_credit_cents: Optional[int] = None,
        save_payment_method: bool = False,
    ) -> dict[str, Any]:
        """Process payment for a booking end-to-end."""
        try:
            with self.transaction():
                context = self._load_payment_processing_context(booking_id=booking_id)
            customer = self.get_or_create_customer(context.student_id)
            charge_context = self.build_charge_context(
                booking_id=booking_id,
                requested_credit_cents=requested_credit_cents,
            )
            if charge_context.student_pay_cents <= 0:
                return self._handle_credit_only_payment(
                    booking_id=booking_id,
                    charge_context=charge_context,
                )
            if not payment_method_id:
                return self._create_payment_element_intent(
                    context=context,
                    customer_id=customer.stripe_customer_id,
                    charge_context=charge_context,
                    save_payment_method=save_payment_method,
                )
            payment_record = self.create_payment_intent(
                booking_id=booking_id,
                customer_id=customer.stripe_customer_id,
                destination_account_id=context.stripe_account_id,
                charge_context=charge_context,
            )
            stripe_intent, stripe_error = (
                self._confirm_immediate_authorization(
                    payment_intent_id=payment_record.stripe_payment_intent_id,
                    payment_method_id=payment_method_id,
                )
                if context.immediate_auth
                else (None, None)
            )
            with self.transaction():
                self._persist_authorization_state(
                    context=context,
                    payment_record=payment_record,
                    payment_method_id=payment_method_id,
                    stripe_intent=stripe_intent,
                    stripe_error=stripe_error,
                )
            if context.immediate_auth and (
                stripe_intent is None
                or stripe_intent.status not in {"requires_capture", "succeeded"}
            ):
                try:
                    _stripe_service_module().enqueue_task(
                        "app.tasks.payment_tasks.check_immediate_auth_timeout",
                        args=(booking_id,),
                        countdown=30 * 60,
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to enqueue immediate authorization timeout check: %s",
                        str(exc),
                        extra={"booking_id": booking_id},
                        exc_info=True,
                    )
            return self._build_process_payment_response(
                payment_record=payment_record,
                immediate_auth=context.immediate_auth,
                stripe_intent=stripe_intent,
            )
        except Exception as exc:
            if isinstance(exc, ServiceException):
                raise
            self.logger.error("Error processing booking payment: %s", exc)
            raise ServiceException(f"Failed to process payment: {str(exc)}")
