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

from __future__ import annotations

from datetime import timedelta
import logging
import time as _time
from typing import TYPE_CHECKING, Any, Callable, ClassVar, Optional, Protocol
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
from ..repositories.factory import RepositoryFactory
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

STRIPE_API_VERSION = "2026-03-25.dahlia"

if TYPE_CHECKING:  # pragma: no cover
    from contextlib import AbstractContextManager

    from ..core.config import Settings
    from ..schemas.payment_schemas import CheckoutResponse

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
        set_instructor_payout_schedule: Callable[..., Any]
        get_instructor_dashboard_link: Callable[..., Any]
        request_instructor_instant_payout: Callable[..., Any]
        set_payout_schedule_for_account: Callable[..., dict[str, Any]]
        _top_up_from_pi_metadata: Callable[[Any], int]

    class StripeIdentityMixin(BaseService):
        create_identity_verification_session: Callable[..., Any]
        refresh_instructor_identity: Callable[..., Any]
        _persist_verified_identity: Callable[..., None]

    class StripeOnboardingMixin(BaseService):
        start_instructor_onboarding: Callable[..., Any]
        get_instructor_onboarding_status: Callable[..., Any]
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

    class StripePaymentIntentsMixin(BaseService):
        create_payment_intent: Callable[..., Any]
        create_and_confirm_manual_authorization: Callable[..., Any]
        confirm_payment_intent: Callable[..., Any]

    class StripePaymentFlowMixin(BaseService):
        build_charge_context: Callable[..., ChargeContext]
        create_or_retry_booking_payment_intent: Callable[..., Any]
        capture_booking_payment_intent: Callable[..., Any]

    class StripePaymentMixin(BaseService):
        create_booking_checkout: Callable[..., CheckoutResponse]
        process_booking_payment: Callable[..., Any]

    class StripeWebhookDisputesMixin(BaseService):
        _handle_charge_webhook: Callable[..., bool]
        _resolve_payment_intent_id_from_charge: Callable[..., Optional[str]]
        _handle_dispute_created: Callable[..., bool]
        _handle_dispute_closed: Callable[..., bool]

    class StripeWebhookPayoutsMixin(BaseService):
        _handle_payout_webhook: Callable[..., bool]

    class StripeWebhookRouterMixin(BaseService):
        verify_webhook_signature: Callable[..., bool]
        handle_webhook_event: Callable[..., dict[str, Any]]
        handle_payment_intent_webhook: Callable[..., bool]
        _advance_booking_on_capture: Callable[..., None]
        _handle_successful_payment: Callable[..., None]
        _handle_account_webhook: Callable[..., bool]
        _handle_transfer_webhook: Callable[..., bool]
        _handle_identity_webhook: Callable[..., bool]

else:
    from .stripe.capture_refund import StripeCaptureRefundMixin
    from .stripe.customer import StripeCustomerMixin
    from .stripe.earnings import StripeEarningsMixin
    from .stripe.earnings_export import StripeEarningsExportMixin
    from .stripe.helpers import StripeHelpersMixin
    from .stripe.identity import StripeIdentityMixin
    from .stripe.onboarding import StripeOnboardingMixin
    from .stripe.payment import StripePaymentMixin
    from .stripe.payment_flow import StripePaymentFlowMixin
    from .stripe.payment_intents import StripePaymentIntentsMixin
    from .stripe.transfer import StripeTransferMixin
    from .stripe.webhook_disputes import StripeWebhookDisputesMixin
    from .stripe.webhook_payouts import StripeWebhookPayoutsMixin
    from .stripe.webhook_router import StripeWebhookRouterMixin

logger: logging.Logger = logging.getLogger(__name__)

# Sentinel for absent secret values in payment responses (avoids B105 false positive)
_ABSENT: None = None


class StripeBookingLockSyncProtocol(Protocol):
    """Typed view of the sync booking lock helper re-exported by the facade."""

    def __call__(self, booking_id: str, ttl_s: int = 90) -> "AbstractContextManager[bool]":
        ...


class StripeServiceModuleProtocol(Protocol):
    """Typed surface exposed through lazy stripe facade imports."""

    StripeService: ClassVar[type[StripeService]]
    stripe: ClassVar[Any]
    settings: ClassVar["Settings"]
    StripeBalance: ClassVar[type[StripeBalance]]
    StripeTransfer: ClassVar[type[StripeTransfer]]
    StripeRefund: ClassVar[type[StripeRefund]]
    _ABSENT: ClassVar[None]
    enqueue_task: ClassVar[Callable[..., Any]]
    booking_lock_sync: ClassVar[StripeBookingLockSyncProtocol]
    RepositoryFactory: ClassVar[type[RepositoryFactory]]
    StudentCreditService: ClassVar[type[StudentCreditService]]
    logger: ClassVar[logging.Logger]
    uuid: ClassVar[Any]


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

_FACADE_TEST_PATCH_TARGETS = (
    StripeBalance,
    uuid,
    timedelta,
    origin_from_header,
    is_allowed_origin,
    booking_lock_sync,
    enqueue_task,
    RepositoryFactory,
    StudentCreditService,
)


class StripeService(
    StripeHelpersMixin,
    StripeEarningsMixin,
    StripeEarningsExportMixin,
    StripeCaptureRefundMixin,
    StripeTransferMixin,
    StripeIdentityMixin,
    StripeOnboardingMixin,
    StripeCustomerMixin,
    StripePaymentIntentsMixin,
    StripePaymentFlowMixin,
    StripePaymentMixin,
    StripeWebhookDisputesMixin,
    StripeWebhookPayoutsMixin,
    StripeWebhookRouterMixin,
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

        self.stripe_configured = False
        self._last_client_secret: Optional[str] = None
        try:
            if settings.stripe_secret_key:
                stripe.api_key = settings.stripe_secret_key.get_secret_value()
                # Stripe's type stubs declare api_version as read-only even though
                # it's writable at runtime. setattr() avoids a suppression while
                # still matching the runtime behavior.
                setattr(stripe, "api_version", STRIPE_API_VERSION)
                self.logger.info(
                    "Stripe SDK %s, API version %s",
                    getattr(stripe, "VERSION", "unknown"),
                    getattr(stripe, "api_version", "unknown"),
                )
                try:
                    http_client_module = getattr(stripe, "_http_client", None) or getattr(
                        stripe, "http_client", None
                    )
                    if http_client_module:
                        stripe.default_http_client = http_client_module.RequestsClient(timeout=30)
                    stripe.max_network_retries = 1
                    stripe.verify_ssl_certs = True
                except Exception:
                    logger.debug("Non-fatal error ignored", exc_info=True)
                self.stripe_configured = True
                self.logger.info("Stripe service configured successfully")
            else:
                self.logger.warning(
                    "Stripe secret key not configured - service will operate in mock mode"
                )
        except Exception as exc:
            self.logger.error(
                "Failed to configure Stripe service: %s - service will operate in mock mode",
                exc,
            )

        self.platform_fee_percentage = (
            getattr(settings, "stripe_platform_fee_percentage", 15) / 100.0
        )
        self.logger = logging.getLogger(__name__)
