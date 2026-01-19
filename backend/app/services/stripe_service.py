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

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Dict, List, Optional, cast
from urllib.parse import ParseResult, urljoin, urlparse

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
import stripe
from stripe._refund import Refund as StripeRefund
from stripe._transfer import Transfer as StripeTransfer

from ..constants.payment_status import map_payment_status
from ..constants.pricing_defaults import PRICING_DEFAULTS
from ..core.booking_lock import booking_lock_sync
from ..core.config import settings
from ..core.exceptions import (
    BookingCancelledException,
    BookingNotFoundException,
    ServiceException,
)
from ..models.booking import BookingStatus, PaymentStatus
from ..models.payment import PaymentIntent, PaymentMethod, StripeConnectedAccount, StripeCustomer
from ..models.user import User
from ..repositories.factory import RepositoryFactory
from ..schemas.payment_schemas import (
    CheckoutResponse,
    CreateCheckoutRequest,
    CreditBalanceResponse,
    DashboardLinkResponse,
    EarningsResponse,
    IdentityRefreshResponse,
    InstantPayoutResponse,
    InstructorInvoiceSummary,
    OnboardingResponse,
    OnboardingStatusResponse,
    PayoutHistoryResponse,
    PayoutScheduleResponse,
    PayoutSummary,
    TransactionHistoryItem,
)
from ..utils.url_validation import is_allowed_origin, origin_from_header
from .base import BaseService
from .cache_service import CacheService, CacheServiceSyncAdapter
from .config_service import ConfigService
from .payment_summary_service import build_student_payment_summary
from .pricing_service import PricingService
from .student_credit_service import StudentCreditService

if TYPE_CHECKING:  # pragma: no cover
    from .booking_service import BookingService


@dataclass
class ChargeContext:
    booking_id: str
    applied_credit_cents: int
    base_price_cents: int
    student_fee_cents: int
    instructor_platform_fee_cents: int
    target_instructor_payout_cents: int
    student_pay_cents: int
    application_fee_cents: int
    top_up_transfer_cents: int
    instructor_tier_pct: Decimal


logger: logging.Logger = logging.getLogger(__name__)


class StripeService(BaseService):
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
        try:
            if settings.stripe_secret_key:
                stripe.api_key = settings.stripe_secret_key.get_secret_value()
                # Set sane network timeouts/retries to avoid blocking the server on Stripe calls
                # IMPORTANT: Keep timeout low (3s) to avoid holding DB transactions open too long
                # during cancel_booking and other flows that call Stripe inside transactions.
                try:
                    # 3s overall timeout; 1 retry for transient failures
                    # Note: Stripe 14.x moved http_client to _http_client (private API)
                    http_client_module = getattr(stripe, "_http_client", None) or getattr(
                        stripe, "http_client", None
                    )
                    if http_client_module:
                        stripe.default_http_client = http_client_module.RequestsClient(timeout=3)
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
                f"Failed to configure Stripe service: {e} - service will operate in mock mode"
            )

        # Platform fee percentage (15 means 15%, not 0.15)
        self.platform_fee_percentage = (
            getattr(settings, "stripe_platform_fee_percentage", 15) / 100.0
        )

        self.logger = logging.getLogger(__name__)

    def _check_stripe_configured(self) -> None:
        """Check if Stripe is properly configured before making API calls."""
        if not self.stripe_configured:
            raise ServiceException(
                "Stripe service not configured. Please check STRIPE_SECRET_KEY environment variable."
            )

    # --------------------------------------------------------------------- #
    # Instructor onboarding and account management
    # --------------------------------------------------------------------- #

    @BaseService.measure_operation("stripe_start_instructor_onboarding")
    def start_instructor_onboarding(
        self,
        *,
        user: User,
        request_host: str,
        request_scheme: str,
        request_origin: str | None = None,
        request_referer: str | None = None,
        return_to: str | None = None,
    ) -> OnboardingResponse:
        """Create or reuse a Stripe Express account and return onboarding link."""
        instructor_profile = self.instructor_repository.get_by_user_id(user.id)
        if not instructor_profile:
            raise ServiceException(
                "Instructor profile not found",
                code="PAYMENTS_INSTRUCTOR_PROFILE_NOT_FOUND",
            )

        existing_account = self.payment_repository.get_connected_account_by_instructor_id(
            instructor_profile.id
        )
        if existing_account and existing_account.stripe_account_id:
            account_id = existing_account.stripe_account_id
            account_status = self.check_account_status(instructor_profile.id)
            if account_status.get("onboarding_completed"):
                return OnboardingResponse(
                    account_id=account_id,
                    onboarding_url="",
                    already_onboarded=True,
                )
        else:
            created_account = self.create_connected_account(instructor_profile.id, user.email)
            account_id = created_account.stripe_account_id

        callback_from: str | None = None
        if return_to and return_to.startswith("/"):
            parsed_return = urlparse(return_to)
            redirect_path = (parsed_return.path or "").strip().lower()
            if redirect_path:
                segments = [segment for segment in redirect_path.split("/") if segment]
                if (
                    len(segments) >= 3
                    and segments[0] == "instructor"
                    and segments[1] == "onboarding"
                ):
                    callback_from = segments[2]
                elif len(segments) >= 2 and segments[0] == "instructor":
                    callback_from = segments[1]
                elif segments:
                    callback_from = segments[-1]
        if callback_from:
            sanitized = "".join(ch for ch in callback_from if ch.isalnum() or ch in {"-", "_"})
            callback_from = sanitized or None

        configured_frontend = (settings.frontend_url or "").strip()
        local_frontend = (settings.local_beta_frontend_origin or "").strip()
        request_host_clean = (request_host or "").strip()

        def _normalize_origin(raw: str | None) -> str | None:
            if not raw:
                return None
            parsed_raw: ParseResult = urlparse(raw)
            scheme = parsed_raw.scheme or request_scheme
            if parsed_raw.netloc:
                return f"{scheme}://{parsed_raw.netloc}".rstrip("/")
            if parsed_raw.path and raw.startswith(("http://", "https://")):
                return raw.rstrip("/")
            return None

        origin_candidates: list[str] = []
        header_origin = origin_from_header(request_origin) or origin_from_header(request_referer)
        if header_origin and is_allowed_origin(header_origin):
            origin_candidates.append(header_origin)
        if configured_frontend:
            origin_candidates.append(configured_frontend)

        request_host_lower = request_host_clean.lower()
        parsed_front = urlparse(configured_frontend) if configured_frontend else None
        configured_hostname = (parsed_front.hostname or "").lower() if parsed_front else ""

        if (
            request_host_lower.startswith("api.")
            and configured_hostname
            and request_host_lower.split(":", 1)[0].removeprefix("api.") == configured_hostname
        ):
            scheme = parsed_front.scheme or request_scheme if parsed_front else request_scheme
            origin_candidates.append(f"{scheme}://{configured_hostname}".rstrip("/"))
        if local_frontend:
            origin_candidates.append(local_frontend)

        origin = None
        for candidate in origin_candidates:
            origin = _normalize_origin(candidate)
            if origin:
                break

        if not origin and configured_frontend:
            origin = _normalize_origin(configured_frontend)

        if not origin:
            origin = f"{request_scheme}://{request_host_clean}".rstrip("/")

        if callback_from == "payment-setup":
            success_path = "/instructor/onboarding/payment-setup"
        else:
            success_path = (
                f"/instructor/onboarding/status/{callback_from}"
                if callback_from
                else "/instructor/onboarding/status"
            )
        refresh_path = "/instructor/onboarding/start"
        onboarding_link = self.create_account_link(
            instructor_profile_id=instructor_profile.id,
            refresh_url=urljoin(origin + "/", refresh_path.lstrip("/")),
            return_url=urljoin(origin + "/", success_path.lstrip("/")),
        )

        return OnboardingResponse(
            account_id=account_id,
            onboarding_url=onboarding_link,
            already_onboarded=False,
        )

    @BaseService.measure_operation("stripe_get_onboarding_status")
    def get_instructor_onboarding_status(self, *, user: User) -> OnboardingStatusResponse:
        """Return onboarding status for instructor."""
        profile = self.instructor_repository.get_by_user_id(user.id)
        if not profile:
            raise ServiceException("Instructor profile not found", code="not_found")

        connected = self.payment_repository.get_connected_account_by_instructor_id(profile.id)
        if not connected or not connected.stripe_account_id:
            return OnboardingStatusResponse(
                has_account=False,
                onboarding_completed=False,
                charges_enabled=False,
                payouts_enabled=False,
                details_submitted=False,
                requirements=[],
            )

        account = self.check_account_status(profile.id)
        charges_enabled = bool(
            account.get(
                "charges_enabled",
                account.get("can_accept_payments", False),
            )
        )
        payouts_enabled = bool(account.get("payouts_enabled", False))
        details_submitted = bool(account.get("details_submitted", False))
        onboarding_completed = bool(account.get("onboarding_completed", False))
        requirements_list: list[str] = account.get("requirements", []) or []

        return OnboardingStatusResponse(
            has_account=True,
            onboarding_completed=onboarding_completed,
            charges_enabled=charges_enabled,
            payouts_enabled=payouts_enabled,
            details_submitted=details_submitted,
            requirements=requirements_list,
        )

    @BaseService.measure_operation("stripe_refresh_identity_status")
    def refresh_instructor_identity(self, *, user: User) -> IdentityRefreshResponse:
        """Refresh instructor identity verification status."""
        profile = self.instructor_repository.get_by_user_id(user.id)
        if not profile:
            raise ServiceException("Instructor profile not found", code="not_found")

        profile_id = profile.id
        self.instructor_repository.update(profile_id, bgc_in_dispute=False)
        account = self.check_account_status(profile_id)
        # Determine verification status based on account state
        has_requirements = bool(account.get("requirements"))
        is_verified = account.get("charges_enabled", False) and not has_requirements
        status = "verified" if is_verified else "pending"
        return IdentityRefreshResponse(
            status=status,
            verified=is_verified,
        )

    @BaseService.measure_operation("stripe_set_payout_schedule")
    def set_instructor_payout_schedule(
        self, *, user: User, monthly_anchor: int | None, interval: str
    ) -> PayoutScheduleResponse:
        """Update payout schedule for instructor connected account."""
        profile = self.instructor_repository.get_by_user_id(user.id)
        if not profile:
            raise ServiceException("Instructor profile not found", code="not_found")

        connected = self.payment_repository.get_connected_account_by_instructor_id(profile.id)
        if not connected or not connected.stripe_account_id:
            raise ServiceException("Instructor is not onboarded to Stripe", code="not_onboarded")

        schedule_settings: dict[str, object] = {
            "interval": interval,
        }
        if monthly_anchor:
            schedule_settings["monthly_anchor"] = monthly_anchor

        account = stripe.Account.modify(
            connected.stripe_account_id,
            settings={
                "payouts": {
                    "schedule": schedule_settings,
                }
            },
        )
        account_id = (
            account.get("id") if isinstance(account, dict) else getattr(account, "id", None)
        )
        return PayoutScheduleResponse(
            ok=True,
            account_id=account_id,
            settings={"interval": interval, "monthly_anchor": monthly_anchor},
        )

    @BaseService.measure_operation("stripe_dashboard_link")
    def get_instructor_dashboard_link(self, *, user: User) -> DashboardLinkResponse:
        """Generate Stripe dashboard link for instructor."""
        profile = self.instructor_repository.get_by_user_id(user.id)
        if not profile:
            raise ServiceException("Instructor profile not found", code="not_found")

        connected = self.payment_repository.get_connected_account_by_instructor_id(profile.id)
        if not connected or not connected.stripe_account_id:
            raise ServiceException("Instructor is not onboarded to Stripe", code="not_onboarded")

        link = stripe.Account.create_login_link(connected.stripe_account_id)
        dashboard_url = link.get("url") if isinstance(link, dict) else getattr(link, "url", None)
        return DashboardLinkResponse(
            dashboard_url=dashboard_url or "",
            expires_in_minutes=5,
        )

    @BaseService.measure_operation("stripe_request_instant_payout")
    def request_instructor_instant_payout(
        self, *, user: User, amount_cents: int
    ) -> InstantPayoutResponse:
        """Request an instant payout for an instructor."""
        profile = self.instructor_repository.get_by_user_id(user.id)
        if not profile:
            raise ServiceException("Instructor profile not found", code="not_found")

        connected = self.payment_repository.get_connected_account_by_instructor_id(profile.id)
        if not connected or not connected.stripe_account_id:
            raise ServiceException("Instructor is not onboarded to Stripe", code="not_onboarded")

        payout = stripe.Payout.create(
            amount=amount_cents,
            currency="usd",
            stripe_account=connected.stripe_account_id,
            method="instant",
        )
        payout_id = (
            getattr(payout, "id", None) if not isinstance(payout, dict) else payout.get("id")
        )
        payout_status = (
            getattr(payout, "status", None)
            if not isinstance(payout, dict)
            else payout.get("status")
        )
        return InstantPayoutResponse(
            ok=True,
            payout_id=payout_id,
            status=payout_status,
        )

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

        booking = self.booking_repository.get_by_id(payload.booking_id)
        if not booking:
            raise ServiceException("Booking not found", code="not_found")
        if booking.student_id != current_user.id:
            raise ServiceException("You can only pay for your own bookings", code="forbidden")
        if booking.status not in ["CONFIRMED", "PENDING"]:
            raise ServiceException(
                f"Cannot process payment for booking with status: {booking.status}",
                code="invalid_booking_status",
            )

        existing_payment = self.payment_repository.get_payment_by_booking_id(booking.id)
        if existing_payment and existing_payment.status == "succeeded":
            raise ServiceException("Booking has already been paid", code="already_paid")

        if payload.save_payment_method:
            if not payload.payment_method_id:
                raise ServiceException(
                    "Payment method is required when saving for future use",
                    code="missing_payment_method",
                )
            self.save_payment_method(
                user_id=current_user.id,
                payment_method_id=payload.payment_method_id,
                set_as_default=False,
            )

        payment_result = self.process_booking_payment(
            payload.booking_id,
            payload.payment_method_id,
            payload.requested_credit_cents,
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
            if payment_result["status"] == "requires_capture":
                fresh_booking.payment_status = PaymentStatus.AUTHORIZED.value
            elif payment_result["status"] == "scheduled":
                fresh_booking.payment_status = PaymentStatus.SCHEDULED.value

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
            if payment_result.get("status") in ["requires_action", "requires_confirmation"]
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
            in ["requires_action", "requires_confirmation"],
        }
        return CheckoutResponse(**response_data)

    @BaseService.measure_operation("stripe_get_instructor_earnings_summary")
    def get_instructor_earnings_summary(self, *, user: User) -> EarningsResponse:
        """Aggregate instructor earnings summary and invoice list."""
        profile = self.instructor_repository.get_by_user_id(user.id)
        if not profile:
            raise ServiceException("Instructor profile not found", code="not_found")

        earnings = self.get_instructor_earnings(user.id)
        payment_repo = self.payment_repository
        pricing_config, _ = self.config_service.get_pricing_config()
        tip_repo = RepositoryFactory.create_review_tip_repository(self.db)
        instructor_payments = payment_repo.get_instructor_payment_history(
            instructor_id=user.id,
            limit=100,
        )

        def _money_to_cents(value: Optional[Any]) -> int:
            if value is None:
                return 0
            try:
                return int((Decimal(value) * Decimal("100")).quantize(Decimal("1")))
            except Exception:
                return 0

        def _compute_base_price_cents(hourly_rate: Any, duration_minutes: int) -> int:
            """Calculate base lesson price from hourly rate and duration."""
            try:
                rate = Decimal(str(hourly_rate or 0))
                cents_value = rate * Decimal(duration_minutes) * Decimal(100) / Decimal(60)
                return int(cents_value.quantize(Decimal("1")))
            except Exception:
                return 0

        def _get_instructor_tier_pct(config: Dict[str, Any], instructor_profile: Any) -> float:
            """Get instructor's platform fee tier percentage."""
            is_founding = getattr(instructor_profile, "is_founding_instructor", False)
            if is_founding is True:
                default_founding_rate = PRICING_DEFAULTS.get("founding_instructor_rate_pct", 0)
                raw_rate = config.get(
                    "founding_instructor_rate_pct",
                    default_founding_rate,
                )
                try:
                    return float(Decimal(str(raw_rate)))
                except Exception:
                    return float(default_founding_rate)
            tiers = config.get("instructor_tiers") or PRICING_DEFAULTS.get("instructor_tiers", [])
            if tiers:
                entry_tier = min(tiers, key=lambda tier: tier.get("min", 0))
                default_entry_pct = PRICING_DEFAULTS.get("instructor_tiers", [{}])[0].get("pct", 0)
                default_pct = float(entry_tier.get("pct", default_entry_pct))
            else:
                default_pct = float(PRICING_DEFAULTS.get("instructor_tiers", [{}])[0].get("pct", 0))

            raw_pct = getattr(instructor_profile, "current_tier_pct", None)
            if raw_pct is None:
                return default_pct
            try:
                pct_decimal = Decimal(str(raw_pct))
                if pct_decimal > 1:
                    pct_decimal = pct_decimal / Decimal("100")
                return float(pct_decimal)
            except Exception:
                return default_pct

        student_fee_pct = float(
            pricing_config.get("student_fee_pct", PRICING_DEFAULTS["student_fee_pct"])
        )
        # Fallback tier for edge cases where calculation fails
        fallback_tier_pct = _get_instructor_tier_pct(pricing_config, profile)

        invoices: List[InstructorInvoiceSummary] = []
        total_minutes = 0
        total_lesson_value = 0
        total_platform_fees = 0
        total_tips = 0

        for payment in instructor_payments:
            booking = payment.booking
            if not booking:
                continue

            minutes = int(getattr(booking, "duration_minutes", 0) or 0)
            total_minutes += minutes

            student = getattr(booking, "student", None)
            student_name = None
            if student:
                last_initial = (student.last_name or "").strip()[:1]
                student_name = (
                    f"{student.first_name} {last_initial}." if last_initial else student.first_name
                )

            try:
                summary = build_student_payment_summary(
                    booking=booking,
                    pricing_config=pricing_config,
                    payment_repo=payment_repo,
                    review_tip_repo=tip_repo,
                )
            except Exception:
                summary = None

            total_paid_cents = int(payment.amount or 0)
            tip_cents = _money_to_cents(summary.tip_paid if summary else None)
            total_tips += tip_cents

            # Read earnings metadata from DB (stored at payment creation time)
            # Falls back to computed values for legacy payments without metadata
            if payment.base_price_cents is not None:
                lesson_price_cents = payment.base_price_cents
            else:
                lesson_price_cents = _compute_base_price_cents(booking.hourly_rate, minutes)

            if payment.instructor_tier_pct is not None:
                actual_tier_pct = float(payment.instructor_tier_pct)
            else:
                actual_tier_pct = fallback_tier_pct

            if payment.instructor_payout_cents is not None:
                instructor_share_cents = payment.instructor_payout_cents
            else:
                # Fallback: calculate from payment amounts
                instructor_share_cents = max(
                    0, int(payment.amount or 0) - int(payment.application_fee or 0)
                )

            # Calculate platform fee from tier (or derive from payment data for legacy)
            platform_fee_cents = int(lesson_price_cents * actual_tier_pct)

            # Calculate student fee for display
            student_fee_cents_calc = int(
                Decimal(lesson_price_cents) * Decimal(str(student_fee_pct))
            )

            # Aggregate totals
            total_lesson_value += lesson_price_cents
            total_platform_fees += platform_fee_cents

            display_status = map_payment_status(payment.status)

            invoices.append(
                InstructorInvoiceSummary(
                    booking_id=booking.id,
                    lesson_date=booking.booking_date,
                    start_time=booking.start_time,
                    service_name=booking.service_name,
                    student_name=student_name,
                    duration_minutes=minutes or None,
                    total_paid_cents=total_paid_cents,
                    tip_cents=tip_cents,
                    instructor_share_cents=instructor_share_cents,
                    status=display_status,
                    created_at=payment.created_at,
                    # New instructor-centric fields
                    lesson_price_cents=lesson_price_cents,
                    platform_fee_cents=platform_fee_cents,
                    platform_fee_rate=actual_tier_pct,
                    student_fee_cents=student_fee_cents_calc,
                )
            )

        hours_invoiced = total_minutes / 60.0 if total_minutes else 0.0

        response_payload = {
            "total_earned": earnings.get("total_earned"),
            "total_fees": earnings.get("total_fees"),
            "booking_count": earnings.get("booking_count"),
            "average_earning": earnings.get("average_earning"),
            "hours_invoiced": hours_invoiced,
            "service_count": len(instructor_payments),
            "period_start": earnings.get("period_start"),
            "period_end": earnings.get("period_end"),
            "invoices": invoices,
            # New instructor-centric aggregate fields
            "total_lesson_value": total_lesson_value,
            "total_platform_fees": total_platform_fees,
            "total_tips": total_tips,
        }
        return EarningsResponse(**response_payload)

    def _build_earnings_export_rows(
        self,
        *,
        instructor_id: str,
        start_date: Optional[date],
        end_date: Optional[date],
    ) -> List[Dict[str, Any]]:
        profile = self.instructor_repository.get_by_user_id(instructor_id)
        if not profile:
            raise ServiceException("Instructor profile not found", code="not_found")

        pricing_config, _ = self.config_service.get_pricing_config()

        def _compute_base_price_cents(hourly_rate: Any, duration_minutes: int) -> int:
            """Calculate base lesson price from hourly rate and duration."""
            try:
                rate = Decimal(str(hourly_rate or 0))
                cents_value = rate * Decimal(duration_minutes) * Decimal(100) / Decimal(60)
                return int(cents_value.quantize(Decimal("1")))
            except Exception:
                return 0

        def _get_instructor_tier_pct(config: Dict[str, Any], instructor_profile: Any) -> float:
            """Get instructor's platform fee tier percentage."""
            is_founding = getattr(instructor_profile, "is_founding_instructor", False)
            if is_founding is True:
                default_founding_rate = PRICING_DEFAULTS.get("founding_instructor_rate_pct", 0)
                raw_rate = config.get(
                    "founding_instructor_rate_pct",
                    default_founding_rate,
                )
                try:
                    return float(Decimal(str(raw_rate)))
                except Exception:
                    return float(default_founding_rate)
            tiers = config.get("instructor_tiers") or PRICING_DEFAULTS.get("instructor_tiers", [])
            if tiers:
                entry_tier = min(tiers, key=lambda tier: tier.get("min", 0))
                default_entry_pct = PRICING_DEFAULTS.get("instructor_tiers", [{}])[0].get("pct", 0)
                default_pct = float(entry_tier.get("pct", default_entry_pct))
            else:
                default_pct = float(PRICING_DEFAULTS.get("instructor_tiers", [{}])[0].get("pct", 0))

            raw_pct = getattr(instructor_profile, "current_tier_pct", None)
            if raw_pct is None:
                return default_pct
            try:
                pct_decimal = Decimal(str(raw_pct))
                if pct_decimal > 1:
                    pct_decimal = pct_decimal / Decimal("100")
                return float(pct_decimal)
            except Exception:
                return default_pct

        # Fallback tier for edge cases where calculation fails
        fallback_tier_pct = _get_instructor_tier_pct(pricing_config, profile)
        earnings_rows = self.payment_repository.get_instructor_earnings_for_export(
            instructor_id,
            start_date=start_date,
            end_date=end_date,
        )

        computed_rows: List[Dict[str, Any]] = []
        for row in earnings_rows:
            lesson_price_cents = _compute_base_price_cents(
                row.get("hourly_rate"), int(row.get("duration_minutes") or 0)
            )
            # Derive actual tier percentage from payment data
            # instructor_fee = lesson_price - instructor_share (credits cancel out)
            net_earnings_cents = max(
                0,
                int(row.get("payment_amount_cents") or 0)
                - int(row.get("application_fee_cents") or 0),
            )
            actual_instructor_fee_cents = lesson_price_cents - net_earnings_cents
            if lesson_price_cents > 0 and actual_instructor_fee_cents >= 0:
                actual_tier_pct = float(actual_instructor_fee_cents) / float(lesson_price_cents)
                # Sanity check: tier should be between 0 and 25%
                if not (0 <= actual_tier_pct <= 0.25):
                    actual_tier_pct = fallback_tier_pct
            else:
                actual_tier_pct = fallback_tier_pct

            platform_fee_cents = (
                actual_instructor_fee_cents if actual_instructor_fee_cents >= 0 else 0
            )
            display_status = map_payment_status(row.get("status"))
            status_label = display_status.replace("_", " ").title()

            computed_rows.append(
                {
                    "lesson_date": row.get("lesson_date"),
                    "student_name": row.get("student_name") or "Student",
                    "service_name": row.get("service_name") or "Lesson",
                    "duration_minutes": row.get("duration_minutes") or 0,
                    "lesson_price_cents": lesson_price_cents,
                    "platform_fee_cents": platform_fee_cents,
                    "net_earnings_cents": net_earnings_cents,
                    "status": status_label,
                    "payment_id": row.get("payment_id") or "",
                }
            )

        return computed_rows

    @BaseService.measure_operation("stripe_generate_earnings_csv")
    def generate_earnings_csv(
        self,
        *,
        instructor_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> str:
        """Generate CSV export for instructor earnings."""
        import csv
        import io

        rows = self._build_earnings_export_rows(
            instructor_id=instructor_id,
            start_date=start_date,
            end_date=end_date,
        )

        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(
            [
                "Date",
                "Student",
                "Service",
                "Duration (min)",
                "Lesson Price",
                "Platform Fee",
                "Net Earnings",
                "Status",
                "Payment ID",
            ]
        )

        for row in rows:
            lesson_date = row.get("lesson_date")
            date_value = lesson_date.isoformat() if lesson_date else ""
            writer.writerow(
                [
                    date_value,
                    row.get("student_name"),
                    row.get("service_name"),
                    row.get("duration_minutes"),
                    f"${row.get('lesson_price_cents', 0) / 100:.2f}",
                    f"${row.get('platform_fee_cents', 0) / 100:.2f}",
                    f"${row.get('net_earnings_cents', 0) / 100:.2f}",
                    row.get("status"),
                    row.get("payment_id"),
                ]
            )

        return output.getvalue()

    @BaseService.measure_operation("stripe_generate_earnings_pdf")
    def generate_earnings_pdf(
        self,
        *,
        instructor_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> bytes:
        """Generate PDF export for instructor earnings."""
        import io

        rows = self._build_earnings_export_rows(
            instructor_id=instructor_id,
            start_date=start_date,
            end_date=end_date,
        )

        start_label = start_date.isoformat() if start_date else "N/A"
        end_label = end_date.isoformat() if end_date else "N/A"

        columns: List[Dict[str, Any]] = [
            {"label": "Date", "width": 10, "align": "left"},
            {"label": "Student", "width": 14, "align": "left"},
            {"label": "Service", "width": 20, "align": "left"},
            {"label": "Dur", "width": 5, "align": "right"},
            {"label": "Lesson", "width": 10, "align": "right"},
            {"label": "Fee", "width": 10, "align": "right"},
            {"label": "Net", "width": 10, "align": "right"},
            {"label": "Status", "width": 10, "align": "left"},
            {"label": "Payment", "width": 10, "align": "left"},
        ]

        def _fit_cell(text: str, width: int, align: str) -> str:
            if len(text) > width:
                if width <= 3:
                    text = text[:width]
                else:
                    text = f"{text[: width - 3]}..."
            if align == "right":
                return text.rjust(width)
            return text.ljust(width)

        def _format_row(values: List[str]) -> str:
            parts: List[str] = []
            for value, col in zip(values, columns):
                parts.append(_fit_cell(value, col["width"], col["align"]))
            return " ".join(parts)

        header_row = _format_row([col["label"] for col in columns])
        separator_row = "-" * len(header_row)
        header_lines = [
            "Earnings Report",
            f"Range: {start_label} to {end_label}",
            "",
            header_row,
            separator_row,
        ]

        body_lines: List[str] = []
        if not rows:
            body_lines.append("No earnings found for the selected range.")
        else:
            for row in rows:
                lesson_date = row.get("lesson_date")
                date_value = lesson_date.isoformat() if lesson_date else ""
                body_lines.append(
                    _format_row(
                        [
                            date_value,
                            str(row.get("student_name") or ""),
                            str(row.get("service_name") or ""),
                            str(row.get("duration_minutes") or 0),
                            f"${row.get('lesson_price_cents', 0) / 100:.2f}",
                            f"${row.get('platform_fee_cents', 0) / 100:.2f}",
                            f"${row.get('net_earnings_cents', 0) / 100:.2f}",
                            str(row.get("status") or ""),
                            str(row.get("payment_id") or ""),
                        ]
                    )
                )

        def _escape_pdf_text(value: str) -> str:
            sanitized = value.encode("ascii", "replace").decode("ascii")
            return (
                sanitized.replace("\\", "\\\\")
                .replace("(", "\\(")
                .replace(")", "\\)")
                .replace("\r", "")
                .replace("\n", " ")
            )

        def _build_pdf(header: List[str], data_lines: List[str]) -> bytes:
            page_width = 612
            page_height = 792
            left_margin = 40
            top_margin = 742
            line_height = 12
            font_size = 9
            usable_height = top_margin - 72
            lines_per_page = max(1, int(usable_height / line_height))
            header_count = len(header)
            data_per_page = max(1, lines_per_page - header_count)

            pages: List[List[str]] = []
            if not data_lines:
                pages = [header + [""]]
            else:
                for idx in range(0, len(data_lines), data_per_page):
                    pages.append(header + data_lines[idx : idx + data_per_page])

            page_obj_nums = [4 + i * 2 for i in range(len(pages))]
            content_obj_nums = [5 + i * 2 for i in range(len(pages))]
            kids = " ".join(f"{num} 0 R" for num in page_obj_nums)

            objects: List[bytes] = []
            objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
            objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode("ascii"))
            objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>")

            for page_index, page_lines_chunk in enumerate(pages):
                content_obj_num = content_obj_nums[page_index]
                page_obj = (
                    f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_width} {page_height}] "
                    f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_obj_num} 0 R >>"
                ).encode("ascii")
                objects.append(page_obj)

                content_lines = [
                    "BT",
                    f"/F1 {font_size} Tf",
                    f"{left_margin} {top_margin} Td",
                ]
                for line_index, line in enumerate(page_lines_chunk):
                    if line_index > 0:
                        content_lines.append(f"0 -{line_height} Td")
                    content_lines.append(f"({_escape_pdf_text(line)}) Tj")
                content_lines.append("ET")
                content_stream = "\n".join(content_lines).encode("ascii")
                content_obj = (
                    f"<< /Length {len(content_stream)} >>\nstream\n".encode("ascii")
                    + content_stream
                    + b"\nendstream"
                )
                objects.append(content_obj)

            buffer = io.BytesIO()
            buffer.write(b"%PDF-1.4\n")
            offsets = [0]
            for index, obj in enumerate(objects, start=1):
                offsets.append(buffer.tell())
                buffer.write(f"{index} 0 obj\n".encode("ascii"))
                buffer.write(obj)
                buffer.write(b"\nendobj\n")

            xref_offset = buffer.tell()
            buffer.write(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
            buffer.write(b"0000000000 65535 f \n")
            for offset in offsets[1:]:
                buffer.write(f"{offset:010d} 00000 n \n".encode("ascii"))

            buffer.write(b"trailer\n")
            buffer.write(f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode("ascii"))
            buffer.write(b"startxref\n")
            buffer.write(f"{xref_offset}\n".encode("ascii"))
            buffer.write(b"%%EOF")
            return buffer.getvalue()

        return _build_pdf(header_lines, body_lines)

    @BaseService.measure_operation("stripe_get_instructor_payout_history")
    def get_instructor_payout_history(
        self, *, user: User, limit: int = 50
    ) -> PayoutHistoryResponse:
        """
        Get payout history for an instructor.

        Returns recorded payout events from the instructor's Stripe connected account.
        """
        profile = self.instructor_repository.get_by_user_id(user.id)
        if not profile:
            raise ServiceException("Instructor profile not found", code="not_found")

        payout_events = self.payment_repository.get_instructor_payout_history(
            instructor_profile_id=profile.id,
            limit=limit,
        )

        payouts: List[PayoutSummary] = []
        total_paid_cents = 0
        total_pending_cents = 0

        for event in payout_events:
            amount_cents = event.amount_cents or 0
            payout_status = event.status or "unknown"

            # Track totals
            if payout_status == "paid":
                total_paid_cents += amount_cents
            elif payout_status in ("pending", "in_transit"):
                total_pending_cents += amount_cents

            payouts.append(
                PayoutSummary(
                    id=event.payout_id,
                    amount_cents=amount_cents,
                    status=payout_status,
                    arrival_date=event.arrival_date,
                    failure_code=event.failure_code,
                    failure_message=event.failure_message,
                    created_at=event.created_at,
                )
            )

        return PayoutHistoryResponse(
            payouts=payouts,
            total_paid_cents=total_paid_cents,
            total_pending_cents=total_pending_cents,
            payout_count=len(payouts),
        )

    @BaseService.measure_operation("stripe_get_user_transaction_history")
    def get_user_transaction_history(
        self, *, user: User, limit: int = 20, offset: int = 0
    ) -> List[TransactionHistoryItem]:
        """Return transaction history for a user."""
        payment_repo = self.payment_repository
        fetch_limit = max(limit + offset + 10, limit)
        transactions = payment_repo.get_user_payment_history(
            user_id=user.id,
            limit=fetch_limit,
            offset=0,
        )

        tip_repo = RepositoryFactory.create_review_tip_repository(self.db)
        pricing_config, _ = self.config_service.get_pricing_config()

        result: List[TransactionHistoryItem] = []
        seen_bookings: set[str] = set()

        for payment in transactions:
            booking = payment.booking
            if not booking or booking.id in seen_bookings:
                continue

            seen_bookings.add(booking.id)

            try:
                summary = build_student_payment_summary(
                    booking=booking,
                    pricing_config=pricing_config,
                    payment_repo=payment_repo,
                    review_tip_repo=tip_repo,
                )
            except Exception:
                logger.debug("Non-fatal error ignored", exc_info=True)
                continue
            instructor = booking.instructor
            instructor_name = "Instructor"
            if instructor and instructor.last_name:
                instructor_name = f"{instructor.first_name} {instructor.last_name[0]}."
            elif instructor and instructor.first_name:
                instructor_name = instructor.first_name

            result.append(
                TransactionHistoryItem(
                    id=payment.id,
                    booking_id=booking.id,
                    service_name=booking.service_name,
                    instructor_name=instructor_name,
                    booking_date=booking.booking_date.isoformat(),
                    start_time=booking.start_time.isoformat(),
                    end_time=booking.end_time.isoformat(),
                    duration_minutes=booking.duration_minutes,
                    hourly_rate=float(booking.hourly_rate),
                    lesson_amount=summary.lesson_amount,
                    service_fee=summary.service_fee,
                    credit_applied=summary.credit_applied,
                    tip_amount=summary.tip_amount,
                    tip_paid=summary.tip_paid,
                    tip_status=summary.tip_status,
                    total_paid=summary.total_paid,
                    status=payment.status,
                    created_at=payment.created_at.isoformat(),
                )
            )

            if len(result) >= offset + limit:
                break

        return result[offset : offset + limit]

    @BaseService.measure_operation("stripe_get_user_credit_balance")
    def get_user_credit_balance(self, *, user: User) -> CreditBalanceResponse:
        """Return credit balance for a user."""
        from .credit_service import CreditService

        credit_service = CreditService(self.db)
        total_cents = credit_service.get_available_balance(user_id=user.id)
        reserved_cents = credit_service.get_reserved_balance(user_id=user.id)

        earliest_exp: str | None = None
        try:
            credits = credit_service.credit_repository.get_available_credits(user_id=user.id)
            expiries = [c.expires_at for c in credits if getattr(c, "expires_at", None) is not None]
            if expiries:
                earliest_exp = min(expiries).isoformat()
        except Exception:
            earliest_exp = None

        response_payload = {
            "available": float(total_cents) / 100.0,
            "expires_at": earliest_exp,
            "pending": float(reserved_cents) / 100.0,
        }
        return CreditBalanceResponse(**response_payload)

    @BaseService.measure_operation("stripe_ensure_top_up_transfer")
    def ensure_top_up_transfer(
        self,
        *,
        booking_id: str,
        payment_intent_id: str,
        destination_account_id: str,
        amount_cents: int,
    ) -> Optional[Dict[str, Any]]:
        """Create a one-time top-up transfer when credits exceed platform share."""

        if amount_cents <= 0:
            return None

        try:
            existing_event = self.payment_repository.get_latest_payment_event(
                booking_id, "top_up_transfer_created"
            )
            if existing_event:
                data = existing_event.event_data or {}
                if data.get("payment_intent_id") == payment_intent_id and int(
                    data.get("amount_cents") or 0
                ) == int(amount_cents):
                    return None

            transfer = stripe.Transfer.create(  # type: ignore[attr-defined]
                amount=amount_cents,
                currency="usd",
                destination=destination_account_id,
                transfer_group=f"booking:{booking_id}",
                metadata={
                    "booking_id": booking_id,
                    "payment_intent_id": payment_intent_id,
                },
                idempotency_key=f"topup:{payment_intent_id}",
            )

            try:
                self.payment_repository.create_payment_event(
                    booking_id=booking_id,
                    event_type="top_up_transfer_created",
                    event_data={
                        "payment_intent_id": payment_intent_id,
                        "transfer_id": getattr(transfer, "id", None),
                        "amount_cents": int(amount_cents),
                    },
                )
            except Exception:
                logger.debug("Non-fatal error ignored", exc_info=True)
            self.logger.info(
                "Issued top-up transfer",
                extra={
                    "booking_id": booking_id,
                    "payment_intent_id": payment_intent_id,
                    "amount_cents": amount_cents,
                    "destination_account_id": destination_account_id,
                },
            )

            return cast(Optional[Dict[str, Any]], transfer)
        except stripe.StripeError as exc:  # pragma: no cover - network path
            self.logger.error(
                "Stripe error creating top-up transfer for booking %s: %s",
                booking_id,
                str(exc),
            )
            raise ServiceException("Failed to create top-up transfer") from exc

    @BaseService.measure_operation("stripe_create_manual_transfer")
    def create_manual_transfer(
        self,
        *,
        booking_id: str,
        destination_account_id: str,
        amount_cents: int,
        idempotency_key: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a manual transfer to a connected account."""
        if amount_cents <= 0:
            return {"skipped": True, "transfer_id": None}

        transfer_metadata = {
            "booking_id": booking_id,
        }
        if metadata:
            transfer_metadata.update(metadata)

        try:
            transfer = stripe.Transfer.create(  # type: ignore[attr-defined]
                amount=amount_cents,
                currency="usd",
                destination=destination_account_id,
                transfer_group=f"booking:{booking_id}",
                metadata=transfer_metadata,
                idempotency_key=idempotency_key,
            )
            transfer_id = (
                transfer.get("id") if isinstance(transfer, dict) else getattr(transfer, "id", None)
            )
            return {
                "transfer": transfer,
                "transfer_id": transfer_id,
                "amount": amount_cents,
            }
        except stripe.StripeError as exc:  # pragma: no cover - network path
            self.logger.error(
                "Stripe error creating transfer for booking %s: %s",
                booking_id,
                str(exc),
            )
            raise ServiceException("Failed to create transfer") from exc
        except Exception as exc:
            self.logger.error(
                "Unexpected error creating transfer for booking %s: %s",
                booking_id,
                str(exc),
            )
            raise ServiceException("Failed to create transfer") from exc

    @BaseService.measure_operation("stripe_create_referral_bonus_transfer")
    def create_referral_bonus_transfer(
        self,
        *,
        payout_id: str,
        destination_account_id: str,
        amount_cents: int,
        referrer_user_id: str,
        referred_instructor_id: str,
        was_founding_bonus: bool,
    ) -> Dict[str, Any]:
        """Create a Stripe Transfer for instructor referral bonuses."""
        if amount_cents <= 0:
            return {"skipped": True, "transfer_id": None}

        idempotency_key = f"instructor_referral_bonus_{payout_id}"
        description = (
            "Instructor referral bonus - Founding $75"
            if was_founding_bonus
            else "Instructor referral bonus - Standard $50"
        )

        metadata = {
            "type": "instructor_referral_bonus",
            "payout_id": payout_id,
            "referrer_user_id": referrer_user_id,
            "referred_instructor_id": referred_instructor_id,
            "was_founding_bonus": str(was_founding_bonus).lower(),
            "amount_dollars": str(amount_cents / 100),
        }

        try:
            transfer = stripe.Transfer.create(  # type: ignore[attr-defined]
                amount=amount_cents,
                currency="usd",
                destination=destination_account_id,
                description=description,
                metadata=metadata,
                idempotency_key=idempotency_key,
            )
            transfer_id = (
                transfer.get("id") if isinstance(transfer, dict) else getattr(transfer, "id", None)
            )
            self.logger.info(
                "Created referral bonus transfer",
                extra={
                    "payout_id": payout_id,
                    "transfer_id": transfer_id,
                    "amount_cents": amount_cents,
                    "destination_account_id": destination_account_id,
                },
            )
            return {
                "transfer": transfer,
                "transfer_id": transfer_id,
                "amount_cents": amount_cents,
            }
        except stripe.StripeError as exc:  # pragma: no cover - network path
            self.logger.error(
                "Stripe error creating referral bonus transfer for payout %s: %s",
                payout_id,
                str(exc),
            )
            raise ServiceException("Failed to create referral bonus transfer") from exc
        except Exception as exc:
            self.logger.error(
                "Unexpected error creating referral bonus transfer for payout %s: %s",
                payout_id,
                str(exc),
            )
            raise ServiceException("Failed to create referral bonus transfer") from exc

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
        }

        if payment_method_id:
            stripe_kwargs["payment_method"] = payment_method_id
            stripe_kwargs["confirm"] = True
            stripe_kwargs["off_session"] = True

        try:
            stripe_intent = stripe.PaymentIntent.create(**stripe_kwargs)
        except Exception as exc:
            if not self.stripe_configured:
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
                booking.payment_intent_id = mock_id
                booking.payment_status = PaymentStatus.AUTHORIZED.value
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

        booking.payment_intent_id = stripe_intent.id
        if stripe_intent.status in {"requires_capture", "requires_confirmation", "succeeded"}:
            booking.payment_status = PaymentStatus.AUTHORIZED.value

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
                        booking.credits_reserved_cents = applied_credit_cents
                else:
                    applied_credit_cents = existing_applied

                if existing_applied > 0 and (
                    getattr(booking, "credits_reserved_cents", 0) != existing_applied
                ):
                    booking.credits_reserved_cents = existing_applied

                pricing = self.pricing_service.compute_booking_pricing(
                    booking_id=booking_id,
                    applied_credit_cents=applied_credit_cents,
                    persist=True,
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

    # ========== Identity Verification ==========
    @BaseService.measure_operation("stripe_create_identity_session")
    def create_identity_verification_session(
        self,
        *,
        user_id: str,
        return_url: str,
    ) -> Dict[str, Any]:
        """Create a Stripe Identity verification session for the given user.

        Returns dict with `client_secret` and `verification_session_id`.
        """
        try:
            self._check_stripe_configured()

            user: Optional[User] = self.user_repository.get_by_id(user_id)
            if not user:
                raise ServiceException("User not found for identity verification")

            # Build verification session parameters
            params: Dict[str, Any] = {
                "type": "document",
                "metadata": {"user_id": user_id},
                "options": {
                    "document": {"require_live_capture": True, "require_matching_selfie": True}
                },
                "return_url": return_url,
            }

            session = stripe.identity.VerificationSession.create(**params)

            client_secret = getattr(session, "client_secret", None)
            if not client_secret:
                raise ServiceException("Failed to create identity verification session")

            return {
                "verification_session_id": getattr(session, "id", None),
                "client_secret": client_secret,
            }
        except stripe.StripeError as e:
            self.logger.error(f"Stripe error creating identity session: {str(e)}")
            raise ServiceException(f"Failed to start identity verification: {str(e)}")
        except Exception as e:
            if isinstance(e, ServiceException):
                raise
            self.logger.error(f"Error creating identity session: {str(e)}")
            raise ServiceException("Failed to start identity verification")

    @BaseService.measure_operation("stripe_get_latest_identity_status")
    def get_latest_identity_status(self, user_id: str) -> Dict[str, Any]:
        """Return latest Stripe Identity verification status for a user.

        Uses session metadata.user_id to find the most recent session.
        """
        try:
            self._check_stripe_configured()
            # Fetch recent sessions and filter by our metadata
            # Run list call with bounded timeout via stripe client defaults
            sessions = stripe.identity.VerificationSession.list(limit=20)
            latest = None
            for s in sessions.get("data", []):
                try:
                    meta = getattr(s, "metadata", {}) or {}
                    if str(meta.get("user_id")) == str(user_id):
                        if latest is None or getattr(s, "created", 0) > getattr(
                            latest, "created", 0
                        ):
                            latest = s
                except Exception:
                    logger.debug("Non-fatal error ignored", exc_info=True)
                    continue
            if not latest:
                return {"status": "not_found"}

            return {
                "status": getattr(latest, "status", "unknown"),
                "id": getattr(latest, "id", None),
                "created": getattr(latest, "created", None),
            }
        except stripe.StripeError as e:
            self.logger.error(f"Stripe error getting identity status: {str(e)}")
            raise ServiceException(f"Failed to get identity status: {str(e)}")
        except Exception as e:
            if isinstance(e, ServiceException):
                raise
            self.logger.error(f"Error getting identity status: {str(e)}")
            raise ServiceException("Failed to get identity status")

    def _mock_payment_response(self, booking_id: str, amount_cents: int) -> Dict[str, Any]:
        """Return a mock payment response for testing/CI when Stripe is not configured."""
        return {
            "success": True,
            "payment_intent_id": f"mock_pi_{booking_id}",
            "status": "succeeded",
            "amount": amount_cents / 100.0,
            "application_fee": 0,
            "client_secret": None,
        }

    # ========== Customer Management ==========

    @BaseService.measure_operation("stripe_create_customer")
    def create_customer(self, user_id: str, email: str, name: str) -> StripeCustomer:
        """
        Create a Stripe customer for a user.

        Uses 3-phase pattern to avoid holding DB locks during Stripe calls:
        - Phase 1: Check if customer exists (quick transaction)
        - Phase 2: stripe.Customer.create (NO transaction)
        - Phase 3: Save customer record (quick transaction)

        Args:
            user_id: User's ID (ULID string)
            email: User's email address
            name: User's full name

        Returns:
            StripeCustomer record

        Raises:
            ServiceException: If customer creation fails
        """
        try:
            # ========== PHASE 1: Check if customer exists (quick transaction) ==========
            with self.transaction():
                existing_customer = self.payment_repository.get_customer_by_user_id(user_id)
                if existing_customer:
                    self.logger.info(f"Customer already exists for user {user_id}")
                    return existing_customer

            # ========== PHASE 2: Stripe Customer.create (NO transaction) ==========
            try:
                stripe_customer = stripe.Customer.create(
                    email=email, name=name, metadata={"user_id": user_id}
                )
                stripe_customer_id = stripe_customer.id
            except Exception as e:
                # If Stripe isn't configured, decide between mock fallback and raising
                if not self.stripe_configured:
                    msg = str(e)
                    auth_error = False
                    try:
                        # AuthenticationError indicates missing/invalid API key
                        auth_error = isinstance(e, stripe.error.AuthenticationError)
                    except Exception:
                        auth_error = False

                    if auth_error or "No API key" in msg or "api key" in msg.lower():
                        self.logger.warning(
                            f"Stripe not configured (auth error); using mock customer for user {user_id}"
                        )
                        stripe_customer_id = f"mock_cust_{user_id}"
                    else:
                        # For other errors (e.g., tests patching to raise API Error), surface as ServiceException
                        self.logger.error(f"Stripe customer creation failed: {msg}")
                        raise ServiceException(f"Failed to create Stripe customer: {msg}")
                else:
                    # If configured, bubble up as a service error
                    raise

            # ========== PHASE 3: Save customer record (quick transaction) ==========
            with self.transaction():
                customer_record = self.payment_repository.create_customer_record(
                    user_id=user_id, stripe_customer_id=stripe_customer_id
                )

            self.logger.info(f"Created Stripe customer {stripe_customer_id} for user {user_id}")
            return customer_record

        except stripe.StripeError as e:
            self.logger.error(f"Stripe error creating customer: {str(e)}")
            raise ServiceException(f"Failed to create Stripe customer: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error creating customer: {str(e)}")
            raise ServiceException(f"Failed to create customer: {str(e)}")

    @BaseService.measure_operation("stripe_get_or_create_customer")
    def get_or_create_customer(self, user_id: str) -> StripeCustomer:
        """
        Get existing customer or create a new one.

        Args:
            user_id: User's ID

        Returns:
            StripeCustomer record

        Raises:
            ServiceException: If user not found or customer creation fails
        """
        try:
            # Check if customer already exists
            existing_customer = self.payment_repository.get_customer_by_user_id(user_id)
            if existing_customer:
                return existing_customer

            # Get user details
            user = self.user_repository.get_by_id(user_id)
            if not user:
                raise ServiceException(f"User {user_id} not found")

            # Create new customer
            full_name = f"{user.first_name} {user.last_name}".strip()
            return self.create_customer(user_id, user.email, full_name)

        except Exception as e:
            if isinstance(e, ServiceException):
                raise
            self.logger.error(f"Error getting or creating customer: {str(e)}")
            raise ServiceException(f"Failed to get or create customer: {str(e)}")

    # ========== Connected Account Management ==========

    @BaseService.measure_operation("stripe_create_connected_account")
    def create_connected_account(
        self, instructor_profile_id: str, email: str
    ) -> StripeConnectedAccount:
        """
        Create a Stripe Connect Express account for an instructor.

        Args:
            instructor_profile_id: Instructor profile ID
            email: Instructor's email address

        Returns:
            StripeConnectedAccount record

        Raises:
            ServiceException: If account creation fails
        """
        existing = self.payment_repository.get_connected_account_by_instructor_id(
            instructor_profile_id
        )
        if existing:
            return existing

        def _persist_connected_account(stripe_account_id: str) -> StripeConnectedAccount:
            try:
                with self.payment_repository.transaction():
                    record = self.payment_repository.create_connected_account_record(
                        instructor_profile_id=instructor_profile_id,
                        stripe_account_id=stripe_account_id,
                        onboarding_completed=False,
                    )
                return record
            except IntegrityError:
                existing_record = self.payment_repository.get_connected_account_by_instructor_id(
                    instructor_profile_id
                )
                if existing_record:
                    return existing_record
                raise

        try:
            # Try real Stripe path first (allows tests to @patch)
            stripe_account = stripe.Account.create(
                type="express",
                email=email,
                capabilities={"transfers": {"requested": True}},
                metadata={"instructor_profile_id": instructor_profile_id},
            )

            account_record = _persist_connected_account(stripe_account.id)

            # Set default payout schedule (best-effort)
            try:
                stripe.Account.modify(
                    stripe_account.id,
                    settings={
                        "payouts": {
                            "schedule": {
                                "interval": "weekly",
                                "weekly_anchor": "tuesday",
                            }
                        }
                    },
                )
            except Exception:
                logger.debug("Non-fatal error ignored", exc_info=True)
            self.logger.info(
                f"Created Stripe Express account {stripe_account.id} for instructor {instructor_profile_id}"
            )
            return account_record
        except IntegrityError as e:
            self.logger.warning(
                "Race detected creating connected account for instructor %s: %s",
                instructor_profile_id,
                str(e),
            )
            existing_record = self.payment_repository.get_connected_account_by_instructor_id(
                instructor_profile_id
            )
            if existing_record:
                return existing_record
            raise ServiceException("Failed to create connected account due to conflict") from e
        except stripe.StripeError as e:
            self.logger.error(f"Stripe error creating connected account: {str(e)}")
            raise ServiceException(f"Failed to create connected account: {str(e)}")
        except Exception as e:
            if not self.stripe_configured:
                self.logger.warning(
                    "Stripe not configured or call failed (%s); using mock connected account for instructor %s",
                    str(e),
                    instructor_profile_id,
                )
                try:
                    return _persist_connected_account(f"mock_acct_{instructor_profile_id}")
                except IntegrityError as conflict:
                    self.logger.warning(
                        "Race detected creating mock account for instructor %s: %s",
                        instructor_profile_id,
                        str(conflict),
                    )
                    existing_record = (
                        self.payment_repository.get_connected_account_by_instructor_id(
                            instructor_profile_id
                        )
                    )
                    if existing_record:
                        return existing_record
                    raise ServiceException(
                        "Failed to create connected account due to conflict"
                    ) from conflict
            self.logger.error(f"Error creating connected account: {str(e)}")
            raise ServiceException(f"Failed to create connected account: {str(e)}")

    @BaseService.measure_operation("stripe_create_account_link")
    def create_account_link(
        self, instructor_profile_id: str, refresh_url: str, return_url: str
    ) -> str:
        """
        Create an account link for Express account onboarding.

        Args:
            instructor_profile_id: Instructor profile ID
            refresh_url: URL to redirect if link expires
            return_url: URL to redirect after onboarding

        Returns:
            Account link URL

        Raises:
            ServiceException: If account link creation fails
        """
        try:
            # Get connected account
            account_record = self.payment_repository.get_connected_account_by_instructor_id(
                instructor_profile_id
            )
            if not account_record:
                raise ServiceException(
                    f"No connected account found for instructor {instructor_profile_id}"
                )

            # Create account link
            account_link = stripe.AccountLink.create(
                account=account_record.stripe_account_id,
                refresh_url=refresh_url,
                return_url=return_url,
                type="account_onboarding",
            )

            self.logger.info(f"Created account link for instructor {instructor_profile_id}")
            url_attr = getattr(account_link, "url", None)
            return str(url_attr) if url_attr is not None else ""

        except stripe.StripeError as e:
            self.logger.error(f"Stripe error creating account link: {str(e)}")
            raise ServiceException(f"Failed to create account link: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error creating account link: {str(e)}")
            raise ServiceException(f"Failed to create account link: {str(e)}")

    @BaseService.measure_operation("stripe_set_payout_schedule")
    def set_payout_schedule_for_account(
        self,
        *,
        instructor_profile_id: str,
        interval: str = "weekly",
        weekly_anchor: str = "tuesday",
    ) -> Dict[str, Any]:
        """
        Set the payout schedule for a connected account (Express).

        Recommended to run right after onboarding completes and via a periodic audit.
        """
        try:
            account = self.payment_repository.get_connected_account_by_instructor_id(
                instructor_profile_id
            )
            if not account:
                raise ServiceException("Connected account not found for instructor")

            updated = stripe.Account.modify(
                account.stripe_account_id,
                settings={
                    "payouts": {
                        "schedule": {
                            "interval": interval,
                            "weekly_anchor": weekly_anchor,
                        }
                    }
                },
            )
            self.logger.info(
                f"Updated payout schedule for {account.stripe_account_id}: interval={interval}, anchor={weekly_anchor}"
            )
            # Return minimal details to caller
            try:
                settings_obj = getattr(updated, "settings", {})
            except Exception:
                settings_obj = {}
            return {"account_id": account.stripe_account_id, "settings": settings_obj}
        except stripe.StripeError as e:
            self.logger.error(f"Stripe error setting payout schedule: {str(e)}")
            raise ServiceException(f"Failed to set payout schedule: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error setting payout schedule: {str(e)}")
            raise ServiceException(f"Failed to set payout schedule: {str(e)}")

    @BaseService.measure_operation("stripe_check_account_status")
    def check_account_status(self, instructor_profile_id: str) -> Dict[str, Any]:
        """
        Check the onboarding status of a connected account.

        Args:
            instructor_profile_id: Instructor profile ID

        Returns:
            Dictionary with account status information

        Raises:
            ServiceException: If status check fails
        """
        try:
            # Get connected account
            account_record = self.payment_repository.get_connected_account_by_instructor_id(
                instructor_profile_id
            )
            if not account_record:
                return {
                    "has_account": False,
                    "onboarding_completed": False,
                    "charges_enabled": False,
                    "can_accept_payments": False,
                    "payouts_enabled": False,
                    "details_submitted": False,
                    "requirements": [],
                }

            # Get account details from Stripe
            stripe_account = stripe.Account.retrieve(account_record.stripe_account_id)

            charges_enabled = bool(getattr(stripe_account, "charges_enabled", False))
            payouts_enabled = bool(getattr(stripe_account, "payouts_enabled", False))
            details_submitted = bool(getattr(stripe_account, "details_submitted", False))
            requirements: list[str] = []
            try:
                req_obj = getattr(stripe_account, "requirements", None)
                if req_obj:
                    for field_name in ("currently_due", "past_due", "pending_verification"):
                        items = getattr(req_obj, field_name, None) or []
                        if isinstance(items, (list, tuple, set)):
                            for item in items:
                                if isinstance(item, str):
                                    requirements.append(item)
            except Exception:
                requirements = []

            # Compute actual onboarding completion from live Stripe fields
            computed_completed = bool(charges_enabled and details_submitted)

            # Keep DB flag in sync (do not force true when not actually completed)
            if account_record.onboarding_completed != computed_completed:
                try:
                    self.payment_repository.update_onboarding_status(
                        account_record.stripe_account_id, computed_completed
                    )
                    account_record.onboarding_completed = computed_completed
                except Exception:
                    # Non-fatal if persistence fails; return live-computed status
                    logger.debug("Non-fatal error ignored", exc_info=True)
            return {
                "has_account": True,
                "onboarding_completed": computed_completed,
                "charges_enabled": charges_enabled,
                "can_accept_payments": charges_enabled,
                "payouts_enabled": payouts_enabled,
                "details_submitted": details_submitted,
                "requirements": requirements,
                "stripe_account_id": account_record.stripe_account_id,
            }

        except stripe.StripeError as e:
            self.logger.error(f"Stripe error checking account status: {str(e)}")
            raise ServiceException(f"Failed to check account status: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error checking account status: {str(e)}")
            raise ServiceException(f"Failed to check account status: {str(e)}")

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
                platform_retained_cents = int(amount * self.platform_fee_percentage)
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
                stripe_kwargs = {
                    "amount": amount,
                    "currency": currency,
                    "customer": customer_id,
                    "transfer_data": {
                        "destination": destination_account_id,
                        "amount": transfer_amount_cents,
                    },
                    "metadata": metadata,
                    "capture_method": "manual",
                }
                if ctx is not None:
                    stripe_kwargs["transfer_group"] = f"booking:{booking_id}"

                stripe_intent = stripe.PaymentIntent.create(**stripe_kwargs)
                stripe_intent_id = stripe_intent.id
                stripe_intent_status = stripe_intent.status

            except Exception as e:
                if not self.stripe_configured:
                    self.logger.warning(
                        f"Stripe not configured or call failed ({e}); using mock payment intent for booking {booking_id}"
                    )
                    stripe_intent_id = f"mock_pi_{booking_id}"
                    stripe_intent_status = "requires_payment_method"
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

            self.logger.info(f"Created payment intent {stripe_intent_id} for booking {booking_id}")
            return payment_record

        except stripe.StripeError as e:
            self.logger.error(f"Stripe error creating payment intent: {str(e)}")
            raise ServiceException(f"Failed to create payment intent: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error creating payment intent: {str(e)}")
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
            platform_retained_cents = int(amount_cents * self.platform_fee_percentage)
            transfer_amount_cents = amount_cents - platform_retained_cents

            pi = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency=currency,
                customer=customer_id,
                payment_method=payment_method_id,
                capture_method="manual",
                confirm=True,
                off_session=True,
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
                result.update({"requires_action": False, "client_secret": None})

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
            self.logger.error(f"Stripe error creating manual authorization: {str(e)}")
            raise ServiceException(f"Failed to authorize payment: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error creating manual authorization: {str(e)}")
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

            self.logger.info(f"Confirmed payment intent {payment_intent_id}")
            return payment_record

        except stripe.StripeError as e:
            self.logger.error(f"Stripe error confirming payment: {str(e)}")
            raise ServiceException(f"Failed to confirm payment: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error confirming payment: {str(e)}")
            raise ServiceException(f"Failed to confirm payment: {str(e)}")

    @BaseService.measure_operation("stripe_capture_payment_intent")
    def capture_payment_intent(
        self, payment_intent_id: str, *, idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Capture a manual-capture PaymentIntent and return charge and transfer info.

        With transfer_data[amount] architecture:
        - amount_received: Total charge amount (what student paid)
        - transfer_amount: Amount transferred to instructor (subset of amount_received)

        Returns dict: {
            "payment_intent": pi,
            "charge_id": str|None,
            "transfer_id": str|None,
            "amount_received": int|None,
            "transfer_amount": int|None,  # The instructor payout amount
        }
        """
        import time

        try:
            # Log Stripe API call timing separately for slow query diagnosis
            api_start = time.time()
            pi = stripe.PaymentIntent.capture(payment_intent_id, idempotency_key=idempotency_key)
            api_duration_ms = (time.time() - api_start) * 1000
            self.logger.info(
                f"Stripe PaymentIntent.capture API call took {api_duration_ms:.0f}ms",
                extra={
                    "stripe_api_duration_ms": api_duration_ms,
                    "payment_intent_id": payment_intent_id,
                },
            )

            charge_id = None
            transfer_id = None
            amount_received = None
            transfer_amount = None

            try:
                if pi.get("charges") and pi["charges"]["data"]:
                    charge = pi["charges"]["data"][0]
                    charge_id = charge.get("id")
                    amount_received = charge.get("amount") or pi.get("amount_received")
                    # For destination charges, charge.transfer holds the transfer id
                    transfer_id = charge.get("transfer")

                    # Retrieve transfer to get the actual transfer amount
                    if transfer_id:
                        try:
                            transfer = StripeTransfer.retrieve(transfer_id)
                            transfer_amount = (
                                transfer.get("amount")
                                if hasattr(transfer, "get")
                                else getattr(transfer, "amount", None)
                            )
                        except Exception:
                            # Fallback: try to get from PaymentIntent metadata
                            metadata = (
                                pi.get("metadata", {})
                                if hasattr(pi, "get")
                                else getattr(pi, "metadata", {})
                            )
                            if metadata and metadata.get("target_instructor_payout_cents"):
                                try:
                                    transfer_amount = int(
                                        metadata["target_instructor_payout_cents"]
                                    )
                                except (ValueError, TypeError):
                                    pass
            except Exception:
                logger.debug("Non-fatal error ignored", exc_info=True)
            # Update stored payment status if present
            try:
                self.payment_repository.update_payment_status(payment_intent_id, pi.status)
            except Exception:
                logger.debug("Non-fatal error ignored", exc_info=True)
            if amount_received is None:
                amount_received = getattr(pi, "amount_received", None)
                if amount_received is None and hasattr(pi, "get"):
                    amount_received = pi.get("amount_received")
            if amount_received is None:
                fallback_amount = getattr(pi, "amount", None)
                if fallback_amount is None and hasattr(pi, "get"):
                    fallback_amount = pi.get("amount")
                if fallback_amount is not None:
                    try:
                        amount_received = int(fallback_amount)
                    except (TypeError, ValueError):
                        amount_received = fallback_amount

            return {
                "payment_intent": pi,
                "charge_id": charge_id,
                "transfer_id": transfer_id,
                "amount_received": amount_received,
                "transfer_amount": transfer_amount,
            }
        except stripe.StripeError as e:
            self.logger.error(f"Stripe error capturing payment intent: {str(e)}")
            raise ServiceException(f"Failed to capture payment: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error capturing payment intent: {str(e)}")
            raise ServiceException(f"Failed to capture payment: {str(e)}")

    @BaseService.measure_operation("stripe_get_payment_intent_details")
    def get_payment_intent_capture_details(self, payment_intent_id: str) -> Dict[str, Any]:
        """
        Retrieve a PaymentIntent and extract charge/transfer details without capturing.
        """
        try:
            pi = stripe.PaymentIntent.retrieve(payment_intent_id)
        except stripe.StripeError as e:
            self.logger.error(f"Stripe error retrieving payment intent: {str(e)}")
            raise ServiceException(f"Failed to retrieve payment intent: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error retrieving payment intent: {str(e)}")
            raise ServiceException(f"Failed to retrieve payment intent: {str(e)}")

        charge_id = None
        transfer_id = None
        amount_received = None
        transfer_amount = None

        try:
            if pi.get("charges") and pi["charges"]["data"]:
                charge = pi["charges"]["data"][0]
                charge_id = charge.get("id")
                amount_received = charge.get("amount") or pi.get("amount_received")
                transfer_id = charge.get("transfer")

                if transfer_id:
                    try:
                        transfer = StripeTransfer.retrieve(transfer_id)
                        transfer_amount = (
                            transfer.get("amount")
                            if hasattr(transfer, "get")
                            else getattr(transfer, "amount", None)
                        )
                    except Exception:
                        metadata = pi.get("metadata", {}) if hasattr(pi, "get") else {}
                        if metadata and metadata.get("target_instructor_payout_cents"):
                            try:
                                transfer_amount = int(metadata["target_instructor_payout_cents"])
                            except (ValueError, TypeError):
                                pass
        except Exception:
            logger.debug("Non-fatal error ignored", exc_info=True)
        if amount_received is None:
            amount_received = getattr(pi, "amount_received", None)
            if amount_received is None and hasattr(pi, "get"):
                amount_received = pi.get("amount_received")
        if amount_received is None:
            fallback_amount = getattr(pi, "amount", None)
            if fallback_amount is None and hasattr(pi, "get"):
                fallback_amount = pi.get("amount")
            if fallback_amount is not None:
                try:
                    amount_received = int(fallback_amount)
                except (TypeError, ValueError):
                    amount_received = fallback_amount

        return {
            "payment_intent": pi,
            "charge_id": charge_id,
            "transfer_id": transfer_id,
            "amount_received": amount_received,
            "transfer_amount": transfer_amount,
        }

    @BaseService.measure_operation("stripe_reverse_transfer")
    def reverse_transfer(
        self,
        *,
        transfer_id: str,
        amount_cents: Optional[int] = None,
        idempotency_key: Optional[str] = None,
        reason: str = "",
    ) -> Dict[str, Any]:
        """
        Reverse a transfer (full or partial) back to platform balance.
        """
        import time

        try:
            # stripe.Transfer.create_reversal expects transfer id as positional arg
            kwargs: Dict[str, Any] = {}
            if amount_cents is not None:
                kwargs["amount"] = amount_cents
            if reason:
                kwargs["metadata"] = {"reason": reason}

            # Log Stripe API call timing separately for slow query diagnosis
            api_start = time.time()
            reversal = stripe.Transfer.create_reversal(
                transfer_id, idempotency_key=idempotency_key, **kwargs
            )
            api_duration_ms = (time.time() - api_start) * 1000
            self.logger.info(
                f"Stripe Transfer.create_reversal API call took {api_duration_ms:.0f}ms",
                extra={"stripe_api_duration_ms": api_duration_ms, "transfer_id": transfer_id},
            )

            # Alert/metrics for insufficient funds or negative balance scenarios
            try:
                # Stripe returns balance_transaction on reversal; if missing or amount < requested, log alert
                reversed_amount = getattr(reversal, "amount_reversed", None) or getattr(
                    reversal, "amount", None
                )
                if (
                    amount_cents is not None
                    and reversed_amount is not None
                    and reversed_amount < amount_cents
                ):
                    self.logger.warning(
                        f"Partial reversal for transfer {transfer_id}: requested={amount_cents} reversed={reversed_amount}"
                    )
                # If failure_code present in reversal (rare), log as error
                failure_code = (
                    getattr(reversal, "failure_code", None) or reversal.get("failure_code")
                    if isinstance(reversal, dict)
                    else None
                )
                if failure_code:
                    self.logger.error(
                        f"Transfer reversal reported failure_code={failure_code} for transfer {transfer_id}"
                    )
            except Exception:
                # Do not fail the main flow for metrics issues
                logger.debug("Non-fatal error ignored", exc_info=True)
            return {"reversal": reversal}
        except stripe.StripeError as e:
            self.logger.error(f"Stripe error reversing transfer: {str(e)}")
            raise ServiceException(f"Failed to reverse transfer: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error reversing transfer: {str(e)}")
            raise ServiceException(f"Failed to reverse transfer: {str(e)}")

    @BaseService.measure_operation("stripe_cancel_payment_intent")
    def cancel_payment_intent(
        self, payment_intent_id: str, *, idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Cancel a PaymentIntent to release authorization.
        """
        try:
            pi = stripe.PaymentIntent.cancel(payment_intent_id, idempotency_key=idempotency_key)
            try:
                self.payment_repository.update_payment_status(payment_intent_id, pi.status)
            except Exception:
                logger.debug("Non-fatal error ignored", exc_info=True)
            return {"payment_intent": pi}
        except stripe.StripeError as e:
            self.logger.error(f"Stripe error canceling payment intent: {str(e)}")
            raise ServiceException(f"Failed to cancel payment intent: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error canceling payment intent: {str(e)}")
            raise ServiceException(f"Failed to cancel payment intent: {str(e)}")

    @BaseService.measure_operation("stripe_void_or_refund_payment")
    def _void_or_refund_payment(self, payment_intent_id: Optional[str]) -> None:
        """Void an uncaptured payment or refund a captured payment intent."""
        if not payment_intent_id:
            return

        if not payment_intent_id.startswith("pi_"):
            self.logger.info(
                "Skipping void/refund for non-Stripe payment intent %s", payment_intent_id
            )
            return

        if not self.stripe_configured:
            self.logger.info(
                "Stripe not configured; skipping void/refund for %s", payment_intent_id
            )
            return

        try:
            pi = stripe.PaymentIntent.retrieve(payment_intent_id)
            status = getattr(pi, "status", None)

            if status == "requires_capture":
                self.cancel_payment_intent(
                    payment_intent_id,
                    idempotency_key=f"void_{payment_intent_id}",
                )
                self.logger.info("Voided uncaptured payment %s", payment_intent_id)
            elif status == "succeeded":
                self.refund_payment(
                    payment_intent_id,
                    reverse_transfer=True,
                    refund_application_fee=True,
                    idempotency_key=f"refund_{payment_intent_id}",
                )
                self.logger.info("Refunded captured payment %s", payment_intent_id)
            else:
                self.logger.info(
                    "Payment %s in state %s; no refund action required",
                    payment_intent_id,
                    status,
                )
        except stripe.StripeError as e:
            self.logger.error("Failed to void/refund payment %s: %s", payment_intent_id, e)
        except Exception as e:
            self.logger.error("Failed to void/refund payment %s: %s", payment_intent_id, e)

    @BaseService.measure_operation("stripe_refund_payment")
    def refund_payment(
        self,
        payment_intent_id: str,
        *,
        amount_cents: Optional[int] = None,
        reason: str = "requested_by_customer",
        reverse_transfer: bool = True,
        refund_application_fee: bool = False,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Issue a refund for a captured PaymentIntent with automatic transfer reversal.

        With transfer_data[amount] architecture, setting reverse_transfer=True will
        automatically reverse the proportional amount from the connected account.

        Args:
            payment_intent_id: The PaymentIntent to refund
            amount_cents: Optional partial refund amount (None = full refund)
            reason: Refund reason (requested_by_customer, duplicate, fraudulent)
            reverse_transfer: Whether to reverse the instructor's transfer (default True)
            refund_application_fee: Whether to refund the application fee (default False)
            idempotency_key: Optional idempotency key

        Returns:
            Dict with refund_id, status, and amount_refunded

        Raises:
            ServiceException: If refund fails
        """
        try:
            refund_kwargs: Dict[str, Any] = {
                "payment_intent": payment_intent_id,
                "reverse_transfer": reverse_transfer,
            }

            if amount_cents is not None:
                refund_kwargs["amount"] = amount_cents

            if reason:
                # Stripe only accepts specific reason values
                valid_reasons = {"requested_by_customer", "duplicate", "fraudulent"}
                if reason in valid_reasons:
                    refund_kwargs["reason"] = reason

            if refund_application_fee:
                refund_kwargs["refund_application_fee"] = True

            if idempotency_key:
                refund_kwargs["idempotency_key"] = idempotency_key

            refund = StripeRefund.create(**refund_kwargs)

            # Update payment status
            try:
                self.payment_repository.update_payment_status(payment_intent_id, "refunded")
            except Exception:
                logger.debug("Non-fatal error ignored", exc_info=True)
            self.logger.info(
                f"Refund created for PI {payment_intent_id}: "
                f"refund_id={refund.id}, amount={refund.amount}, "
                f"reverse_transfer={reverse_transfer}"
            )

            return {
                "refund_id": refund.id,
                "status": refund.status,
                "amount_refunded": refund.amount,
                "payment_intent_id": payment_intent_id,
            }
        except stripe.StripeError as e:
            self.logger.error(f"Stripe error creating refund: {str(e)}")
            raise ServiceException(f"Failed to create refund: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error creating refund: {str(e)}")
            raise ServiceException(f"Failed to create refund: {str(e)}")

    @BaseService.measure_operation("stripe_process_booking_payment")
    def process_booking_payment(
        self,
        booking_id: str,
        payment_method_id: Optional[str] = None,
        requested_credit_cents: Optional[int] = None,
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
                        booking.payment_status = PaymentStatus.AUTHORIZED.value
                        booking.auth_attempted_at = datetime.now(timezone.utc)
                        booking.auth_failure_count = 0
                        booking.auth_last_error = None

                return {
                    "success": True,
                    "payment_intent_id": "credit_only",
                    "status": "succeeded",
                    "amount": 0,
                    "application_fee": 0,
                    "client_secret": None,
                }

            if not payment_method_id:
                raise ServiceException("Payment method required for the remaining balance")

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
                    booking.payment_intent_id = payment_record.stripe_payment_intent_id
                    booking.payment_method_id = payment_method_id

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
                            booking.payment_status = PaymentStatus.AUTHORIZED.value
                            booking.auth_attempted_at = now
                            booking.auth_failure_count = 0
                            booking.auth_last_error = None
                            booking.auth_scheduled_for = None
                        else:
                            booking.payment_status = PaymentStatus.PAYMENT_METHOD_REQUIRED.value
                            booking.auth_attempted_at = now
                            booking.auth_failure_count = (
                                int(getattr(booking, "auth_failure_count", 0) or 0) + 1
                            )
                            booking.auth_last_error = stripe_error or "authorization_failed"
                            booking.auth_scheduled_for = None
                    else:
                        booking.payment_status = PaymentStatus.SCHEDULED.value
                        booking.auth_scheduled_for = auth_scheduled_for
                        booking.auth_failure_count = 0
                        booking.auth_last_error = None

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
                    from app.tasks.payment_tasks import check_immediate_auth_timeout

                    check_immediate_auth_timeout.apply_async(args=[booking_id], countdown=30 * 60)
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
                        "client_secret": None,
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
                "client_secret": None,
            }

        except Exception as e:
            if isinstance(e, ServiceException):
                raise
            self.logger.error(f"Error processing booking payment: {str(e)}")
            raise ServiceException(f"Failed to process payment: {str(e)}")

    # ========== Payment Method Management ==========

    @BaseService.measure_operation("stripe_save_payment_method")
    def save_payment_method(
        self, user_id: str, payment_method_id: str, set_as_default: bool = False
    ) -> PaymentMethod:
        """
        Save a payment method for a user.

        Uses 3-phase pattern to avoid holding DB locks during Stripe calls:
        - Phase 1: Check existing, get customer (quick transaction)
        - Phase 2: Stripe retrieve/attach (NO transaction)
        - Phase 3: Save to database (quick transaction)

        Args:
            user_id: User's ID
            payment_method_id: Stripe payment method ID
            set_as_default: Whether to set as default payment method

        Returns:
            PaymentMethod record

        Raises:
            ServiceException: If saving fails
        """
        try:
            # ========== PHASE 1: Check existing & get customer (quick transaction) ==========
            with self.transaction():
                # Check if payment method already exists in our database
                existing = self.payment_repository.get_payment_method_by_stripe_id(
                    payment_method_id, user_id
                )
                if existing:
                    self.logger.info(
                        f"Payment method {payment_method_id} already exists for user {user_id}"
                    )
                    # If setting as default, update the existing one
                    if set_as_default:
                        self.payment_repository.set_default_payment_method(existing.id, user_id)
                    return existing

            # Ensure user has a Stripe customer (may involve Stripe call, handled separately)
            customer = self.get_or_create_customer(user_id)
            stripe_customer_id = customer.stripe_customer_id

            # ========== PHASE 2: Stripe calls (NO transaction) ==========
            try:
                stripe_pm = stripe.PaymentMethod.retrieve(payment_method_id)

                # Check if already attached to a customer
                if stripe_pm.customer:
                    if stripe_pm.customer != stripe_customer_id:
                        # Payment method is attached to a different customer
                        self.logger.error(
                            f"Payment method {payment_method_id} is attached to a different customer"
                        )
                        raise ServiceException(
                            "This payment method is already in use by another account"
                        )
                    # Already attached to this customer, just retrieve it
                    self.logger.info(
                        f"Payment method {payment_method_id} already attached to customer"
                    )
                else:
                    # Not attached, so attach it
                    stripe_pm = stripe.PaymentMethod.attach(
                        payment_method_id, customer=stripe_customer_id
                    )
                    self.logger.info(f"Attached payment method {payment_method_id} to customer")

            except stripe.error.CardError as e:
                # Handle specific card errors
                self.logger.error(f"Card error: {str(e)}")
                error_message = str(e.user_message) if hasattr(e, "user_message") else str(e)
                raise ServiceException(error_message)

            # Extract card details from Stripe response
            card = stripe_pm.card
            last4 = cast(Optional[str], getattr(card, "last4", None) if card else None)
            brand = cast(Optional[str], getattr(card, "brand", None) if card else None)

            # ========== PHASE 3: Save to database (quick transaction) ==========
            with self.transaction():
                payment_method = self.payment_repository.save_payment_method(
                    user_id=user_id,
                    stripe_payment_method_id=payment_method_id,
                    last4=last4 or "",
                    brand=brand or "",
                    is_default=set_as_default,
                )

            self.logger.info(f"Saved payment method {payment_method_id} for user {user_id}")
            return payment_method

        except ServiceException:
            # Re-raise service exceptions
            raise
        except stripe.StripeError as e:
            self.logger.error(f"Stripe error saving payment method: {str(e)}")
            # Extract user-friendly message from Stripe error
            error_message = str(e.user_message) if hasattr(e, "user_message") else str(e)
            raise ServiceException(f"Failed to save payment method: {error_message}")
        except Exception as e:
            self.logger.error(f"Error saving payment method: {str(e)}")
            raise ServiceException(f"Failed to save payment method: {str(e)}")

    @BaseService.measure_operation("stripe_get_user_payment_methods")
    def get_user_payment_methods(self, user_id: str) -> List[PaymentMethod]:
        """
        Get all payment methods for a user.

        Args:
            user_id: User's ID

        Returns:
            List of PaymentMethod records

        Raises:
            ServiceException: If retrieval fails
        """
        try:
            return list(self.payment_repository.get_payment_methods_by_user(user_id))
        except Exception as e:
            self.logger.error(f"Error getting payment methods: {str(e)}")
            raise ServiceException(f"Failed to get payment methods: {str(e)}")

    @BaseService.measure_operation("stripe_delete_payment_method")
    def delete_payment_method(self, payment_method_id: str, user_id: str) -> bool:
        """
        Delete a payment method.

        Uses 3-phase pattern to avoid holding DB locks during Stripe calls:
        - Phase 1: (none needed - no pre-read required)
        - Phase 2: Stripe detach (NO transaction)
        - Phase 3: Delete from database (quick transaction)

        Args:
            payment_method_id: Payment method ID (can be database ID or Stripe ID)
            user_id: User's ID (for ownership verification)

        Returns:
            True if deleted successfully

        Raises:
            ServiceException: If deletion fails
        """
        try:
            # ========== PHASE 2: Stripe detach (NO transaction) ==========
            # Try to detach from Stripe if it's a Stripe payment method ID
            if payment_method_id.startswith("pm_"):
                try:
                    stripe.PaymentMethod.detach(payment_method_id)
                    self.logger.info(f"Detached payment method {payment_method_id} from Stripe")
                except stripe.StripeError as e:
                    # Log but don't fail - payment method might already be detached
                    self.logger.warning(f"Could not detach payment method from Stripe: {str(e)}")

            # ========== PHASE 3: Delete from database (quick transaction) ==========
            with self.transaction():
                # Delete from database (handles both database ID and Stripe ID)
                success = self.payment_repository.delete_payment_method(payment_method_id, user_id)

            if success:
                self.logger.info(
                    f"Deleted payment method {payment_method_id} from database for user {user_id}"
                )

            return bool(success)

        except Exception as e:
            self.logger.error(f"Error deleting payment method: {str(e)}")
            raise ServiceException(f"Failed to delete payment method: {str(e)}")

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
            self.logger.error(f"Error verifying webhook signature: {str(e)}")
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
            self.logger.info(f"Processing webhook event: {event_type}")

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
                self.logger.info(f"Unhandled webhook event type: {event_type}")
                return {"success": True, "event_type": event_type, "handled": False}

        except Exception as e:
            self.logger.error(f"Error processing webhook event: {str(e)}")
            raise ServiceException(f"Failed to process webhook event: {str(e)}")

    @BaseService.measure_operation("stripe_handle_webhook_legacy")
    def handle_webhook(self, payload: str, signature: str) -> Dict[str, Any]:
        """
        Legacy webhook handler that verifies signature and processes events.

        This method is kept for backward compatibility. New code should use
        handle_webhook_event() with pre-verified events.

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
                self.logger.warning(f"Invalid webhook signature: {str(e)}")
                raise ServiceException("Invalid webhook signature")
            except Exception as e:
                self.logger.error(f"Error constructing webhook event: {str(e)}")
                raise ServiceException(f"Invalid webhook payload: {str(e)}")

            # Use the new method to process the event
            result = self.handle_webhook_event(event)
            return dict(result)

        except ServiceException:
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error handling webhook: {str(e)}")
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
                    self.logger.info(f"Updated payment {payment_intent_id} status to {new_status}")

                    # Handle successful payments
                    if new_status == "succeeded":
                        self._handle_successful_payment(payment_record)

                    return True
                else:
                    self.logger.warning(
                        f"Payment record not found for webhook event {payment_intent_id}"
                    )
                    return False

        except Exception as e:
            self.logger.error(f"Error handling payment intent webhook: {str(e)}")
            raise ServiceException(f"Failed to handle payment webhook: {str(e)}")

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
                self.logger.warning(f"Failed to invalidate booking caches: {str(cache_err)}")

            self.logger.info(
                f"Processed successful payment for booking {payment_record.booking_id}"
            )

        except Exception as e:
            self.logger.error(f"Error handling successful payment: {str(e)}")
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
                    self.logger.info(f"Account {account_id} onboarding completed")

                return True

            elif event_type == "account.application.deauthorized":
                self.logger.warning(f"Account {account_id} was deauthorized")
                # Could implement logic to notify instructor or disable their services
                return True

            return False

        except Exception as e:
            self.logger.error(f"Error handling account webhook: {str(e)}")
            return False

    def _handle_transfer_webhook(self, event: Dict[str, Any]) -> bool:
        """Handle Stripe transfer events."""
        try:
            event_type = event.get("type", "")
            transfer_data = event.get("data", {}).get("object", {})
            transfer_id = transfer_data.get("id")

            if event_type == "transfer.created":
                self.logger.info(f"Transfer {transfer_id} created")
                return True

            elif event_type == "transfer.paid":
                self.logger.info(f"Transfer {transfer_id} paid successfully")
                return True

            elif event_type == "transfer.failed":
                self.logger.error(f"Transfer {transfer_id} failed")
                # Could implement logic to notify instructor or retry
                return True

            elif event_type == "transfer.reversed":
                # Funds moved back to platform balance; record event for the related booking if possible
                try:
                    amount = transfer_data.get("amount")
                    # If we had stored mapping transfer->booking, we would look it up. Fallback: log only.
                    self.logger.info(f"Transfer {transfer_id} reversed (amount={amount})")
                except Exception:
                    logger.debug("Non-fatal error ignored", exc_info=True)
                return True

            return False

        except Exception as e:
            self.logger.error(f"Error handling transfer webhook: {str(e)}")
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
                self.logger.info(f"Charge {charge_id} succeeded")
                return True

            elif event_type == "charge.failed":
                self.logger.error(f"Charge {charge_id} failed")
                # Could implement logic to notify student
                return True

            elif event_type == "charge.refunded":
                self.logger.info(f"Charge {charge_id} refunded")
                try:
                    # Update payment record if possible
                    payment_intent_id = charge_data.get("payment_intent")
                    if payment_intent_id:
                        self.payment_repository.update_payment_status(payment_intent_id, "refunded")
                        booking_payment = self.payment_repository.get_payment_by_intent_id(
                            payment_intent_id
                        )
                        if booking_payment:
                            booking = self.booking_repository.get_by_id(booking_payment.booking_id)
                            if booking:
                                # Emit a domain-level log; event stream is handled by tasks/routes
                                self.logger.info(
                                    f"Marked booking {booking.id} payment as refunded for PI {payment_intent_id}"
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
                    self.logger.error(f"Failed to process charge.refunded: {e}")
                return True

            return False
        except Exception as e:
            self.logger.error(f"Error handling charge webhook: {str(e)}")
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

            transfer_id = booking.stripe_transfer_id
            reversal_id: Optional[str] = None
            reversal_error: Optional[str] = None

            if transfer_id and not booking.transfer_reversed:
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

                booking.payment_status = PaymentStatus.MANUAL_REVIEW.value
                booking.dispute_id = dispute_id
                booking.dispute_status = dispute.get("status")
                booking.dispute_amount = dispute.get("amount")
                booking.dispute_created_at = datetime.now(timezone.utc)

                if reversal_id:
                    booking.transfer_reversed = True
                    booking.transfer_reversal_id = reversal_id
                elif reversal_error:
                    booking.transfer_reversal_failed = True
                    booking.transfer_reversal_error = reversal_error
                    booking.transfer_reversal_failed_at = datetime.now(timezone.utc)
                    booking.transfer_reversal_retry_count = (
                        int(getattr(booking, "transfer_reversal_retry_count", 0) or 0) + 1
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

                booking.dispute_status = status
                booking.dispute_resolved_at = datetime.now(timezone.utc)

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
                    booking.payment_status = PaymentStatus.SETTLED.value
                    booking.settlement_outcome = "dispute_won"
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
                    booking.payment_status = PaymentStatus.SETTLED.value
                    booking.settlement_outcome = "student_wins_dispute_full_refund"

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
                    f"Payout created: {payout_id} amount={amount} status={status} arrival={arrival_date}"
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
                    self.logger.warning(f"Failed to persist payout.created analytics: {e}")
                return True

            if event_type == "payout.paid":
                self.logger.info(
                    f"Payout paid: {payout_id} amount={amount} status={status} arrival={arrival_date}"
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
                    self.logger.warning(f"Failed to persist payout.paid analytics: {e}")
                return True

            if event_type == "payout.failed":
                failure_code = payout.get("failure_code")
                failure_message = payout.get("failure_message")
                self.logger.error(
                    f"Payout failed: {payout_id} amount={amount} code={failure_code} message={failure_message}"
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
                    self.logger.warning(f"Failed to persist payout.failed analytics: {e}")
                return True

            # Unhandled payout event
            return False
        except Exception as e:
            self.logger.error(f"Error handling payout webhook: {str(e)}")
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
                    from datetime import datetime, timezone as _tz

                    self.instructor_repository.update(
                        profile.id,
                        identity_verified_at=datetime.now(_tz.utc),
                        identity_verification_session_id=obj.get("id"),
                    )
                except Exception as e:
                    self.logger.error(
                        f"Failed updating identity verification on profile {profile.id}: {e}"
                    )
                    return False
                return True

            # For other terminal statuses, we can store the session id for audit
            if verification_status in {"requires_input", "canceled", "processing"}:
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
            self.logger.error(f"Error handling identity webhook: {str(e)}")
            return False

    # ========== Analytics and Reporting ==========

    @BaseService.measure_operation("stripe_get_platform_revenue_stats")
    def get_platform_revenue_stats(
        self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get platform revenue statistics.

        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Dictionary with revenue statistics
        """
        try:
            return dict(self.payment_repository.get_platform_revenue_stats(start_date, end_date))
        except Exception as e:
            self.logger.error(f"Error getting platform revenue stats: {str(e)}")
            raise ServiceException(f"Failed to get revenue stats: {str(e)}")

    @BaseService.measure_operation("stripe_get_instructor_earnings")
    def get_instructor_earnings(
        self,
        instructor_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Get instructor earnings statistics.

        Args:
            instructor_id: Instructor user ID
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Dictionary with earnings statistics
        """
        try:
            return dict(
                self.payment_repository.get_instructor_earnings(instructor_id, start_date, end_date)
            )
        except Exception as e:
            self.logger.error(f"Error getting instructor earnings: {str(e)}")
            raise ServiceException(f"Failed to get instructor earnings: {str(e)}")

    @staticmethod
    def _top_up_from_pi_metadata(pi: Any) -> Optional[int]:
        """Compute top-up from PaymentIntent metadata when available.

        If PI metadata contains: base_price_cents, platform_fee_cents, student_fee_cents,
        applied_credit_cents, compute deterministic top-up using the creation-time values:

            A = int(pi.amount)
            B = int(meta["base_price_cents"])
            f = int(meta["platform_fee_cents"])
            s = int(meta["student_fee_cents"])
            C = int(meta["applied_credit_cents"])
            P = B - f
            top_up = max(0, P - A)

        Return top_up; return None if any value is missing/non-int.
        """

        metadata = getattr(pi, "metadata", None)
        if not metadata and hasattr(pi, "get"):
            metadata = pi.get("metadata")
        if not metadata:
            return None

        try:
            base_price_cents = int(str(metadata["base_price_cents"]))
            platform_fee_cents = int(str(metadata["platform_fee_cents"]))
            # student_fee_cents currently unused but validated for completeness
            _ = int(str(metadata["student_fee_cents"]))
            applied_credit_cents = int(str(metadata["applied_credit_cents"]))
        except (KeyError, TypeError, ValueError):
            return None

        if applied_credit_cents < 0:
            return None

        amount_value: Optional[Any] = getattr(pi, "amount", None)
        if amount_value is None and hasattr(pi, "get"):
            amount_value = pi.get("amount")
        if amount_value is None:
            return None

        try:
            student_pay_cents = int(str(amount_value))
        except (TypeError, ValueError):
            return None

        target_instructor_payout = base_price_cents - platform_fee_cents
        top_up = target_instructor_payout - student_pay_cents
        if top_up <= 0:
            return 0
        return top_up
