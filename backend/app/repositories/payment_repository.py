"""Payment repository facade backed by focused internal mixins."""

import logging

from sqlalchemy.orm import Session

from ..models.payment import PaymentIntent
from .base_repository import BaseRepository
from .payment.analytics_mixin import PaymentAnalyticsMixin
from .payment.connected_account_mixin import PaymentConnectedAccountMixin
from .payment.customer_mixin import PaymentCustomerMixin
from .payment.payment_event_mixin import PaymentPaymentEventMixin
from .payment.payment_intent_mixin import PaymentPaymentIntentMixin
from .payment.payment_method_mixin import PaymentPaymentMethodMixin
from .payment.payout_event_mixin import PaymentPayoutEventMixin
from .payment.platform_credit_mixin import PaymentPlatformCreditMixin

logger = logging.getLogger(__name__)


class PaymentRepository(
    PaymentCustomerMixin,
    PaymentConnectedAccountMixin,
    PaymentPaymentIntentMixin,
    PaymentPayoutEventMixin,
    PaymentPaymentMethodMixin,
    PaymentAnalyticsMixin,
    PaymentPaymentEventMixin,
    PaymentPlatformCreditMixin,
    BaseRepository[PaymentIntent],
):
    """Repository facade for payment data access."""

    def __init__(self, db: Session):
        """Initialize with database session."""
        super().__init__(db, PaymentIntent)
        self.logger = logging.getLogger(__name__)
