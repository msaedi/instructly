"""
Stripe Service for InstaInstru Platform

Implements all Stripe API interactions for marketplace payment processing
using Stripe Connect. This service handles customer management, connected
accounts for instructors, payment processing, and webhook handling.

Key Features:
- Marketplace payments with destination charges
- Express accounts for instructor onboarding
- Application fees calculated from pricing configuration for platform revenue
- Webhook signature validation
- Comprehensive error handling and logging

Architecture:
- Uses repository pattern for all database operations
- Performance monitoring on all public methods
- Transaction management for data consistency
- Follows established service patterns
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
import math
import os
import time as _time
from types import SimpleNamespace
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Optional,
    cast,
)
import uuid

from sqlalchemy.orm import Session
import stripe
from stripe._balance import Balance as StripeBalance
from stripe._refund import Refund as StripeRefund
from stripe._transfer import Transfer as StripeTransfer

from app.tasks.enqueue import enqueue_task

from ..constants.pricing_defaults import PRICING_DEFAULTS
from ..core.booking_lock import booking_lock_sync
from ..core.config import settings
from ..core.exceptions import (
    BookingCancelledException,
    BookingNotFoundException,
    ServiceException,
)
from ..models.booking import BookingStatus, PaymentStatus
from ..models.payment import PaymentIntent
from ..models.user import User
from ..repositories.factory import RepositoryFactory
from ..schemas.payment_schemas import (
    CheckoutResponse,
    CreateCheckoutRequest,
)
from ..utils.url_validation import is_allowed_origin, origin_from_header
from .base import BaseService
from .cache_service import CacheService, CacheServiceSyncAdapter
from .config_service import ConfigService
from .payment_summary_service import build_student_payment_summary
from .pricing_service import PricingService
from .stripe.helpers import (
    ChargeContext,
    ReferralBonusTransferResult,
    ReferralBonusTransferSkippedResult,
    ReferralBonusTransferSuccessResult,
)
from .student_credit_service import StudentCreditService

if TYPE_CHECKING:  # pragma: no cover
    from .booking_service import BookingService

    class StripeHelpersMixin(BaseService):
        stripe_configured: bool
        _check_stripe_configured: Callable[[], None]
        _call_with_retry: Callable[..., Any]
        _mock_payment_response: Callable[[str, int], dict[str, Any]]
        _stripe_value: Callable[..., Any]
        _stripe_has_field: Callable[..., bool]

    class StripeEarningsMixin(BaseService):
        get_instructor_earnings_summary: Callable[..., Any]
        get_instructor_payout_history: Callable[..., Any]
        get_user_transaction_history: Callable[..., Any]
        get_user_credit_balance: Callable[..., Any]
        get_platform_revenue_stats: Callable[..., Any]
        get_instructor_earnings: Callable[..., Any]

    class StripeEarningsExportMixin(BaseService):
        generate_earnings_pdf: Callable[..., bytes]
        generate_earnings_csv: Callable[..., bytes]

    class StripeCaptureRefundMixin(BaseService):
        capture_payment_intent: Callable[..., dict[str, Any]]
        get_payment_intent_capture_details: Callable[[str], dict[str, Any]]
        reverse_transfer: Callable[..., dict[str, Any]]
        cancel_payment_intent: Callable[..., bool]
        _void_or_refund_payment: Callable[[Optional[str]], None]
        refund_payment: Callable[..., dict[str, Any]]

    class StripeTransferMixin(BaseService):
        ensure_top_up_transfer: Callable[..., Optional[dict[str, Any]]]
        create_manual_transfer: Callable[..., dict[str, Any]]
        create_referral_bonus_transfer: Callable[..., ReferralBonusTransferResult]
        set_payout_schedule_for_account: Callable[..., dict[str, Any]]
        _top_up_from_pi_metadata: Callable[[Any], int]

    class StripeIdentityMixin(BaseService):
        create_identity_verification_session: Callable[..., Any]
        refresh_instructor_identity: Callable[..., Any]
        get_latest_identity_status: Callable[..., Any]
        _persist_verified_identity: Callable[..., None]

    class StripeOnboardingMixin(BaseService):
        start_instructor_onboarding: Callable[..., Any]
        get_instructor_onboarding_status: Callable[..., Any]
        set_instructor_payout_schedule: Callable[..., Any]
        get_instructor_dashboard_link: Callable[..., Any]
        request_instructor_instant_payout: Callable[..., Any]
        create_connected_account: Callable[..., Any]
        create_account_link: Callable[..., Any]
        check_account_status: Callable[..., Any]

    class StripeCustomerMixin(BaseService):
        create_customer: Callable[..., Any]
        get_or_create_customer: Callable[..., Any]
        save_payment_method: Callable[..., Any]
        create_setup_intent_for_saving: Callable[..., dict[str, str]]
        get_user_payment_methods: Callable[..., Any]
        delete_payment_method: Callable[..., bool]

else:
    from .stripe.capture_refund import StripeCaptureRefundMixin
    from .stripe.customer import StripeCustomerMixin
    from .stripe.earnings import StripeEarningsMixin
    from .stripe.earnings_export import StripeEarningsExportMixin
    from .stripe.helpers import StripeHelpersMixin
    from .stripe.identity import StripeIdentityMixin
    from .stripe.onboarding import StripeOnboardingMixin
    from .stripe.transfer import StripeTransferMixin

logger: logging.Logger = logging.getLogger(__name__)

# Sentinel for absent secret values in payment responses (avoids B105 false positive)
_ABSENT: None = None

__all__ = [
    "ChargeContext",
    "PRICING_DEFAULTS",
    "ReferralBonusTransferResult",
    "ReferralBonusTransferSkippedResult",
    "ReferralBonusTransferSuccessResult",
    "StripeRefund",
    "StripeService",
    "StripeTransfer",
    "_time",
    "build_student_payment_summary",
]

_FACADE_TEST_PATCH_TARGETS = (StripeBalance, uuid, origin_from_header, is_allowed_origin)


class StripeService(
    StripeHelpersMixin,
    StripeEarningsMixin,
    StripeEarningsExportMixin,
    StripeCaptureRefundMixin,
    StripeTransferMixin,
    StripeIdentityMixin,
    StripeOnboardingMixin,
    StripeCustomerMixin,
    BaseService,
):
    """
    Service for all Stripe API interactions and payment business logic.

    Handles marketplace payment processing using Stripe Connect with
    destination charges, express accounts, and application fees.
    """

    def __init__(
        self,
        db: Session,
        *,
        config_service: ConfigService,
        pricing_service: PricingService,
        cache_service: Optional[CacheService | CacheServiceSyncAdapter] = None,
    ):
        """Initialize with explicit configuration dependencies and configure Stripe."""
        cache_impl = cache_service
        cache_adapter: Optional[CacheServiceSyncAdapter] = None
        if isinstance(cache_impl, CacheServiceSyncAdapter):
            cache_adapter = cache_impl
        elif isinstance(cache_impl, CacheService):
            cache_adapter = CacheServiceSyncAdapter(cache_impl)
        super().__init__(db, cache=cache_adapter)
        self.config_service = config_service
        self.pricing_service = pricing_service
        self.cache_service = cache_adapter
        self.payment_repository = RepositoryFactory.create_payment_repository(db)
        self.booking_repository = RepositoryFactory.create_booking_repository(db)
        self.user_repository = RepositoryFactory.create_user_repository(db)
        self.instructor_repository = RepositoryFactory.create_instructor_profile_repository(db)

        # Configure Stripe API key with defensive error handling
        self.stripe_configured = False
        # Per-request instance (via get_stripe_service Depends) — not shared across concurrent requests
        self._last_client_secret: Optional[str] = None
        try:
            if settings.stripe_secret_key:
                stripe.api_key = settings.stripe_secret_key.get_secret_value()
                self.logger.info(
                    "Stripe SDK %s, API version %s",
                    getattr(stripe, "VERSION", "unknown"),
                    getattr(stripe, "api_version", "unknown"),
                )
                # Set sane network timeouts/retries to avoid blocking the server on Stripe calls
                # The 3-phase pattern decouples Stripe calls from DB transactions.
                try:
                    # 30s timeout (Stripe recommended minimum); 1 retry for transient failures
                    # Note: Stripe 14.x moved http_client to _http_client (private API)
                    http_client_module = getattr(stripe, "_http_client", None) or getattr(
                        stripe, "http_client", None
                    )
                    if http_client_module:
                        stripe.default_http_client = http_client_module.RequestsClient(timeout=30)
                    stripe.max_network_retries = 1
                    stripe.verify_ssl_certs = True
                except Exception:
                    # Non-fatal if client customization isn't available
                    logger.debug("Non-fatal error ignored", exc_info=True)
                self.stripe_configured = True
                self.logger.info("Stripe service configured successfully")
            else:
                self.logger.warning(
                    "Stripe secret key not configured - service will operate in mock mode"
                )
        except Exception as e:
            self.logger.error(
                "Failed to configure Stripe service: %s - service will operate in mock mode",
                e,
            )

        # Platform fee percentage (15 means 15%, not 0.15)
        self.platform_fee_percentage = (
            getattr(settings, "stripe_platform_fee_percentage", 15) / 100.0
        )

        self.logger = logging.getLogger(__name__)

    # --------------------------------------------------------------------- #
    # Checkout and earnings
    # --------------------------------------------------------------------- #

    @BaseService.measure_operation("stripe_create_booking_checkout")
    def create_booking_checkout(
        self,
        *,
        current_user: User,
        payload: CreateCheckoutRequest,
        booking_service: "BookingService",
    ) -> CheckoutResponse:
        """Process booking checkout and return payment response."""
        if not current_user.is_student:
            raise ServiceException("Only students can pay for bookings", code="forbidden")

        # Defense-in-depth: filter by student at DB level (AUTHZ-VULN-01)
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

        if payload.save_payment_method and payload.payment_method_id:
            # Saved-card flow: attach existing payment method to customer
            self.save_payment_method(
                user_id=current_user.id,
                payment_method_id=payload.payment_method_id,
                set_as_default=False,
            )

        # PaymentElement flow (no payment_method_id): always save the card via
        # setup_future_usage. Users can delete saved cards from billing.
        save_payment_method = not payload.payment_method_id
        payment_result = self.process_booking_payment(
            payload.booking_id,
            payload.payment_method_id,
            payload.requested_credit_cents,
            save_payment_method=save_payment_method,
        )

        # With capture_method: "manual", successful authorization returns "requires_capture"
        # We treat both "succeeded" (legacy/credits-only) and "requires_capture" as successful auth
        if payment_result["success"] and payment_result["status"] in {
            "succeeded",
            "requires_capture",
            "scheduled",
        }:
            payment_intent_id = payment_result.get("payment_intent_id")
            fresh_booking = self.booking_repository.get_by_id_for_update(
                booking.id, load_relationships=False
            )

            if not fresh_booking:
                self._void_or_refund_payment(payment_intent_id)
                raise BookingNotFoundException(
                    "Booking no longer exists. Payment has been refunded."
                )

            if fresh_booking.status == BookingStatus.CANCELLED.value:
                self._void_or_refund_payment(payment_intent_id)
                raise BookingCancelledException(
                    "This booking was cancelled by the instructor during checkout. "
                    "Your payment has been refunded."
                )

            if fresh_booking.status not in {
                BookingStatus.PENDING.value,
                BookingStatus.CONFIRMED.value,
            }:
                self._void_or_refund_payment(payment_intent_id)
                raise ServiceException(
                    f"Booking is in unexpected state '{fresh_booking.status}'. "
                    "Payment has been refunded.",
                    code="invalid_booking_state",
                )

            was_confirmed = fresh_booking.status == BookingStatus.CONFIRMED.value
            fresh_booking.status = BookingStatus.CONFIRMED.value
            if fresh_booking.confirmed_at is None:
                fresh_booking.confirmed_at = datetime.now(timezone.utc)
            # Set payment_status to reflect authorization state
            if payment_result["status"] in ("requires_capture", "scheduled"):
                bp = self.booking_repository.ensure_payment(fresh_booking.id)
                if payment_result["status"] == "requires_capture":
                    bp.payment_status = PaymentStatus.AUTHORIZED.value
                else:
                    bp.payment_status = PaymentStatus.SCHEDULED.value

            booking = fresh_booking
            booking_service.repository.flush()
            try:
                booking_service.invalidate_booking_cache(booking)
            except Exception:
                logger.debug("Non-fatal error ignored", exc_info=True)
            try:
                service_name = "Lesson"
                if booking.instructor_service and booking.instructor_service.name:
                    service_name = booking.instructor_service.name
                booking_service.system_message_service.create_booking_created_message(
                    student_id=booking.student_id,
                    instructor_id=booking.instructor_id,
                    booking_id=booking.id,
                    service_name=service_name,
                    booking_date=booking.booking_date,
                    start_time=booking.start_time,
                )
            except Exception:
                logger.debug("Non-fatal error ignored", exc_info=True)
            if not was_confirmed:
                try:
                    booking_service.send_booking_notifications_after_confirmation(booking.id)
                except Exception:
                    logger.debug("Non-fatal error ignored", exc_info=True)
        client_secret = (
            payment_result.get("client_secret")
            if payment_result.get("status")
            in ["requires_action", "requires_confirmation", "requires_payment_method"]
            else None
        )

        response_data = {
            "success": payment_result["success"],
            "payment_intent_id": payment_result["payment_intent_id"],
            "status": payment_result["status"],
            "amount": payment_result["amount"],
            "application_fee": payment_result["application_fee"],
            "client_secret": client_secret,
            "requires_action": payment_result["status"]
            in ["requires_action", "requires_confirmation", "requires_payment_method"],
        }
        return CheckoutResponse(**response_data)

    @BaseService.measure_operation("stripe_create_or_retry_booking_pi")
    def create_or_retry_booking_payment_intent(
        self,
        *,
        booking_id: str,
        payment_method_id: Optional[str] = None,
        requested_credit_cents: Optional[int] = None,
    ) -> Any:
        booking = self.booking_repository.get_by_id(booking_id)
        if not booking:
            raise ServiceException(f"Booking {booking_id} not found")

        customer = self.payment_repository.get_customer_by_user_id(booking.student_id)
        if not customer:
            raise ServiceException(f"No Stripe customer for student {booking.student_id}")

        instructor_profile = self.instructor_repository.get_by_user_id(booking.instructor_id)
        if not instructor_profile:
            raise ServiceException(f"Instructor profile not found for user {booking.instructor_id}")

        connected_account = self.payment_repository.get_connected_account_by_instructor_id(
            instructor_profile.id
        )
        if not connected_account or not connected_account.stripe_account_id:
            raise ServiceException("Instructor payment account not set up")

        context = self.build_charge_context(
            booking_id=booking_id, requested_credit_cents=requested_credit_cents
        )

        if context.student_pay_cents <= 0:
            raise ServiceException("Charge amount is zero after applied credits")

        metadata = {
            "booking_id": booking_id,
            "student_id": booking.student_id,
            "instructor_id": booking.instructor_id,
            "instructor_tier_pct": str(context.instructor_tier_pct),
            "base_price_cents": str(context.base_price_cents),
            "student_fee_cents": str(context.student_fee_cents),
            "platform_fee_cents": str(context.instructor_platform_fee_cents),
            "applied_credit_cents": str(context.applied_credit_cents),
            "student_pay_cents": str(context.student_pay_cents),
            "application_fee_cents": str(context.application_fee_cents),
            "target_instructor_payout_cents": str(context.target_instructor_payout_cents),
        }

        # Use transfer_data[amount] architecture: platform receives full charge,
        # then transfers up to target_instructor_payout_cents to instructor.
        # Top-up handles any shortfall when credits reduce the charge.
        transfer_amount_cents = min(
            int(context.student_pay_cents), int(context.target_instructor_payout_cents)
        )
        stripe_kwargs: Dict[str, Any] = {
            "amount": context.student_pay_cents,
            "currency": settings.stripe_currency or "usd",
            "customer": customer.stripe_customer_id,
            "transfer_data": {
                "destination": connected_account.stripe_account_id,
                "amount": transfer_amount_cents,
            },
            "metadata": metadata,
            "transfer_group": f"booking:{booking_id}",
            "capture_method": "manual",
            "automatic_payment_methods": {
                "enabled": True,
                "allow_redirects": "never",
            },
            "idempotency_key": f"pi_booking_{booking_id}",
        }

        if payment_method_id:
            stripe_kwargs["payment_method"] = payment_method_id
            stripe_kwargs["confirm"] = True
            stripe_kwargs["off_session"] = True

        try:
            stripe_intent = self._call_with_retry(stripe.PaymentIntent.create, **stripe_kwargs)
        except Exception as exc:
            if not self.stripe_configured:
                if os.getenv("INSTAINSTRU_PRODUCTION_MODE", "").lower() == "true":
                    raise ServiceException(
                        "Stripe not configured in production mode",
                        code="configuration_error",
                    )
                self.logger.warning(
                    "Stripe call failed (%s); storing local record for booking %s",
                    exc,
                    booking_id,
                )
                mock_id = f"mock_pi_{booking_id}"
                self.payment_repository.create_payment_record(
                    booking_id=booking_id,
                    payment_intent_id=mock_id,
                    amount=context.student_pay_cents,
                    application_fee=context.application_fee_cents,
                    status="requires_payment_method",
                    base_price_cents=context.base_price_cents,
                    instructor_tier_pct=context.instructor_tier_pct,
                    instructor_payout_cents=context.target_instructor_payout_cents,
                )
                bp = self.booking_repository.ensure_payment(booking.id)
                bp.payment_intent_id = mock_id
                bp.payment_status = PaymentStatus.AUTHORIZED.value
                return SimpleNamespace(id=mock_id, status="requires_payment_method")
            raise

        self.payment_repository.create_payment_record(
            booking_id=booking_id,
            payment_intent_id=stripe_intent.id,
            amount=context.student_pay_cents,
            application_fee=context.application_fee_cents,
            status=stripe_intent.status,
            base_price_cents=context.base_price_cents,
            instructor_tier_pct=context.instructor_tier_pct,
            instructor_payout_cents=context.target_instructor_payout_cents,
        )

        bp = self.booking_repository.ensure_payment(booking.id)
        bp.payment_intent_id = stripe_intent.id
        if stripe_intent.status in {"requires_capture", "requires_confirmation", "succeeded"}:
            bp.payment_status = PaymentStatus.AUTHORIZED.value

        return stripe_intent

    @BaseService.measure_operation("stripe_capture_booking_pi")
    def capture_booking_payment_intent(
        self,
        *,
        booking_id: str,
        payment_intent_id: str,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Capture a booking PI and return capture details with top-up metadata.

        Returns dict: {
          "payment_intent": stripe.PaymentIntent,
          "amount_received": int,
          "top_up_transfer_cents": int
        }
        Capture prefers PI metadata to compute top-up; falls back to recompute when metadata is absent.
        """
        capture_result = self.capture_payment_intent(
            payment_intent_id, idempotency_key=idempotency_key
        )

        payment_intent = capture_result.get("payment_intent")
        refreshed_pi = payment_intent

        if self.stripe_configured:
            try:
                refreshed_pi = stripe.PaymentIntent.retrieve(payment_intent_id)
            except Exception as exc:
                self.logger.warning(
                    "failed_to_refresh_payment_intent_after_capture",
                    extra={
                        "booking_id": booking_id,
                        "payment_intent_id": payment_intent_id,
                        "error": str(exc),
                    },
                )

        if refreshed_pi is None:
            refreshed_pi = payment_intent

        top_up_amount: Optional[int] = None
        if refreshed_pi is not None:
            top_up_amount = self._top_up_from_pi_metadata(refreshed_pi)

        if top_up_amount is None:
            self.logger.info(
                "top_up_metadata_missing_falling_back",
                extra={
                    "booking_id": booking_id,
                    "payment_intent_id": payment_intent_id,
                },
            )
            try:
                ctx = self.build_charge_context(booking_id, requested_credit_cents=None)

                amount_value: Optional[Any] = None
                if refreshed_pi is not None:
                    amount_value = getattr(refreshed_pi, "amount", None)
                    if amount_value is None and hasattr(refreshed_pi, "get"):
                        amount_value = refreshed_pi.get("amount")

                charged_amount = (
                    int(str(amount_value))
                    if amount_value is not None
                    else int(ctx.student_pay_cents)
                )

                target_payout = int(ctx.target_instructor_payout_cents)
                top_up_amount = max(0, target_payout - charged_amount)
            except Exception as exc:
                self.logger.warning(
                    "fallback_top_up_computation_failed",
                    extra={
                        "booking_id": booking_id,
                        "payment_intent_id": payment_intent_id,
                        "error": str(exc),
                    },
                )
                top_up_amount = 0

        if top_up_amount is None:
            top_up_amount = 0

        destination_account_id: Optional[str] = None
        try:
            booking = self.booking_repository.get_by_id(booking_id)
        except Exception as exc:
            self.logger.warning(
                "booking_lookup_failed_for_top_up",
                extra={"booking_id": booking_id, "error": str(exc)},
            )
            booking = None

        if booking:
            try:
                instructor_profile = self.instructor_repository.get_by_user_id(
                    booking.instructor_id
                )
            except Exception as exc:
                self.logger.warning(
                    "instructor_profile_lookup_failed_for_top_up",
                    extra={
                        "booking_id": booking_id,
                        "instructor_id": booking.instructor_id,
                        "error": str(exc),
                    },
                )
                instructor_profile = None

            if instructor_profile:
                try:
                    connected_account = (
                        self.payment_repository.get_connected_account_by_instructor_id(
                            instructor_profile.id
                        )
                    )
                    destination_account_id = getattr(connected_account, "stripe_account_id", None)
                except Exception as exc:
                    self.logger.warning(
                        "connected_account_lookup_failed_for_top_up",
                        extra={
                            "booking_id": booking_id,
                            "instructor_profile_id": instructor_profile.id,
                            "error": str(exc),
                        },
                    )

        if top_up_amount > 0 and destination_account_id:
            try:
                self.ensure_top_up_transfer(
                    booking_id=booking_id,
                    payment_intent_id=payment_intent_id,
                    destination_account_id=destination_account_id,
                    amount_cents=top_up_amount,
                )
            except Exception as exc:
                self.logger.error(
                    "ensure_top_up_transfer_failed",
                    extra={
                        "booking_id": booking_id,
                        "payment_intent_id": payment_intent_id,
                        "amount_cents": top_up_amount,
                        "error": str(exc),
                    },
                )

        capture_result["payment_intent"] = refreshed_pi
        capture_result["top_up_transfer_cents"] = top_up_amount
        return capture_result

    @BaseService.measure_operation("stripe_build_charge_context")
    def build_charge_context(
        self, booking_id: str, requested_credit_cents: Optional[int] = None
    ) -> ChargeContext:
        """Return pricing and credit details for a booking without hitting Stripe."""

        try:
            with self.transaction():
                booking = self.booking_repository.get_by_id(booking_id)
                if not booking:
                    raise ServiceException("Booking not found for charge context")

                existing_applied = self.payment_repository.get_applied_credit_cents_for_booking(
                    booking_id
                )

                if requested_credit_cents is not None and requested_credit_cents > 0:
                    if existing_applied > 0:
                        applied_credit_cents = existing_applied
                        self.logger.warning(
                            "requested_credit_ignored_due_to_existing_usage",
                            extra={
                                "booking_id": booking_id,
                                "requested_credit_cents": requested_credit_cents,
                                "existing_applied_cents": existing_applied,
                            },
                        )
                    else:
                        # Part 6: Credits can only cover the lesson price, never the platform fee.
                        # Calculate lesson price (base_price_cents) and cap credits at that value.
                        lesson_price_cents = int(
                            Decimal(str(booking.hourly_rate))
                            * Decimal(booking.duration_minutes)
                            * Decimal(100)
                            / Decimal(60)
                        )
                        max_applicable_credits = min(
                            int(requested_credit_cents), lesson_price_cents
                        )
                        from .credit_service import CreditService

                        credit_service = CreditService(self.db)
                        applied_credit_cents = credit_service.reserve_credits_for_booking(
                            user_id=booking.student_id,
                            booking_id=booking_id,
                            max_amount_cents=max_applicable_credits,
                            use_transaction=False,
                        )
                        bp = self.booking_repository.ensure_payment(booking.id)
                        bp.credits_reserved_cents = applied_credit_cents
                else:
                    applied_credit_cents = existing_applied
                    bp = self.booking_repository.ensure_payment(booking.id)
                    if existing_applied > 0 and (
                        getattr(bp, "credits_reserved_cents", 0) != existing_applied
                    ):
                        bp.credits_reserved_cents = existing_applied

                pricing = self.pricing_service.compute_booking_pricing(
                    booking_id=booking_id,
                    applied_credit_cents=applied_credit_cents,
                )

            tier_pct = Decimal(str(pricing.get("instructor_tier_pct", 0)))
            context = ChargeContext(
                booking_id=booking_id,
                applied_credit_cents=applied_credit_cents,
                base_price_cents=int(pricing.get("base_price_cents", 0)),
                student_fee_cents=int(pricing.get("student_fee_cents", 0)),
                instructor_platform_fee_cents=int(pricing.get("instructor_platform_fee_cents", 0)),
                target_instructor_payout_cents=int(
                    pricing.get("target_instructor_payout_cents", 0)
                ),
                student_pay_cents=int(pricing.get("student_pay_cents", 0)),
                application_fee_cents=int(pricing.get("application_fee_cents", 0)),
                top_up_transfer_cents=int(pricing.get("top_up_transfer_cents", 0)),
                instructor_tier_pct=tier_pct,
            )

            if context.top_up_transfer_cents > 0:
                self.logger.info(
                    "Charge context requires top-up transfer",
                    extra={
                        "booking_id": booking_id,
                        "top_up_transfer_cents": context.top_up_transfer_cents,
                        "student_pay_cents": context.student_pay_cents,
                    },
                )

            return context
        except Exception as exc:
            if isinstance(exc, ServiceException):
                raise
            self.logger.error(
                "Failed to build charge context for booking %s: %s", booking_id, str(exc)
            )
            raise ServiceException("Failed to build charge context") from exc

    # ========== Payment Processing ==========

    @BaseService.measure_operation("stripe_create_payment_intent")
    def create_payment_intent(
        self,
        booking_id: str,
        customer_id: str,
        destination_account_id: str,
        *,
        charge_context: Optional[ChargeContext] = None,
        requested_credit_cents: Optional[int] = None,
        amount_cents: Optional[int] = None,
        currency: str = "usd",
        save_payment_method: bool = False,
    ) -> PaymentIntent:
        """
        Create a Stripe PaymentIntent for a booking.

        Uses 3-phase pattern to avoid holding DB locks during Stripe calls:
        - Phase 1: Build charge context if needed (quick transaction)
        - Phase 2: stripe.PaymentIntent.create (NO transaction)
        - Phase 3: Save payment record (quick transaction)

        Args:
            booking_id: Booking ID
            customer_id: Stripe customer ID
            destination_account_id: Stripe connected account ID
            charge_context: Pre-computed ChargeContext (optional)
            requested_credit_cents: Optional wallet credit amount to lock via ChargeContext
            amount_cents: Fallback amount when not using ChargeContext (e.g., tips)

        Returns:
            PaymentIntent record

        Raises:
            ServiceException: If PaymentIntent creation fails
        """
        try:
            # ========== PHASE 1: Build context/prepare data (quick transaction if needed) ==========
            ctx = charge_context
            if ctx is None and requested_credit_cents is not None:
                ctx = self.build_charge_context(booking_id, requested_credit_cents)

            if ctx is not None:
                amount = int(ctx.student_pay_cents)
                # Cap transfer amount to the actual charge; top-up handles any shortfall.
                transfer_amount_cents = min(amount, int(ctx.target_instructor_payout_cents))
                platform_retained_cents = max(0, amount - transfer_amount_cents)
                metadata = {
                    "booking_id": booking_id,
                    "platform": "instainstru",
                    "instructor_tier_pct": str(ctx.instructor_tier_pct),
                    "base_price_cents": str(ctx.base_price_cents),
                    "student_fee_cents": str(ctx.student_fee_cents),
                    "platform_fee_cents": str(ctx.instructor_platform_fee_cents),
                    "applied_credit_cents": str(ctx.applied_credit_cents),
                    "student_pay_cents": str(ctx.student_pay_cents),
                    "application_fee_cents": str(ctx.application_fee_cents),
                    "target_instructor_payout_cents": str(ctx.target_instructor_payout_cents),
                }

                if settings.environment != "production":
                    try:
                        metadata_student_pay_cents = int(metadata["student_pay_cents"])
                        metadata_base_price_cents = int(metadata["base_price_cents"])
                        metadata_student_fee_cents = int(metadata["student_fee_cents"])
                        metadata_applied_credit_cents = int(metadata["applied_credit_cents"])
                    except (KeyError, ValueError) as parse_error:
                        self.logger.warning(
                            "stripe.pi.preview_parity_parse_error",
                            {
                                "booking_id": booking_id,
                                "error": str(parse_error),
                                "metadata": metadata,
                            },
                        )
                    else:
                        parity_snapshot = {
                            "booking_id": booking_id,
                            "student_pay_cents": ctx.student_pay_cents,
                            "metadata_student_pay_cents": metadata_student_pay_cents,
                            "base_price_cents": ctx.base_price_cents,
                            "metadata_base_price_cents": metadata_base_price_cents,
                            "student_fee_cents": ctx.student_fee_cents,
                            "metadata_student_fee_cents": metadata_student_fee_cents,
                            "applied_credit_cents": ctx.applied_credit_cents,
                            "metadata_applied_credit_cents": metadata_applied_credit_cents,
                        }
                        self.logger.debug("stripe.pi.preview_parity", parity_snapshot)
                        if metadata_student_pay_cents != ctx.student_pay_cents:
                            raise ServiceException(
                                "PaymentIntent amount mismatch preview student pay"
                            )
                        if metadata_base_price_cents != ctx.base_price_cents:
                            raise ServiceException("PaymentIntent base price mismatch preview")
                        if metadata_student_fee_cents != ctx.student_fee_cents:
                            raise ServiceException("PaymentIntent student fee mismatch preview")
                        if metadata_applied_credit_cents != ctx.applied_credit_cents:
                            raise ServiceException("PaymentIntent credit mismatch preview")
            else:
                if amount_cents is None:
                    raise ServiceException(
                        "amount_cents is required when charge context is not provided"
                    )
                amount = int(amount_cents)
                # Fallback: use generic platform fee percentage to compute transfer amount
                platform_retained_cents = math.ceil(amount * self.platform_fee_percentage)
                transfer_amount_cents = amount - platform_retained_cents
                metadata = {
                    "booking_id": booking_id,
                    "platform": "instainstru",
                    "applied_credit_cents": "0",
                }

            # ========== PHASE 2: Stripe PaymentIntent.create (NO transaction) ==========
            try:
                # Use transfer_data[amount] architecture: platform receives full charge,
                # then transfers exactly transfer_amount_cents to instructor.
                stripe_kwargs: Dict[str, Any] = {
                    "amount": amount,
                    "currency": currency,
                    "customer": customer_id,
                    "transfer_data": {
                        "destination": destination_account_id,
                        "amount": transfer_amount_cents,
                    },
                    "metadata": metadata,
                    "capture_method": "manual",
                    "automatic_payment_methods": {
                        "enabled": True,
                        "allow_redirects": "never",
                    },
                    "idempotency_key": f"pi_checkout_{booking_id}_{amount}",
                }
                if ctx is not None:
                    stripe_kwargs["transfer_group"] = f"booking:{booking_id}"
                if save_payment_method:
                    stripe_kwargs["setup_future_usage"] = "off_session"

                stripe_intent = self._call_with_retry(stripe.PaymentIntent.create, **stripe_kwargs)
                stripe_intent_id = stripe_intent.id
                stripe_intent_status = stripe_intent.status
                stripe_client_secret = stripe_intent.client_secret

            except Exception as e:
                if not self.stripe_configured:
                    production_mode = os.getenv("INSTAINSTRU_PRODUCTION_MODE", "").strip().lower()
                    if production_mode in {"1", "true", "yes", "on"}:
                        raise ServiceException(
                            "Stripe is not configured in production mode; refusing mock payment intent fallback"
                        ) from e
                    self.logger.warning(
                        "Stripe not configured or call failed (%s); using mock payment intent for booking %s",
                        e,
                        booking_id,
                    )
                    stripe_intent_id = f"mock_pi_{booking_id}"
                    stripe_intent_status = "requires_payment_method"
                    stripe_client_secret = f"mock_secret_{booking_id}"
                else:
                    raise

            # ========== PHASE 3: Save payment record (quick transaction) ==========
            with self.transaction():
                payment_record = self.payment_repository.create_payment_record(
                    booking_id=booking_id,
                    payment_intent_id=stripe_intent_id,
                    amount=amount,
                    application_fee=platform_retained_cents,
                    status=stripe_intent_status,
                    base_price_cents=ctx.base_price_cents if ctx else None,
                    instructor_tier_pct=ctx.instructor_tier_pct if ctx else None,
                    instructor_payout_cents=ctx.target_instructor_payout_cents if ctx else None,
                )

            # Store client_secret in instance cache for PaymentElement flow
            self._last_client_secret = stripe_client_secret

            self.logger.info(
                "Created payment intent %s for booking %s", stripe_intent_id, booking_id
            )
            return payment_record

        except stripe.StripeError as e:
            self.logger.error("Stripe error creating payment intent: %s", e)
            raise ServiceException(f"Failed to create payment intent: {str(e)}")
        except Exception as e:
            self.logger.error("Error creating payment intent: %s", e)
            raise ServiceException(f"Failed to create payment intent: {str(e)}")

    @BaseService.measure_operation("stripe_create_and_confirm_manual_authorization")
    def create_and_confirm_manual_authorization(
        self,
        *,
        booking_id: str,
        customer_id: str,
        destination_account_id: str,
        payment_method_id: str,
        amount_cents: int,
        currency: str = "usd",
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a manual-capture PaymentIntent for immediate authorization (<24h bookings) and confirm off-session.

        Uses transfer_data[amount] architecture: platform receives full charge, then transfers
        exactly transfer_amount_cents to instructor. Platform retains the difference.

        Returns a dict with keys: payment_intent (Stripe object), status, requires_action, client_secret.
        """
        try:
            # Calculate platform retained amount and instructor transfer amount
            platform_retained_cents = math.ceil(amount_cents * self.platform_fee_percentage)
            transfer_amount_cents = amount_cents - platform_retained_cents

            pi = self._call_with_retry(
                stripe.PaymentIntent.create,
                amount=amount_cents,
                currency=currency,
                customer=customer_id,
                payment_method=payment_method_id,
                capture_method="manual",
                confirm=True,
                off_session=True,
                automatic_payment_methods={
                    "enabled": True,
                    "allow_redirects": "never",
                },
                transfer_data={
                    "destination": destination_account_id,
                    "amount": transfer_amount_cents,
                },
                metadata={
                    "booking_id": booking_id,
                    "platform": "instainstru",
                    "applied_credit_cents": "0",
                    "target_instructor_payout_cents": str(transfer_amount_cents),
                },
                idempotency_key=idempotency_key,
            )

            result: Dict[str, Any] = {"payment_intent": pi, "status": pi.status}
            if getattr(pi, "status", "") == "requires_action":
                result.update(
                    {
                        "requires_action": True,
                        "client_secret": getattr(pi, "client_secret", None),
                    }
                )
            else:
                result.update({"requires_action": False, "client_secret": _ABSENT})

            # Persist/Upsert payment record if present in DB
            try:
                upsert = getattr(self.payment_repository, "upsert_payment_record", None)
                if callable(upsert):
                    upsert(
                        booking_id=booking_id,
                        payment_intent_id=pi.id,
                        amount=amount_cents,
                        application_fee=platform_retained_cents,
                        status=pi.status,
                    )
                else:
                    # Fallback to create; ignore duplicates gracefully
                    existing = self.payment_repository.get_payment_by_intent_id(pi.id)
                    if existing is None:
                        self.payment_repository.create_payment_record(
                            booking_id=booking_id,
                            payment_intent_id=pi.id,
                            amount=amount_cents,
                            application_fee=platform_retained_cents,
                            status=pi.status,
                        )
            except Exception:
                # Repository might not have helper; ignore non-critical persistence issues
                logger.debug("Non-fatal error ignored", exc_info=True)
            return result
        except stripe.StripeError as e:
            self.logger.error("Stripe error creating manual authorization: %s", e)
            raise ServiceException(f"Failed to authorize payment: {str(e)}")
        except Exception as e:
            self.logger.error("Error creating manual authorization: %s", e)
            raise ServiceException(f"Failed to authorize payment: {str(e)}")

    @BaseService.measure_operation("stripe_confirm_payment_intent")
    def confirm_payment_intent(
        self, payment_intent_id: str, payment_method_id: str
    ) -> PaymentIntent:
        """
        Confirm a payment intent with a payment method.

        Uses 3-phase pattern to avoid holding DB locks during Stripe calls:
        - Phase 1: (none needed - no pre-read required)
        - Phase 2: stripe.PaymentIntent.confirm (NO transaction)
        - Phase 3: Update payment status (quick transaction)

        Args:
            payment_intent_id: Stripe payment intent ID
            payment_method_id: Stripe payment method ID

        Returns:
            Updated PaymentIntent record

        Raises:
            ServiceException: If confirmation fails
        """
        try:
            # ========== PHASE 2: Stripe confirm (NO transaction) ==========
            # Confirm payment intent with return_url for redirect-based payment methods
            stripe_intent = stripe.PaymentIntent.confirm(
                payment_intent_id,
                payment_method=payment_method_id,
                return_url=f"{settings.frontend_url}/student/payment/complete",
            )
            stripe_status = stripe_intent.status

            # ========== PHASE 3: Update payment status (quick transaction) ==========
            with self.transaction():
                payment_record = self.payment_repository.update_payment_status(
                    payment_intent_id, stripe_status
                )

                if not payment_record:
                    raise ServiceException(
                        f"Payment record not found for intent {payment_intent_id}"
                    )

            self.logger.info("Confirmed payment intent %s", payment_intent_id)
            return payment_record

        except stripe.StripeError as e:
            self.logger.error("Stripe error confirming payment: %s", e)
            raise ServiceException(f"Failed to confirm payment: {str(e)}")
        except Exception as e:
            self.logger.error("Error confirming payment: %s", e)
            raise ServiceException(f"Failed to confirm payment: {str(e)}")

    @BaseService.measure_operation("stripe_process_booking_payment")
    def process_booking_payment(
        self,
        booking_id: str,
        payment_method_id: Optional[str] = None,
        requested_credit_cents: Optional[int] = None,
        save_payment_method: bool = False,
    ) -> Dict[str, Any]:
        """
        Process payment for a booking end-to-end.

        Architecture Note (v123): This method uses 3-phase pattern to avoid
        holding DB locks during Stripe network calls:
        - Phase 1: Quick read transaction (~5ms)
        - Phase 2: Stripe calls (no transaction, 200-400ms)
        - Phase 3: Quick write transaction (~5ms)

        Args:
            booking_id: Booking ID
            payment_method_id: Stripe payment method ID (required when balance remains)
            requested_credit_cents: Optional wallet credit amount (in cents) requested by student

        Returns:
            Dictionary with payment result

        Raises:
            ServiceException: If payment processing fails
        """
        try:
            # ========== PHASE 1: Read/validate (quick transaction) ==========
            with self.transaction():
                booking = self.booking_repository.get_by_id(booking_id)
                if not booking:
                    raise ServiceException(f"Booking {booking_id} not found")

                instructor_profile = self.instructor_repository.get_by_user_id(
                    booking.instructor_id
                )
                if not instructor_profile:
                    raise ServiceException(
                        f"Instructor profile not found for user {booking.instructor_id}"
                    )

                connected_account = self.payment_repository.get_connected_account_by_instructor_id(
                    instructor_profile.id
                )
                if not connected_account or not connected_account.onboarding_completed:
                    raise ServiceException("Instructor payment account not set up")

                booking_start_utc = booking.booking_start_utc
                if not isinstance(booking_start_utc, datetime):
                    booking_start_utc = datetime.combine(  # tz-pattern-ok: fallback for legacy
                        booking.booking_date,
                        booking.start_time,
                        tzinfo=timezone.utc,
                    )
                elif booking_start_utc.tzinfo is None:
                    booking_start_utc = booking_start_utc.replace(tzinfo=timezone.utc)

                hours_until_lesson = (
                    booking_start_utc - datetime.now(timezone.utc)
                ).total_seconds() / 3600
                immediate_auth = hours_until_lesson < 24
                auth_scheduled_for = (
                    booking_start_utc - timedelta(hours=24) if not immediate_auth else None
                )

                # Store IDs for Phase 2 (avoid holding ORM objects across phases)
                student_id = booking.student_id
                stripe_account_id = connected_account.stripe_account_id

            # ========== PHASE 2: Stripe calls (NO transaction) ==========
            # get_or_create_customer may call Stripe if customer doesn't exist
            customer = self.get_or_create_customer(student_id)

            # build_charge_context has its own transaction for credit application
            charge_context = self.build_charge_context(
                booking_id=booking_id, requested_credit_cents=requested_credit_cents
            )

            # Handle credit-only case (student pays nothing with card)
            if charge_context.student_pay_cents <= 0:
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
                        except Exception:
                            logger.debug("Non-fatal error ignored", exc_info=True)
                        bp = self.booking_repository.ensure_payment(booking.id)
                        bp.payment_status = PaymentStatus.AUTHORIZED.value
                        bp.auth_attempted_at = datetime.now(timezone.utc)
                        bp.auth_failure_count = 0
                        bp.auth_last_error = None

                return {
                    "success": True,
                    "payment_intent_id": "credit_only",
                    "status": "succeeded",
                    "amount": 0,
                    "application_fee": 0,
                    "client_secret": _ABSENT,
                }

            if not payment_method_id:
                # PaymentElement flow: create PaymentIntent without confirming,
                # return client_secret so the frontend can render PaymentElement
                # and call stripe.confirmPayment().
                self._last_client_secret = None
                payment_record = self.create_payment_intent(
                    booking_id=booking_id,
                    customer_id=customer.stripe_customer_id,
                    destination_account_id=stripe_account_id,
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

            # create_payment_intent has its own transaction + Stripe call
            payment_record = self.create_payment_intent(
                booking_id=booking_id,
                customer_id=customer.stripe_customer_id,
                destination_account_id=stripe_account_id,
                charge_context=charge_context,
            )

            stripe_error: Optional[str] = None
            if immediate_auth:
                # Direct Stripe call - NO transaction held during network call
                try:
                    stripe_intent = stripe.PaymentIntent.confirm(
                        payment_record.stripe_payment_intent_id,
                        payment_method=payment_method_id,
                        return_url=f"{settings.frontend_url}/student/payment/complete",
                    )
                except stripe.error.CardError as e:
                    stripe_intent = None
                    stripe_error = str(e)
                except Exception as e:
                    stripe_intent = None
                    stripe_error = str(e)
            else:
                stripe_intent = None
                stripe_error = None

            # ========== PHASE 3: Write (quick transaction) ==========
            with self.transaction():
                # Re-fetch booking to avoid stale ORM object
                booking = self.booking_repository.get_by_id(booking_id)
                if booking:
                    bp = self.booking_repository.ensure_payment(booking.id)
                    bp.payment_intent_id = payment_record.stripe_payment_intent_id
                    bp.payment_method_id = payment_method_id

                    if immediate_auth:
                        now = datetime.now(timezone.utc)
                        if stripe_intent and stripe_intent.status in {
                            "requires_capture",
                            "succeeded",
                        }:
                            try:
                                self.payment_repository.update_payment_status(
                                    payment_record.stripe_payment_intent_id, stripe_intent.status
                                )
                            except Exception:
                                logger.debug("Non-fatal error ignored", exc_info=True)
                            bp.payment_status = PaymentStatus.AUTHORIZED.value
                            bp.auth_attempted_at = now
                            bp.auth_failure_count = 0
                            bp.auth_last_error = None
                            bp.auth_scheduled_for = None
                        else:
                            bp.payment_status = PaymentStatus.PAYMENT_METHOD_REQUIRED.value
                            bp.auth_attempted_at = now
                            bp.auth_failure_count = (
                                int(getattr(bp, "auth_failure_count", 0) or 0) + 1
                            )
                            bp.auth_last_error = stripe_error or "authorization_failed"
                            bp.auth_scheduled_for = None
                    else:
                        bp.payment_status = PaymentStatus.SCHEDULED.value
                        bp.auth_scheduled_for = auth_scheduled_for
                        bp.auth_failure_count = 0
                        bp.auth_last_error = None

                        try:
                            self.payment_repository.create_payment_event(
                                booking_id=booking.id,
                                event_type="auth_scheduled",
                                event_data={
                                    "payment_method_id": payment_method_id,
                                    "scheduled_for": auth_scheduled_for.isoformat()
                                    if auth_scheduled_for
                                    else None,
                                    "hours_until_lesson": hours_until_lesson,
                                },
                            )
                        except Exception:
                            logger.debug("Non-fatal error ignored", exc_info=True)
            immediate_failed = immediate_auth and (
                stripe_intent is None
                or stripe_intent.status not in {"requires_capture", "succeeded"}
            )
            if immediate_failed:
                try:
                    enqueue_task(
                        "app.tasks.payment_tasks.check_immediate_auth_timeout",
                        args=(booking_id,),
                        countdown=30 * 60,
                    )
                except Exception:
                    logger.debug("Non-fatal error ignored", exc_info=True)
            if immediate_auth:
                requires_action = stripe_intent is not None and stripe_intent.status in [
                    "requires_action",
                    "requires_confirmation",
                ]
                client_secret = (
                    getattr(stripe_intent, "client_secret", None) if requires_action else None
                )

                if stripe_intent is None:
                    return {
                        "success": False,
                        "payment_intent_id": payment_record.stripe_payment_intent_id,
                        "status": "auth_failed",
                        "amount": payment_record.amount,
                        "application_fee": payment_record.application_fee,
                        "client_secret": _ABSENT,
                    }

                return {
                    "success": stripe_intent.status in {"requires_capture", "succeeded"},
                    "payment_intent_id": payment_record.stripe_payment_intent_id,
                    "status": stripe_intent.status,
                    "amount": payment_record.amount,
                    "application_fee": payment_record.application_fee,
                    "client_secret": client_secret,
                }

            return {
                "success": True,
                "payment_intent_id": payment_record.stripe_payment_intent_id,
                "status": "scheduled",
                "amount": payment_record.amount,
                "application_fee": payment_record.application_fee,
                "client_secret": _ABSENT,
            }

        except Exception as e:
            if isinstance(e, ServiceException):
                raise
            self.logger.error("Error processing booking payment: %s", e)
            raise ServiceException(f"Failed to process payment: {str(e)}")

    # ========== Webhook Handling ==========

    @BaseService.measure_operation("stripe_verify_webhook_signature")
    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify Stripe webhook signature.

        Args:
            payload: Raw webhook payload
            signature: Stripe signature header

        Returns:
            True if signature is valid

        Raises:
            ServiceException: If verification fails
        """
        try:
            webhook_secret = settings.stripe_webhook_secret
            if not webhook_secret:
                raise ServiceException("Webhook secret not configured")

            # Verify signature
            try:
                secret_value = (
                    webhook_secret.get_secret_value()
                    if hasattr(webhook_secret, "get_secret_value")
                    else str(webhook_secret)
                )
                stripe.Webhook.construct_event(payload, signature, secret_value)
                return True
            except stripe.SignatureVerificationError:
                self.logger.warning("Invalid webhook signature")
                return False

        except Exception as e:
            self.logger.error("Error verifying webhook signature: %s", e)
            raise ServiceException(f"Failed to verify webhook signature: {str(e)}")

    @BaseService.measure_operation("stripe_handle_webhook")
    def handle_webhook_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process an already-verified webhook event.

        This method is called after signature verification has been performed,
        typically when multiple webhook secrets need to be tried.

        Args:
            event: Already-parsed and verified Stripe event dictionary

        Returns:
            Dictionary with processing result

        Raises:
            ServiceException: If event processing fails
        """
        try:
            event_type = event.get("type", "")
            self.logger.info("Processing webhook event: %s", event_type)

            # Route to appropriate handler based on event type
            if event_type.startswith("payment_intent."):
                success = self.handle_payment_intent_webhook(event)
                return {"success": success, "event_type": event_type}

            elif event_type.startswith("account."):
                success = self._handle_account_webhook(event)
                return {"success": success, "event_type": event_type}

            elif event_type.startswith("transfer."):
                success = self._handle_transfer_webhook(event)
                return {"success": success, "event_type": event_type}

            elif event_type.startswith("charge."):
                success = self._handle_charge_webhook(event)
                return {"success": success, "event_type": event_type}

            elif event_type.startswith("payout."):
                success = self._handle_payout_webhook(event)
                return {"success": success, "event_type": event_type}

            elif event_type.startswith("identity.verification_session."):
                success = self._handle_identity_webhook(event)
                return {"success": success, "event_type": event_type}

            else:
                self.logger.info("Unhandled webhook event type: %s", event_type)
                return {"success": True, "event_type": event_type, "handled": False}

        except Exception as e:
            self.logger.error("Error processing webhook event: %s", e)
            raise ServiceException(f"Failed to process webhook event: {str(e)}")

    @BaseService.measure_operation("stripe_handle_webhook_with_verification")
    def handle_webhook(self, payload: str, signature: str) -> Dict[str, Any]:
        """
        Webhook handler that verifies signature and processes events.

        Combines signature verification with event processing in a single call.
        For pre-verified events, use handle_webhook_event() directly.

        Args:
            payload: Raw webhook payload as string
            signature: Stripe signature header

        Returns:
            Dictionary with processing result

        Raises:
            ServiceException: If webhook processing fails
        """
        try:
            # Verify webhook signature and construct event
            webhook_secret = (
                settings.stripe_webhook_secret.get_secret_value()
                if settings.stripe_webhook_secret
                else None
            )
            if not webhook_secret:
                raise ServiceException("Webhook secret not configured")

            try:
                event = stripe.Webhook.construct_event(
                    payload.encode("utf-8") if isinstance(payload, str) else payload,
                    signature,
                    webhook_secret,
                )
            except stripe.SignatureVerificationError as e:
                self.logger.warning("Invalid webhook signature: %s", e)
                raise ServiceException("Invalid webhook signature")
            except Exception as e:
                self.logger.error("Error constructing webhook event: %s", e)
                raise ServiceException(f"Invalid webhook payload: {str(e)}")

            # Use the new method to process the event
            result = self.handle_webhook_event(event)
            return dict(result)

        except ServiceException:
            raise
        except Exception as e:
            self.logger.error("Unexpected error handling webhook: %s", e)
            raise ServiceException(f"Failed to process webhook: {str(e)}")

    @BaseService.measure_operation("stripe_handle_payment_intent_webhook")
    def handle_payment_intent_webhook(self, event: Dict[str, Any]) -> bool:
        """
        Handle payment intent webhook events.

        Args:
            event: Stripe webhook event

        Returns:
            True if handled successfully

        Raises:
            ServiceException: If handling fails
        """
        try:
            with self.transaction():
                payment_intent = event["data"]["object"]
                payment_intent_id = payment_intent["id"]
                new_status = payment_intent["status"]

                # Update payment status
                payment_record = self.payment_repository.update_payment_status(
                    payment_intent_id, new_status
                )

                if payment_record:
                    self.logger.info(
                        "Updated payment %s status to %s", payment_intent_id, new_status
                    )

                    # Handle successful payments
                    if new_status == "succeeded":
                        self._handle_successful_payment(payment_record)

                    # Handle requires_capture — advance booking to CONFIRMED
                    # This fires after PaymentElement confirmPayment() succeeds
                    if new_status == "requires_capture":
                        self._advance_booking_on_capture(payment_record)

                    return True
                else:
                    self.logger.warning(
                        "Payment record not found for webhook event %s",
                        payment_intent_id,
                    )
                    return False

        except Exception as e:
            self.logger.error("Error handling payment intent webhook: %s", e)
            raise ServiceException(f"Failed to handle payment webhook: {str(e)}")

    @BaseService.measure_operation("stripe_advance_booking_on_capture")
    def _advance_booking_on_capture(self, payment_record: PaymentIntent) -> None:
        """Advance booking to CONFIRMED when PI reaches requires_capture (PaymentElement flow).

        Uses atomic UPDATE ... WHERE status='PENDING' to avoid TOCTOU races.
        Must NOT swallow exceptions — the webhook handler relies on exceptions
        to return 5xx so Stripe retries on transient failures.
        """
        booking_id = payment_record.booking_id
        now = datetime.now(timezone.utc)

        with self.transaction():
            # Atomic: only update if still PENDING (idempotent — no-op if already CONFIRMED)
            rows = self.booking_repository.atomic_confirm_if_pending(booking_id, now)

            if rows == 0:
                # Already confirmed or booking doesn't exist — idempotent no-op
                self.logger.info(
                    "Booking %s not in PENDING state (rows=%d), skipping capture advance",
                    booking_id,
                    rows,
                )
                return

            bp = self.booking_repository.ensure_payment(booking_id)
            bp.payment_status = PaymentStatus.AUTHORIZED.value
            bp.payment_intent_id = payment_record.stripe_payment_intent_id
            bp.auth_attempted_at = now
            bp.auth_failure_count = 0
            bp.auth_last_error = None

        self.logger.info(
            "Booking %s confirmed via PaymentElement webhook (requires_capture)",
            booking_id,
        )

    def _handle_successful_payment(self, payment_record: PaymentIntent) -> None:
        """
        Handle successful payment processing.

        Args:
            payment_record: PaymentIntent record
        """
        try:
            booking = self.booking_repository.get_by_id(payment_record.booking_id)
            if not booking:
                self.logger.warning(
                    "Successful payment received for missing booking %s",
                    payment_record.booking_id,
                )
                return

            if booking.status == "PENDING":
                booking.status = "CONFIRMED"
                self.booking_repository.flush()

            from ..services.booking_service import BookingService

            booking_service = BookingService(self.db, cache_service=self.cache_service)
            try:
                booking_service.invalidate_booking_cache(booking)
            except Exception as cache_err:
                self.logger.warning("Failed to invalidate booking caches: %s", cache_err)

            self.logger.info(
                "Processed successful payment for booking %s",
                payment_record.booking_id,
            )

        except Exception as e:
            self.logger.error("Error handling successful payment: %s", e)
            # Don't raise exception to avoid webhook retry loops

    def _handle_account_webhook(self, event: Dict[str, Any]) -> bool:
        """Handle Stripe Connect account events."""
        try:
            event_type = event.get("type", "")
            account_data = event.get("data", {}).get("object", {})
            account_id = account_data.get("id")

            if event_type == "account.updated":
                # Check if onboarding completed
                charges_enabled = account_data.get("charges_enabled", False)
                details_submitted = account_data.get("details_submitted", False)

                if charges_enabled and details_submitted:
                    self.payment_repository.update_onboarding_status(account_id, True)
                    self.logger.info("Account %s onboarding completed", account_id)

                return True

            elif event_type == "account.application.deauthorized":
                self.logger.warning("Account %s was deauthorized", account_id)
                # Could implement logic to notify instructor or disable their services
                return True

            return False

        except Exception as e:
            self.logger.error("Error handling account webhook: %s", e)
            return False

    def _handle_transfer_webhook(self, event: Dict[str, Any]) -> bool:
        """Handle Stripe transfer events."""
        try:
            event_type = event.get("type", "")
            transfer_data = event.get("data", {}).get("object", {})
            transfer_id = transfer_data.get("id")

            if event_type == "transfer.created":
                self.logger.info("Transfer %s created", transfer_id)
                return True

            elif event_type == "transfer.paid":
                self.logger.info("Transfer %s paid successfully", transfer_id)
                return True

            elif event_type == "transfer.failed":
                self.logger.error("Transfer %s failed", transfer_id)
                # Could implement logic to notify instructor or retry
                return True

            elif event_type == "transfer.reversed":
                # Funds moved back to platform balance; record event for the related booking if possible
                try:
                    amount = transfer_data.get("amount")
                    # If we had stored mapping transfer->booking, we would look it up. Fallback: log only.
                    self.logger.info("Transfer %s reversed (amount=%s)", transfer_id, amount)
                except Exception:
                    logger.debug("Non-fatal error ignored", exc_info=True)
                return True

            return False

        except Exception as e:
            self.logger.error("Error handling transfer webhook: %s", e)
            return False

    def _handle_charge_webhook(self, event: Dict[str, Any]) -> bool:
        """Handle Stripe charge events."""
        try:
            event_type = event.get("type", "")
            if event_type == "charge.dispute.created":
                return self._handle_dispute_created(event)
            if event_type == "charge.dispute.closed":
                return self._handle_dispute_closed(event)

            charge_data = event.get("data", {}).get("object", {})
            charge_id = charge_data.get("id")

            if event_type == "charge.succeeded":
                self.logger.info("Charge %s succeeded", charge_id)
                return True

            elif event_type == "charge.failed":
                self.logger.error("Charge %s failed", charge_id)
                # Could implement logic to notify student
                return True

            elif event_type == "charge.refunded":
                self.logger.info("Charge %s refunded", charge_id)
                try:
                    # Update payment record if possible
                    payment_intent_id = charge_data.get("payment_intent")
                    if payment_intent_id:
                        self.payment_repository.update_payment_status(payment_intent_id, "refunded")
                        booking_payment = self.payment_repository.get_payment_by_intent_id(
                            payment_intent_id
                        )
                        if not booking_payment:
                            self.logger.critical(
                                "Stripe refund reconciliation gap: no local payment record for "
                                "payment_intent %s (charge %s)",
                                payment_intent_id,
                                charge_id,
                            )
                        else:
                            booking = self.booking_repository.get_by_id(booking_payment.booking_id)
                            if not booking:
                                self.logger.critical(
                                    "Stripe refund reconciliation gap: no booking %s for "
                                    "payment_intent %s (charge %s)",
                                    booking_payment.booking_id,
                                    payment_intent_id,
                                    charge_id,
                                )
                            else:
                                # Emit a domain-level log; event stream is handled by tasks/routes
                                self.logger.info(
                                    "Marked booking %s payment as refunded for PI %s",
                                    booking.id,
                                    payment_intent_id,
                                )
                                try:
                                    credit_service = StudentCreditService(self.db)
                                    credit_service.process_refund_hooks(booking=booking)
                                except Exception as hook_exc:
                                    self.logger.error(
                                        "Failed adjusting student credits on refund for booking %s: %s",
                                        booking.id,
                                        hook_exc,
                                    )
                except Exception as e:
                    self.logger.error("Failed to process charge.refunded: %s", e)
                return True

            return False
        except Exception as e:
            self.logger.error("Error handling charge webhook: %s", e)
            return False

    def _resolve_payment_intent_id_from_charge(self, charge_id: Optional[str]) -> Optional[str]:
        if not charge_id or not self.stripe_configured:
            return None
        try:
            charge_resource = getattr(stripe, "Charge", None)
            if charge_resource is None:
                return None
            charge = charge_resource.retrieve(charge_id)
            payment_intent_id = getattr(charge, "payment_intent", None)
            if payment_intent_id is None and hasattr(charge, "get"):
                payment_intent_id = charge.get("payment_intent")
            return cast(Optional[str], payment_intent_id)
        except Exception as exc:  # pragma: no cover - network path
            self.logger.warning(
                "Failed to resolve payment_intent from charge %s: %s", charge_id, exc
            )
            return None

    def _handle_dispute_created(self, event: Dict[str, Any]) -> bool:
        """Handle charge.dispute.created events."""
        dispute = event.get("data", {}).get("object", {}) or {}
        dispute_id = dispute.get("id")
        payment_intent_id = dispute.get(
            "payment_intent"
        ) or self._resolve_payment_intent_id_from_charge(dispute.get("charge"))

        if not payment_intent_id:
            self.logger.warning("Dispute %s missing payment_intent", dispute_id)
            return False

        payment_record = self.payment_repository.get_payment_by_intent_id(payment_intent_id)
        if not payment_record:
            self.logger.warning(
                "Dispute %s for unknown payment_intent %s", dispute_id, payment_intent_id
            )
            return False

        booking = self.booking_repository.get_by_id(payment_record.booking_id)
        if not booking:
            self.logger.warning(
                "Dispute %s for unknown booking %s", dispute_id, payment_record.booking_id
            )
            return False

        with booking_lock_sync(booking.id) as acquired:
            if not acquired:
                self.logger.warning(
                    "Dispute %s skipped due to lock for booking %s", dispute_id, booking.id
                )
                return False

            transfer = self.booking_repository.get_transfer_by_booking_id(booking.id)
            transfer_id = transfer.stripe_transfer_id if transfer else None
            reversal_id: Optional[str] = None
            reversal_error: Optional[str] = None

            if transfer_id and not (transfer.transfer_reversed if transfer else False):
                try:
                    reversal = self.reverse_transfer(
                        transfer_id=transfer_id,
                        idempotency_key=f"dispute_reversal_{booking.id}",
                        reason="dispute_opened",
                    )
                    reversal_payload = reversal.get("reversal")
                    reversal_id = (
                        reversal_payload.get("id")
                        if isinstance(reversal_payload, dict)
                        else getattr(reversal_payload, "id", None)
                    )
                except Exception as exc:
                    reversal_error = str(exc)

            with self.transaction():
                booking = self.booking_repository.get_by_id(booking.id)
                if not booking:
                    return False

                bp = self.booking_repository.ensure_payment(booking.id)
                bp.payment_status = PaymentStatus.MANUAL_REVIEW.value
                dispute_record = self.booking_repository.ensure_dispute(booking.id)
                dispute_record.dispute_id = dispute_id
                dispute_record.dispute_status = dispute.get("status")
                dispute_record.dispute_amount = dispute.get("amount")
                dispute_record.dispute_created_at = datetime.now(timezone.utc)

                if reversal_id:
                    transfer_record = self.booking_repository.ensure_transfer(booking.id)
                    transfer_record.transfer_reversed = True
                    transfer_record.transfer_reversal_id = reversal_id
                elif reversal_error:
                    transfer_record = self.booking_repository.ensure_transfer(booking.id)
                    transfer_record.transfer_reversal_failed = True
                    transfer_record.transfer_reversal_error = reversal_error
                    transfer_record.transfer_reversal_failed_at = datetime.now(timezone.utc)
                    transfer_record.transfer_reversal_retry_count = (
                        int(getattr(transfer_record, "transfer_reversal_retry_count", 0) or 0) + 1
                    )

                from .credit_service import CreditService

                credit_service = CreditService(self.db)
                credit_service.freeze_credits_for_booking(
                    booking_id=booking.id,
                    reason=f"Dispute opened for booking {booking.id}",
                    use_transaction=False,
                )
                try:
                    events = self.payment_repository.get_payment_events_for_booking(booking.id)
                except Exception:
                    events = []
                already_applied = any(
                    getattr(event, "event_type", None) == "negative_balance_applied"
                    and isinstance(getattr(event, "event_data", None), dict)
                    and getattr(event, "event_data", {}).get("dispute_id") == dispute_id
                    for event in events
                )
                spent_cents = credit_service.get_spent_credits_for_booking(booking_id=booking.id)
                if spent_cents > 0 and not already_applied:
                    credit_service.apply_negative_balance(
                        user_id=booking.student_id,
                        amount_cents=spent_cents,
                        reason=f"dispute_opened:{dispute_id}",
                        use_transaction=False,
                    )
                    try:
                        self.payment_repository.create_payment_event(
                            booking_id=booking.id,
                            event_type="negative_balance_applied",
                            event_data={
                                "dispute_id": dispute_id,
                                "amount_cents": spent_cents,
                            },
                        )
                    except Exception:
                        logger.debug("Non-fatal error ignored", exc_info=True)
                try:
                    self.payment_repository.create_payment_event(
                        booking_id=booking.id,
                        event_type="dispute_opened",
                        event_data={
                            "dispute_id": dispute_id,
                            "payment_intent_id": payment_intent_id,
                            "status": dispute.get("status"),
                            "amount": dispute.get("amount"),
                            "transfer_reversal_id": reversal_id,
                            "transfer_reversal_error": reversal_error,
                        },
                    )
                except Exception:
                    logger.debug("Non-fatal error ignored", exc_info=True)
        return True

    def _handle_dispute_closed(self, event: Dict[str, Any]) -> bool:
        """Handle charge.dispute.closed events."""
        dispute = event.get("data", {}).get("object", {}) or {}
        dispute_id = dispute.get("id")
        payment_intent_id = dispute.get(
            "payment_intent"
        ) or self._resolve_payment_intent_id_from_charge(dispute.get("charge"))

        if not payment_intent_id:
            self.logger.warning("Dispute %s missing payment_intent", dispute_id)
            return False

        payment_record = self.payment_repository.get_payment_by_intent_id(payment_intent_id)
        if not payment_record:
            self.logger.warning(
                "Dispute %s for unknown payment_intent %s", dispute_id, payment_intent_id
            )
            return False

        booking = self.booking_repository.get_by_id(payment_record.booking_id)
        if not booking:
            self.logger.warning(
                "Dispute %s for unknown booking %s", dispute_id, payment_record.booking_id
            )
            return False

        status = dispute.get("status")

        with booking_lock_sync(booking.id) as acquired:
            if not acquired:
                self.logger.warning(
                    "Dispute %s skipped due to lock for booking %s", dispute_id, booking.id
                )
                return False

            with self.transaction():
                booking = self.booking_repository.get_by_id(booking.id)
                if not booking:
                    return False

                bp = self.booking_repository.ensure_payment(booking.id)
                dispute_record = self.booking_repository.ensure_dispute(booking.id)
                dispute_record.dispute_status = status
                dispute_record.dispute_resolved_at = datetime.now(timezone.utc)

                from .credit_service import CreditService

                credit_service = CreditService(self.db)

                if status in {"won", "warning_closed"}:
                    try:
                        events = self.payment_repository.get_payment_events_for_booking(booking.id)
                    except Exception:
                        events = []
                    negative_event = next(
                        (
                            event
                            for event in events
                            if getattr(event, "event_type", None) == "negative_balance_applied"
                            and isinstance(getattr(event, "event_data", None), dict)
                            and getattr(event, "event_data", {}).get("dispute_id") == dispute_id
                        ),
                        None,
                    )
                    if negative_event:
                        spent_cents = credit_service.get_spent_credits_for_booking(
                            booking_id=booking.id
                        )
                        event_payload = getattr(negative_event, "event_data", None)
                        if isinstance(event_payload, dict):
                            try:
                                spent_cents = int(
                                    event_payload.get("amount_cents", spent_cents) or spent_cents
                                )
                            except (TypeError, ValueError):
                                pass
                        credit_service.clear_negative_balance(
                            user_id=booking.student_id,
                            amount_cents=spent_cents,
                            reason=f"dispute_won:{dispute_id}",
                            use_transaction=False,
                        )
                        try:
                            self.payment_repository.create_payment_event(
                                booking_id=booking.id,
                                event_type="negative_balance_cleared",
                                event_data={
                                    "dispute_id": dispute_id,
                                    "amount_cents": spent_cents,
                                },
                            )
                        except Exception:
                            logger.debug("Non-fatal error ignored", exc_info=True)
                    credit_service.unfreeze_credits_for_booking(
                        booking_id=booking.id, use_transaction=False
                    )
                    bp.payment_status = PaymentStatus.SETTLED.value
                    bp.settlement_outcome = "dispute_won"
                elif status == "lost":
                    credit_service.revoke_credits_for_booking(
                        booking_id=booking.id,
                        reason=f"dispute_lost:{dispute_id}",
                        use_transaction=False,
                    )
                    spent_cents = credit_service.get_spent_credits_for_booking(
                        booking_id=booking.id
                    )
                    try:
                        events = self.payment_repository.get_payment_events_for_booking(booking.id)
                    except Exception:
                        events = []
                    already_applied = any(
                        getattr(event, "event_type", None) == "negative_balance_applied"
                        and isinstance(getattr(event, "event_data", None), dict)
                        and getattr(event, "event_data", {}).get("dispute_id") == dispute_id
                        for event in events
                    )
                    if spent_cents > 0 and not already_applied:
                        credit_service.apply_negative_balance(
                            user_id=booking.student_id,
                            amount_cents=spent_cents,
                            reason=f"dispute_lost:{dispute_id}",
                            use_transaction=False,
                        )
                        try:
                            self.payment_repository.create_payment_event(
                                booking_id=booking.id,
                                event_type="negative_balance_applied",
                                event_data={
                                    "dispute_id": dispute_id,
                                    "amount_cents": spent_cents,
                                },
                            )
                        except Exception:
                            logger.debug("Non-fatal error ignored", exc_info=True)
                    user_repo = RepositoryFactory.create_base_repository(self.db, User)
                    user = user_repo.get_by_id(booking.student_id)
                    if user:
                        user.account_restricted = True
                        user.account_restricted_at = datetime.now(timezone.utc)
                        user.account_restricted_reason = f"dispute_lost:{dispute_id}"
                    bp.payment_status = PaymentStatus.SETTLED.value
                    bp.settlement_outcome = "student_wins_dispute_full_refund"

                try:
                    self.payment_repository.create_payment_event(
                        booking_id=booking.id,
                        event_type="dispute_closed",
                        event_data={
                            "dispute_id": dispute_id,
                            "payment_intent_id": payment_intent_id,
                            "status": status,
                        },
                    )
                except Exception:
                    logger.debug("Non-fatal error ignored", exc_info=True)
        return True

    def _handle_payout_webhook(self, event: Dict[str, Any]) -> bool:
        """Handle Stripe payout events for connected accounts."""
        try:
            event_type = event.get("type", "")
            payout = event.get("data", {}).get("object", {})
            payout_id = payout.get("id")
            amount = payout.get("amount")
            status = payout.get("status")
            arrival_raw = payout.get("arrival_date")
            arrival_date: Optional[datetime] = None
            if isinstance(arrival_raw, datetime):
                arrival_date = (
                    arrival_raw.replace(tzinfo=timezone.utc)
                    if arrival_raw.tzinfo is None
                    else arrival_raw
                )
            elif isinstance(arrival_raw, (int, float)):
                arrival_date = datetime.fromtimestamp(arrival_raw, tz=timezone.utc)
            elif isinstance(arrival_raw, str):
                try:
                    parsed = datetime.fromisoformat(arrival_raw)
                    arrival_date = (
                        parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
                    )
                except ValueError:
                    arrival_date = None
            account_id = payout.get("destination") or payout.get("stripe_account")

            if event_type == "payout.created":
                self.logger.info(
                    "Payout created: %s amount=%s status=%s arrival=%s",
                    payout_id,
                    amount,
                    status,
                    arrival_date,
                )
                try:
                    # Resolve instructor_profile_id via connected account
                    if account_id:
                        acct = self.payment_repository.get_connected_account_by_stripe_id(
                            account_id
                        )
                        if acct and acct.instructor_profile_id:
                            self.payment_repository.record_payout_event(
                                instructor_profile_id=acct.instructor_profile_id,
                                stripe_account_id=account_id,
                                payout_id=payout_id,
                                amount_cents=amount,
                                status=status,
                                arrival_date=arrival_date,
                            )
                except Exception as e:  # best-effort analytics only
                    self.logger.warning("Failed to persist payout.created analytics: %s", e)
                return True

            if event_type == "payout.paid":
                self.logger.info(
                    "Payout paid: %s amount=%s status=%s arrival=%s",
                    payout_id,
                    amount,
                    status,
                    arrival_date,
                )
                try:
                    if account_id:
                        acct = self.payment_repository.get_connected_account_by_stripe_id(
                            account_id
                        )
                        if acct and acct.instructor_profile_id:
                            self.payment_repository.record_payout_event(
                                instructor_profile_id=acct.instructor_profile_id,
                                stripe_account_id=account_id,
                                payout_id=payout_id,
                                amount_cents=amount,
                                status=status,
                                arrival_date=arrival_date,
                            )
                            try:
                                profile = self.instructor_repository.get_by_id_join_user(
                                    acct.instructor_profile_id
                                )
                                if profile and profile.user_id and amount is not None:
                                    from app.services.notification_service import (
                                        NotificationService,
                                    )

                                    notification_service = NotificationService(self.db)
                                    notification_service.send_payout_notification(
                                        instructor_id=profile.user_id,
                                        amount_cents=int(amount),
                                        payout_date=arrival_date or datetime.now(timezone.utc),
                                    )
                            except Exception as exc:
                                self.logger.warning(
                                    "Failed to send payout notification for account %s: %s",
                                    account_id,
                                    exc,
                                )
                except Exception as e:
                    self.logger.warning("Failed to persist payout.paid analytics: %s", e)
                return True

            if event_type == "payout.failed":
                failure_code = payout.get("failure_code")
                failure_message = payout.get("failure_message")
                self.logger.error(
                    "Payout failed: %s amount=%s code=%s message=%s",
                    payout_id,
                    amount,
                    failure_code,
                    failure_message,
                )
                # TODO: optionally notify instructor and disable instant payout UI until resolved
                try:
                    if account_id:
                        acct = self.payment_repository.get_connected_account_by_stripe_id(
                            account_id
                        )
                        if acct and acct.instructor_profile_id:
                            self.payment_repository.record_payout_event(
                                instructor_profile_id=acct.instructor_profile_id,
                                stripe_account_id=account_id,
                                payout_id=payout_id,
                                amount_cents=amount,
                                status="failed",
                                arrival_date=arrival_date,
                                failure_code=failure_code,
                                failure_message=failure_message,
                            )
                except Exception as e:
                    self.logger.warning("Failed to persist payout.failed analytics: %s", e)
                return True

            # Unhandled payout event
            return False
        except Exception as e:
            self.logger.error("Error handling payout webhook: %s", e)
            return False

    def _handle_identity_webhook(self, event: Dict[str, Any]) -> bool:
        """Handle Stripe Identity verification session events to persist verification status."""
        try:
            _evt_type = event.get("type", "")
            obj = event.get("data", {}).get("object", {})
            verification_status = obj.get("status")

            # Locate our user via metadata.user_id
            meta = obj.get("metadata") or {}
            user_id = meta.get("user_id")
            if not user_id:
                # Not our session; ignore
                return True

            # Find instructor profile by user_id
            profile = self.instructor_repository.get_by_user_id(user_id)
            if not profile:
                # User exists but no profile yet; ignore graciously
                return True

            # On verified, mark identity_verified_at and store session id
            if verification_status == "verified":
                try:
                    has_verified_outputs = self._stripe_has_field(obj, "verified_outputs")
                    self._persist_verified_identity(
                        profile_id=profile.id,
                        user_id=user_id,
                        session=obj,
                        session_id=obj.get("id"),
                        refresh_session=not has_verified_outputs,
                        prefetched_session=obj if has_verified_outputs else None,
                    )
                except Exception as e:
                    self.logger.error(
                        "Failed updating identity verification on profile %s: %s",
                        profile.id,
                        e,
                    )
                    try:
                        self.instructor_repository.update(
                            profile.id,
                            identity_verified_at=datetime.now(timezone.utc),
                            identity_verification_session_id=obj.get("id"),
                        )
                    except Exception:
                        logger.warning(
                            "Non-fatal identity webhook fallback persistence failure",
                            exc_info=True,
                        )
                    return True
                return True

            # Processing: Stripe is still reviewing — keep session_id as "in progress"
            if verification_status == "processing":
                try:
                    self.instructor_repository.update(
                        profile.id,
                        identity_verification_session_id=obj.get("id"),
                    )
                except Exception:
                    logger.debug("Non-fatal error ignored", exc_info=True)
                return True

            # Terminal failures: preserve the session ID so refresh/create can inspect it later.
            if verification_status in {"requires_input", "canceled"}:
                try:
                    self.instructor_repository.update(
                        profile.id,
                        identity_verification_session_id=obj.get("id"),
                    )
                except Exception:
                    logger.debug("Non-fatal error ignored", exc_info=True)
                return True

            return True
        except Exception as e:
            self.logger.error("Error handling identity webhook: %s", e)
            return False
